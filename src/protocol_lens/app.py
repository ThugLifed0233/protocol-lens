"""Local Protocol Lens dashboard."""

from __future__ import annotations

import os
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

from protocol_lens import __version__
from protocol_lens.analysis import correlations, daily_metrics, workout_comparison
from protocol_lens.apple_health import iter_export
from protocol_lens.database import connect, ingest_records
from protocol_lens.experiments import (
    add_compound_period,
    analyze_compound_periods,
    import_compound_periods,
    list_compound_periods,
    public_snapshot_csv,
    public_snapshot_json,
)
from protocol_lens.sample import build_sample_database
from protocol_lens.spreadsheet import (
    fetch_google_sheet,
    metric_label,
    read_spreadsheet,
    spreadsheet_records,
)

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "processed"
REAL_DB = Path(os.environ.get("PROTOCOL_LENS_DB", DATA_DIR / "protocol-lens.duckdb"))
SAMPLE_DB = DATA_DIR / "sample.duckdb"
TEMPLATE = "date,metric,value,unit\n2026-07-28,weight,101,kg\n2026-07-28,protein,142,g\n"
INTERVENTION_TEMPLATE = (
    "intervention,category,start_date,end_date,dose_note,purpose,confidence,visibility,notes\n"
    "Example supplement,supplement,2026-07-01,2026-07-14,,,confirmed,personal_only,\n"
)

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

    _metric_cards(frame)
    st.markdown('<div class="section-kicker space-top">EXPLORE</div>', unsafe_allow_html=True)
    st.subheader("Mix any available metrics")
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

    timeline, relationship_tab, workouts_tab, personal_lab_tab, sources_tab = st.tabs(
        ["Timeline", "Relationships", "Workouts", "Personal Lab", "Sources"]
    )
    with timeline:
        if selected:
            st.plotly_chart(
                _timeline_figure(frame, selected),
                width="stretch",
                config={"displayModeBar": False},
            )
        else:
            st.caption("Choose at least one metric.")

    with relationship_tab:
        _relationship_view(frame)

    with workouts_tab:
        _workout_view(connection, frame)

    with personal_lab_tab:
        _compound_view(personal_connection)

    with sources_tab:
        _source_view(connection, demo)

    st.markdown(
        '<p class="disclaimer">Descriptive personal analytics—not diagnosis or medical advice. '
        "A relationship does not establish causation.</p>",
        unsafe_allow_html=True,
    )


def _metric_cards(frame: pd.DataFrame) -> None:
    definitions = [
        ("resting_heart_rate", "RESTING HR", "bpm", "#ff453a"),
        ("hrv_sdnn", "HRV", "ms", "#bf5af2"),
        ("sleep_hours", "SLEEP", "hours", "#5e5ce6"),
        ("steps", "STEPS", "", "#30d158"),
    ]
    columns = st.columns(4)
    for column, (metric, title, unit, color) in zip(columns, definitions, strict=True):
        values = frame[metric].dropna() if metric in frame else pd.Series(dtype=float)
        with column:
            if values.empty:
                st.markdown(
                    f'<div class="metric-card"><small>{title}</small>'
                    '<strong class="empty">—</strong><span>No data yet</span></div>',
                    unsafe_allow_html=True,
                )
            else:
                latest = float(values.iloc[-1])
                value = f"{latest:,.0f}" if metric == "steps" else f"{latest:.1f}"
                st.markdown(
                    f'<div class="metric-card" style="--metric:{color}"><small>{title}</small>'
                    f"<strong>{value}</strong><span>{unit} · latest available</span></div>",
                    unsafe_allow_html=True,
                )


