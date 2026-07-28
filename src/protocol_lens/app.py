"""Local Protocol Lens dashboard."""

from __future__ import annotations

import html
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile

import duckdb
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from plotly.subplots import make_subplots

from protocol_lens import __version__
from protocol_lens.analysis import (
    correlations,
    daily_metrics,
    metric_window_summary,
    workout_comparison,
)
from protocol_lens.apple_health import iter_export
from protocol_lens.catalog import BY_KEY
from protocol_lens.database import connect, ingest_records
from protocol_lens.experiments import (
    add_compound_period,
    analyze_compound_periods,
    import_compound_periods,
    list_compound_periods,
    list_intervention_profiles,
    public_snapshot_csv,
    public_snapshot_json,
    save_intervention_profile,
)
from protocol_lens.sample import build_sample_database
from protocol_lens.spreadsheet import (
    canonical_metric,
    fetch_google_sheet,
    metric_label,
    read_spreadsheet,
    spreadsheet_records,
)
from protocol_lens.workouts import public_workout_snapshot

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "processed"
REAL_DB = Path(os.environ.get("PROTOCOL_LENS_DB", DATA_DIR / "protocol-lens.duckdb"))
SAMPLE_DB = DATA_DIR / "sample.duckdb"
TEMPLATE = "date,metric,value,unit\n2026-07-28,weight,101,kg\n2026-07-28,protein,142,g\n"
INTERVENTION_TEMPLATE = (
    "intervention,category,start_date,end_date,dose_note,purpose,confidence,visibility,notes\n"
    "Example supplement,supplement,2026-07-01,2026-07-14,,,confirmed,personal_only,\n"
)
METRIC_UNITS = {
    "resting_heart_rate": "bpm",
    "walking_heart_rate": "bpm",
    "hrv_sdnn": "ms",
    "sleep_hours": "hours",
    "steps": "steps/day",
    "active_energy": "kcal/day",
    "walking_running_distance": "km/day",
    "body_mass": "kg",
    "vo2_max": "mL/kg/min",
    "workout_minutes": "min/day",
    "workout_count": "sessions/day",
}

