"""Compare optimisation algorithms on the *same* objective and eval budget.

Every algorithm minimises total vehicle delay over the same integer genome
(green-phase durations) and is given the *same number of SUMO evaluations*, so
the comparison is fair. Evaluations go through the same ``map_fn`` as the GA, so
the whole study runs in parallel on Cyfronet Ares.

Algorithms:
  * baseline     -- fixed-time plan (reference, 1 evaluation)
  * random       -- random search (sample genomes, keep the best)
  * hillclimb    -- parallel random-restart hill climbing
  * anneal       -- parallel simulated annealing
  * ga           -- our genetic algorithm (the production optimiser)

Launch on the cluster (workers = N-1, rank 0 is the master)::

    srun python -m mpi4py.futures -m src.compare.benchmark_algorithms \
        --parallel --config config/scenario_large.yaml \
        --csv results/algorithms.csv --summary results/algorithms_summary.csv

Writes two CSVs: a long-form convergence trace (algorithm, evals, best) and a
one-row-per-algorithm summary. Plot locally with analysis/plot_algorithms.py.
"""
from __future__ import annotations

import argparse
import csv
import math
import random
import time
from functools import partial
from pathlib import Path

import yaml

from src.ga.optimizer import _eval_individual, optimize
from src.network.build_network import build_network
from src.sim.encoding import clamp, read_tls_spec


# --------------------------------------------------------------------------- #
# Evaluation plumbing (shared by every algorithm)
# --------------------------------------------------------------------------- #
class Evaluator:
    """Counts SUMO evaluations and dispatches them through ``map_fn``."""

    def __init__(self, eval_one, map_fn):
        self.eval_one = eval_one
        self.map_fn = map_fn
        self.count = 0

    def batch(self, genomes: list[list[int]]) -> list[float]:
        genomes = list(genomes)
        fits = [r[0] for r in self.map_fn(self.eval_one, genomes)]
        self.count += len(genomes)
        return fits


def _random_genome(rng, length, lo, hi):
    return [rng.randint(lo, hi) for _ in range(length)]


def _neighbor(rng, genome, lo, hi):
    """One-gene uniform-reset neighbour (same move scale as GA mutation)."""
    n = list(genome)
    n[rng.randrange(len(n))] = rng.randint(lo, hi)
    return n


# --------------------------------------------------------------------------- #
# Algorithms -- each returns (best_genome, best_fit, trace[(evals, best)])
# --------------------------------------------------------------------------- #
def random_search(ev, rng, budget, batch, length, lo, hi, base_g, base_f):
    best_f, best_g, trace = base_f, base_g, []   # never worse than baseline
    while ev.count < budget:
        k = min(batch, budget - ev.count)
        genomes = [_random_genome(rng, length, lo, hi) for _ in range(k)]
        for g, f in zip(genomes, ev.batch(genomes)):
            if f < best_f:
                best_f, best_g = f, g
        trace.append((ev.count, best_f))
    return best_g, best_f, trace


def hill_climbing(ev, rng, budget, n_chains, length, lo, hi, base_g, base_f):
    # Seed one chain from the baseline plan, the rest random (random restarts).
    chains = [list(base_g)] + [_random_genome(rng, length, lo, hi)
                               for _ in range(n_chains - 1)]
    cur = ev.batch(chains)
    best_f, best_g = base_f, base_g
    if min(cur) < best_f:
        best_f, best_g = min(cur), chains[cur.index(min(cur))]
    trace = [(ev.count, best_f)]
    while ev.count + n_chains <= budget:
        props = [_neighbor(rng, c, lo, hi) for c in chains]
        pf = ev.batch(props)
        for i, f in enumerate(pf):
            if f < cur[i]:                       # greedy accept
                chains[i], cur[i] = props[i], f
                if f < best_f:
                    best_f, best_g = f, props[i]
        trace.append((ev.count, best_f))
    return best_g, best_f, trace


