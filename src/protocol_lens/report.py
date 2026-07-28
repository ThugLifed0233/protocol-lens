"""Generate a polished, local-only HTML report from normalized Apple Health data."""

from __future__ import annotations

import html
from pathlib import Path

import duckdb
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

from .analysis import correlations, daily_metrics, workout_comparison
from .catalog import BY_KEY


def generate_report(connection: duckdb.DuckDBPyConnection, output: Path) -> None:
    frame = daily_metrics(connection)
    if frame.empty:
        raise ValueError("No supported Apple Health records were found")

    output.parent.mkdir(parents=True, exist_ok=True)
    plots = [
        _timeline(frame),
        _workout_overlay(frame),
        _correlation_heatmap(frame),
    ]
    cards = _summary_cards(frame)
    relationships = _relationship_rows(frame)
    date_min = frame.index.min().date().isoformat()
    date_max = frame.index.max().date().isoformat()

    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Protocol Lens — Apple Health Report</title>
  <style>{_css()}</style>
</head>
<body>
  <main>
    <header>
      <div class="eyebrow">PROTOCOL LENS · APPLE HEALTH</div>
      <h1>Your health history,<br><span>in one lens.</span></h1>
      <p class="lede">A local report built only from the Apple Health data you imported.
      Trends are descriptive; relationships are not medical conclusions.</p>
      <div class="range">{date_min} → {date_max}</div>
    </header>
    <section class="cards">{cards}</section>
    <section class="panel">
      <div class="panel-copy"><span>01</span><h2>Long view</h2>
      <p>Daily signals retain gaps instead of inventing continuity.</p></div>
      {plots[0]}
    </section>
    <section class="panel">
      <div class="panel-copy"><span>02</span><h2>Workout context</h2>
      <p>Apple workouts are overlaid against recovery and activity data.</p></div>
      {plots[1]}
    </section>
    <section class="panel">
      <div class="panel-copy"><span>03</span><h2>Within-Apple relationships</h2>
      <p>Only metric pairs with at least seven overlapping days appear.</p></div>
      {plots[2]}
      <div class="relationships">{relationships}</div>
    </section>
    <footer>Personal by default. Generated locally by Protocol Lens.</footer>
  </main>
</body>
</html>"""
    output.write_text(document)


def _timeline(frame: pd.DataFrame) -> str:
    figure = go.Figure()
    preferred = ["resting_heart_rate", "hrv_sdnn", "sleep_hours"]
    for metric in preferred:
        if metric not in frame.columns:
            continue
        definition = BY_KEY.get(metric)
        figure.add_trace(
            go.Scatter(
                x=frame.index,
                y=frame[metric],
                name=definition.label if definition else "Sleep",
                mode="lines",
                connectgaps=False,
                line={"width": 2.4, "color": definition.color if definition else "#5e5ce6"},
            )
        )
    return _plot(figure, 430)


def _workout_overlay(frame: pd.DataFrame) -> str:
    figure = go.Figure()
    if "steps" in frame:
        figure.add_trace(
            go.Bar(
                x=frame.index,
                y=frame["steps"],
                name="Steps",
                marker_color="rgba(48, 209, 88, .35)",
            )
        )
    if "resting_heart_rate" in frame:
        figure.add_trace(
            go.Scatter(
                x=frame.index,
                y=frame["resting_heart_rate"],
                name="Resting HR",
                yaxis="y2",
                mode="lines",
                line={"color": "#ff453a", "width": 2.2},
                connectgaps=False,
            )
        )
    workout_days = frame[frame.get("workout_count", pd.Series(index=frame.index)).fillna(0) > 0]
    if not workout_days.empty:
        anchor = (
            workout_days["resting_heart_rate"]
            if "resting_heart_rate" in workout_days
            else pd.Series(0, index=workout_days.index)
        )
        figure.add_trace(
            go.Scatter(
                x=workout_days.index,
                y=anchor,
                name="Workout",
                yaxis="y2",
                mode="markers",
                marker={"symbol": "diamond", "size": 9, "color": "#0a84ff"},
            )
        )
    figure.update_layout(
        yaxis={"title": "Steps"},
        yaxis2={"title": "Resting HR", "overlaying": "y", "side": "right"},
        barmode="overlay",
    )
    return _plot(figure, 430)


def _correlation_heatmap(frame: pd.DataFrame) -> str:
    available = [
        metric
        for metric in [
            "resting_heart_rate",
            "hrv_sdnn",
            "sleep_hours",
            "steps",
            "active_energy",
            "workout_minutes",
        ]
        if metric in frame.columns
    ]
    available = [metric for metric in available if frame[metric].dropna().nunique() > 1]
    correlation = frame[available].corr(min_periods=7)
    figure = go.Figure(
        data=go.Heatmap(
            z=correlation.values,
            x=[_label(metric) for metric in correlation.columns],
            y=[_label(metric) for metric in correlation.index],
            zmin=-1,
            zmax=1,
            colorscale=[
                [0, "#0a84ff"],
                [0.5, "#1c1c1e"],
                [1, "#ff453a"],
            ],
            colorbar={"title": "r"},
            hovertemplate="%{y} × %{x}<br>r = %{z:.2f}<extra></extra>",
        )
    )
    return _plot(figure, 480)


def _summary_cards(frame: pd.DataFrame) -> str:
    definitions = [
        ("resting_heart_rate", "bpm", "RESTING HR"),
        ("hrv_sdnn", "ms", "HRV"),
        ("sleep_hours", "h", "SLEEP"),
        ("steps", "", "STEPS"),
    ]
    cards = []
    for metric, unit, title in definitions:
        if metric not in frame or frame[metric].dropna().empty:
            continue
        latest = frame[metric].dropna().iloc[-1]
        value = f"{latest:,.0f}" if metric == "steps" else f"{latest:.1f}"
        cards.append(
            f'<article class="card"><div>{title}</div><strong>{value}</strong>'
            f'<span>{unit} · latest available</span></article>'
        )
    return "".join(cards)


def _relationship_rows(frame: pd.DataFrame) -> str:
    rows = []
    for result in correlations(frame)[:5]:
        rows.append(
            "<div class='relationship'>"
            f"<b>{html.escape(_label(result.left))} × {html.escape(_label(result.right))}</b>"
            f"<span>r = {result.coefficient:+.2f} · {result.observations} days</span>"
            "</div>"
        )
    comparison = workout_comparison(frame, "resting_heart_rate")
    if comparison:
        workout, rest, workout_n, rest_n = comparison
        rows.insert(
            0,
            "<div class='relationship feature'>"
            "<b>Workout days × resting heart rate</b>"
            f"<span>{workout:.1f} bpm on {workout_n} workout days · "
            f"{rest:.1f} bpm on {rest_n} other days</span></div>",
        )
    return "".join(rows) or "<p>Not enough overlapping data yet.</p>"


def _plot(figure: go.Figure, height: int) -> str:
    figure.update_layout(
        height=height,
        margin={"l": 35, "r": 35, "t": 25, "b": 35},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "-apple-system, BlinkMacSystemFont, Inter, sans-serif", "color": "#a1a1a6"},
        legend={"orientation": "h", "y": 1.08},
        hovermode="x unified",
        xaxis={"gridcolor": "rgba(255,255,255,.06)", "zeroline": False},
        yaxis={"gridcolor": "rgba(255,255,255,.06)", "zeroline": False},
    )
    return pio.to_html(
        figure,
        include_plotlyjs="cdn",
        full_html=False,
        config={"displayModeBar": False, "responsive": True},
    )


def _label(metric: str) -> str:
    if metric == "sleep_hours":
        return "Sleep"
    if metric == "workout_minutes":
        return "Workout minutes"
    if metric == "workout_count":
        return "Workout count"
    return BY_KEY[metric].label if metric in BY_KEY else metric.replace("_", " ").title()


def _css() -> str:
    return """
