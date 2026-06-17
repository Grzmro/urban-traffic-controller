"""Run a simulation and collect per-timestep vehicle positions for animation.

Unlike :mod:`src.sim.evaluate` (which only accumulates a score), this records where
every vehicle is at each sampled step, so the dashboard can animate the traffic for
a given signal plan. Frames are subsampled to keep the browser payload small.
"""
from __future__ import annotations

from .encoding import TLSSpec, apply_genome
from .sumo import base_command, conn


def collect_frames(spec: TLSSpec, genome: list[int], net: str, routes: str, *,
                   end: float = 300.0, step_length: float = 1.0, seed: int = 42,
                   max_frames: int = 120) -> list[dict]:
    """Simulate with the given signal plan and return animation frames.

    Each frame: ``{"t": seconds, "x": [...], "y": [...], "speed": [...]}``.
    """
    conn.start(base_command(net, routes, step_length=step_length, seed=seed))
    try:
        apply_genome(spec, genome)
        steps = int(end / step_length)
        stride = max(1, steps // max_frames)

        frames: list[dict] = []
        step = 0
        while step < steps and conn.simulation.getMinExpectedNumber() > 0:
            conn.simulationStep()
            if step % stride == 0:
                xs, ys, spd = [], [], []
                for v in conn.vehicle.getIDList():
                    x, y = conn.vehicle.getPosition(v)
                    xs.append(x)
                    ys.append(y)
                    spd.append(conn.vehicle.getSpeed(v))
                frames.append({"t": step * step_length, "x": xs, "y": ys, "speed": spd})
            step += 1
    finally:
        conn.close()
    return frames
