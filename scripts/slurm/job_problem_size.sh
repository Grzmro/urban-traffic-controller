#!/bin/bash -l
#SBATCH --job-name=traffic-size
#SBATCH --account=plglscclass26-cpu
#SBATCH --partition=plgrid
#SBATCH --nodes=1
#SBATCH --ntasks=24
#SBATCH --time=24:00:00
#SBATCH --output=results/size_%j.log
#
# Study B5 — cost of one simulation vs city size, fixed worker count.

set -euo pipefail

module load miniconda3/24.5.0-0
eval "$(conda shell.bash hook)"
conda activate traffic

export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:${LD_LIBRARY_PATH:-}
export PATH=$HOME/sumo-local/bin:$PATH
export SUMO_HOME=$CONDA_PREFIX/lib/python3.11/site-packages/sumo
export PYTHONPATH=$SUMO_HOME/tools:${PYTHONPATH:-}

mkdir -p results

CSV=results/problem_size.csv
rm -f "$CSV"

srun python -m mpi4py.futures -m src.bench.benchmark \
    --parallel --config config/scenario_large.yaml \
    --grids 3,5,8,12,16,24,32 --evals 96 --csv "$CSV"

python analysis/plot_throughput.py --csv "$CSV" --out results/problem_size.png --mode size
