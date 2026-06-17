#!/bin/bash -l
#SBATCH --job-name=traffic-throughput
#SBATCH --account=plglscclass26-cpu
#SBATCH --partition=plgrid
#SBATCH --nodes=2
#SBATCH --ntasks=48
#SBATCH --time=24:00:00
#SBATCH --output=results/throughput_%j.log
#
# Study B4 — throughput (SUMO evals/s) vs number of MPI workers.

set -euo pipefail

module load miniconda3/24.5.0-0
eval "$(conda shell.bash hook)"
conda activate traffic

export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:${LD_LIBRARY_PATH:-}
export PATH=$HOME/sumo-local/bin:$PATH
export SUMO_HOME=$CONDA_PREFIX/lib/python3.11/site-packages/sumo
export PYTHONPATH=$SUMO_HOME/tools:${PYTHONPATH:-}

mkdir -p results

CONFIG=config/scenario_large.yaml
CSV=results/throughput.csv
rm -f "$CSV"

for K in 2 4 8 16 24 32 48; do
    echo "=== ranks=$K ==="
    srun --ntasks="$K" python -m mpi4py.futures -m src.bench.benchmark \
        --parallel --config "$CONFIG" --grids 8 --evals 480 --csv "$CSV"
done

python analysis/plot_throughput.py --csv "$CSV" --out results/throughput.png --mode cores
