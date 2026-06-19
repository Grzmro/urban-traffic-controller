#!/bin/bash -l
#SBATCH --job-name=traffic-strong
#SBATCH --account=plglscclass26-cpu
#SBATCH --partition=plgrid
#SBATCH --nodes=2
#SBATCH --ntasks=48
#SBATCH --time=24:00:00
#SBATCH --output=results/strong_%j.log

set -euo pipefail

module load miniconda3/24.5.0-0
module load openmpi/4.1.6-gcc-13.2.0
eval "$(conda shell.bash hook)"
conda activate traffic

export SUMO_HOME=$HOME/sumo-1_20_0
export PATH=$SUMO_HOME/bin:$PATH
export PYTHONPATH=$SUMO_HOME/tools:${PYTHONPATH:-}
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$SUMO_HOME/bin:${LD_LIBRARY_PATH:-}

export SLURM_MPI_TYPE=pmix

mkdir -p results runs/hpc

CONFIG=config/scenario_large.yaml
CSV=results/scaling_strong.csv

python -m src.network.build_network --config "$CONFIG" --out runs/hpc

rm -f "$CSV"
for K in 2 4 8 16 24 32 48; do
    echo "=== ranks=$K ==="
    srun --ntasks="$K" python -m mpi4py.futures -m src.ga.parallel \
        --config "$CONFIG" --out runs/hpc --csv "$CSV"
done

python analysis/plot_scaling.py --csv "$CSV" --out results/strong_scaling.png --mode strong
