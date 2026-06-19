"""Interactive dashboard: build a network, optimize its signals, compare before/after.

Run with:  python -m app.dashboard   (then open http://127.0.0.1:8050)

This is the project centerpiece. The HPC/parallel scaling study is a separate
experiment (see scripts/slurm + analysis/) and is not driven from here.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

from dash import Dash, Input, Output, State, dcc, html, no_update

from app.viz import (animation_figure, comparison_figure, congestion_figure,
                     convergence_figure, network_figure, placeholder_figure)
from src.export.bundle import build_bundle
from src.ga.optimizer import optimize
from src.network.build_network import build_network
from src.sim.congestion import collect_edge_congestion
from src.sim.encoding import read_tls_spec
from src.sim.replay import collect_frames

RUN_DIR = Path("runs/dashboard")

app = Dash(__name__, title="Urban Traffic Controller")


def _slider(label, _id, mn, mx, step, value, marks=None, opt=False):
    """A labelled slider — always holds a valid value, so nothing 'disappears'."""
    return html.Div([
        html.Div(html.Span(label), className="field-label"),
        dcc.Slider(id=_id, min=mn, max=mx, step=step, value=value,
                   marks=marks or {}, className="opt-slider" if opt else "",
                   tooltip={"placement": "bottom", "always_visible": True}),
    ], className="field")


def _initial_summary():
    return html.Div("Build a network and run the optimization to see how much the "
                    "genetic algorithm reduces total vehicle delay.",
                    style={"color": "#6b7280"})


def _section(num, title, kind=""):
    return html.Div([html.Span(str(num), className="num"), title],
                    className=f"section-title {kind}")


controls = html.Div([
    _section(1, "Network"),
    html.Div([html.Div(html.Span("Topology"), className="field-label"),
              dcc.Dropdown(id="topo", options=["grid", "spider"], value="grid",
                           clearable=False)], className="field"),
    _slider("Junctions per side", "grid_number", 2, 10, 1, 3,
            {2: "2", 4: "4", 6: "6", 8: "8", 10: "10"}),
    _slider("Lanes per direction", "lanes", 1, 3, 1, 1, {1: "1", 2: "2", 3: "3"}),
    _slider("Edge length [m]", "grid_length", 50, 400, 25, 150,
            {50: "50", 250: "250", 400: "400"}),
    _slider("Vehicle every [s]", "period", 0.5, 4, 0.1, 1.6,
            {0.5: "0.5", 2: "2", 4: "4"}),
    _slider("Simulation horizon [s]", "end", 200, 1800, 100, 600,
            {200: "200", 1000: "1000", 1800: "1800"}),
    html.Button("Build & show network", id="build_btn", n_clicks=0,
                className="btn btn-build"),

    html.Div(className="divider"),
    _section(2, "Optimize", "opt"),
    _slider("GA population", "population", 8, 100, 4, 20,
            {8: "8", 40: "40", 80: "80", 100: "100"}, opt=True),
    _slider("GA generations", "generations", 5, 40, 1, 12,
            {5: "5", 20: "20", 40: "40"}, opt=True),
    html.Button("Run optimization", id="opt_btn", n_clicks=0,
                className="btn btn-opt"),

    html.Div(className="divider"),
    _section(3, "Visualize", "viz"),
    html.Button("▶  Animate traffic", id="anim_btn", n_clicks=0,
                className="btn btn-anim"),
    html.Button("🔥  Congestion heatmap", id="heat_btn", n_clicks=0,
                className="btn btn-heat"),

    html.Div(className="divider"),
    _section(4, "Cyfronet", "cyf"),
    html.Div([html.Div(html.Span("PLGrid grant id"), className="field-label"),
              dcc.Input(id="grant", type="text", value="",
                        placeholder="e.g. plgXXXX-cpu", className="text-input")],
             className="field"),
    _slider("MPI cores (ntasks)", "ntasks", 4, 48, 4, 24,
            {4: "4", 24: "24", 48: "48"}),
    html.Button("⬇  Export to Cyfronet", id="export_btn", n_clicks=0,
                className="btn btn-cyf"),
    dcc.Download(id="download"),
    dcc.Upload(id="import_upload", className="upload", children=html.Div(
        "⬆  Import result (.json from cluster)")),

    html.Div(id="status", className="status"),
], className="card controls")


_TAB = {"border": "none", "backgroundColor": "transparent", "color": "#cbd5e1",
        "padding": "9px 16px", "fontWeight": 600, "borderRadius": "10px"}
_TAB_SEL = {**_TAB, "backgroundColor": "#ffffff", "color": "#1f2937",
            "boxShadow": "0 6px 18px rgba(2,6,23,0.25)"}


def _graph(_id, height, hint):
    return html.Div(dcc.Loading(dcc.Graph(
        id=_id, style={"height": height}, figure=placeholder_figure(hint))),
        className="card")


results = html.Div([
    dcc.Tabs(id="tabs", value="network",
             style={"display": "flex", "flexDirection": "row", "flexWrap": "wrap",
                    "gap": "8px", "borderBottom": "none"},
             children=[
                 dcc.Tab(label="🗺️ Network", value="network", style=_TAB,
                         selected_style=_TAB_SEL),
                 dcc.Tab(label="📊 Optimization", value="optimization", style=_TAB,
                         selected_style=_TAB_SEL),
                 dcc.Tab(label="▶ Animation", value="animation", style=_TAB,
                         selected_style=_TAB_SEL),
                 dcc.Tab(label="🔥 Heatmap", value="heatmap", style=_TAB,
                         selected_style=_TAB_SEL),
             ]),
    html.Div([
        html.Div(_graph("network_fig", "520px",
                        "Click “Build & show network” (or import a real network) to start"),
                 id="panel-network", className="panel"),
        html.Div([
            html.Div(_initial_summary(), id="summary", className="card summary-card"),
            html.Div([_graph("conv_fig", "320px", "Run optimization to see convergence"),
                      _graph("cmp_fig", "320px", "Run optimization to compare before/after")],
                     className="graph-grid"),
        ], id="panel-optimization", className="panel", style={"display": "none"}),
        html.Div(_graph("traffic_anim", "560px",
                        "Click “Animate traffic” to watch cars move "
                        "(red = stopped, green = moving)"),
                 id="panel-animation", className="panel", style={"display": "none"}),
        html.Div(_graph("heatmap_fig", "520px",
                        "Click “Congestion heatmap” to see where queues form (before vs after)"),
                 id="panel-heatmap", className="panel", style={"display": "none"}),
    ], className="panels"),
], className="results")


app.layout = html.Div(html.Div([
    html.Div([
        html.H1("🚦 Urban Traffic Controller"),
        html.P("Design an intersection network, optimize its traffic-light timings, "
               "and compare before vs after."),
    ], className="app-header"),
    html.Div([controls, results], className="layout"),
    dcc.Store(id="paths"),
    dcc.Store(id="opt_store"),
], className="app-shell"))


def _v(value, default):
    """Fall back to the default if a number input was cleared (Dash sends None)."""
    return default if value is None else value


def _build_cfg(topo, grid_number, lanes, grid_length, period, end,
               population, generations) -> dict:
    return {
        "network": {"type": topo or "grid",
                    "grid_number": int(_v(grid_number, 3)),
                    "lanes": int(_v(lanes, 1)),
                    "grid_length": float(_v(grid_length, 150)),
                    "attach_length": 100},
        "demand": {"end": int(_v(end, 600)), "period": float(_v(period, 1.6)),
                   "fringe_factor": 5, "seed": 42},
        "simulation": {"step_length": 1.0, "seed": 42},
        "signals": {"min_green": 5, "max_green": 60, "yellow": 3},
        "ga": {"population": int(_v(population, 20)),
               "generations": int(_v(generations, 12)),
               "cx_prob": 0.6, "mut_prob": 0.3, "tournament_size": 3, "seed": 1},
    }


@app.callback(
    Output("panel-network", "style"),
    Output("panel-optimization", "style"),
    Output("panel-animation", "style"),
    Output("panel-heatmap", "style"),
    Input("tabs", "value"),
)
def show_panel(tab):
    """Show only the active tab's panel (all panels stay in the DOM)."""
    show, hide = {"display": "block"}, {"display": "none"}
    order = ["network", "optimization", "animation", "heatmap"]
    return tuple(show if tab == name else hide for name in order)