def simulated_annealing(ev, rng, budget, n_chains, length, lo, hi, base_g, base_f):
    chains = [list(base_g)] + [_random_genome(rng, length, lo, hi)
                               for _ in range(n_chains - 1)]
    cur = ev.batch(chains)
    best_f, best_g = base_f, base_g
    if min(cur) < best_f:
        best_f, best_g = min(cur), chains[cur.index(min(cur))]
    trace = [(ev.count, best_f)]

    spread = (max(cur) - min(cur)) or 1.0       # set the temperature scale
    t0, t_end = spread, spread * 0.01
    rounds = max(1, (budget - ev.count) // n_chains)
    alpha = (t_end / t0) ** (1.0 / rounds)

    temp = t0
    while ev.count + n_chains <= budget:
        props = [_neighbor(rng, c, lo, hi) for c in chains]
        pf = ev.batch(props)
        for i, f in enumerate(pf):
            delta = f - cur[i]
            if delta < 0 or rng.random() < math.exp(-delta / max(temp, 1e-9)):
                chains[i], cur[i] = props[i], f
                if f < best_f:
                    best_f, best_g = f, props[i]
        trace.append((ev.count, best_f))
        temp *= alpha
    return best_g, best_f, trace


class _GATracer:
    """Wraps a map_fn so the GA reports a (evals, best-so-far) convergence trace."""

    def __init__(self, map_fn):
        self.map_fn = map_fn
        self.count = 0
        self.best = math.inf
        self.trace = []

    def __call__(self, fn, iterable):
        items = list(iterable)
        results = list(self.map_fn(fn, items))
        self.count += len(results)
        for r in results:
            f = r[0] if isinstance(r, (tuple, list)) else r
            if f < self.best:
                self.best = f
        self.trace.append((self.count, self.best))
        return results


# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description="Compare optimisation algorithms")
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", default="runs/compare")
    ap.add_argument("--csv", default="results/algorithms.csv")
    ap.add_argument("--summary", default="results/algorithms_summary.csv")
    ap.add_argument("--budget", type=int, default=None,
                    help="evaluations per algorithm (default: match the GA)")
    ap.add_argument("--parallel", action="store_true",
                    help="evaluate via MPIPoolExecutor (cluster); else serial")
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()

    with open(args.config) as fh:
        cfg = yaml.safe_load(fh)

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
    sim_cfg = cfg.get("simulation", {})
    lo, hi, length = spec.min_green, spec.max_green, spec.length

    eval_one = partial(_eval_individual, spec=spec, net=net, routes=routes,
                       sim_cfg=sim_cfg)

    # Set up the parallel map (same machinery the GA scaling study uses).
    if args.parallel:
        from mpi4py import MPI
        from mpi4py.futures import MPIPoolExecutor
        executor = MPIPoolExecutor()
        map_fn = executor.map
        workers = max(1, MPI.COMM_WORLD.Get_size() - 1)
    else:
        executor = None
        map_fn = map
        workers = 1
    batch = max(2, workers)

    results = {}      # name -> (best_fit, trace, wall_s)
    baseline_fit = None

    # ----- GA first: it also fixes the shared evaluation budget ----------- #
    print("[ga] running ...", flush=True)
    tracer = _GATracer(map_fn)
    t0 = time.perf_counter()
    ga_res = optimize(spec, net, routes, sim_cfg, cfg.get("ga", {}), map_fn=tracer)
    results["ga"] = (ga_res.best_fitness, tracer.trace, time.perf_counter() - t0)
    baseline_fit = ga_res.baseline_fitness
    budget = args.budget or tracer.count
    print(f"[ga] best={ga_res.best_fitness:.0f} evals={tracer.count} "
          f"budget={budget}", flush=True)

    # ----- the metaheuristics, all on the same budget --------------------- #
    base_g = spec.baseline_genome()
    base_f = baseline_fit
    algos = {
        "random": lambda ev, rng: random_search(ev, rng, budget, batch, length, lo, hi, base_g, base_f),
        "hillclimb": lambda ev, rng: hill_climbing(ev, rng, budget, batch, length, lo, hi, base_g, base_f),
        "anneal": lambda ev, rng: simulated_annealing(ev, rng, budget, batch, length, lo, hi, base_g, base_f),
    }
    for i, (name, run) in enumerate(algos.items(), start=1):
        print(f"[{name}] running ...", flush=True)
        ev = Evaluator(eval_one, map_fn)
        rng = random.Random(args.seed + i)
        t0 = time.perf_counter()
        _, best_f, trace = run(ev, rng)
        results[name] = (best_f, trace, time.perf_counter() - t0)
        print(f"[{name}] best={best_f:.0f} evals={ev.count}", flush=True)

    if executor is not None:
        executor.shutdown()

    # ----- write convergence + summary CSVs ------------------------------- #
    csv_path, sum_path = Path(args.csv), Path(args.summary)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["algorithm", "evals", "best"])
        for name, (_, trace, _) in results.items():
            for evals, best in trace:
                w.writerow([name, evals, f"{best:.1f}"])

    with open(sum_path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["algorithm", "best", "baseline", "improvement_pct",
                    "evals", "wall_s"])
        w.writerow(["baseline", f"{baseline_fit:.0f}", f"{baseline_fit:.0f}",
                    "0.0", 1, "0.00"])
        for name, (best, trace, wall) in results.items():
            imp = 100.0 * (baseline_fit - best) / baseline_fit if baseline_fit else 0.0
            w.writerow([name, f"{best:.0f}", f"{baseline_fit:.0f}",
                        f"{imp:.1f}", trace[-1][0], f"{wall:.2f}"])

    print(f"\nbaseline={baseline_fit:.0f}")
    for name, (best, _, wall) in results.items():
        imp = 100.0 * (baseline_fit - best) / baseline_fit
        print(f"  {name:10s} best={best:8.0f}  (-{imp:4.1f}%)  {wall:6.1f}s")
    print(f"Saved {csv_path} and {sum_path}")


if __name__ == "__main__":
    main()
