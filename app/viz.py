"""Plotly figures for the dashboard: network map, convergence, before/after.

Network geometry is read straight from the generated ``.net.xml`` via sumolib, so
the dashboard always reflects the real SUMO network the optimizer scored.
"""
from __future__ import annotations

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sumolib

_BG = "rgba(0,0,0,0)"
_HEAT = [[0.0, "#2ecc71"], [0.5, "#f1c40f"], [1.0, "#e74c3c"]]


def placeholder_figure(text: str) -> go.Figure:
    """An empty figure carrying a hint, so the dashboard never shows a blank box."""
    fig = go.Figure()
    fig.add_annotation(text=text, x=0.5, y=0.5, xref="paper", yref="paper",
                       showarrow=False, font=dict(size=15, color="#888"))
    fig.update_layout(paper_bgcolor=_BG, plot_bgcolor=_BG,
                      margin=dict(l=10, r=10, t=10, b=10),
                      xaxis=dict(visible=False), yaxis=dict(visible=False))
    return fig


def network_figure(net_path: str, title: str = "Road network") -> go.Figure:
    """Draw edges as lines and signalized junctions as markers."""
    net = sumolib.net.readNet(net_path)

    edge_x: list[float | None] = []
    edge_y: list[float | None] = []
    for edge in net.getEdges():
        shape = edge.getShape()
        for (x, y) in shape:
            edge_x.append(x)
            edge_y.append(y)
        edge_x.append(None)
        edge_y.append(None)

    tls_ids = {t.getID() for t in net.getTrafficLights()}
    node_x, node_y, node_text = [], [], []
    for node in net.getNodes():
        x, y = node.getCoord()
        node_x.append(x)
        node_y.append(y)
        node_text.append(node.getID())

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=edge_x, y=edge_y, mode="lines",
        line=dict(color="#7f8c9a", width=2), hoverinfo="skip", name="roads"))
    fig.add_trace(go.Scatter(
        x=node_x, y=node_y, mode="markers", text=node_text,
        marker=dict(size=12, color="#e74c3c", symbol="square",
                    line=dict(color="#c0392b", width=1)),
        hovertemplate="junction %{text}<extra></extra>",
        name="traffic lights"))
    fig.update_layout(
        title=title, showlegend=False, paper_bgcolor=_BG, plot_bgcolor=_BG,
        margin=dict(l=10, r=10, t=40, b=10),
        xaxis=dict(visible=False, scaleanchor="y", scaleratio=1),
        yaxis=dict(visible=False))
    return fig


def _edge_lines(net):
    edge_x: list[float | None] = []
    edge_y: list[float | None] = []
    for edge in net.getEdges():
        for (x, y) in edge.getShape():
            edge_x.append(x)
            edge_y.append(y)
        edge_x.append(None)
        edge_y.append(None)
    return edge_x, edge_y


_SPEED_SCALE = [[0.0, "#e74c3c"], [0.5, "#f39c12"], [1.0, "#27ae60"]]


def _vehicle_trace(frame: dict) -> go.Scatter:
    return go.Scatter(
        x=frame["x"], y=frame["y"], mode="markers",
        marker=dict(size=8, color=frame["speed"], colorscale=_SPEED_SCALE,
                    cmin=0, cmax=13.9, line=dict(width=0)),
        hoverinfo="skip", name="vehicles")


def animation_figure(frames: list[dict], net_path: str,
                     title: str = "Traffic simulation") -> go.Figure:
    """Animated map: roads as a static backdrop, vehicles colored by speed.

    Red = stopped, green = free-flow. Includes Play/Pause and a time slider.
    """
    net = sumolib.net.readNet(net_path)
    edge_x, edge_y = _edge_lines(net)
    empty = {"x": [], "y": [], "speed": []}
    first = frames[0] if frames else empty

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=edge_x, y=edge_y, mode="lines",
                             line=dict(color="#7f8c9a", width=2), hoverinfo="skip"))
    fig.add_trace(_vehicle_trace(first))

    fig.frames = [go.Frame(data=[_vehicle_trace(f)], traces=[1], name=str(i))
                  for i, f in enumerate(frames)]

    play = dict(label="▶ Play", method="animate",
                args=[None, {"frame": {"duration": 120, "redraw": True},
                             "fromcurrent": True, "transition": {"duration": 0}}])
    pause = dict(label="⏸ Pause", method="animate",
                 args=[[None], {"frame": {"duration": 0, "redraw": False},
                                "mode": "immediate"}])
    slider = dict(active=0, x=0.12, len=0.85, y=0,
                  currentvalue=dict(prefix="t = ", suffix=" s"),
                  steps=[dict(method="animate", label=f"{f['t']:.0f}",
                              args=[[str(i)], {"frame": {"duration": 0, "redraw": True},
                                               "mode": "immediate"}])
                         for i, f in enumerate(frames)])

    fig.update_layout(
        title=title, showlegend=False, paper_bgcolor=_BG, plot_bgcolor=_BG,
        margin=dict(l=10, r=10, t=40, b=10),
        xaxis=dict(visible=False, scaleanchor="y", scaleratio=1),
        yaxis=dict(visible=False),
        updatemenus=[dict(type="buttons", showactive=False, direction="left",
                          x=0.12, y=1.02, xanchor="left", yanchor="bottom",
                          buttons=[play, pause])],
        sliders=[slider] if frames else [])
    return fig


