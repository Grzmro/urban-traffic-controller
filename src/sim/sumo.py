"""Thin wrapper around the SUMO control API.

We prefer ``libsumo`` (in-process, fast — ideal for the HPC scaling section)
and transparently fall back to ``traci`` (socket-based) when libsumo is not
installed. Both expose the same surface we use here, so the rest of the code is
agnostic to which one is active.
"""
from __future__ import annotations

import shutil

import sumolib

try:
    import libsumo as _conn
    HAVE_LIBSUMO = True
except ImportError:
    import traci as _conn
    HAVE_LIBSUMO = False

conn = _conn


def sumo_binary(gui: bool = False) -> str:
    name = "sumo-gui" if gui else "sumo"
    return shutil.which(name) or sumolib.checkBinary(name)


def base_command(net: str, routes: str, *, step_length: float = 1.0,
                 seed: int = 42, gui: bool = False,
                 extra: list[str] | None = None) -> list[str]:
    """Standard headless command line shared by every simulation run."""
    cmd = [
        sumo_binary(gui),
        "-n", net,
        "-r", routes,
        "--step-length", str(step_length),
        "--seed", str(seed),
        "--no-step-log", "true",
        "--no-warnings", "true",
        "--duration-log.disable", "true",
        "--time-to-teleport", "300",
    ]
    if extra:
        cmd += extra
    return cmd
