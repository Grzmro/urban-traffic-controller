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
| `analysis/plot_scaling.py`, `analysis/plot_throughput.py` | scaling & throughput plots |
| `config/`                       | scenario presets |
