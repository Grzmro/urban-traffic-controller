"""HPC section: evaluate the GA population in parallel with mpi4py.

The *only* change from the serial optimizer is the ``map_fn``: we hand the GA an
``MPIPoolExecutor.map`` so every individual in a generation is simulated on a
different MPI worker. This is what we scale on Cyfronet Ares.

Launch (workers = N-1, rank 0 is the master)::

    mpiexec -n 8 python -m mpi4py.futures -m src.ga.parallel \
        --config config/scenario_large.yaml --out runs/hpc --csv results/scaling.csv

The wall-clock time and result are appended to a CSV for the scaling plots.
"""
from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path

import yaml
from mpi4py import MPI
from mpi4py.futures import MPIPoolExecutor

from src.ga.optimizer import optimize
from src.network.build_network import build_network
from src.sim.encoding import read_tls_spec


def main() -> None:
    ap = argparse.ArgumentParser(description="Parallel GA (MPI) for scaling study")
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", default="runs/hpc")
    ap.add_argument("--csv", default="results/scaling.csv")
    ap.add_argument("--result", default=None,
                    help="write the trained signal plan (best genome + metrics) as JSON")
    ap.add_argument("--max-workers", type=int, default=None)
    ap.add_argument("--population", type=int, default=None,
                    help="override GA population (used for weak scaling)")
    args = ap.parse_args()

    with open(args.config) as fh:
        cfg = yaml.safe_load(fh)
    if args.population:
        cfg.setdefault("ga", {})["population"] = args.population

    out = Path(args.out)
    net, routes = out / "net.net.xml", out / "routes.rou.xml"
    if not net.exists() or not routes.exists():
        paths = build_network(cfg, out)
        net, routes = paths["net"], paths["routes"]
    else:
        net, routes = str(net), str(routes)

    sig = cfg.get("signals", {})
    spec = read_tls_spec(net, routes, min_green=sig.get("min_green", 5),
                         max_green=sig.get("max_green", 60))

    # Workers available to the pool = total ranks - 1 (master).
    workers = args.max_workers or (MPI.COMM_WORLD.Get_size() - 1) or 1

    t0 = time.perf_counter()
    with MPIPoolExecutor(max_workers=args.max_workers) as executor:
        res = optimize(spec, net, routes, cfg.get("simulation", {}),
                       cfg.get("ga", {}), map_fn=executor.map)
    elapsed = time.perf_counter() - t0

    print(f"workers={workers} elapsed={elapsed:.1f}s "
          f"baseline={res.baseline_fitness:.0f} best={res.best_fitness:.0f} "
          f"improvement={res.improvement_pct:.1f}%")

    csv_path = Path(args.csv)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    new = not csv_path.exists()
    with open(csv_path, "a", newline="") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["workers", "elapsed_s", "baseline", "best",
                        "improvement_pct", "population", "generations"])
        ga = cfg.get("ga", {})
        w.writerow([workers, f"{elapsed:.2f}", f"{res.baseline_fitness:.0f}",
                    f"{res.best_fitness:.0f}", f"{res.improvement_pct:.1f}",
                    ga.get("population"), ga.get("generations")])

    # The trained signal plan — this is what gets imported back into the dashboard.
    if args.result:
        import json
        result_path = Path(args.result)
        result_path.parent.mkdir(parents=True, exist_ok=True)
        with open(result_path, "w") as fh:
            json.dump({
                "scenario": cfg.get("name", "scenario"),
                "best_genome": res.best_genome,
                "best_fitness": res.best_fitness,
                "baseline_fitness": res.baseline_fitness,
                "improvement_pct": res.improvement_pct,
                "convergence": res.convergence,
                "workers": workers,
                "elapsed_s": elapsed,
                "intersections": len(spec.programs),
                "green_phases": spec.length,
            }, fh, indent=2)
        print(f"Saved trained plan -> {result_path}")


if __name__ == "__main__":
    main()
