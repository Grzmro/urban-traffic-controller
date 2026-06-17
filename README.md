# Urban Traffic Controller

Interactive dashboard for **designing intersections and optimizing their traffic-light
timings**, plus an HPC study showing that the optimization scales on a supercomputer.

Project for the *Large Scale Computing* course.

- **Build** a road network in the dashboard (parametric SUMO grid/spider, or upload your own).
- **Optimize** the signal timings with a genetic algorithm — fully automatic.
- **Compare** before/after: how much shorter is the total vehicle delay vs fixed-time signals?
- **Scale** the same optimization across many CPUs with MPI on Cyfronet Ares.

## How it works

```
Dashboard (Dash/Plotly)  ──►  Genetic Algorithm (DEAP)  ──►  SUMO simulation (headless)
   build / edit network        searches green durations        scores each candidate
   show before/after           keeps the best plan             = total vehicle delay
                                      │
                                      └─ parallel evaluation via mpi4py  → HPC scaling study
```

- **Genome:** green-phase durations across every intersection (yellow/red phases stay fixed,
  so generated programs are always valid). See `src/sim/encoding.py`.
- **Fitness:** total vehicle delay (vehicle-seconds spent halting) from one headless SUMO run.
  See `src/sim/evaluate.py`.
- **Optimizer:** DEAP GA; evaluation is dispatched through a `map_fn` so the *same* code runs
  serially (`map`) or in parallel (`MPIPoolExecutor.map`). See `src/ga/`.

## Requirements

