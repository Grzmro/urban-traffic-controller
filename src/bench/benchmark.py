"""Compute-performance benchmark for the traffic-light evaluations.

This measures the *cost of the simulation work itself* — how long one SUMO
evaluation takes and how many run per second — which is the basis of the Cyfronet
studies:

  * **B4 throughput**   — evaluations/second vs. number of MPI workers
                          (run in parallel on the cluster with several `srun -n K`).
  * **B5 problem size** — cost per evaluation vs. city size (sweep `--grids`).
  * **B6 backend**      — the `backend` column is `traci` locally and `libsumo` on
                          the cluster; comparing two runs quantifies the speedup.

It runs **serially by default** (no MPI needed — works on a laptop) and **in
parallel** with `--parallel` (MPIPoolExecutor) on the cluster. A fixed, known
number of independent evaluations is timed, so throughput is exact (unlike timing
the GA, whose evaluation count depends on chance).

Local (meaningful numbers without a cluster):
    python -m src.bench.benchmark --grids 3,5,8 --evals 20

Cluster, throughput vs cores (one row appended per run):
    srun -n 16 python -m mpi4py.futures -m src.bench.benchmark \
        --parallel --grids 8 --evals 480 --csv results/throughput.csv
"""
from __future__ import annotations

import argparse
import csv
import random
import time
from functools import partial
from pathlib import Path

import yaml

from src.ga.optimizer import _eval_individual
from src.network.build_network import build_network
from src.sim.encoding import read_tls_spec
from src.sim.sumo import HAVE_LIBSUMO


def _random_genomes(spec, n, seed=0):
    rng = random.Random(seed)
    return [[rng.randint(spec.min_green, spec.max_green) for _ in range(spec.length)]
            for _ in range(n)]


def benchmark_grid(cfg: dict, grid_number: int, out_dir, n_evals: int,
                   map_fn=map, workers: int = 1) -> dict:
    """Build a grid of the given size and time `n_evals` independent evaluations."""
    cfg = {**cfg, "network": {**cfg.get("network", {}), "grid_number": grid_number}}
    paths = build_network(cfg, out_dir)
    sig = cfg.get("signals", {})
    spec = read_tls_spec(paths["net"], paths["routes"],
                         min_green=sig.get("min_green", 5),
                         max_green=sig.get("max_green", 60))
    sim_cfg = cfg.get("simulation", {})
    evaluate_one = partial(_eval_individual, spec=spec, net=paths["net"],
                           routes=paths["routes"], sim_cfg=sim_cfg)

    genomes = _random_genomes(spec, n_evals)
    # One warm-up evaluation so process/JIT/SUMO startup isn't charged to the timing.
    list(map(evaluate_one, genomes[:1]))

    t0 = time.perf_counter()
    list(map_fn(evaluate_one, genomes))
    wall = time.perf_counter() - t0

    return {
        "workers": workers,
        "grid_number": grid_number,
        "intersections": len(spec.programs),
        "genome_len": spec.length,
        "evals": n_evals,
        "wall_s": round(wall, 3),
        "evals_per_s": round(n_evals / wall, 3),
        "ms_per_eval": round(1000 * wall / n_evals, 1),
        "backend": "libsumo" if HAVE_LIBSUMO else "traci",
    }


def _append_rows(csv_path: str, rows: list[dict]) -> None:
    path = Path(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with open(path, "a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        if new:
            w.writeheader()
        w.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description="Simulation throughput / problem-size benchmark")
    ap.add_argument("--config", default="config/scenario_small.yaml")
    ap.add_argument("--grids", default="3,5,8", help="comma-separated grid sizes (NxN)")
    ap.add_argument("--evals", type=int, default=20, help="evaluations per grid size")
    ap.add_argument("--parallel", action="store_true",
                    help="distribute evaluations with MPIPoolExecutor (cluster)")
    ap.add_argument("--out", default="runs/bench")
    ap.add_argument("--csv", default="results/benchmark.csv")
    args = ap.parse_args()

    with open(args.config) as fh:
        cfg = yaml.safe_load(fh)
    grids = [int(x) for x in args.grids.split(",") if x.strip()]

    if args.parallel:
        from mpi4py import MPI
        from mpi4py.futures import MPIPoolExecutor
        workers = max(MPI.COMM_WORLD.Get_size() - 1, 1)
        executor = MPIPoolExecutor()
        map_fn = executor.map
    else:
        workers, executor, map_fn = 1, None, map

    try:
        rows = []
        for g in grids:
            row = benchmark_grid(cfg, g, Path(args.out) / f"grid{g}",
                                 args.evals, map_fn=map_fn, workers=workers)
            print(f"grid {g:>2} ({row['intersections']:>3} TLS): "
                  f"{row['evals_per_s']:.2f} evals/s, {row['ms_per_eval']:.0f} ms/eval "
                  f"[{row['backend']}, {workers} worker(s)]")
            rows.append(row)
    finally:
        if executor is not None:
            executor.shutdown()

    _append_rows(args.csv, rows)
    print(f"Saved {args.csv}")


if __name__ == "__main__":
    main()
