#!/bin/bash
#SBATCH --job-name=traffic-strong
#SBATCH --account=PLGRID_GRANT_ID        # <-- set your PLGrid grant id
#SBATCH --partition=plgrid
#SBATCH --nodes=2
#SBATCH --ntasks=48
#SBATCH --time=08:00:00
#SBATCH --output=results/strong_%j.log
#
# Strong scaling: FIXED problem (scenario_large), increasing number of MPI ranks.
# Each srun appends one row (workers, elapsed_s, ...) to the CSV; analysis/plot_scaling.py
# turns that CSV into speedup / efficiency plots.

set -euo pipefail

module load python                       # adjust to the modules available on Ares
# Expect a conda/venv with: pip install eclipse-sumo mpi4py deap pyyaml numpy
source activate traffic || true

export SUMO_HOME="${SUMO_HOME:?set SUMO_HOME to the SUMO install}"
CONFIG=config/scenario_large.yaml
CSV=results/scaling_strong.csv

# Build the network once (serial) so all runs share identical inputs.
python -m src.network.build_network --config "$CONFIG" --out runs/hpc

rm -f "$CSV"
for K in 2 4 8 16 24 32 48; do
    echo "=== ranks=$K ==="
    srun --ntasks="$K" python -m mpi4py.futures -m src.ga.parallel \
        --config "$CONFIG" --out runs/hpc --csv "$CSV"
done

python analysis/plot_scaling.py --csv "$CSV" --out results/strong_scaling.png --mode strong
