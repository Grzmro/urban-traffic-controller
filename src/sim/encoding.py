"""Genome <-> SUMO traffic-light program mapping.

The optimizer searches over **green-phase durations**. The genome is a flat list
of integer durations, one entry per controllable (green) phase across all traffic
lights. Yellow/red transition phases are left untouched, so generated programs are
always valid.

A ``TLSSpec`` captures everything the GA needs to know up front (genome length,
bounds, baseline) without keeping a SUMO connection open.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .sumo import base_command, conn


def _is_green(state: str) -> bool:
    """A phase that gives at least one movement green (it is worth optimizing)."""
    return "G" in state or "g" in state


@dataclass
class PhaseInfo:
    state: str
    duration: float
    controllable: bool


@dataclass
class TLSSpec:
    """Structure of all traffic-light programs in a network."""
    programs: dict[str, str]                       # tls_id -> programID
    phases: dict[str, list[PhaseInfo]]             # tls_id -> phases
    slots: list[tuple[str, int]] = field(default_factory=list)  # genome index -> (tls, phase idx)
    min_green: int = 5
    max_green: int = 60

    @property
    def length(self) -> int:
        return len(self.slots)

    def baseline_genome(self) -> list[int]:
        """Durations of the controllable phases in SUMO's default program."""
        return [int(round(self.phases[tls][idx].duration)) for tls, idx in self.slots]


def read_tls_spec(net: str, routes: str, *, min_green: int = 5,
                  max_green: int = 60, seed: int = 42) -> TLSSpec:
    """Start SUMO briefly to read the default programs, then close."""
    conn.start(base_command(net, routes, seed=seed))
    try:
        programs: dict[str, str] = {}
        phases: dict[str, list[PhaseInfo]] = {}
        slots: list[tuple[str, int]] = []
        for tls in conn.trafficlight.getIDList():
            logic = conn.trafficlight.getAllProgramLogics(tls)[0]
            programs[tls] = logic.programID
            infos: list[PhaseInfo] = []
            for i, ph in enumerate(logic.phases):
                green = _is_green(ph.state)
                infos.append(PhaseInfo(ph.state, ph.duration, green))
                if green:
                    slots.append((tls, i))
            phases[tls] = infos
    finally:
        conn.close()
    return TLSSpec(programs, phases, slots, min_green, max_green)


def clamp(value: int, spec: TLSSpec) -> int:
    return max(spec.min_green, min(spec.max_green, int(value)))


def apply_genome(spec: TLSSpec, genome: list[int]) -> None:
    """Push the genome onto an *already running* SUMO connection.

    Builds one fixed-time (static) Logic per traffic light, overriding only the
    controllable green durations.
    """
    Logic = conn.trafficlight.Logic
    Phase = conn.trafficlight.Phase

    # Group genome values by traffic light.
    by_tls: dict[str, dict[int, int]] = {}
    for value, (tls, idx) in zip(genome, spec.slots):
        by_tls.setdefault(tls, {})[idx] = clamp(value, spec)

    for tls, infos in spec.phases.items():
        overrides = by_tls.get(tls, {})
        new_phases = []
        for i, ph in enumerate(infos):
            dur = float(overrides.get(i, ph.duration))
            new_phases.append(Phase(dur, ph.state, dur, dur))
        logic = Logic(spec.programs[tls], 0, 0, new_phases)
        conn.trafficlight.setProgramLogic(tls, logic)
