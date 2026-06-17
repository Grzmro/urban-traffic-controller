"""Algorithm comparison plot (data from src.compare.benchmark_algorithms).

Two panels:
  * left  -- convergence: best total delay vs number of SUMO evaluations,
             one line per algorithm, with the fixed-time baseline as reference.
  * right -- final improvement over baseline per algorithm (bar chart).

Usage::

    python analysis/plot_algorithms.py --csv results/algorithms.csv \
        --summary results/algorithms_summary.csv --out results/algorithms.png
"""
from __future__ import annotations

import argparse

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

LABELS = {"ga": "Genetic algorithm", "random": "Random search",
          "hillclimb": "Hill climbing", "anneal": "Simulated annealing"}
COLORS = {"ga": "#27ae60", "random": "#7f8c8d", "hillclimb": "#2980b9",
          "anneal": "#e67e22"}
ORDER = ["ga", "anneal", "hillclimb", "random"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, help="convergence CSV (algorithm,evals,best)")
    ap.add_argument("--summary", required=True, help="summary CSV (per-algorithm)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    conv = pd.read_csv(args.csv)
    summ = pd.read_csv(args.summary).set_index("algorithm")
    baseline = float(summ.loc["baseline", "baseline"])

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))

    # ---- convergence ---------------------------------------------------- #
    present = [a for a in ORDER if a in conv["algorithm"].unique()]
    for algo in present:
        d = conv[conv["algorithm"] == algo].sort_values("evals")
        ax1.plot(d["evals"], d["best"], "-o", ms=3, color=COLORS.get(algo),
                 label=LABELS.get(algo, algo))
    ax1.axhline(baseline, ls="--", color="#c0392b", lw=1.2,
                label="baseline (fixed-time)")
    ax1.set(xlabel="SUMO evaluations (equal budget)",
            ylabel="best total delay [veh·s]",
            title="Convergence — lower is better")
    ax1.legend(fontsize=9); ax1.grid(alpha=0.3)

    # ---- final improvement bars ----------------------------------------- #
    algos = [a for a in ORDER if a in summ.index]
    imp = [float(summ.loc[a, "improvement_pct"]) for a in algos]
    bars = ax2.bar([LABELS.get(a, a) for a in algos], imp,
                   color=[COLORS.get(a) for a in algos])
    for b, v in zip(bars, imp):
        ax2.text(b.get_x() + b.get_width() / 2, v, f"-{v:.1f}%",
                 ha="center", va="bottom", fontsize=10)
    ax2.set(ylabel="improvement over baseline [%]",
            title="Final result (same evaluation budget)")
    ax2.tick_params(axis="x", rotation=20)
    ax2.grid(alpha=0.3, axis="y")

    fig.tight_layout(); fig.savefig(args.out, dpi=130)
    print(f"Saved {args.out}")


if __name__ == "__main__":
    main()
