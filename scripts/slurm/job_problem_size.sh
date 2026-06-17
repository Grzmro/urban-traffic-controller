#!/bin/bash -l
#SBATCH --job-name=traffic-size
#SBATCH --account=PLG_GRANT_ID            # <-- set your PLGrid grant id
#SBATCH --partition=plgrid
#SBATCH --nodes=1
#SBATCH --ntasks=24
#SBATCH --time=12:00:00
#SBATCH --output=results/size_%j.log
#
# Study B5 — how the cost of one simulation grows with city size, and how big a
# city stays tractable. One run sweeps several grid sizes at a fixed worker count.

set -euo pipefail
module load Miniconda3/23.3.1-0 || true
conda activate traffic
export SUMO_HOME="$(python -c 'import sumolib, os; print(os.path.dirname(os.path.dirname(sumolib.__file__)))' 2>/dev/null || echo)"

CSV=results/problem_size.csv
rm -f "$CSV"

# Sweep increasingly large cities; evaluations distributed across the allocation.
srun python -m mpi4py.futures -m src.bench.benchmark \
    --parallel --config config/scenario_large.yaml \
    --grids 3,5,8,12,16,24,32 --evals 96 --csv "$CSV"

python analysis/plot_throughput.py --csv "$CSV" --out results/problem_size.png --mode size
