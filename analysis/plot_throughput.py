"""Plots for the compute-performance studies (data from src.bench.benchmark).

  --mode size   : cost per evaluation & throughput vs city size           (study B5)
  --mode cores  : throughput (evals/s) vs number of MPI workers           (study B4)

The CSV's `backend` column (traci vs libsumo) feeds study B6 directly.
"""
from __future__ import annotations

import argparse

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def plot_size(df: pd.DataFrame, out: str) -> None:
    df = df.sort_values("intersections")
    x = df["intersections"].to_numpy()

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    ax1.plot(x, df["ms_per_eval"], "o-", color="#e67e22")
    ax1.set(xlabel="intersections (city size)", ylabel="ms per evaluation",
            title="B5 — simulation cost vs problem size")
    ax1.grid(alpha=0.3)

    ax2.plot(x, df["evals_per_s"], "s-", color="#2980b9")
    ax2.set(xlabel="intersections (city size)", ylabel="evaluations / s",
            title="B5 — throughput vs problem size")
    ax2.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(out, dpi=130)
    print(f"Saved {out}")


def plot_cores(df: pd.DataFrame, out: str) -> None:
    df = df.sort_values("workers")
    k = df["workers"].to_numpy()
    tput = df["evals_per_s"].to_numpy()
    ideal = tput[0] * (k / k[0])

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    ax1.plot(k, tput, "o-", color="#27ae60", label="measured")
    ax1.plot(k, ideal, "--", color="#888", label="ideal (linear)")
    ax1.set(xlabel="MPI workers", ylabel="evaluations / s",
            title="B4 — throughput scaling"); ax1.legend(); ax1.grid(alpha=0.3)

    efficiency = tput / ideal
    ax2.plot(k, efficiency, "s-", color="#2980b9")
    ax2.axhline(1.0, ls="--", color="#888")
    ax2.set(xlabel="MPI workers", ylabel="throughput efficiency",
            title="B4 — efficiency", ylim=(0, 1.1)); ax2.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(out, dpi=130)
    print(f"Saved {out}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--mode", choices=["size", "cores"], default="size")
    args = ap.parse_args()

    df = pd.read_csv(args.csv)
    (plot_size if args.mode == "size" else plot_cores)(df, args.out)


if __name__ == "__main__":
    main()
