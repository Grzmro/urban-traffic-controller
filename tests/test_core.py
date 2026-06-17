"""Core correctness tests for the simulation + optimization pipeline."""
from __future__ import annotations

from src.ga.optimizer import optimize
from src.sim.encoding import apply_genome, read_tls_spec
from src.sim.evaluate import evaluate
from src.sim.sumo import base_command, conn


def _spec(network, cfg):
    sig = cfg["signals"]
    return read_tls_spec(network["net"], network["routes"],
                         min_green=sig["min_green"], max_green=sig["max_green"])


def test_spec_and_baseline(network, cfg):
    spec = _spec(network, cfg)
    assert spec.length > 0
    base = spec.baseline_genome()
    assert len(base) == spec.length
    assert all(spec.min_green <= v <= spec.max_green for v in base)


def test_apply_genome_sets_durations(network, cfg):
    """Genome durations must land on the controllable phases in SUMO."""
    spec = _spec(network, cfg)
    genome = [spec.min_green] * spec.length  # distinct from baseline
    conn.start(base_command(network["net"], network["routes"]))
    try:
        apply_genome(spec, genome)
        for tls, idx in spec.slots:
            logic = conn.trafficlight.getAllProgramLogics(tls)[0]
            assert logic.phases[idx].duration == spec.min_green
    finally:
        conn.close()


def test_evaluate_is_deterministic(network, cfg):
    spec = _spec(network, cfg)
    genome = spec.baseline_genome()
    r1 = evaluate(spec, genome, network["net"], network["routes"], end=200)
    r2 = evaluate(spec, genome, network["net"], network["routes"], end=200)
    assert r1.fitness == r2.fitness
    assert r1.departed == r2.departed


def test_optimize_beats_baseline(network, cfg):
    spec = _spec(network, cfg)
    res = optimize(spec, network["net"], network["routes"],
                   cfg["simulation"], cfg["ga"])
    # The GA keeps the best-so-far (elitism), so it can never end up worse.
    assert res.best_fitness <= res.baseline_fitness
    assert len(res.convergence) == cfg["ga"]["generations"] + 1
