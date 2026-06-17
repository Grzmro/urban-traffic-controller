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

# Use the locally compiled SUMO (source tree): binaries in bin/, python
# bindings (libsumo, traci, sumolib, randomTrips) in tools/. libsumocpp.so
# and xerces-c must be on LD_LIBRARY_PATH for libsumo to import.
export SUMO_HOME=$HOME/sumo-1_20_0
export PATH=$SUMO_HOME/bin:$PATH
export PYTHONPATH=$SUMO_HOME/tools:${PYTHONPATH:-}
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$SUMO_HOME/bin:${LD_LIBRARY_PATH:-}

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