@app.callback(
    Output("network_fig", "figure"),
    Output("paths", "data"),
    Output("status", "children"),
    Output("tabs", "value"),
    Input("build_btn", "n_clicks"),
    State("topo", "value"), State("grid_number", "value"), State("lanes", "value"),
    State("grid_length", "value"), State("period", "value"), State("end", "value"),
    prevent_initial_call=True,
)
def on_build(_n, topo, grid_number, lanes, grid_length, period, end):
    cfg = _build_cfg(topo, grid_number, lanes, grid_length, period, end, 1, 1)
    paths = build_network(cfg, RUN_DIR)
    fig = network_figure(paths["net"], title=f"{topo} network")
    return fig, paths, "Network built. Ready to optimize.", "network"


@app.callback(
    Output("conv_fig", "figure"),
    Output("cmp_fig", "figure"),
    Output("summary", "children"),
    Output("opt_store", "data"),
    Output("paths", "data", allow_duplicate=True),
    Output("status", "children", allow_duplicate=True),
    Output("tabs", "value", allow_duplicate=True),
    Input("opt_btn", "n_clicks"),
    State("paths", "data"),
    State("topo", "value"), State("grid_number", "value"), State("lanes", "value"),
    State("grid_length", "value"), State("period", "value"), State("end", "value"),
    State("population", "value"), State("generations", "value"),
    prevent_initial_call=True,
)
def on_optimize(_n, paths, topo, grid_number, lanes, grid_length, period, end,
                population, generations):
    cfg = _build_cfg(topo, grid_number, lanes, grid_length, period, end,
                     population, generations)
    if not paths:
        paths = build_network(cfg, RUN_DIR)

    sig = cfg["signals"]
    spec = read_tls_spec(paths["net"], paths["routes"],
                         min_green=sig["min_green"], max_green=sig["max_green"])
    res = optimize(spec, paths["net"], paths["routes"],
                   cfg["simulation"], cfg["ga"])

    conv = convergence_figure(res.convergence, res.baseline_fitness)
    cmp = comparison_figure({"baseline": res.baseline_fitness,
                             "optimized": res.best_fitness})
    summary = _summary_cards(
        res.baseline_fitness, res.best_fitness, res.improvement_pct,
        spec.length, len(spec.programs), res.convergence)
    store = {"genome": res.best_genome, "end": cfg["simulation"].get("end", 600)}
    return conv, cmp, summary, store, paths, "Optimization complete.", "optimization"


