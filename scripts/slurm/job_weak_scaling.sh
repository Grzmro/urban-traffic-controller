#!/bin/bash -l
#SBATCH --job-name=traffic-weak
#SBATCH --account=plglscclass26-cpu
#SBATCH --partition=plgrid
#SBATCH --nodes=2
#SBATCH --ntasks=48
#SBATCH --time=24:00:00
#SBATCH --output=results/weak_%j.log
#
# Study B2 — weak scaling: problem grows with ranks (population scales with workers).

set -euo pipefail

module load miniconda3/24.5.0-0
eval "$(conda shell.bash hook)"
conda activate traffic

export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:${LD_LIBRARY_PATH:-}
export PATH=$HOME/sumo-local/bin:$PATH
export SUMO_HOME=$CONDA_PREFIX/lib/python3.11/site-packages/sumo
export PYTHONPATH=$SUMO_HOME/tools:${PYTHONPATH:-}

mkdir -p results runs/hpc

CONFIG=config/scenario_large.yaml
CSV=results/scaling_weak.csv

python -m src.network.build_network --config "$CONFIG" --out runs/hpc

rm -f "$CSV"
for K in 2 4 8 16 24 32 48; do
    POP=$(( 4 * (K - 1) ))
    [ "$POP" -lt 8 ] && POP=8
    echo "=== ranks=$K population=$POP ==="
    srun --ntasks="$K" python -m mpi4py.futures -m src.ga.parallel \
        --config "$CONFIG" --out runs/hpc --csv "$CSV" --population "$POP"
done

python analysis/plot_scaling.py --csv "$CSV" --out results/weak_scaling.png --mode weak
