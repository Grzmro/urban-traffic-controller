# Urban Traffic Controller

A project for the Large Scale Computing course. The idea is simple: take an
intersection grid, look at how long cars sit waiting at red lights, and let a
genetic algorithm retune the green-phase durations so they wait less. Then run
that optimization on a cluster, because evaluating signal plans means running a
lot of traffic simulations and they're all independent.

There's a dashboard to play with it interactively, and a set of SLURM jobs that
measure how well the whole thing scales on Cyfronet Ares.

## What it does

You build a road network (a parametric SUMO grid or spider, or upload your own
`.net.xml`), and the GA searches for the green durations that minimize total
vehicle delay. "Delay" here just means vehicle-seconds spent halting, measured
by running the network through SUMO once per candidate plan. The dashboard shows
you the before/after so you can see how much you actually gained over plain
fixed-time signals.

Because each plan is scored by an independent SUMO run, the population can be
evaluated in parallel with MPI. That's the large-scale part: the exact same
optimizer runs serially on a laptop or across dozens of workers on Ares.

```
Dashboard (Dash/Plotly)  ->  Genetic Algorithm (DEAP)  ->  SUMO (headless)
   build/edit network          searches green durations      scores each plan
   show before/after           keeps the best one            = total delay
                                      |
                                      +-- parallel eval via mpi4py -> scaling study
```

A few details that matter:

- **Genome** is the list of green durations across every intersection. Yellow
  and all-red phases are left alone, so whatever the GA produces is still a
  valid, safe signal program (`src/sim/encoding.py`).
- **Fitness** is the total vehicle delay from one headless SUMO run
  (`src/sim/evaluate.py`).
- The optimizer dispatches every evaluation through a `map_fn`, so swapping
  `map` for `MPIPoolExecutor.map` is the only difference between the local and
  the parallel run (`src/ga/`).

## Setup

You need SUMO installed with `SUMO_HOME` set so the bundled `traci`/`sumolib`
import. I tested with 1.27 locally and 1.20 on the cluster.

```bash
pip install -r requirements.txt
```

For the HPC part you also need `mpi4py` built against the cluster's MPI.

## Running it

```bash
# quick CLI check: build a small grid, optimize, print the improvement
python -m src.ga.optimizer --config config/scenario_small.yaml --out runs/cli

# the dashboard
python -m app.dashboard          # http://127.0.0.1:8050

# tests
pytest -q
```

## The scaling studies on Ares

Each study is its own SLURM job. They all share the same environment block (load
the modules, activate the `traffic` conda env, point at the source-built SUMO),
then launch the parallel GA with `srun python -m mpi4py.futures`. Set your PLGrid
grant in the `#SBATCH --account=` line before submitting.

| Study | Run it with | Output |
|-------|-------------|--------|
| Strong scaling (speedup, efficiency) | `sbatch scripts/slurm/job_strong_scaling.sh` | `results/strong_scaling.png` |
| Weak scaling | `sbatch scripts/slurm/job_weak_scaling.sh` | `results/weak_scaling.png` |
| Throughput (evals/s vs workers) | `sbatch scripts/slurm/job_throughput.sh` | `results/throughput.png` |
| Problem size (cost vs city size) | `sbatch scripts/slurm/job_problem_size.sh` | `results/problem_size.png` |
| Algorithm comparison (GA vs random / hill-climb / annealing) | `sbatch scripts/slurm/job_algorithms.sh` | `results/algorithms.png` |

Each job appends rows to a CSV; the plots are made afterwards from those CSVs
(matplotlib isn't installed on the cluster on purpose, so plotting never blocks a
run). Plot locally, e.g.:

```bash
python analysis/plot_algorithms.py --csv results/algorithms.csv \
    --summary results/algorithms_summary.csv --out results/algorithms.png
```