def _edge_points(net, values: dict[str, float]):
    """Midpoint of each edge + its congestion value, for the heatmap markers."""
    xs, ys, vals, txt = [], [], [], []
    for edge in net.getEdges():
        shape = edge.getShape()
        if not shape:
            continue
        mx, my = shape[len(shape) // 2]
        xs.append(mx)
        ys.append(my)
        vals.append(values.get(edge.getID(), 0.0))
        txt.append(edge.getID())
    return xs, ys, vals, txt


def congestion_figure(net_path: str, baseline_vals: dict[str, float],
                      optimized_vals: dict[str, float] | None = None) -> go.Figure:
    """Before/after congestion heatmap: hot = many halting vehicles on that street."""
    net = sumolib.net.readNet(net_path)
    edge_x, edge_y = _edge_lines(net)

    panels = [("Baseline (fixed-time)", baseline_vals)]
    if optimized_vals is not None:
        panels.append(("Optimized (GA)", optimized_vals))
    cmax = max((v for _, vals in panels for v in vals.values()), default=1.0) or 1.0

    fig = make_subplots(rows=1, cols=len(panels),
                        subplot_titles=[t for t, _ in panels],
                        horizontal_spacing=0.04)
    for i, (_, vals) in enumerate(panels, start=1):
        fig.add_trace(go.Scatter(x=edge_x, y=edge_y, mode="lines",
                                 line=dict(color="#d0d5da", width=1.5),
                                 hoverinfo="skip"), row=1, col=i)
        xs, ys, cv, txt = _edge_points(net, vals)
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="markers", text=txt,
            marker=dict(size=9, color=cv, colorscale=_HEAT, cmin=0, cmax=cmax,
                        showscale=(i == len(panels)),
                        colorbar=dict(title="halting<br>veh")),
            hovertemplate="%{text}: %{marker.color:.2f}<extra></extra>"),
            row=1, col=i)

    fig.update_layout(showlegend=False, paper_bgcolor=_BG, plot_bgcolor=_BG,
                      margin=dict(l=10, r=10, t=40, b=10),
                      title="Congestion heatmap — green = clear, red = queued")
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    for i in range(1, len(panels) + 1):
        fig.update_xaxes(scaleanchor=f"y{'' if i == 1 else i}", scaleratio=1,
                         row=1, col=i)
    return fig


def convergence_figure(convergence: list[float], baseline: float | None = None) -> go.Figure:
    """Best fitness per generation, with the baseline as a reference line."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        y=convergence, x=list(range(len(convergence))), mode="lines+markers",
        line=dict(color="#27ae60", width=3), name="best (GA)"))
    if baseline is not None:
        fig.add_hline(y=baseline, line=dict(color="#e74c3c", dash="dash"),
                      annotation_text="baseline (fixed-time)",
                      annotation_position="top right")
    fig.update_layout(
        title="GA convergence", paper_bgcolor=_BG, plot_bgcolor=_BG,
        margin=dict(l=50, r=10, t=40, b=40),
        xaxis_title="generation", yaxis_title="total delay [veh·s]")
    return fig


def comparison_figure(results: dict[str, float]) -> go.Figure:
    """Bar chart comparing total delay across strategies (baseline/manual/optimized)."""
    labels = list(results.keys())
    values = list(results.values())
    colors = {"baseline": "#e74c3c", "manual": "#f39c12", "optimized": "#27ae60"}
    bar_colors = [colors.get(k, "#3498db") for k in labels]
    fig = go.Figure(go.Bar(x=labels, y=values, marker_color=bar_colors,
                           text=[f"{v:.0f}" for v in values], textposition="auto"))
    fig.update_layout(
        title="Total delay: lower is better", paper_bgcolor=_BG, plot_bgcolor=_BG,
        margin=dict(l=50, r=10, t=40, b=40),
        yaxis_title="total delay [veh·s]")
    return fig
