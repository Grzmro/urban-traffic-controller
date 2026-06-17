"""Shared fixtures: build one tiny SUMO network for the whole test session."""
from __future__ import annotations

import pytest

from src.network.build_network import build_network

TINY_CFG = {
    "network": {"type": "grid", "grid_number": 2, "grid_length": 120,
                "lanes": 1, "attach_length": 80},
    "demand": {"end": 200, "period": 2.0, "fringe_factor": 5, "seed": 7},
    "simulation": {"step_length": 1.0, "seed": 7},
    "signals": {"min_green": 5, "max_green": 50, "yellow": 3},
    "ga": {"population": 8, "generations": 3, "cx_prob": 0.6, "mut_prob": 0.3,
           "tournament_size": 3, "seed": 1},
}


@pytest.fixture(scope="session")
def network(tmp_path_factory):
    out = tmp_path_factory.mktemp("net")
    paths = build_network(TINY_CFG, out)
    return paths


@pytest.fixture(scope="session")
def cfg():
    return TINY_CFG
