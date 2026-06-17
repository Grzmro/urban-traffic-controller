"""Run one headless SUMO simulation for a given signal plan and score it.

This is the GA fitness function and the single most expensive operation in the
whole project (it is what the HPC section parallelizes). Lower fitness is better:
fitness = total vehicle delay (vehicle-seconds spent halting).
"""
from __future__ import annotations

from dataclasses import dataclass

from .encoding import TLSSpec, apply_genome
from .sumo import base_command, conn

HALT_SPEED = 0.1  # m/s below which a vehicle counts as waiting


@dataclass
class SimResult:
    fitness: float            # total delay [veh*s] — the GA minimizes this
    total_waiting_time: float
    departed: int
    arrived: int
    mean_waiting_time: float  # delay per departed vehicle [s]

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def evaluate(spec: TLSSpec, genome: list[int], net: str, routes: str, *,
             end: float = 600.0, step_length: float = 1.0, seed: int = 42,
             gui: bool = False, fcd_output: str | None = None) -> SimResult:
    extra = ["--fcd-output", fcd_output] if fcd_output else None
    conn.start(base_command(net, routes, step_length=step_length, seed=seed,
                            gui=gui, extra=extra))
    try:
        apply_genome(spec, genome)

        total_wait = 0.0
        departed = 0
        arrived = 0
        max_steps = int(end / step_length)
        step = 0
        while step < max_steps and conn.simulation.getMinExpectedNumber() > 0:
            conn.simulationStep()
            for v in conn.vehicle.getIDList():
                if conn.vehicle.getSpeed(v) < HALT_SPEED:
                    total_wait += step_length
            departed += conn.simulation.getDepartedNumber()
            arrived += conn.simulation.getArrivedNumber()
            step += 1
    finally:
        conn.close()

    mean_wait = total_wait / departed if departed else float("inf")
    return SimResult(
        fitness=total_wait,
        total_waiting_time=total_wait,
        departed=departed,
        arrived=arrived,
        mean_waiting_time=mean_wait,
    )