- **SUMO** installed with `SUMO_HOME` set (so the bundled `traci`/`sumolib` import). Tested with SUMO 1.27.
- Python deps: `pip install -r requirements.txt`
- HPC section only: `pip install mpi4py` (built against the cluster's MPI).

## Run it

```bash
# 1) CLI smoke test: build a small grid, optimize, print improvement
python -m src.ga.optimizer --config config/scenario_small.yaml --out runs/cli

# 2) Dashboard (the centerpiece)
python -m app.dashboard          # open http://127.0.0.1:8050

# 3) Tests
pytest -q
```

## Cyfronet (Ares) compute studies

| Study | Command | Output |
|-------|---------|--------|
| **B1 strong scaling** (speedup, efficiency, time-to-solution) | `sbatch scripts/slurm/job_strong_scaling.sh` | `results/strong_scaling.png` |
| **B2 weak scaling** | `sbatch scripts/slurm/job_weak_scaling.sh` | `results/weak_scaling.png` |
| **B4 throughput** (evals/s vs workers) | `sbatch scripts/slurm/job_throughput.sh` | `results/throughput.png` |
| **B5 problem size** (cost vs city size) | `sbatch scripts/slurm/job_problem_size.sh` | `results/problem_size.png` |
| **B6 traci vs libsumo** | compare the `backend` column across a local vs cluster run | — |
| **Algorithm comparison** (GA vs random / hill climbing / simulated annealing, equal eval budget) | `sbatch scripts/slurm/job_algorithms.sh` | `results/algorithms.png` |

Each job appends rows to a CSV and renders a plot via `analysis/plot_scaling.py` /
`analysis/plot_throughput.py`. Set your PLGrid grant in each `#SBATCH --account=` line.

**Run meaningful numbers locally (no cluster, serial):**
```bash
# per-evaluation cost & throughput vs city size — real data from your machine
python -m src.bench.benchmark --grids 3,5,8 --evals 15 --csv results/benchmark.csv
python analysis/plot_throughput.py --csv results/benchmark.csv --out results/size.png --mode size
```

> Locally SUMO ships only `traci` (socket-based). On the cluster, install the `eclipse-sumo`
> wheel (or `libsumo`) so simulations run in-process and per-evaluation overhead is minimal —
> the `backend` column in the benchmark CSV quantifies exactly that difference (study B6).

## Train your own network on Cyfronet (round-trip)

The dashboard ↔ Ares round-trip lets you design a network locally, **train** its
signal timings on the cluster, then bring the result back to *see* how much it
improved. The whole exchange is two files: a ZIP up, a JSON down.

```
Dashboard ──Export to Cyfronet──► cyfronet_<name>.zip ──scp──► Ares
                                                                  │ sbatch optimize_job.sh
                                                                  │ (parallel GA trains the lights)
Dashboard ◄──Import result──── optimization_result.json ◄──scp──┘
```

### 1) Export the model from the dashboard

In the dashboard build a grid/spider network (or upload your own `*.net.xml`),
optionally tune the demand, then in **section 3 (Cyfronet)** click
**Export to Cyfronet**. You get `cyfronet_<name>.zip` containing the exact network
+ demand, a beefed-up `scenario.yaml` (bigger GA than the local smoke run), the
project `src/`, `requirements.txt` and a ready `optimize_job.sh`.

### 2) Copy it to Ares and unzip

```bash
# from your machine
scp cyfronet_<name>.zip plgUSER@ares.cyfronet.pl:/net/afscra/people/plgUSER/
# on Ares
cd /net/afscra/people/plgUSER && unzip cyfronet_<name>.zip && cd cyfronet_<name>
```

### 3) Point the job at the working SUMO + MPI environment

> The `optimize_job.sh` shipped in the bundle installs the `eclipse-sumo` wheel —
> **that binary SIGSEGVs on Ares compute nodes**. Use the SUMO built from source
> instead (see the one-time build recipe in `scripts/slurm/*.sh`). Replace the
> environment block at the top of `optimize_job.sh` with:

```bash
module load miniconda3/24.5.0-0
module load openmpi/4.1.6-gcc-13.2.0    # libmpi.so + PMIx for srun-launched ranks
eval "$(conda shell.bash hook)"
conda activate traffic

export SUMO_HOME=$HOME/sumo-1_20_0       # SUMO compiled from source (with libsumo)
export PATH=$SUMO_HOME/bin:$PATH
export PYTHONPATH=$SUMO_HOME/tools:${PYTHONPATH:-}
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$SUMO_HOME/bin:${LD_LIBRARY_PATH:-}
export SLURM_MPI_TYPE=pmix               # else MPI_Init aborts on a NULL communicator
```

Set `--account` to your PLGrid grant, and launch the training with `srun` (the
bundle uses `srun python -m mpi4py.futures -m src.ga.parallel … --result …`):

```bash
sbatch optimize_job.sh
squeue -u $USER          # watch it run; log is in result/train_<jobid>.log
```

The parallel GA evaluates the whole population across MPI workers and writes
**`result/optimization_result.json`** — the trained plan (best genome, baseline vs
optimized delay, learning curve). `result/scaling.csv` additionally logs
(workers, elapsed) if you want the scaling numbers.

### 4) Bring the result back and evaluate it

```bash
# from your machine
scp plgUSER@ares.cyfronet.pl:/net/afscra/people/plgUSER/cyfronet_<name>/result/optimization_result.json .
```

Open the dashboard, go to **section 3 → Import result**, and upload that JSON.
The before/after charts redraw with the cluster-trained timings: total vehicle
delay vs the fixed-time baseline, the `improvement_pct`, and the GA learning
curve — so you can judge directly how well the trained controller performs.

## Layout

| Path | Purpose |
|------|---------|
| `src/network/build_network.py` | wrap `netgenerate` + `randomTrips.py` |
| `src/sim/`                      | SUMO connection, genome encoding, fitness |
| `src/ga/optimizer.py`           | genetic algorithm (serial) |
| `src/ga/parallel.py`            | MPI-parallel GA (strong/weak scaling, trained-plan JSON) |
| `src/bench/benchmark.py`        | throughput / problem-size benchmark (serial or MPI) |
| `src/export/bundle.py`          | "Export to Cyfronet" bundle builder |
| `app/`                          | Dash dashboard + Plotly figures |
| `scripts/slurm/`                | Ares batch jobs (B1, B2, B4, B5) |
| `src/compare/benchmark_algorithms.py` | algorithm comparison (GA vs random/hill-climb/anneal, equal budget) |
| `analysis/plot_scaling.py`, `analysis/plot_throughput.py`, `analysis/plot_algorithms.py` | scaling, throughput & algorithm-comparison plots |
| `config/`                       | scenario presets |
