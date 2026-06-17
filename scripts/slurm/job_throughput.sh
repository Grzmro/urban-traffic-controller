#!/bin/bash -l
#SBATCH --job-name=traffic-throughput
#SBATCH --account=PLG_GRANT_ID            # <-- set your PLGrid grant id
#SBATCH --partition=plgrid
#SBATCH --nodes=2
#SBATCH --ntasks=48
#SBATCH --time=08:00:00
#SBATCH --output=results/throughput_%j.log
#
# Study B4 — throughput (SUMO evaluations / second) vs number of MPI workers.
# A FIXED batch of independent evaluations is distributed across K ranks; each srun
# appends one (workers, evals_per_s, ...) row. Ideal scaling = linear in workers.

set -euo pipefail
module load Miniconda3/23.3.1-0 || true
conda activate traffic
export SUMO_HOME="$(python -c 'import sumolib, os; print(os.path.dirname(os.path.dirname(sumolib.__file__)))' 2>/dev/null || echo)"

CONFIG=config/scenario_large.yaml
CSV=results/throughput.csv
rm -f "$CSV"

# Fixed total work (480 evaluations of an 8x8 city), increasing worker count.
for K in 2 4 8 16 24 32 48; do
    echo "=== ranks=$K ==="
    srun --ntasks="$K" python -m mpi4py.futures -m src.bench.benchmark \
        --parallel --config "$CONFIG" --grids 8 --evals 480 --csv "$CSV"
done

python analysis/plot_throughput.py --csv "$CSV" --out results/throughput.png --mode cores