:root{color-scheme:dark;--bg:#050506;--panel:#101012;--hair:#2c2c2e;--muted:#98989d}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:#f5f5f7;font-family:-apple-system,
BlinkMacSystemFont,"SF Pro Display",Inter,sans-serif}main{width:min(1180px,calc(100% - 32px));
margin:auto;padding:72px 0}header{padding:54px 4px 68px;position:relative}.eyebrow{color:#30d158;
font-size:12px;font-weight:700;letter-spacing:.16em}h1{font-size:clamp(54px,8vw,104px);
line-height:.92;letter-spacing:-.065em;margin:26px 0 28px;max-width:950px}h1 span{color:#73737a}
.lede{color:var(--muted);font-size:20px;line-height:1.5;max-width:670px}.range{position:absolute;
right:5px;top:60px;color:#636366;font-variant-numeric:tabular-nums}.cards{display:grid;
grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:58px}.card{background:linear-gradient(145deg,
#171719,#0c0c0e);border:1px solid var(--hair);border-radius:26px;padding:24px;min-height:170px}
.card div{color:#77777d;font-size:11px;font-weight:700;letter-spacing:.12em}.card strong{
display:block;font-size:46px;letter-spacing:-.05em;margin-top:34px}.card span{color:#77777d;font-size:12px}
.panel{background:linear-gradient(180deg,#111113,#09090b);border:1px solid var(--hair);
border-radius:34px;margin:18px 0;padding:30px 30px 22px;overflow:hidden}.panel-copy{display:grid;
grid-template-columns:42px 1fr;align-items:start}.panel-copy>span{color:#4c4c50;font-size:12px;
padding-top:8px}.panel-copy h2{font-size:28px;letter-spacing:-.03em;margin:0}.panel-copy p{
grid-column:2;color:#77777d;margin:8px 0 22px}.relationships{display:grid;
grid-template-columns:repeat(2,1fr);gap:10px;margin:8px 6px}.relationship{display:flex;
justify-content:space-between;gap:18px;border-top:1px solid var(--hair);padding:16px 4px;
font-size:13px}.relationship span{color:#77777d;text-align:right}.relationship.feature{grid-column:1/-1;
color:#64d2ff}footer{color:#48484a;text-align:center;padding:52px 0 0;font-size:12px}
@media(max-width:760px){main{padding-top:18px}.range{position:static;margin-top:24px}.cards{
grid-template-columns:repeat(2,1fr)}.panel{padding:22px 10px}.panel-copy{padding:0 12px}
.relationships{grid-template-columns:1fr}.relationship{display:block}.relationship span{
display:block;text-align:left;margin-top:6px}}"""