st.set_page_config(
    page_title="Protocol Lens",
    page_icon="◉",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def main() -> None:
    _style()
    real_connection = connect(REAL_DB)
    has_real_data = _has_data(real_connection)
    display_connection = real_connection
    demo = False

    if not has_real_data:
        if not SAMPLE_DB.exists():
            build_sample_database(SAMPLE_DB)
        display_connection = connect(SAMPLE_DB)
        demo = True

    try:
        _header(demo)
        if not has_real_data or st.session_state.get("show_import", False):
            _intake(real_connection, expanded=not has_real_data)
        _dashboard(display_connection, real_connection, demo)
    finally:
        if display_connection is not real_connection:
            display_connection.close()
        real_connection.close()


def _header(demo: bool) -> None:
    left, right = st.columns([5, 1])
    with left:
        st.markdown('<div class="wordmark"><i></i> PROTOCOL LENS</div>', unsafe_allow_html=True)
        st.markdown(
            '<h1>Your health history,<br><span>in one lens.</span></h1>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<p class="lede">Import once. Explore trends, workouts, and relationships '
            "without sending your health history to a cloud dashboard.</p>",
            unsafe_allow_html=True,
        )
    with right:
        st.markdown(
            '<div class="local-pill">● Personal · On this Mac</div>',
            unsafe_allow_html=True,
        )
        if st.button("＋ Add data", width="stretch"):
            st.session_state["show_import"] = not st.session_state.get("show_import", False)
            st.rerun()
    if demo:
        st.markdown(
            '<div class="demo-banner"><b>Synthetic preview</b> — add your data above to '
            "replace this demonstration instantly.</div>",
            unsafe_allow_html=True,
        )


def _intake(connection: duckdb.DuckDBPyConnection, expanded: bool) -> None:
    with st.container(border=True):
        st.markdown('<div class="section-kicker">ADD DATA</div>', unsafe_allow_html=True)
        st.subheader("What would you like to explore?")
        st.caption(
            "Apple Health and uploaded files are processed on this Mac. "
            "A Google Sheet is downloaded only when you provide its link."
        )
        apple_tab, file_tab, sheet_tab = st.tabs(
            ["Apple Health", "Excel or CSV", "Google Sheets link"]
        )

        with apple_tab:
            st.write("Drop in the complete ZIP exported by the Health app, or `export.xml`.")
            apple_file = st.file_uploader(
                "Choose Apple Health data",
                type=["zip", "xml"],
                key="apple_upload",
                label_visibility="collapsed",
            )
            if apple_file and st.button("Import Apple Health", type="primary"):
                _import_apple(connection, apple_file.name, apple_file.getvalue())

        with file_tab:
            st.write(
                "Use long format (`date, metric, value, unit`) or a date column beside "
                "numeric metric columns."
            )
            st.download_button(
                "Download sheet template",
                TEMPLATE,
                "protocol-lens-template.csv",
                "text/csv",
            )
            sheet_file = st.file_uploader(
                "Choose Excel or CSV",
                type=["csv", "xlsx", "xlsm"],
                key="sheet_upload",
                label_visibility="collapsed",
            )
            if sheet_file and st.button("Import spreadsheet", type="primary"):
                _import_sheet(
                    connection,
                    sheet_file.name,
                    sheet_file.getvalue(),
                )

        with sheet_tab:
            st.write(
                "Paste a viewable Google Sheets link. Keep the sheet read-only; "
                "Protocol Lens never writes back to it."
            )
            link = st.text_input(
                "Google Sheets link",
                placeholder="https://docs.google.com/spreadsheets/d/…",
                label_visibility="collapsed",
            )
            if link and st.button("Connect sheet", type="primary"):
                try:
                    with st.spinner("Downloading the sheet…"):
                        content, filename = fetch_google_sheet(link)
                    _import_sheet(connection, filename, content)
                except (ValueError, requests.RequestException) as error:
                    st.error(str(error))

        if not expanded and st.button("Close"):
            st.session_state["show_import"] = False
            st.rerun()


def _import_apple(
    connection: duckdb.DuckDBPyConnection,
    filename: str,
    content: bytes,
) -> None:
    suffix = Path(filename).suffix
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as stream:
            stream.write(content)
            temporary = Path(stream.name)
        with st.spinner("Reading your Apple Health history…"):
            seen, inserted = ingest_records(
                connection,
                iter_export(temporary),
                temporary,
                __version__,
                display_filename=filename,
            )
        message = (
            f"Imported {inserted:,} supported records."
            if inserted
            else f"This export is already present ({seen:,} records)."
        )
        st.success(message)
        st.session_state["show_import"] = False
        st.rerun()
    except (BadZipFile, ParseError, ValueError, OSError, duckdb.Error) as error:
        st.error(f"Apple Health import could not finish: {error}")
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def _import_sheet(
    connection: duckdb.DuckDBPyConnection,
    filename: str,
    content: bytes,
) -> None:
    temporary: Path | None = None
    try:
        frame = read_spreadsheet(content, filename)
        records = spreadsheet_records(frame, filename)
        suffix = Path(filename).suffix or ".xlsx"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as stream:
            stream.write(content)
            temporary = Path(stream.name)
        _, inserted = ingest_records(
            connection,
            records,
            temporary,
            f"sheet-{__version__}",
            display_filename=filename,
        )
        st.success(f"Imported {inserted:,} sheet measurements.")
        st.session_state["show_import"] = False
        st.rerun()
    except (ValueError, OSError, duckdb.Error) as error:
        st.error(f"Spreadsheet import could not finish: {error}")
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def _dashboard(
    connection: duckdb.DuckDBPyConnection,
    personal_connection: duckdb.DuckDBPyConnection,
    demo: bool,
) -> None:
    frame = daily_metrics(connection)
    if frame.empty:
        st.info("Add data to begin.")
        return

    st.markdown('<div class="section-kicker space-top">YOUR TIMELINE</div>', unsafe_allow_html=True)
    st.subheader("See the signal. Change the scale.")
    available = [column for column in frame.columns if frame[column].notna().any()]
    default = [
        metric
        for metric in ["resting_heart_rate", "hrv_sdnn", "sleep_hours"]
        if metric in available
    ][:3]
    selected = st.multiselect(
        "Metrics",
        available,
        default=default or available[:2],
        format_func=metric_label,
        max_selections=3,
        label_visibility="collapsed",
    )

    range_start, range_end = _date_window_controls(
        frame,
        key="main_timeline",
        default="1Y",
    )
    visible_frame = frame.loc[range_start:range_end]

    if selected:
        with st.container(border=True):
            st.markdown(
                '<div class="chart-heading"><small>VISIBLE WINDOW</small>'
                f"<strong>{range_start:%d %b %Y} — {range_end:%d %b %Y}</strong>"
                "<span>Drag to inspect · scroll to zoom</span></div>",
                unsafe_allow_html=True,
            )
            st.plotly_chart(
                _timeline_figure(visible_frame, selected),
                width="stretch",
                config={"displayModeBar": False, "scrollZoom": True},
            )
        _metric_cards(frame, selected, range_start, range_end)
    else:
        st.caption("Choose at least one metric.")

    personal_lab_tab, relationship_tab, workouts_tab, sources_tab = st.tabs(
        ["Personal Lab", "Relationships", "Workouts", "Sources"]
    )
    with personal_lab_tab:
        _compound_view(personal_connection)
    with relationship_tab:
        _relationship_view(visible_frame)

    with workouts_tab:
        _workout_view(connection, visible_frame, range_start, range_end)

    with sources_tab:
        _source_view(connection, demo)

    st.markdown(
        '<p class="disclaimer">Descriptive personal analytics—not diagnosis or medical advice. '
        "A relationship does not establish causation.</p>",
        unsafe_allow_html=True,
    )


def _metric_cards(
    frame: pd.DataFrame,
    selected: list[str],
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> None:
    days = max((end - start).days + 1, 1)
    visible = frame.loc[start:end]
    workout_series = visible.get("workout_count", pd.Series(dtype=float))
    workout_days = int((workout_series.fillna(0) > 0).sum())
    cards = [
        (
            "VISIBLE WINDOW",
            f"{days:,} days",
            f"{workout_days} workout days",
            "#30D158",
        )
    ]
    for metric in selected:
        summary = metric_window_summary(frame, metric, start, end)
        if summary is None:
            cards.append(
                (
                    metric_label(metric).upper(),
                    "—",
                    "No values in view",
                    _metric_color(metric),
                )
            )
            continue
        detail = f"{summary.observations} days · {summary.coverage * 100:.0f}% coverage"
        if summary.change_percent is not None and summary.coverage >= 0.35:
            detail = f"{_format_change(summary.change_percent)} vs prior window"
        unit = _metric_unit(metric)
        cards.append(
            (
                metric_label(metric).upper(),
                _format_metric_value(summary.mean, metric),
                f"{unit} · {detail}" if unit else detail,
                _metric_color(metric),
            )
        )

    columns = st.columns(len(cards))
    for column, (label, value, detail, color) in zip(columns, cards, strict=True):
        with column:
            st.markdown(
                f'<div class="range-card" style="--metric:{html.escape(color)}">'
                f"<small>{html.escape(label)}</small><strong>{html.escape(value)}</strong>"
                f"<span>{html.escape(detail)}</span></div>",
                unsafe_allow_html=True,
            )


def _timeline_figure(frame: pd.DataFrame, selected: list[str]) -> go.Figure:
    has_workouts = bool(
        "workout_count" in frame and (frame["workout_count"].fillna(0) > 0).any()
    )
    metric_rows = len(selected)
    total_rows = metric_rows + (1 if has_workouts else 0)
    titles = [metric_label(metric) for metric in selected]
    if has_workouts:
        titles.append("Apple workouts")
    row_heights = [1.0] * metric_rows + ([0.18] if has_workouts else [])
    figure = make_subplots(
        rows=total_rows,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.065,
        subplot_titles=titles,
        row_heights=row_heights,
    )

    for row, metric in enumerate(selected, start=1):
        values = frame[metric].dropna()
        if values.empty:
            continue
        color = _metric_color(metric)
        trend = _trend_series(values)
        figure.add_trace(
            go.Scatter(
                x=values.index,
                y=values.values,
                name="Daily values",
                mode="lines",
                connectgaps=False,
                line={"color": _rgba(color, 0.18), "width": 1},
                showlegend=row == 1,
                hovertemplate="%{x|%d %b %Y}<br>%{y:.2f}<extra></extra>",
            ),
            row=row,
            col=1,
        )
        figure.add_trace(
            go.Scatter(
                x=trend.index,
                y=trend.values,
                name=_trend_label(values),
                mode="lines",
                connectgaps=False,
                line={"color": color, "width": 2.8, "shape": "spline"},
                showlegend=row == 1,
                hovertemplate="%{x|%d %b %Y}<br>%{y:.2f}<extra></extra>",
            ),
            row=row,
            col=1,
        )
        figure.update_yaxes(
            title_text=_metric_unit(metric),
            row=row,
            col=1,
            title_font={"size": 10, "color": "#636366"},
        )

    if has_workouts:
        workout_days = frame[frame["workout_count"].fillna(0) > 0]
        figure.add_trace(
            go.Scatter(
                x=workout_days.index,
                y=[0] * len(workout_days),
                name="Workout day",
                mode="markers",
                marker={
                    "symbol": "square",
                    "size": 5,
                    "color": "#0A84FF",
                    "opacity": 0.62,
                },
                showlegend=False,
                hovertemplate="%{x|%d %b %Y}<br>Workout day<extra></extra>",
            ),
            row=total_rows,
            col=1,
        )
        figure.update_yaxes(visible=False, row=total_rows, col=1, range=[-1, 1])

    figure.update_layout(dragmode="zoom", showlegend=True)
    for annotation in figure.layout.annotations:
        annotation.update(font={"size": 12, "color": "#A1A1A6"}, x=0, xanchor="left")
    height = 170 * metric_rows + (65 if has_workouts else 0) + 80
    return _chart_layout(figure, max(height, 470))


def _relationship_view(frame: pd.DataFrame) -> None:
    results = correlations(frame)
    if not results:
        st.info("At least seven overlapping days with changing values are needed.")
        return
    metric_order = sorted({item.left for item in results} | {item.right for item in results})
    matrix = frame[metric_order].corr(min_periods=7)
    figure = go.Figure(
        go.Heatmap(
            z=matrix.values,
            x=[metric_label(metric) for metric in matrix.columns],
            y=[metric_label(metric) for metric in matrix.index],
            zmin=-1,
            zmax=1,
            colorscale=[[0, "#0a84ff"], [0.5, "#18181b"], [1, "#ff453a"]],
            hovertemplate="%{y} × %{x}<br>r = %{z:.2f}<extra></extra>",
        )
    )
    st.plotly_chart(
        _chart_layout(figure, 460),
        width="stretch",
        config={"displayModeBar": False},
    )
    strongest = results[0]
    st.markdown(
        f'<div class="insight"><b>Strongest observed relationship</b><br>'
        f"{metric_label(strongest.left)} × {metric_label(strongest.right)}: "
        f"<strong>r = {strongest.coefficient:+.2f}</strong> across "
        f"{strongest.observations} overlapping days.</div>",
        unsafe_allow_html=True,
    )


def _workout_view(
    connection: duckdb.DuckDBPyConnection,
    frame: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> None:
    snapshot = public_workout_snapshot(connection)
    overview = snapshot["overview"]
    if not overview["workout_count"]:
        st.info("No Apple workouts have been imported yet.")
        return

    st.markdown(
        '<div class="workout-banner"><small>TRAINING HISTORY</small>'
        "<strong>Consistency, volume, and movement across time.</strong>"
        "<span>Only aggregate results leave this Mac; individual sessions stay local.</span>"
        "</div>",
        unsafe_allow_html=True,
    )
    cards = [
        ("RECORDED WORKOUTS", f"{overview['workout_count']:,}", "Apple workout events"),
        (
            "TRAINING TIME",
            _duration_label(float(overview["total_minutes"])),
            "Across the complete record",
        ),
        (
            "ACTIVE WEEKS",
            f"{overview['active_weeks']:,}",
            "Weeks with ≥1 recorded workout",
        ),
        (
            "LONGEST RUN",
            f"{overview['longest_consistency_streak_weeks']} weeks",
            "Consecutive active weeks",
        ),
    ]
    card_columns = st.columns(4)
    for column, (label, value, detail) in zip(card_columns, cards, strict=True):
        with column:
            st.markdown(
                '<div class="workout-card">'
                f"<small>{html.escape(label)}</small><strong>{html.escape(value)}</strong>"
                f"<span>{html.escape(detail)}</span></div>",
                unsafe_allow_html=True,
            )

    monthly = pd.DataFrame(snapshot["monthly"])
    monthly["date"] = pd.to_datetime(monthly["month"])
    visible_monthly = monthly[
        (monthly["date"] >= start.to_period("M").to_timestamp())
        & (monthly["date"] <= end.to_period("M").to_timestamp())
    ]
    if visible_monthly.empty:
        visible_monthly = monthly

    activity_types = pd.DataFrame(snapshot["activity_types"])
    activity_types["display_name"] = activity_types["activity_type"].map(_workout_label)
    history_column, mix_column = st.columns([1.6, 1])
    with history_column:
        st.markdown("#### Training rhythm")
        history_figure = go.Figure()
        history_figure.add_trace(
            go.Bar(
                x=visible_monthly["date"],
                y=visible_monthly["workout_count"],
                name="Workouts",
                marker={
                    "color": visible_monthly["workout_count"],
                    "colorscale": [[0, "#17233a"], [1, "#0A84FF"]],
                    "line": {"width": 0},
                },
                hovertemplate="%{x|%b %Y}<br>%{y:.0f} workouts<extra></extra>",
            )
        )
        history_figure.add_trace(
            go.Scatter(
                x=visible_monthly["date"],
                y=visible_monthly["workout_count"].rolling(3, min_periods=1).mean(),
                name="3-month rhythm",
                mode="lines",
                line={"color": "#64D2FF", "width": 2.5, "shape": "spline"},
                hovertemplate="%{x|%b %Y}<br>%{y:.1f} average<extra></extra>",
            )
        )
        st.plotly_chart(
            _chart_layout(history_figure, 390),
            width="stretch",
            config={"displayModeBar": False, "scrollZoom": True},
        )

    with mix_column:
        st.markdown("#### What the Watch recorded")
        top_types = activity_types.head(8).sort_values("workout_count")
        type_figure = go.Figure(
            go.Bar(
                x=top_types["workout_count"],
                y=top_types["display_name"],
                orientation="h",
                marker={
                    "color": top_types["workout_count"],
                    "colorscale": [[0, "#1c1c34"], [1, "#5E5CE6"]],
                    "line": {"width": 0},
                },
                hovertemplate="%{y}<br>%{x:.0f} workouts<extra></extra>",
            )
        )
        type_figure.update_layout(showlegend=False)
        st.plotly_chart(
            _chart_layout(type_figure, 390),
            width="stretch",
            config={"displayModeBar": False},
        )

    yearly = pd.DataFrame(snapshot["by_year"])
    if not yearly.empty:
        st.markdown("#### Year by year")
        year_columns = st.columns(min(len(yearly), 6))
        for column, row in zip(year_columns, yearly.tail(6).itertuples(), strict=False):
            with column:
                st.markdown(
                    '<div class="year-chip">'
                    f"<small>{int(row.year)}</small><strong>{int(row.workout_count)}</strong>"
                    f"<span>{int(row.active_weeks)} active weeks</span></div>",
                    unsafe_allow_html=True,
                )

    comparison = workout_comparison(frame.loc[start:end], "resting_heart_rate")
    if comparison:
        workout, rest, workout_n, rest_n = comparison
        st.markdown(
            '<div class="workout-insight"><small>APPLE SIGNAL CONTEXT</small>'
            f"<strong>{workout:.1f} vs {rest:.1f} bpm</strong>"
            f"<span>Average resting heart rate on {workout_n} recorded workout days "
            f"and {rest_n} other observed days in the visible window.</span></div>",
            unsafe_allow_html=True,
        )

    workout_frame = connection.execute(
        """
        SELECT start_at, activity_type, duration_minutes, energy_kcal, distance_km
        FROM workouts
        WHERE CAST(start_at AS DATE) BETWEEN ? AND ?
        ORDER BY start_at DESC
        LIMIT 100
        """,
        [start.date(), end.date()],
    ).df()
    if not workout_frame.empty:
        with st.expander("Inspect individual sessions on this Mac"):
            st.dataframe(
                workout_frame.rename(
                    columns={
                        "start_at": "Date",
                        "activity_type": "Workout",
                        "duration_minutes": "Minutes",
                        "energy_kcal": "Energy (kcal)",
                        "distance_km": "Distance (km)",
                    }
                ),
                width="stretch",
                hide_index=True,
            )


def _source_view(connection: duckdb.DuckDBPyConnection, demo: bool) -> None:
    imported = connection.execute(
        """
        SELECT filename, imported_at, record_count
        FROM imports ORDER BY imported_at DESC
        """
    ).df()
    if demo:
        st.info("You are viewing deterministic synthetic data. It is never mixed with real data.")
    st.dataframe(
        imported.rename(
            columns={
                "filename": "Source",
                "imported_at": "Imported",
                "record_count": "Supported records",
            }
        ),
        width="stretch",
        hide_index=True,
    )
    st.caption(f"Local database: {REAL_DB}")


def _compound_view(connection: duckdb.DuckDBPyConnection) -> None:
    st.markdown(
        '<div class="personal-lab-banner"><small>PERSONAL LAB</small>'
        "<strong>Map a routine against your signals.</strong>"
        "<span>Violet marks entries you add yourself; Apple metrics retain their "
        "original colors.</span></div>",
        unsafe_allow_html=True,
    )
    _intervention_explorer(connection)

    st.markdown("#### Build your Personal Lab")
    profile_tab, period_tab = st.tabs(["Describe a supplement", "Record a usage period"])
    with profile_tab:
        _profile_form(connection)
    with period_tab:
        _period_form(connection)


def _intervention_explorer(connection: duckdb.DuckDBPyConnection) -> None:
    profiles = list_intervention_profiles(connection)
    periods = list_compound_periods(connection)
    profile_names = profiles["display_name"].tolist() if not profiles.empty else []
    period_names = periods["display_name"].tolist() if not periods.empty else []
    names = sorted(set(profile_names + period_names), key=str.casefold)
    if not names:
        st.markdown(
            '<div class="personal-empty"><strong>Your supplement pages will live here.</strong>'
            "<span>Add a description and one or more usage periods. Apple outcomes appear "
            "automatically when dates overlap.</span></div>",
            unsafe_allow_html=True,
        )
        return

    selected_name = st.selectbox(
        "Choose a supplement or intervention",
        names,
        key="personal_lab_selection",
    )
    selected_key = canonical_metric(selected_name)
    profile_rows = (
        profiles[profiles["intervention_key"] == selected_key]
        if not profiles.empty
        else pd.DataFrame()
    )
    selected_periods = (
        periods[periods["compound_key"] == selected_key]
        if not periods.empty
        else pd.DataFrame()
    )
    profile = profile_rows.iloc[0] if not profile_rows.empty else None
    color = str(profile["color"]) if profile is not None else "#BF5AF2"

    analysis = analyze_compound_periods(connection)
    selected_analysis = (
        analysis[analysis["compound"].map(canonical_metric) == selected_key]
        if not analysis.empty
        else pd.DataFrame()
    )
    if selected_periods.empty:
        _profile_context(profile, selected_name, color)
        st.caption("Add a usage period to connect this profile with Apple metrics.")
        return

    if selected_analysis.empty:
        _profile_context(profile, selected_name, color)
        st.info("Apple data does not yet overlap these periods.")
        return

    metric_keys = selected_analysis["metric"].drop_duplicates().tolist()
    metric_column, period_column = st.columns([1, 1.25])
    with metric_column:
        chosen_metric = st.selectbox(
            "Apple metric",
            metric_keys,
            format_func=metric_label,
            key=f"metric_{selected_key}",
        )
    with period_column:
        period_options = ["all", *selected_periods["period_id"].tolist()]
        period_choice = st.selectbox(
            "Usage period",
            period_options,
            format_func=lambda value: (
                f"All {len(selected_periods)} recorded periods"
                if value == "all"
                else _period_label(selected_periods, value)
            ),
            key=f"period_{selected_key}",
        )

    focus_periods = (
        selected_periods
        if period_choice == "all"
        else selected_periods[selected_periods["period_id"] == period_choice]
    )
    metric_results = selected_analysis[selected_analysis["metric"] == chosen_metric].copy()
    if period_choice != "all":
        metric_results = metric_results[metric_results["period_id"] == period_choice]

    frame = daily_metrics(connection)
    period_starts = pd.to_datetime(focus_periods["start_date"])
    period_ends = pd.to_datetime(focus_periods["end_date"], errors="coerce")
    focus_start = period_starts.min() - pd.DateOffset(days=14)
    focus_end = (
        period_ends.max()
        if period_ends.notna().any()
        else pd.Timestamp(frame.index.max())
    ) + pd.DateOffset(days=14)
    range_start, range_end = _date_window_controls(
        frame,
        key=f"supplement_{selected_key}",
        default="Periods",
        focus=(focus_start, focus_end),
    )
    visible_frame = frame.loc[range_start:range_end]

    if chosen_metric in visible_frame and visible_frame[chosen_metric].notna().any():
        with st.container(border=True):
            st.markdown(
                '<div class="chart-heading"><small>APPLE SIGNAL × PERSONAL PERIOD</small>'
                f"<strong>{html.escape(metric_label(chosen_metric))}</strong>"
                f"<span>{range_start:%d %b %Y} — {range_end:%d %b %Y}</span></div>",
                unsafe_allow_html=True,
            )
            st.plotly_chart(
                _intervention_metric_figure(
                    visible_frame,
                    chosen_metric,
                    focus_periods,
                    color,
                    selected_name,
                ),
                width="stretch",
                config={"displayModeBar": False, "scrollZoom": True},
            )

    _supplement_outcome_cards(metric_results, chosen_metric, color)
    _profile_context(profile, selected_name, color)
    _period_summary(focus_periods)

    with st.expander("View period-level observations"):
        display_results = metric_results[
            [
                "start_date",
                "end_date",
                "baseline_mean",
                "during_mean",
                "after_mean",
                "relative_change_percent",
                "baseline_days",
                "during_days",
                "analysis_confidence",
            ]
        ].rename(
            columns={
                "start_date": "Period start",
                "end_date": "Period end",
                "baseline_mean": "Before",
                "during_mean": "During",
                "after_mean": "After",
                "relative_change_percent": "Change %",
                "baseline_days": "Before days",
                "during_days": "During days",
                "analysis_confidence": "Confidence",
            }
        )
        st.dataframe(
            display_results,
            width="stretch",
            hide_index=True,
            column_config={
                "Before": st.column_config.NumberColumn(format="%.2f"),
                "During": st.column_config.NumberColumn(format="%.2f"),
                "After": st.column_config.NumberColumn(format="%.2f"),
                "Change %": st.column_config.NumberColumn(format="%.1f%%"),
            },
        )
    st.caption(
        "Observed changes describe these windows only. They do not show that the intervention "
        "caused the metric to change."
    )


def _profile_context(profile: pd.Series | None, selected_name: str, color: str) -> None:
    description = (
        str(profile["description"]).strip()
        if profile is not None and not pd.isna(profile["description"])
        else ""
    )
    expected = (
        str(profile["expected_outcomes"]).strip()
        if profile is not None and not pd.isna(profile["expected_outcomes"])
        else ""
    )
    goal = (
        str(profile["personal_goal"]).strip()
        if profile is not None and not pd.isna(profile["personal_goal"])
        else ""
    )
    description_column, context_column = st.columns([1.35, 1])
    with description_column:
        st.markdown(
            '<div class="profile-card" style="--profile-color:'
            f'{html.escape(color)}"><small>PROFILE</small>'
            f"<h3>{html.escape(selected_name)}</h3>"
            f"<p>{html.escape(description or 'Description not added yet.')}</p></div>",
            unsafe_allow_html=True,
        )
    with context_column:
        st.markdown(
            '<div class="expectation-card"><small>EXPECTED</small>'
            f"<p>{html.escape(expected or 'Not recorded yet.')}</p>"
            "<small>WHY IT WAS TRACKED</small>"
            f"<p>{html.escape(goal or 'Not recorded yet.')}</p></div>",
            unsafe_allow_html=True,
        )


def _supplement_outcome_cards(
    results: pd.DataFrame,
    metric: str,
    color: str,
) -> None:
    if results.empty:
        return
    baseline = _weighted_result(results, "baseline_mean", "baseline_days")
    during = _weighted_result(results, "during_mean", "during_days")
    after = _weighted_result(results, "after_mean", "after_days")
    change = (
        (during - baseline) / abs(baseline) * 100
        if baseline is not None and during is not None and baseline != 0
        else None
    )
    coverage = float(results["coverage"].mean()) * 100
    confidence_counts = results["analysis_confidence"].value_counts()
    confidence = str(confidence_counts.index[0]).title() if not confidence_counts.empty else "—"
    unit = _metric_unit(metric)
    values = [
        ("BEFORE", _format_metric_value(baseline, metric), unit),
        (
            "DURING",
            _format_metric_value(during, metric),
            f"{_format_change(change)} vs before",
        ),
        ("AFTER", _format_metric_value(after, metric), unit),
        ("DATA QUALITY", f"{coverage:.0f}%", f"{confidence} confidence"),
    ]
    columns = st.columns(4)
    for column, (label, value, detail) in zip(columns, values, strict=True):
        with column:
            st.markdown(
                f'<div class="range-card" style="--metric:{html.escape(color)}">'
                f"<small>{html.escape(label)}</small><strong>{html.escape(value)}</strong>"
                f"<span>{html.escape(detail)}</span></div>",
                unsafe_allow_html=True,
            )


def _period_summary(periods: pd.DataFrame) -> None:
    period_count = len(periods)
    earliest = pd.to_datetime(periods["start_date"]).min().date()
    end_values = pd.to_datetime(periods["end_date"], errors="coerce")
    latest = end_values.max().date() if end_values.notna().any() else "ongoing"
    st.markdown(
        '<div class="period-strip">'
        f"<span><b>{period_count}</b> period{'s' if period_count != 1 else ''} shown</span>"
        f"<span>First: <b>{earliest}</b></span><span>Latest end: <b>{latest}</b></span></div>",
        unsafe_allow_html=True,
    )


def _weighted_result(results: pd.DataFrame, value: str, weight: str) -> float | None:
    valid = results[[value, weight]].dropna()
    if valid.empty or float(valid[weight].sum()) <= 0:
        return None
    return float((valid[value] * valid[weight]).sum() / valid[weight].sum())


def _period_label(periods: pd.DataFrame, period_id: str) -> str:
    row = periods.loc[periods["period_id"] == period_id].iloc[0]
    start = pd.Timestamp(row["start_date"]).strftime("%d %b %Y")
    end = (
        "ongoing"
        if pd.isna(row["end_date"])
        else pd.Timestamp(row["end_date"]).strftime("%d %b %Y")
    )
    return f"{start} — {end}"


def _profile_form(connection: duckdb.DuckDBPyConnection) -> None:
    with st.form("intervention_profile_form", clear_on_submit=True):
        name_column, category_column, color_column = st.columns([1.4, 1, 0.7])
        with name_column:
            profile_name = st.text_input(
                "Supplement or intervention",
                placeholder="L-theanine",
            )
        with category_column:
            profile_category = st.selectbox(
                "Category",
                ["supplement", "nootropic", "nutrition", "other"],
                format_func=lambda value: value.title(),
            )
        with color_column:
            profile_color = st.color_picker("Timeline color", "#BF5AF2")
        description = st.text_area(
            "What is it?",
            placeholder="A short neutral description of the supplement.",
        )
        expected = st.text_area(
            "What was expected?",
            placeholder="The outcomes or metrics that were expected to change.",
        )
        personal_goal = st.text_area(
            "Why was it tracked?",
            placeholder="The personal reason for trying or monitoring it.",
        )
        profile_confidence = st.selectbox(
            "Description confidence",
            ["confirmed", "approximate", "unverified"],
        )
        profile_submitted = st.form_submit_button("Save profile", type="primary")
        if profile_submitted:
            try:
                save_intervention_profile(
                    connection,
                    display_name=profile_name,
                    category=profile_category,
                    description=description,
                    expected_outcomes=expected,
                    personal_goal=personal_goal,
                    color=profile_color,
                    confidence=profile_confidence,
                )
                st.success("Profile saved locally.")
                st.rerun()
            except (ValueError, duckdb.Error) as error:
                st.error(str(error))


def _period_form(connection: duckdb.DuckDBPyConnection) -> None:
    st.markdown("#### Record an intervention period")
    st.caption(
        "Add supplements, nootropics, nutrition interventions, or another personal routine. "
        "Analysis compares equal windows before, during, and after."
    )
    with st.expander("Bulk import intervention history"):
        st.caption(
            "Use this for a history reconstructed from notes or chats. Keep uncertain dates "
            "labelled approximate or unverified."
        )
        st.download_button(
            "Download intervention template",
            INTERVENTION_TEMPLATE,
            "protocol-lens-interventions.csv",
            "text/csv",
        )
        intervention_file = st.file_uploader(
            "Choose intervention CSV or Excel",
            type=["csv", "xlsx", "xlsm"],
            key="intervention_upload",
        )
        if intervention_file and st.button("Import intervention history", type="primary"):
            try:
                intervention_frame = read_spreadsheet(
                    intervention_file.getvalue(),
                    intervention_file.name,
                )
                imported = import_compound_periods(connection, intervention_frame)
                st.success(f"Imported {imported} intervention periods locally.")
                st.rerun()
            except (ValueError, OSError, duckdb.Error) as error:
                st.error(str(error))

    today = datetime.now(UTC).astimezone().date()
    with st.form("compound_period_form", clear_on_submit=True):
        name_column, category_column = st.columns(2)
        with name_column:
            display_name = st.text_input(
                "Compound or intervention",
                placeholder="L-theanine",
            )
        with category_column:
            category = st.selectbox(
                "Category",
                [
                    "supplement",
                    "nootropic",
                    "nutrition",
                    "other",
                ],
                format_func=lambda value: value.replace("_", " ").title(),
            )
        start_column, end_column = st.columns(2)
        with start_column:
            start_date = st.date_input("Start date", value=today)
        with end_column:
            ongoing = st.checkbox("Ongoing", value=True)
            end_date = None if ongoing else st.date_input("End date", value=today)
        dose_column, purpose_column = st.columns(2)
        with dose_column:
            dose_note = st.text_input("Dose note (personal, optional)")
        with purpose_column:
            purpose = st.text_input("Purpose (personal, optional)")
        confidence_column, visibility_column = st.columns(2)
        with confidence_column:
            confidence = st.selectbox(
                "Date confidence",
                ["confirmed", "approximate", "unverified"],
            )
        with visibility_column:
            visibility = st.selectbox(
                "Result visibility",
                ["personal_only", "publishable"],
                format_func=lambda value: (
                    "Personal only"
                    if value == "personal_only"
                    else "Publishable summary"
                ),
            )
        notes = st.text_area("Notes (personal, optional)")
        submitted = st.form_submit_button("Save intervention", type="primary")
        if submitted:
            try:
                add_compound_period(
                    connection,
                    display_name=display_name,
                    category=category,
                    start_date=start_date,
                    end_date=end_date,
                    dose_note=dose_note,
                    purpose=purpose,
                    confidence=confidence,
                    visibility=visibility,
                    notes=notes,
                )
                st.success("Intervention period saved locally.")
                st.rerun()
            except (ValueError, duckdb.Error) as error:
                st.error(str(error))

    periods = list_compound_periods(connection)
    if periods.empty:
        st.info("No intervention periods recorded yet.")
        return

    st.markdown("#### Recorded periods")
    st.dataframe(
        periods[
            [
                "display_name",
                "category",
                "start_date",
                "end_date",
                "confidence",
                "visibility",
            ]
        ].rename(
            columns={
                "display_name": "Intervention",
                "category": "Category",
                "start_date": "Start",
                "end_date": "End",
                "confidence": "Date confidence",
                "visibility": "Visibility",
            }
        ),
        width="stretch",
        hide_index=True,
    )

    analysis = analyze_compound_periods(connection)
    if analysis.empty:
        st.caption("Import Apple Health data that overlaps these periods to calculate results.")
        return

    st.markdown("#### Before / during / after")
    selected_period = st.selectbox(
        "Period",
        periods["period_id"].tolist(),
        format_func=lambda period_id: periods.loc[
            periods["period_id"] == period_id, "display_name"
        ].iloc[0],
    )
    selected = analysis[analysis["period_id"] == selected_period].copy()
    st.dataframe(
        selected[
            [
                "metric_label",
                "baseline_mean",
                "during_mean",
                "after_mean",
                "relative_change_percent",
                "baseline_days",
                "during_days",
                "analysis_confidence",
            ]
        ].rename(
            columns={
                "metric_label": "Metric",
                "baseline_mean": "Before",
                "during_mean": "During",
                "after_mean": "After",
                "relative_change_percent": "Change %",
                "baseline_days": "Before days",
                "during_days": "During days",
                "analysis_confidence": "Confidence",
            }
        ),
        width="stretch",
        hide_index=True,
        column_config={
            "Before": st.column_config.NumberColumn(format="%.2f"),
            "During": st.column_config.NumberColumn(format="%.2f"),
            "After": st.column_config.NumberColumn(format="%.2f"),
            "Change %": st.column_config.NumberColumn(format="%.1f%%"),
        },
    )

    snapshot_json = public_snapshot_json(connection)
    snapshot_csv = public_snapshot_csv(connection)
    public_count = len(analysis[analysis["visibility"] == "publishable"])
    st.markdown("#### Public results snapshot")
    st.caption(
        "The export contains summaries only: no exact dates, doses, notes, or raw values. "
        "Review it before committing anything to GitHub."
    )
    if public_count:
        json_column, csv_column = st.columns(2)
        with json_column:
            st.download_button(
                "Download public JSON",
                snapshot_json,
                "protocol-lens-results.json",
                "application/json",
                width="stretch",
            )
        with csv_column:
            st.download_button(
                "Download public CSV",
                snapshot_csv,
                "protocol-lens-results.csv",
                "text/csv",
                width="stretch",
            )
    else:
        st.info(
            "Mark a period as publishable to create a summary export."
        )


def _intervention_metric_figure(
    frame: pd.DataFrame,
    metric: str,
    periods: pd.DataFrame,
    color: str,
    intervention_name: str,
) -> go.Figure:
    values = frame[metric].dropna()
    color_metric = _metric_color(metric)
    trend = _trend_series(values)
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=values.index,
            y=values.values,
            name="Daily",
            mode="lines",
            line={"color": _rgba(color_metric, 0.22), "width": 1},
            hovertemplate="%{x|%d %b %Y}<br>%{y:.2f}<extra></extra>",
            connectgaps=False,
        )
    )
    figure.add_trace(
        go.Scatter(
            x=trend.index,
            y=trend.values,
            name=_trend_label(values),
            mode="lines",
            line={"color": color_metric, "width": 3, "shape": "spline"},
            hovertemplate="%{x|%d %b %Y}<br>%{y:.2f}<extra></extra>",
            connectgaps=False,
        )
    )
    for row in periods.itertuples(index=False):
        period_end = row.end_date if not pd.isna(row.end_date) else values.index.max()
        figure.add_vrect(
            x0=row.start_date,
            x1=period_end,
            fillcolor=color,
            opacity=0.16,
            line_width=1,
            line_color=color,
        )
    figure.update_layout(
        yaxis_title=_metric_unit(metric),
        dragmode="zoom",
        showlegend=True,
    )
    figure.add_annotation(
        text=f"{intervention_name} periods",
        xref="paper",
        yref="paper",
        x=1,
        y=1.12,
        showarrow=False,
        font={"color": color, "size": 11},
    )
    return _chart_layout(figure, 460)


def _date_window_controls(
    frame: pd.DataFrame,
    *,
    key: str,
    default: str,
    focus: tuple[pd.Timestamp, pd.Timestamp] | None = None,
) -> tuple[pd.Timestamp, pd.Timestamp]:
    earliest = pd.Timestamp(frame.index.min()).normalize()
    latest = pd.Timestamp(frame.index.max()).normalize()
    options = ["30D", "90D", "6M", "1Y"]
    if focus is not None:
        options.append("Periods")
    options.extend(["All", "Custom"])
    selection = st.segmented_control(
        "Visible window",
        options,
        default=default if default in options else "1Y",
        key=f"{key}_range",
        label_visibility="collapsed",
    )
    choice = selection or default

    if choice == "All":
        return earliest, latest
    if choice == "Periods" and focus is not None:
        start = max(pd.Timestamp(focus[0]).normalize(), earliest)
        end = min(pd.Timestamp(focus[1]).normalize(), latest)
        return start, end
    if choice == "Custom":
        default_start = max(latest - pd.DateOffset(years=1), earliest)
        custom = st.date_input(
            "Custom dates",
            value=(default_start.date(), latest.date()),
            min_value=earliest.date(),
            max_value=latest.date(),
            key=f"{key}_custom_dates",
        )
        if isinstance(custom, tuple) and len(custom) == 2:
            return pd.Timestamp(custom[0]), pd.Timestamp(custom[1])
        return default_start, latest

    offsets = {
        "30D": pd.DateOffset(days=29),
        "90D": pd.DateOffset(days=89),
        "6M": pd.DateOffset(months=6),
        "1Y": pd.DateOffset(years=1),
    }
    start = latest - offsets[choice]
    return max(pd.Timestamp(start).normalize(), earliest), latest


def _metric_color(metric: str) -> str:
    definition = BY_KEY.get(metric)
    if definition:
        return definition.color
    return {
        "sleep_hours": "#5E5CE6",
        "workout_minutes": "#64D2FF",
        "workout_count": "#0A84FF",
    }.get(metric, "#64D2FF")


def _metric_unit(metric: str) -> str:
    return METRIC_UNITS.get(metric, "")


def _format_metric_value(value: float | None, metric: str) -> str:
    if value is None or pd.isna(value):
        return "—"
    if metric in {"steps", "active_energy", "workout_minutes", "workout_count"}:
        return f"{value:,.0f}"
    return f"{value:,.1f}"


def _format_change(change: float | None) -> str:
    if change is None or pd.isna(change):
        return "No comparison"
    return f"{change:+.1f}%"


def _duration_label(minutes: float) -> str:
    hours = minutes / 60
    if hours >= 1000:
        return f"{hours / 1000:.1f}k hr"
    return f"{hours:,.0f} hr"


def _workout_label(value: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", " ", value).strip()


def _trend_series(values: pd.Series) -> pd.Series:
    span_days = max((values.index.max() - values.index.min()).days, 1)
    if span_days > 3 * 365:
        return values.resample("30D").mean()
    if span_days > 365:
        return values.resample("7D").mean()
    return values.rolling(7, min_periods=2).mean()


def _trend_label(values: pd.Series) -> str:
    span_days = max((values.index.max() - values.index.min()).days, 1)
    if span_days > 3 * 365:
        return "Monthly trend"
    if span_days > 365:
        return "Weekly trend"
    return "7-day trend"


def _rgba(hex_color: str, alpha: float) -> str:
    clean = hex_color.lstrip("#")
    red, green, blue = (int(clean[index : index + 2], 16) for index in (0, 2, 4))
    return f"rgba({red},{green},{blue},{alpha})"


def _has_data(connection: duckdb.DuckDBPyConnection) -> bool:
    counts = connection.execute(
        """
        SELECT
          (SELECT COUNT(*) FROM signals) +
          (SELECT COUNT(*) FROM intervals) +
          (SELECT COUNT(*) FROM workouts)
        """
    ).fetchone()
    return bool(counts and counts[0])


def _chart_layout(figure: go.Figure, height: int) -> go.Figure:
    figure.update_layout(
        height=height,
        margin={"l": 26, "r": 18, "t": 42, "b": 20},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "-apple-system, BlinkMacSystemFont, Inter", "color": "#a1a1a6"},
        legend={"orientation": "h", "y": 1.07, "x": 1, "xanchor": "right"},
        hovermode="x unified",
        hoverlabel={"bgcolor": "#1C1C1E", "bordercolor": "#3A3A3C"},
    )
    figure.update_xaxes(
        gridcolor="rgba(255,255,255,.045)",
        zeroline=False,
        showline=False,
        tickfont={"color": "#636366", "size": 10},
        rangeslider_visible=False,
    )
    figure.update_yaxes(
        gridcolor="rgba(255,255,255,.055)",
        zeroline=False,
        showline=False,
        tickfont={"color": "#636366", "size": 10},
    )
    return figure


def _style() -> None:
    st.markdown(
        """
        <style>
        :root { color-scheme: dark; }
        .stApp { background:
          radial-gradient(circle at 85% -10%, rgba(48,209,88,.08), transparent 28rem),
          radial-gradient(circle at -5% 30%, rgba(10,132,255,.07), transparent 28rem),
          #050506; }
        .block-container { max-width: 1240px; padding-top: 2.7rem; padding-bottom: 5rem; }
        [data-testid="stHeader"] { display:none; }
        h1 { font-size: clamp(3.15rem, 5.2vw, 5rem) !important; line-height: .92 !important;
          letter-spacing: -.06em !important; margin: 1rem 0 .9rem !important; }
        h1 span { color: #6e6e73; }
        h2, h3 { letter-spacing: -.035em !important; }
        .wordmark { color: #30d158; font-size: .72rem; letter-spacing: .16em; font-weight: 700; }
        .wordmark i { display:inline-block; width:8px; height:8px; background:#30d158;
          border-radius:50%; margin-right:8px; box-shadow:0 0 18px #30d158; }
        .lede { color:#98989d; max-width:720px; font-size:1.08rem; line-height:1.5; }
        .local-pill { border:1px solid #2c2c2e; color:#8e8e93; border-radius:999px;
          font-size:.76rem; padding:.62rem .82rem; margin:.15rem 0 1rem; text-align:center; }
        .local-pill::first-letter { color:#30d158; }
        .demo-banner { margin:2rem 0 1rem; padding:.9rem 1.1rem; border-radius:14px;
          color:#a1a1a6; background:rgba(10,132,255,.08); border:1px solid rgba(10,132,255,.24); }
        .section-kicker { color:#636366; font-size:.7rem; font-weight:700; letter-spacing:.17em; }
        .space-top { margin-top:2.1rem; }
        [data-testid="stVerticalBlockBorderWrapper"] { background:linear-gradient(145deg,
          rgba(28,28,30,.95),rgba(11,11,13,.95)); border-color:#2c2c2e !important;
          border-radius:28px !important; padding: .35rem; }
        [data-baseweb="tab-list"] { gap:.45rem; }
        [data-baseweb="tab"] { border-radius:999px; background:#171719; padding:.55rem 1rem; }
        [aria-selected="true"][data-baseweb="tab"] { background:#f5f5f7; color:#050506; }
        .metric-card { min-height:170px; padding:1.45rem; border:1px solid #2c2c2e;
          border-radius:25px; background:linear-gradient(145deg,#19191c,#0c0c0e);
          box-shadow:0 24px 70px rgba(0,0,0,.18); position:relative; overflow:hidden; }
        .metric-card::after { content:""; position:absolute; width:80px; height:80px; right:-30px;
          top:-30px; border-radius:50%; background:var(--metric,#36363a); filter:blur(38px); opacity:.35; }
        .metric-card small { color:#77777d; font-size:.69rem; font-weight:700; letter-spacing:.13em; }
        .metric-card strong { display:block; color:#f5f5f7; font-size:2.8rem; letter-spacing:-.06em;
          margin-top:2rem; line-height:1; }
        .metric-card strong.empty { color:#4c4c50; }
        .metric-card span { color:#77777d; font-size:.74rem; }
        .insight { border-left:2px solid #64d2ff; color:#8e8e93; padding:.75rem 1rem;
          background:rgba(100,210,255,.045); border-radius:0 14px 14px 0; }
        .insight b, .insight strong { color:#f5f5f7; }
        .personal-lab-banner { margin:.2rem 0 1.5rem; padding:1.35rem 1.5rem;
          border-radius:24px; border:1px solid rgba(191,90,242,.38);
          background:linear-gradient(135deg,rgba(191,90,242,.18),rgba(94,92,230,.06));
          box-shadow:0 20px 70px rgba(175,82,222,.10); }
        .personal-lab-banner small { display:block; color:#bf5af2; font-weight:750;
          letter-spacing:.16em; margin-bottom:.65rem; }
        .personal-lab-banner strong { display:block; color:#f5f5f7; font-size:1.35rem;
          letter-spacing:-.025em; }
        .personal-lab-banner span { display:block; color:#98989d; margin-top:.35rem; }
        .personal-empty { margin:0 0 1.7rem; padding:1.4rem 1.5rem; border-radius:22px;
          border:1px dashed rgba(191,90,242,.35); background:rgba(191,90,242,.04); }
        .personal-empty strong { display:block; color:#f5f5f7; font-size:1.05rem; }
        .personal-empty span { display:block; color:#8e8e93; margin-top:.35rem; }
        .profile-card, .expectation-card { min-height:210px; padding:1.35rem 1.45rem;
          border-radius:24px; border:1px solid #2c2c2e; background:#111113; }
        .profile-card { position:relative; overflow:hidden; }
        .profile-card::after { content:""; position:absolute; width:160px; height:160px;
          right:-70px; top:-75px; border-radius:50%; background:var(--profile-color);
          filter:blur(55px); opacity:.24; }
        .profile-card small, .expectation-card small { color:#8e8e93; font-size:.67rem;
          font-weight:750; letter-spacing:.15em; }
        .profile-card h3 { margin:.7rem 0 !important; font-size:2rem; color:#f5f5f7; }
        .profile-card p, .expectation-card p { color:#a1a1a6; line-height:1.5; }
        .expectation-card p { margin:.35rem 0 1.25rem; }
        .period-strip { display:flex; flex-wrap:wrap; gap:.65rem; margin:1rem 0 1.2rem; }
        .period-strip span { padding:.55rem .8rem; border-radius:999px; color:#8e8e93;
          border:1px solid #2c2c2e; background:#111113; font-size:.76rem; }
        .period-strip b { color:#f5f5f7; }
        .workout-banner { margin:.2rem 0 1.3rem; padding:1.35rem 1.5rem;
          border-radius:24px; border:1px solid rgba(10,132,255,.38);
          background:linear-gradient(135deg,rgba(10,132,255,.18),rgba(94,92,230,.05));
          box-shadow:0 20px 70px rgba(10,132,255,.09); }
        .workout-banner small { display:block; color:#64d2ff; font-weight:750;
          letter-spacing:.16em; margin-bottom:.65rem; }
        .workout-banner strong { display:block; color:#f5f5f7; font-size:1.35rem;
          letter-spacing:-.025em; }
        .workout-banner span { display:block; color:#98989d; margin-top:.35rem; }
        .workout-card { min-height:128px; padding:1.05rem 1.15rem; border-radius:22px;
          border:1px solid rgba(10,132,255,.22);
          background:linear-gradient(145deg,rgba(23,31,48,.92),#0d0d0f); }
        .workout-card small { color:#64d2ff; font-size:.63rem; font-weight:750;
          letter-spacing:.13em; }
        .workout-card strong { display:block; color:#f5f5f7; font-size:1.7rem;
          letter-spacing:-.05em; margin:.75rem 0 .25rem; line-height:1; }
        .workout-card span { color:#77777d; font-size:.7rem; }
        .year-chip { padding:.9rem 1rem; border-radius:20px; background:#111113;
          border:1px solid #2c2c2e; }
        .year-chip small { color:#64d2ff; font-weight:750; letter-spacing:.09em; }
        .year-chip strong { display:block; color:#f5f5f7; font-size:1.65rem;
          letter-spacing:-.05em; margin:.45rem 0 .15rem; }
        .year-chip span { color:#77777d; font-size:.68rem; }
        .workout-insight { display:grid; grid-template-columns:auto auto 1fr;
          align-items:center; gap:1rem; margin:1.2rem 0; padding:1rem 1.15rem;
          border-radius:20px; border:1px solid rgba(100,210,255,.22);
          background:rgba(100,210,255,.055); }
        .workout-insight small { color:#64d2ff; font-size:.63rem; font-weight:750;
          letter-spacing:.13em; }
        .workout-insight strong { color:#f5f5f7; font-size:1.3rem; }
        .workout-insight span { color:#8e8e93; font-size:.78rem; }
        .chart-heading { display:flex; align-items:baseline; gap:.75rem; padding:.35rem .45rem 0; }
        .chart-heading small { color:#636366; font-size:.64rem; font-weight:750;
          letter-spacing:.14em; }
        .chart-heading strong { color:#f5f5f7; font-size:1.1rem; }
        .chart-heading span { color:#636366; font-size:.72rem; margin-left:auto; }
        .range-card { min-height:128px; padding:1.05rem 1.15rem; border:1px solid #2c2c2e;
          border-radius:22px; background:linear-gradient(145deg,#171719,#0d0d0f);
          position:relative; overflow:hidden; }
        .range-card::after { content:""; position:absolute; width:78px; height:78px; right:-32px;
          top:-30px; border-radius:50%; background:var(--metric,#36363a);
          filter:blur(34px); opacity:.28; }
        .range-card small { color:#77777d; font-size:.64rem; font-weight:750;
          letter-spacing:.13em; }
        .range-card strong { display:block; color:#f5f5f7; font-size:1.75rem;
          letter-spacing:-.05em; margin:.7rem 0 .2rem; line-height:1; }
        .range-card span { color:#77777d; font-size:.7rem; }
        .disclaimer { color:#48484a; text-align:center; font-size:.72rem; margin-top:3.5rem; }
        .stButton > button, .stDownloadButton > button { border-radius:999px; }
        [data-testid="stFileUploaderDropzone"] { border-radius:20px; background:#101012; }
        @media(max-width: 760px) {
          .block-container { padding-top:2rem; }
          h1 { font-size:3.8rem !important; }
          .metric-card { min-height:140px; padding:1rem; }
          .metric-card strong { font-size:2.15rem; margin-top:1.4rem; }
          .workout-insight { grid-template-columns:1fr; gap:.35rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