def _timeline_figure(frame: pd.DataFrame, selected: list[str]) -> go.Figure:
    palette = ["#ff453a", "#64d2ff", "#bf5af2"]
    figure = go.Figure()
    for index, metric in enumerate(selected):
        figure.add_trace(
            go.Scatter(
                x=frame.index,
                y=frame[metric],
                name=metric_label(metric),
                mode="lines",
                connectgaps=False,
                line={"color": palette[index], "width": 2.6, "shape": "spline"},
            )
        )
    workout_days = frame[frame.get("workout_count", pd.Series(index=frame.index)).fillna(0) > 0]
    if not workout_days.empty and selected:
        anchor = frame[selected[0]].reindex(workout_days.index)
        figure.add_trace(
            go.Scatter(
                x=workout_days.index,
                y=anchor,
                name="Apple workout",
                mode="markers",
                marker={"symbol": "diamond", "size": 8, "color": "#0a84ff"},
            )
        )
    return _chart_layout(figure, 470)


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


def _workout_view(connection: duckdb.DuckDBPyConnection, frame: pd.DataFrame) -> None:
    workout_frame = connection.execute(
        """
        SELECT start_at, activity_type, duration_minutes, energy_kcal, distance_km
        FROM workouts ORDER BY start_at DESC LIMIT 100
        """
    ).df()
    if workout_frame.empty:
        st.info("No Apple workouts have been imported yet.")
        return
    comparison = workout_comparison(frame, "resting_heart_rate")
    if comparison:
        workout, rest, workout_n, rest_n = comparison
        first, second = st.columns(2)
        first.metric("Workout-day resting HR", f"{workout:.1f} bpm", f"{workout_n} days")
        second.metric("Other-day resting HR", f"{rest:.1f} bpm", f"{rest_n} days")
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
        margin={"l": 20, "r": 20, "t": 28, "b": 20},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "-apple-system, BlinkMacSystemFont, Inter", "color": "#a1a1a6"},
        legend={"orientation": "h", "y": 1.08},
        hovermode="x unified",
        xaxis={"gridcolor": "rgba(255,255,255,.06)", "zeroline": False},
        yaxis={"gridcolor": "rgba(255,255,255,.06)", "zeroline": False},
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
        .block-container { max-width: 1180px; padding-top: 4.2rem; padding-bottom: 5rem; }
        [data-testid="stHeader"] { display:none; }
        h1 { font-size: clamp(3.6rem, 7.6vw, 7rem) !important; line-height: .91 !important;
          letter-spacing: -.065em !important; margin: 1.5rem 0 1.4rem !important; }
        h1 span { color: #6e6e73; }
        h2, h3 { letter-spacing: -.035em !important; }
        .wordmark { color: #30d158; font-size: .72rem; letter-spacing: .16em; font-weight: 700; }
        .wordmark i { display:inline-block; width:8px; height:8px; background:#30d158;
          border-radius:50%; margin-right:8px; box-shadow:0 0 18px #30d158; }
        .lede { color:#98989d; max-width:720px; font-size:1.24rem; line-height:1.55; }
        .local-pill { border:1px solid #2c2c2e; color:#8e8e93; border-radius:999px;
          font-size:.76rem; padding:.62rem .82rem; margin:.15rem 0 1rem; text-align:center; }
        .local-pill::first-letter { color:#30d158; }
        .demo-banner { margin:2rem 0 1rem; padding:.9rem 1.1rem; border-radius:14px;
          color:#a1a1a6; background:rgba(10,132,255,.08); border:1px solid rgba(10,132,255,.24); }
        .section-kicker { color:#636366; font-size:.7rem; font-weight:700; letter-spacing:.17em; }
        .space-top { margin-top:4rem; }
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
        .disclaimer { color:#48484a; text-align:center; font-size:.72rem; margin-top:3.5rem; }
        .stButton > button, .stDownloadButton > button { border-radius:999px; }
        [data-testid="stFileUploaderDropzone"] { border-radius:20px; background:#101012; }
        @media(max-width: 760px) {
          .block-container { padding-top:2rem; }
          h1 { font-size:3.8rem !important; }
          .metric-card { min-height:140px; padding:1rem; }
          .metric-card strong { font-size:2.15rem; margin-top:1.4rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