def _metric(label, value, kind):
    return html.Div([html.Div(label, className="label"),
                     html.Div(value, className="value")], className=f"metric {kind}")


def _summary_cards(baseline, best, improvement, green_phases, intersections,
                   convergence, opt_label="Optimized (GA)", note_prefix=""):
    near_optimal = _plateaued(convergence)
    return html.Div([
        html.Div([html.Span("Total vehicle delay ", style={"fontWeight": 600}),
                  html.Span("(veh·s — lower is better)",
                            style={"color": "#6b7280"})]),
        html.Div([
            _metric("Baseline (fixed-time)", f"{baseline:,.0f}", "base"),
            _metric(opt_label, f"{best:,.0f}", "opt"),
            _metric("Improvement", f"-{improvement:.1f}%", "win"),
        ], className="metric-row"),
        html.P([f"{note_prefix}Optimized {green_phases} green phases at "
                f"{intersections} intersections. ",
                "Convergence has plateaued → result is close to optimal."
                if near_optimal else
                "Still improving → more generations may help."],
               style={"color": "#6b7280", "marginBottom": 0}),
    ])


def _plateaued(convergence: list[float], window: int = 4) -> bool:
    if len(convergence) <= window:
        return False
    return convergence[-window] == convergence[-1]


@app.callback(
    Output("download", "data"),
    Output("status", "children", allow_duplicate=True),
    Input("export_btn", "n_clicks"),
    State("paths", "data"),
    State("topo", "value"), State("grid_number", "value"), State("lanes", "value"),
    State("grid_length", "value"), State("period", "value"), State("end", "value"),
    State("population", "value"), State("generations", "value"),
    State("grant", "value"), State("ntasks", "value"),
    prevent_initial_call=True,
)
def on_export(_n, paths, topo, grid_number, lanes, grid_length, period, end,
              population, generations, grant, ntasks):
    if not paths:
        return no_update, "Build a network first, then export."
    cfg = _build_cfg(topo, grid_number, lanes, grid_length, period, end,
                     population, generations)
    name = f"{topo or 'grid'}{int(_v(grid_number, 3))}"
    data = build_bundle(cfg, paths["net"], paths["routes"], name=name,
                        grant=grant or "PLG_GRANT_ID", ntasks=int(_v(ntasks, 24)))
    fname = f"cyfronet_{name}.zip"
    return (dcc.send_bytes(lambda b: b.write(data), fname),
            f"Exported {fname} ({len(data) // 1024} KB) — upload it to Ares.")


