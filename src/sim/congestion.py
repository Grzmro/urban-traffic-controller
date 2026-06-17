"""Collect per-edge congestion for the before/after heatmap.

Runs a simulation for a given signal plan and records, for every road (edge), the
mean number of halting vehicles over time — a direct measure of how congested that
street is. Comparing the baseline vs optimized plan shows *where* the queues melt.
"""
from __future__ import annotations

from .encoding import TLSSpec, apply_genome
from .sumo import base_command, conn


def collect_edge_congestion(spec: TLSSpec, genome: list[int], net: str, routes: str,
                            *, end: float = 300.0, step_length: float = 1.0,
                            seed: int = 42, stride: int = 2) -> dict[str, float]:
    """Return ``{edge_id: mean halting vehicles}`` for the given plan."""
    conn.start(base_command(net, routes, step_length=step_length, seed=seed))
    try:
        apply_genome(spec, genome)
        edges = [e for e in conn.edge.getIDList() if not e.startswith(":")]
        accum = {e: 0.0 for e in edges}

        steps = int(end / step_length)
        samples = 0
        step = 0
        while step < steps and conn.simulation.getMinExpectedNumber() > 0:
            conn.simulationStep()
            if step % stride == 0:
                for e in edges:
                    accum[e] += conn.edge.getLastStepHaltingNumber(e)
                samples += 1
            step += 1
        if samples:
            for e in accum:
                accum[e] /= samples
    finally:
        conn.close()
    return accum
