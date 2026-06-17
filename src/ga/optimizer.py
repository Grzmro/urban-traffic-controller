"""Genetic-algorithm optimization of traffic-light timings (DEAP).

The GA searches green-phase durations to minimize total vehicle delay, evaluating
each candidate with a headless SUMO run (:mod:`src.sim.evaluate`).

Evaluation is dispatched through a ``map_fn`` argument. Locally this is the
built-in ``map`` (serial); the HPC section swaps in an MPI pool executor's
``map`` to evaluate the population in parallel (see :mod:`src.ga.parallel`).
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from deap import base, creator, tools

from src.sim.encoding import TLSSpec, read_tls_spec
from src.sim.evaluate import evaluate

# DEAP requires creating the fitness/individual types once per process.
if not hasattr(creator, "FitnessMin"):
    creator.create("FitnessMin", base.Fitness, weights=(-1.0,))
if not hasattr(creator, "Individual"):
    creator.create("Individual", list, fitness=creator.FitnessMin)


def _eval_individual(genome, spec: TLSSpec, net: str, routes: str,
                     sim_cfg: dict):
    """Module-level so it is picklable for MPI workers."""
    res = evaluate(spec, list(genome), net, routes,
                   end=sim_cfg.get("end", 600.0),
                   step_length=sim_cfg.get("step_length", 1.0),
                   seed=sim_cfg.get("seed", 42))
    return (res.fitness,)


@dataclass
class OptResult:
    best_genome: list[int]
    best_fitness: float
    baseline_fitness: float
    convergence: list[float] = field(default_factory=list)  # best fitness per generation

    @property
    def improvement_pct(self) -> float:
        if not self.baseline_fitness:
            return 0.0
        return 100.0 * (self.baseline_fitness - self.best_fitness) / self.baseline_fitness


def optimize(spec: TLSSpec, net: str, routes: str, sim_cfg: dict, ga_cfg: dict,
             map_fn=map, progress_cb=None) -> "OptResult":
    """Run the GA and return the best plan plus the convergence trace.

    ``map_fn`` controls how the population is evaluated (serial or parallel).
    ``progress_cb(gen, best)`` is called after every generation (for the dashboard).
    """
    rng = random.Random(ga_cfg.get("seed", 1))

    toolbox = base.Toolbox()
    toolbox.register("attr", lambda: rng.randint(spec.min_green, spec.max_green))
    toolbox.register("individual", tools.initRepeat, creator.Individual,
                     toolbox.attr, n=spec.length)
    toolbox.register("population", tools.initRepeat, list, toolbox.individual)
    toolbox.register("evaluate", _eval_individual, spec=spec, net=net,
                     routes=routes, sim_cfg=sim_cfg)
    toolbox.register("mate", tools.cxUniform, indpb=0.5)
    toolbox.register("mutate", tools.mutUniformInt, low=spec.min_green,
                     up=spec.max_green, indpb=0.2)
    toolbox.register("select", tools.selTournament,
                     tournsize=ga_cfg.get("tournament_size", 3))
    toolbox.register("map", map_fn)

    pop_size = ga_cfg.get("population", 24)
    generations = ga_cfg.get("generations", 15)
    cx_prob = ga_cfg.get("cx_prob", 0.6)
    mut_prob = ga_cfg.get("mut_prob", 0.3)

    # Seed the RNG used by DEAP's variation operators for reproducibility.
    random.seed(ga_cfg.get("seed", 1))
    pop = toolbox.population(n=pop_size)
    if pop:
        pop[0][:] = spec.baseline_genome()

    def evaluate_pop(individuals):
        fits = toolbox.map(toolbox.evaluate, individuals)
        for ind, fit in zip(individuals, fits):
            ind.fitness.values = fit

    evaluate_pop(pop)
    hof = tools.HallOfFame(1)
    hof.update(pop)
    convergence = [hof[0].fitness.values[0]]
    if progress_cb:
        progress_cb(0, hof[0])

    for gen in range(1, generations + 1):
        offspring = toolbox.select(pop, len(pop))
        offspring = [toolbox.clone(ind) for ind in offspring]

        for c1, c2 in zip(offspring[::2], offspring[1::2]):
            if random.random() < cx_prob:
                toolbox.mate(c1, c2)
                del c1.fitness.values, c2.fitness.values
        for mutant in offspring:
            if random.random() < mut_prob:
                toolbox.mutate(mutant)
                del mutant.fitness.values

        invalid = [ind for ind in offspring if not ind.fitness.valid]
        evaluate_pop(invalid)

        # Elitism: keep the best individual seen so far.
        pop = offspring
        pop[0] = toolbox.clone(hof[0])
        hof.update(pop)
        convergence.append(hof[0].fitness.values[0])
        if progress_cb:
            progress_cb(gen, hof[0])

    best = list(hof[0])
    baseline = evaluate(spec, spec.baseline_genome(), net, routes,
                        end=sim_cfg.get("end", 600.0),
                        step_length=sim_cfg.get("step_length", 1.0),
                        seed=sim_cfg.get("seed", 42)).fitness
    return OptResult(best_genome=best, best_fitness=hof[0].fitness.values[0],
                     baseline_fitness=baseline, convergence=convergence)


def _main() -> None:
    import argparse
    import json
    import time
    from pathlib import Path

    import yaml

    from src.network.build_network import build_network

    ap = argparse.ArgumentParser(description="Optimize traffic-light timings (GA)")
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", default="runs/cli")
    ap.add_argument("--rebuild", action="store_true",
                    help="regenerate the network even if it already exists")
    args = ap.parse_args()

    with open(args.config) as fh:
        cfg = yaml.safe_load(fh)

    out = Path(args.out)
    net, routes = out / "net.net.xml", out / "routes.rou.xml"
    if args.rebuild or not net.exists() or not routes.exists():
        paths = build_network(cfg, out)
        net, routes = paths["net"], paths["routes"]
    else:
        net, routes = str(net), str(routes)

    sig = cfg.get("signals", {})
    spec = read_tls_spec(net, routes, min_green=sig.get("min_green", 5),
                         max_green=sig.get("max_green", 60),
                         seed=cfg.get("simulation", {}).get("seed", 42))
    print(f"Traffic lights: {len(spec.programs)} | genome length: {spec.length}")

    t0 = time.perf_counter()
    res = optimize(spec, net, routes, cfg.get("simulation", {}), cfg.get("ga", {}),
                   progress_cb=lambda g, b: print(
                       f"  gen {g:>3}: best={b.fitness.values[0]:.0f}"))
    elapsed = time.perf_counter() - t0

    print(f"\nBaseline (default fixed-time): {res.baseline_fitness:.0f} veh*s")
    print(f"Optimized:                     {res.best_fitness:.0f} veh*s")
    print(f"Improvement:                   {res.improvement_pct:.1f}%")
    print(f"Elapsed:                       {elapsed:.1f}s")

    result_path = out / "optimization_result.json"
    with open(result_path, "w") as fh:
        json.dump({
            "best_genome": res.best_genome,
            "best_fitness": res.best_fitness,
            "baseline_fitness": res.baseline_fitness,
            "improvement_pct": res.improvement_pct,
            "convergence": res.convergence,
            "elapsed_s": elapsed,
        }, fh, indent=2)
    print(f"Saved {result_path}")


if __name__ == "__main__":
    _main()
