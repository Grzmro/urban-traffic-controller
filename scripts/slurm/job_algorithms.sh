#!/bin/bash -l
#SBATCH --job-name=traffic-algos
#SBATCH --account=plglscclass26-cpu
#SBATCH --partition=plgrid
#SBATCH --nodes=1
#SBATCH --ntasks=24
#SBATCH --time=12:00:00
#SBATCH --output=results/algos_%j.log
#
# Algorithm comparison — random search vs hill climbing vs simulated annealing
# vs the genetic algorithm, all on the SAME objective and SAME evaluation budget
# (the budget is the GA's own evaluation count). Fixed worker count.

set -euo pipefail

module load miniconda3/24.5.0-0
module load openmpi/4.1.6-gcc-13.2.0    # provides libmpi.so + PMIx for srun-launched ranks
eval "$(conda shell.bash hook)"
conda activate traffic

# Use the locally compiled SUMO (source tree): binaries in bin/, python
# bindings (libsumo, traci, sumolib, randomTrips) in tools/. libsumocpp.so
# and xerces-c must be on LD_LIBRARY_PATH for libsumo to import.
export SUMO_HOME=$HOME/sumo-1_20_0
export PATH=$SUMO_HOME/bin:$PATH
export PYTHONPATH=$SUMO_HOME/tools:${PYTHONPATH:-}
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$SUMO_HOME/bin:${LD_LIBRARY_PATH:-}

# OpenMPI 4.1.6 was built with PMIx; tell srun to launch ranks via PMIx.
export SLURM_MPI_TYPE=pmix

mkdir -p results

srun python -m mpi4py.futures -m src.compare.benchmark_algorithms \
    --parallel --config config/scenario_large.yaml \
    --out runs/compare \
    --csv results/algorithms.csv \
    --summary results/algorithms_summary.csv

# Plot locally (matplotlib is intentionally not installed on the cluster):
#   python analysis/plot_algorithms.py --csv results/algorithms.csv \
#       --summary results/algorithms_summary.csv --out results/algorithms.png