@app.callback(
    Output("conv_fig", "figure", allow_duplicate=True),
    Output("cmp_fig", "figure", allow_duplicate=True),
    Output("summary", "children", allow_duplicate=True),
    Output("status", "children", allow_duplicate=True),
    Input("import_upload", "contents"),
    prevent_initial_call=True,
)
def on_import(contents):
    if not contents:
        return no_update, no_update, no_update, no_update
    try:
        _, b64 = contents.split(",", 1)
        data = json.loads(base64.b64decode(b64))
    except Exception as exc:
        return no_update, no_update, no_update, f"Import failed: {exc}"

    conv = convergence_figure(data["convergence"], data["baseline_fitness"])
    cmp = comparison_figure({"baseline": data["baseline_fitness"],
                             "optimized": data["best_fitness"]})
    summary = _summary_cards(
        data["baseline_fitness"], data["best_fitness"],
        data.get("improvement_pct", 0.0), data.get("green_phases", 0),
        data.get("intersections", 0), data["convergence"],
        opt_label="Trained on Cyfronet",
        note_prefix=f"Trained on {data.get('workers', '?')} MPI workers. ")
    return conv, cmp, summary, f"Imported trained plan: {data.get('scenario', '')}."


@app.callback(
    Output("traffic_anim", "figure"),
    Output("status", "children", allow_duplicate=True),
    Output("tabs", "value", allow_duplicate=True),
    Input("anim_btn", "n_clicks"),
    State("paths", "data"), State("opt_store", "data"),
    State("topo", "value"), State("grid_number", "value"), State("lanes", "value"),
    State("grid_length", "value"), State("period", "value"), State("end", "value"),
    prevent_initial_call=True,
)
def on_animate(_n, paths, opt_store, topo, grid_number, lanes, grid_length,
               period, end):
    if not paths:
        return no_update, "Build a network first, then animate.", no_update

    cfg = _build_cfg(topo, grid_number, lanes, grid_length, period, end, 1, 1)
    sig = cfg["signals"]
    spec = read_tls_spec(paths["net"], paths["routes"],
                         min_green=sig["min_green"], max_green=sig["max_green"])
    if opt_store and opt_store.get("genome"):
        genome, label = opt_store["genome"], "optimized plan"
    else:
        genome, label = spec.baseline_genome(), "baseline (fixed-time) plan"

    horizon = min(int(_v(end, 600)), 300)
    frames = collect_frames(spec, genome, paths["net"], paths["routes"],
                            end=horizon, seed=cfg["simulation"]["seed"])
    fig = animation_figure(frames, paths["net"], title=f"Traffic — {label}")
    return fig, f"Animation ready: {label}, {len(frames)} frames.", "animation"


@app.callback(
    Output("heatmap_fig", "figure"),
    Output("status", "children", allow_duplicate=True),
    Output("tabs", "value", allow_duplicate=True),
    Input("heat_btn", "n_clicks"),
    State("paths", "data"), State("opt_store", "data"),
    State("topo", "value"), State("grid_number", "value"), State("lanes", "value"),
    State("grid_length", "value"), State("period", "value"), State("end", "value"),
    prevent_initial_call=True,
)
def on_heatmap(_n, paths, opt_store, topo, grid_number, lanes, grid_length,
               period, end):
    if not paths:
        return no_update, "Build a network first, then show the heatmap.", no_update

    cfg = _build_cfg(topo, grid_number, lanes, grid_length, period, end, 1, 1)
    sig = cfg["signals"]
    spec = read_tls_spec(paths["net"], paths["routes"],
                         min_green=sig["min_green"], max_green=sig["max_green"])
    horizon = min(int(_v(end, 600)), 300)

    base = collect_edge_congestion(spec, spec.baseline_genome(), paths["net"],
                                   paths["routes"], end=horizon,
                                   seed=cfg["simulation"]["seed"])
    optimized = None
    if opt_store and opt_store.get("genome"):
        optimized = collect_edge_congestion(spec, opt_store["genome"], paths["net"],
                                            paths["routes"], end=horizon,
                                            seed=cfg["simulation"]["seed"])
    fig = congestion_figure(paths["net"], base, optimized)
    note = "baseline vs optimized" if optimized else "baseline (run optimization for after)"
    return fig, f"Congestion heatmap ready: {note}.", "heatmap"


if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
