#!/bin/bash
#SBATCH --job-name=traffic-weak
#SBATCH --account=PLGRID_GRANT_ID        # <-- set your PLGrid grant id
#SBATCH --partition=plgrid
#SBATCH --nodes=2
#SBATCH --ntasks=48
#SBATCH --time=08:00:00
#SBATCH --output=results/weak_%j.log
#
# Weak scaling: problem grows WITH the number of ranks (GA population scales with
# worker count, so work-per-worker stays ~constant). Ideal weak scaling => flat
# wall-clock time as ranks increase.

set -euo pipefail

module load python
source activate traffic || true
export SUMO_HOME="${SUMO_HOME:?set SUMO_HOME to the SUMO install}"

CONFIG=config/scenario_large.yaml
CSV=results/scaling_weak.csv
python -m src.network.build_network --config "$CONFIG" --out runs/hpc

rm -f "$CSV"
# population per worker kept constant (~4); total population = 4 * (ranks-1).
for K in 2 4 8 16 24 32 48; do
    POP=$(( 4 * (K - 1) ))
    [ "$POP" -lt 8 ] && POP=8
    echo "=== ranks=$K population=$POP ==="
    srun --ntasks="$K" python -m mpi4py.futures -m src.ga.parallel \
        --config "$CONFIG" --out runs/hpc --csv "$CSV" --population "$POP"
done

python analysis/plot_scaling.py --csv "$CSV" --out results/weak_scaling.png --mode weak
