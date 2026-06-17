"""Generate a SUMO road network + traffic demand from a scenario config.

Wraps SUMO's own tools so we never hand-write XML:
  * ``netgenerate`` builds a parametric network (grid/spider/random) with
    traffic lights already placed at every junction.
  * ``randomTrips.py`` generates randomized trips and routes them.

Both are shipped with SUMO; we locate them via ``SUMO_HOME``.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import sumolib  # type: ignore  # provided by %SUMO_HOME%/tools


def _sumo_home() -> Path:
    home = os.environ.get("SUMO_HOME")
    if not home:
        raise RuntimeError("SUMO_HOME is not set; cannot locate SUMO tools.")
    return Path(home)


def _netgenerate_args(net_cfg: dict, out_net: Path) -> list[str]:
    """Build the netgenerate command for the requested topology."""
    binary = shutil.which("netgenerate") or sumolib.checkBinary("netgenerate")
    args = [binary]

    topo = net_cfg.get("type", "grid")
    if topo == "grid":
        n = int(net_cfg.get("grid_number", 3))
        args += ["--grid", "--grid.number", str(n),
                 "--grid.length", str(net_cfg.get("grid_length", 150))]
        attach = net_cfg.get("attach_length", 0)
        if attach:
            args += ["--grid.attach-length", str(attach)]
    elif topo == "spider":
        args += ["--spider",
                 "--spider.arm-number", str(net_cfg.get("spider_arms", 6)),
                 "--spider.circle-number", str(net_cfg.get("spider_circles", 3)),
                 "--spider.space-radius", str(net_cfg.get("grid_length", 150))]
    elif topo == "rand":
        args += ["--rand", "--rand.iterations",
                 str(net_cfg.get("rand_iterations", 50))]
    else:
        raise ValueError(f"Unknown network type: {topo!r}")

    # Make every junction a real signalized intersection and keep geometry simple.
    args += [
        "--default.lanenumber", str(net_cfg.get("lanes", 1)),
        "--default-junction-type", "traffic_light",
        "--no-turnarounds", "true",
        "--tls.default-type", "static",
        "-o", str(out_net),
    ]
    return args


def build_network(cfg: dict, out_dir: str | os.PathLike) -> dict:
    """Generate ``net.net.xml`` and ``routes.rou.xml`` into ``out_dir``.

    Returns a dict with the resolved file paths. Each call writes into a fresh
    subdirectory so SUMO helpers do not collide with locked Windows files.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    run_dir = out / f"run_{uuid.uuid4().hex[:8]}"
    run_dir.mkdir(parents=True, exist_ok=True)

    net_path = run_dir / "net.net.xml"
    routes_path = run_dir / "routes.rou.xml"

    # 1) Network ----------------------------------------------------------
    net_args = _netgenerate_args(cfg.get("network", {}), net_path)
    subprocess.run(net_args, check=True, capture_output=True, text=True)

    # 2) Demand -----------------------------------------------------------
    demand = cfg.get("demand", {})
    random_trips = _sumo_home() / "tools" / "randomTrips.py"
    trips_args = [
        sys.executable, str(random_trips),
        "-n", str(net_path),
        "-r", str(routes_path),
        "-e", str(demand.get("end", 600)),
        "-p", str(demand.get("period", 1.6)),
        "--fringe-factor", str(demand.get("fringe_factor", 5)),
        "--seed", str(demand.get("seed", 42)),
        # Our SUMO is built without FOX, so duarouter cannot route in parallel.
        # --threads 1 stops randomTrips from passing --routing-threads to duarouter.
        "--threads", "1",
    ]
    subprocess.run(trips_args, check=True, capture_output=True, text=True)

    return {"net": str(net_path), "routes": str(routes_path)}


if __name__ == "__main__":
    import argparse
    import yaml

    ap = argparse.ArgumentParser(description="Build SUMO network + demand")
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", default="runs/cli")
    args = ap.parse_args()

    with open(args.config) as fh:
        scenario = yaml.safe_load(fh)
    paths = build_network(scenario, args.out)
    print("Generated:")
    for k, v in paths.items():
        print(f"  {k}: {v}")