The headline numbers from my runs: the GA cuts total delay by 27.3% on an 8x8
city, the parallel evaluator hits a 26.96x speedup on 47 workers and sustains up
to ~46 SUMO evaluations per second.

If you don't have cluster access, you can still get real numbers locally (serial):

```bash
python -m src.bench.benchmark --grids 3,5,8 --evals 15 --csv results/benchmark.csv
python analysis/plot_throughput.py --csv results/benchmark.csv --out results/size.png --mode size
```

One caveat: locally SUMO usually ships only `traci` (socket-based), which is
slow. On the cluster I build SUMO from source so `libsumo` runs the simulations
in-process; that's what makes each evaluation cheap enough for the scaling to
look good.

## Training a network on Ares and bringing it back

The dashboard can hand a network off to the cluster and take the result back, so
you design locally, train on Ares, and then see how much it improved. The whole
exchange is two files: a zip up, a json down.

```
Dashboard --Export to Cyfronet--> cyfronet_<name>.zip --scp--> Ares
                                                                 | sbatch optimize_job.sh
                                                                 | (parallel GA trains the lights)
Dashboard <--Import result-- optimization_result.json <--scp----+
```

**1. Export.** Build (or upload) a network in the dashboard, tweak the demand if
you want, then hit *Export to Cyfronet* in section 3. You get a
`cyfronet_<name>.zip` with the network, demand, a bigger `scenario.yaml`, the
project `src/`, `requirements.txt` and a ready `optimize_job.sh`.

**2. Copy it over.**

```bash
scp cyfronet_<name>.zip plgUSER@ares.cyfronet.pl:/net/afscra/people/plgUSER/
# on Ares
cd /net/afscra/people/plgUSER && unzip cyfronet_<name>.zip && cd cyfronet_<name>
```

**3. Fix the environment.** The `optimize_job.sh` in the bundle tries to install
the `eclipse-sumo` wheel, and that binary segfaults on Ares compute nodes. Use
the SUMO built from source instead (the build recipe is in the
`scripts/slurm/*.sh` headers) and replace the top of `optimize_job.sh` with:

```bash
module load miniconda3/24.5.0-0
module load openmpi/4.1.6-gcc-13.2.0
eval "$(conda shell.bash hook)"
conda activate traffic

export SUMO_HOME=$HOME/sumo-1_20_0
export PATH=$SUMO_HOME/bin:$PATH
export PYTHONPATH=$SUMO_HOME/tools:${PYTHONPATH:-}
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$SUMO_HOME/bin:${LD_LIBRARY_PATH:-}
export SLURM_MPI_TYPE=pmix
```

Set `--account` to your grant and submit:

```bash
sbatch optimize_job.sh
squeue -u $USER
```

The job writes `result/optimization_result.json` with the trained plan (best
genome, baseline vs optimized delay, the learning curve).

**4. Bring it back.**

```bash
scp plgUSER@ares.cyfronet.pl:/net/afscra/people/plgUSER/cyfronet_<name>/result/optimization_result.json .
```

Open the dashboard, go to section 3 -> Import result, upload the json, and the
before/after charts redraw with the cluster-trained timings.

## Where things are

| Path | What's in it |
|------|--------------|
| `src/network/build_network.py` | wraps `netgenerate` + `randomTrips.py` |
| `src/sim/` | SUMO connection, genome encoding, fitness |
| `src/ga/optimizer.py` | the genetic algorithm (serial) |
| `src/ga/parallel.py` | MPI version for the scaling studies + trained-plan json |
| `src/bench/benchmark.py` | throughput / problem-size benchmark |
| `src/compare/benchmark_algorithms.py` | GA vs random / hill-climb / annealing |
| `src/export/bundle.py` | the "Export to Cyfronet" bundle builder |
| `app/` | the Dash dashboard and Plotly figures |
| `analysis/` | the plotting scripts |
| `scripts/slurm/` | the Ares batch jobs |
| `config/` | scenario presets |
