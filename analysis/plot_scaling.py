"""Turn a scaling CSV (written by src.ga.parallel) into speedup/efficiency plots.

Strong scaling:  speedup(K) = T(ref) / T(K);  efficiency = speedup / (K/ref).
Weak scaling:    plot wall-clock vs ranks (ideal = flat) + efficiency T(ref)/T(K).
"""
from __future__ import annotations

import argparse

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def plot_strong(df: pd.DataFrame, out: str) -> None:
    df = df.sort_values("workers")
    k = df["workers"].to_numpy()
    t = df["elapsed_s"].to_numpy()
    ref_k, ref_t = k[0], t[0]
    speedup = ref_t / t
    ideal = k / ref_k
    efficiency = speedup / ideal

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    ax1.plot(k, speedup, "o-", label="measured", color="#27ae60")
    ax1.plot(k, ideal, "--", label="ideal (linear)", color="#888")
    ax1.set(xlabel="MPI workers", ylabel="speedup", title="Strong scaling — speedup")
    ax1.legend(); ax1.grid(alpha=0.3)

    ax2.plot(k, efficiency, "s-", color="#2980b9")
    ax2.axhline(1.0, ls="--", color="#888")
    ax2.set(xlabel="MPI workers", ylabel="parallel efficiency",
            title="Strong scaling — efficiency", ylim=(0, 1.1))
    ax2.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(out, dpi=130)
    print(f"Saved {out}")


def plot_weak(df: pd.DataFrame, out: str) -> None:
    df = df.sort_values("workers")
    k = df["workers"].to_numpy()
    t = df["elapsed_s"].to_numpy()
    efficiency = t[0] / t

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    ax1.plot(k, t, "o-", color="#27ae60")
    ax1.axhline(t[0], ls="--", color="#888", label="ideal (flat)")
    ax1.set(xlabel="MPI workers", ylabel="wall-clock [s]",
            title="Weak scaling — runtime"); ax1.legend(); ax1.grid(alpha=0.3)

    ax2.plot(k, efficiency, "s-", color="#2980b9")
    ax2.axhline(1.0, ls="--", color="#888")
    ax2.set(xlabel="MPI workers", ylabel="weak efficiency",
            title="Weak scaling — efficiency", ylim=(0, 1.1)); ax2.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(out, dpi=130)
    print(f"Saved {out}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--mode", choices=["strong", "weak"], default="strong")
    args = ap.parse_args()

    df = pd.read_csv(args.csv)
    if args.mode == "strong":
        plot_strong(df, args.out)
    else:
        plot_weak(df, args.out)


if __name__ == "__main__":
    main()
