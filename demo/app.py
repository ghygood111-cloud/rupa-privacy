"""Local Streamlit research interface for the validated RUPA API."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Optional

import pandas as pd
import yaml

try:
    import altair as alt
    import streamlit as st
except ImportError:  # Keep the module importable without the optional demo extra.
    alt = None
    st = None

from rupa_privacy import __version__
from hazardous_waste_requirements import (
    CHECKLIST,
    load_requirements,
    readiness_checklist_csv,
    requirement_rows,
    requirements_csv,
)
from result_presentation import physical_stage_table
from demo_support import (
    RUNS_ROOT,
    apply_basic_config,
    apply_field_rows,
    build_public_run_archive,
    constraint_expression,
    execute_demo,
    field_rows,
    load_example,
    load_public_run,
    reproduction_commands,
    sanitized_calibration_preview,
    validate_demo,
)


PAGES = (
    "01  Overview",
    "02  Data",
    "03  Configuration",
    "04  Validation",
    "05  Run",
    "06  Analysis",
    "07  Export",
    "08  Research",
)

WORKFLOW_PAGE_KEY = "workflow_page"
PENDING_WORKFLOW_PAGE_KEY = "pending_workflow_page"

CHART_COLORS = {
    "primary": "#174A7E",
    "secondary": "#168A83",
    "success": "#25875A",
    "warning": "#C47A18",
    "muted": "#7B8794",
}

RUPA_STYLES = """
<style>
:root {
    --rupa-primary: #174A7E;
    --rupa-primary-strong: #103757;
    --rupa-primary-soft: #EAF2F8;
    --rupa-secondary: #168A83;
    --rupa-bg: #F4F7FB;
    --rupa-card: #FFFFFF;
    --rupa-border: #D8E1EA;
    --rupa-text: #1D2939;
    --rupa-muted: #667085;
    --rupa-success: #25875A;
    --rupa-success-soft: #EAF6EF;
    --rupa-warning: #C47A18;
    --rupa-warning-soft: #FFF5E6;
    --rupa-error: #C24444;
    --rupa-error-soft: #FCEEEE;
}
.stApp { background: var(--rupa-bg); color: var(--rupa-text); }
.block-container {
    padding-top: 1.35rem;
    padding-bottom: 3rem;
    max-width: 1680px;
}
[data-testid="stSidebar"] {
    background: #F9FBFD;
    border-right: 1px solid var(--rupa-border);
}
[data-testid="stSidebar"] [data-testid="stSidebarContent"] {
    padding-top: 1.15rem;
}
.rupa-brand { padding: 0.2rem 0.1rem 0.8rem; }
.rupa-brand-name {
    color: var(--rupa-primary-strong);
    font-size: 1.55rem;
    font-weight: 750;
    line-height: 1.1;
    letter-spacing: 0;
}
.rupa-brand-meta {
    color: var(--rupa-muted);
    font-size: 0.78rem;
    line-height: 1.5;
    margin-top: 0.35rem;
}
[data-testid="stSidebar"] .stRadio > div[role="radiogroup"] { gap: 0.28rem; }
[data-testid="stSidebar"] .stRadio > div[role="radiogroup"] > label {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    color: #344054;
    min-height: 2.5rem;
    padding: 0.38rem 0.58rem;
}
[data-testid="stSidebar"] .stRadio > div[role="radiogroup"] > label:has(input:checked) {
    background: var(--rupa-primary-soft);
    border-color: #BDD2E5;
    color: var(--rupa-primary-strong);
    font-weight: 650;
}
.rupa-sidebar-label {
    color: #8993A1;
    font-size: 0.68rem;
    font-weight: 700;
    margin: 0.9rem 0 0.32rem;
    text-transform: uppercase;
}
.rupa-status-row {
    align-items: center;
    color: #475467;
    display: flex;
    font-size: 0.77rem;
    justify-content: space-between;
    padding: 0.22rem 0;
}
.rupa-status-value { color: var(--rupa-muted); }
.rupa-status-dot {
    border-radius: 50%;
    display: inline-block;
    height: 0.48rem;
    margin-right: 0.42rem;
    width: 0.48rem;
}
.rupa-status-dot.ready { background: var(--rupa-success); }
.rupa-status-dot.waiting { background: #AAB4C0; }
.rupa-status-dot.failed { background: var(--rupa-error); }
.rupa-header {
    align-items: flex-start;
    background: var(--rupa-card);
    border: 1px solid var(--rupa-border);
    border-left: 4px solid var(--rupa-primary);
    border-radius: 6px;
    display: flex;
    justify-content: space-between;
    margin-bottom: 1.2rem;
    padding: 1rem 1.15rem 0.9rem;
}
.rupa-header-title {
    color: var(--rupa-primary-strong);
    font-size: 1.7rem;
    font-weight: 760;
    line-height: 1.05;
    letter-spacing: 0;
}
.rupa-header-subtitle {
    color: #344054;
    font-size: 0.98rem;
    font-weight: 620;
    margin-top: 0.22rem;
}
.rupa-header-description {
    color: var(--rupa-muted);
    font-size: 0.82rem;
    margin-top: 0.3rem;
}
.rupa-badges { display: flex; flex-wrap: wrap; gap: 0.38rem; justify-content: flex-end; }
.rupa-badge {
    background: #F7F9FC;
    border: 1px solid var(--rupa-border);
    border-radius: 4px;
    color: #475467;
    font-size: 0.7rem;
    font-weight: 650;
    padding: 0.28rem 0.48rem;
}
.rupa-badge.mode { background: var(--rupa-success-soft); border-color: #B9DDC8; color: #1C6B46; }
.rupa-process-line {
    border-top: 1px solid #E7ECF2;
    color: #697586;
    font-size: 0.73rem;
    margin-top: 0.72rem;
    padding-top: 0.55rem;
}
.rupa-page-heading { margin: 0.1rem 0 1.05rem; }
.rupa-page-title {
    color: var(--rupa-text);
    font-size: 1.45rem;
    font-weight: 720;
    letter-spacing: 0;
    line-height: 1.2;
}
.rupa-page-description { color: var(--rupa-muted); font-size: 0.84rem; margin-top: 0.25rem; }
.rupa-section-label {
    color: var(--rupa-primary-strong);
    font-size: 1rem;
    font-weight: 700;
    margin: 1.15rem 0 0.18rem;
}
.rupa-section-note { color: var(--rupa-muted); font-size: 0.78rem; margin-bottom: 0.65rem; }
.rupa-flow {
    display: grid;
    gap: 0.55rem;
    grid-template-columns: repeat(6, minmax(0, 1fr));
    margin: 0.7rem 0 1.2rem;
}
.rupa-flow-step {
    background: var(--rupa-card);
    border: 1px solid var(--rupa-border);
    border-top: 3px solid var(--rupa-primary);
    border-radius: 6px;
    min-height: 5rem;
    padding: 0.68rem 0.72rem;
}
.rupa-flow-index { color: var(--rupa-secondary); font-size: 0.68rem; font-weight: 750; }
.rupa-flow-name { color: #344054; font-size: 0.82rem; font-weight: 650; margin-top: 0.5rem; }
.rupa-feature-grid {
    display: grid;
    gap: 0.9rem;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    margin: 0.65rem 0 1rem;
}
.rupa-feature {
    border-top: 2px solid var(--rupa-secondary);
    padding: 0.72rem 0.2rem 0.2rem;
}
.rupa-feature-title { color: #344054; font-size: 0.84rem; font-weight: 700; }
.rupa-feature-copy { color: var(--rupa-muted); font-size: 0.76rem; line-height: 1.5; margin-top: 0.28rem; }
div[data-testid="stMetric"] {
    background: var(--rupa-card);
    border: 1px solid var(--rupa-border);
    border-radius: 6px;
    min-height: 6.15rem;
    padding: 0.78rem 0.88rem;
}
div[data-testid="stMetric"] label { color: var(--rupa-muted); }
div[data-testid="stMetricValue"] { color: var(--rupa-primary-strong); font-size: 1.48rem; }
div[data-testid="stAlert"] { border-radius: 6px; }
.stButton > button, .stDownloadButton > button, [data-testid="stFormSubmitButton"] > button {
    border-radius: 6px;
    font-weight: 620;
    min-height: 2.45rem;
}
[data-testid="stFileUploader"] { background: var(--rupa-card); border-radius: 6px; }
[data-testid="stDataFrame"] { border: 1px solid var(--rupa-border); border-radius: 6px; overflow: hidden; }
.stTabs [data-baseweb="tab-list"] { border-bottom: 1px solid var(--rupa-border); gap: 0.25rem; }
.stTabs [data-baseweb="tab"] { color: #5B6676; font-weight: 620; padding-left: 0.7rem; padding-right: 0.7rem; }
.stTabs [aria-selected="true"] { color: var(--rupa-primary); }
code { border-radius: 4px; }
h1, h2, h3 { color: var(--rupa-text); letter-spacing: 0; }
@media (max-width: 1000px) {
    .rupa-flow { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .rupa-feature-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .rupa-header { display: block; }
    .rupa-badges { justify-content: flex-start; margin-top: 0.7rem; }
}
@media (max-width: 640px) {
    .rupa-flow, .rupa-feature-grid { grid-template-columns: 1fr; }
}
</style>
"""


def _initial_state() -> dict:
    return {
        "calibration": None,
        "release": None,
        "config": None,
        "dataset_label": "No dataset loaded",
        "calibration_name": "calibration.csv",
        "release_name": "release.csv",
        "config_name": "config.yaml",
        "validation": None,
        "validation_error": None,
        "run_directory": None,
        "run_summary": None,
        "release_preview_authorized": False,
        WORKFLOW_PAGE_KEY: PAGES[0],
        PENDING_WORKFLOW_PAGE_KEY: None,
    }


def init_state() -> None:
    for key, value in _initial_state().items():
        if key not in st.session_state:
            st.session_state[key] = value


def _invalidate_outcomes() -> None:
    st.session_state.pop("research_run_directory", None)
    st.session_state.validation = None
    st.session_state.validation_error = None
    st.session_state.run_directory = None
    st.session_state.run_summary = None
    st.session_state[PENDING_WORKFLOW_PAGE_KEY] = None


def _authorized_workflow_page(
    requested_page: str, *, validation_passed: bool, run_completed: bool
) -> str:
    """Keep forward workflow pages behind their completed prerequisite."""
    if requested_page not in PAGES:
        raise ValueError("Unknown workflow page")
    if requested_page == "05  Run" and not validation_passed:
        return "04  Validation"
    if requested_page in {"06  Analysis", "07  Export"} and not run_completed:
        return "05  Run" if validation_passed else "04  Validation"
    return requested_page


def _request_workflow_navigation(page: str) -> None:
    """Queue a page change for the next rerun, before the radio widget is created."""
    if page not in PAGES:
        raise ValueError("Unknown workflow page")
    st.session_state[PENDING_WORKFLOW_PAGE_KEY] = page


def _prepare_workflow_navigation() -> None:
    """Apply success-driven navigation before Streamlit renders the sidebar radio."""
    requested_page = st.session_state.get(WORKFLOW_PAGE_KEY, PAGES[0])
    pending_page = st.session_state.get(PENDING_WORKFLOW_PAGE_KEY)
    if pending_page is not None:
        requested_page = pending_page
        st.session_state[PENDING_WORKFLOW_PAGE_KEY] = None
    st.session_state[WORKFLOW_PAGE_KEY] = _authorized_workflow_page(
        requested_page,
        validation_passed=bool(st.session_state.validation),
        run_completed=bool(st.session_state.run_directory and st.session_state.run_summary),
    )


def _constrain_sidebar_navigation() -> None:
    """Run as the radio callback so manual forward navigation observes prerequisites."""
    st.session_state[WORKFLOW_PAGE_KEY] = _authorized_workflow_page(
        st.session_state[WORKFLOW_PAGE_KEY],
        validation_passed=bool(st.session_state.validation),
        run_completed=bool(st.session_state.run_directory and st.session_state.run_summary),
    )


def _record_validation_success(result: Mapping) -> None:
    st.session_state.validation = {
        "calibration_rows": result["calibration_rows"],
        "release_rows": result["release_rows"],
        "released_columns": result["released_columns"],
        "constraint_validation": result["constraint_validation"],
        "privacy_unit_id": result["adjacency"].privacy_unit_id,
        "adjacency": result["adjacency"].type,
    }
    st.session_state.validation_error = None
    _request_workflow_navigation("05  Run")


def _record_validation_failure(error: Exception) -> None:
    st.session_state.validation = None
    st.session_state.validation_error = type(error).__name__ + ": " + str(error)
    st.session_state[PENDING_WORKFLOW_PAGE_KEY] = None


def _record_run_success(run) -> None:
    st.session_state.run_directory = str(run.run_directory)
    st.session_state.run_summary = {
        "run_id": run.run_id,
        "runtime_seconds": run.runtime_seconds,
        "release_rows": run.inspection["release_rows"],
        "artifact_count": run.inspection["artifact_count"],
        "released_attributes": len(run.schema.released_columns),
    }
    _request_workflow_navigation("06  Analysis")


def _record_run_failure() -> None:
    st.session_state[PENDING_WORKFLOW_PAGE_KEY] = None


def _load_example_into_state(key: str) -> None:
    example = load_example(key)
    st.session_state.calibration = example["calibration"]
    st.session_state.release = example["release"]
    st.session_state.config = example["config"]
    st.session_state.dataset_label = example["name"]
    st.session_state.calibration_name = example["calibration_path"].name
    st.session_state.release_name = example["release_path"].name
    st.session_state.config_name = example["config_path"].name
    st.session_state.release_preview_authorized = False
    st.session_state.pop("yaml_editor", None)
    st.session_state.pop("field_editor", None)
    _invalidate_outcomes()


def _ready() -> bool:
    return (
        isinstance(st.session_state.calibration, pd.DataFrame)
        and isinstance(st.session_state.release, pd.DataFrame)
        and isinstance(st.session_state.config, Mapping)
    )


def _friendly_error(title: str, error: Exception) -> None:
    st.error(title + ": " + str(error))
    with st.expander("Technical details"):
        st.code(type(error).__name__ + ": " + str(error), language="text")


def _privacy_values(config: Optional[Mapping]) -> dict:
    privacy = dict((config or {}).get("privacy", {}))
    return {
        "epsilon_total": privacy.get("epsilon_total", "Not set"),
        "epsilon_numeric": privacy.get("epsilon_numeric", "Not set"),
        "epsilon_categorical": privacy.get("epsilon_categorical", "Not set"),
        "utility_alpha": privacy.get("utility_alpha", "Not set"),
        "repair_alpha": privacy.get("repair_alpha", "Not set"),
        "random_seed": privacy.get("random_seed", "Not set"),
        "randomness_mode": privacy.get("randomness_mode", "Not set"),
    }


def _status_snapshot() -> dict:
    data_ready = isinstance(st.session_state.calibration, pd.DataFrame) and isinstance(
        st.session_state.release, pd.DataFrame
    )
    config_ready = isinstance(st.session_state.config, Mapping)
    validation_passed = bool(st.session_state.validation)
    validation_failed = bool(st.session_state.validation_error)
    run_completed = bool(st.session_state.run_directory and st.session_state.run_summary)
    return {
        "Data": ("Ready", "ready") if data_ready else ("Waiting", "waiting"),
        "Configuration": ("Ready", "ready") if config_ready else ("Waiting", "waiting"),
        "Validation": (
            ("Passed", "ready")
            if validation_passed
            else ("Failed", "failed")
            if validation_failed
            else ("Pending", "waiting")
        ),
        "Run": ("Completed", "ready") if run_completed else ("Pending", "waiting"),
        "Results": ("Available", "ready") if run_completed else ("Unavailable", "waiting"),
    }


def _render_sidebar() -> str:
    st.sidebar.markdown(
        """
        <div class="rupa-brand">
          <div class="rupa-brand-name">RUPA</div>
          <div class="rupa-brand-meta">Research Software<br>Version {}</div>
        </div>
        """.format(__version__),
        unsafe_allow_html=True,
    )
    st.sidebar.markdown('<div class="rupa-sidebar-label">Workflow</div>', unsafe_allow_html=True)
    page = st.sidebar.radio(
        "Workflow navigation",
        PAGES,
        key=WORKFLOW_PAGE_KEY,
        on_change=_constrain_sidebar_navigation,
        label_visibility="collapsed",
    )
    st.sidebar.markdown('<div class="rupa-sidebar-label">Progress</div>', unsafe_allow_html=True)
    for name, (value, state) in _status_snapshot().items():
        st.sidebar.markdown(
            '<div class="rupa-status-row"><span><span class="rupa-status-dot {}"></span>{}</span>'
            '<span class="rupa-status-value">{}</span></div>'.format(state, name, value),
            unsafe_allow_html=True,
        )
    st.sidebar.markdown('<div class="rupa-sidebar-label">Dataset</div>', unsafe_allow_html=True)
    st.sidebar.write(st.session_state.dataset_label)
    st.sidebar.markdown('<div class="rupa-sidebar-label">Configuration</div>', unsafe_allow_html=True)
    st.sidebar.write(st.session_state.config_name if st.session_state.config else "Not loaded")
    st.sidebar.markdown('<div class="rupa-sidebar-label">Execution mode</div>', unsafe_allow_html=True)
    st.sidebar.success("Reproducibility only")
    if st.session_state.config:
        values = _privacy_values(st.session_state.config)
        st.sidebar.markdown('<div class="rupa-sidebar-label">Run parameters</div>', unsafe_allow_html=True)
        st.sidebar.write("Total epsilon: `{}`".format(values["epsilon_total"]))
        st.sidebar.write("Seed: `{}`".format(values["random_seed"]))
        st.sidebar.write("Repair alpha: `{}`".format(values["repair_alpha"]))
    return page


def _software_header() -> None:
    st.markdown(
        """
        <div class="rupa-header">
          <div>
            <div class="rupa-header-title">RUPA</div>
            <div class="rupa-header-subtitle">Risk&ndash;Utility Privacy Allocation</div>
            <div class="rupa-header-description">Privacy-aware release of fixed-roster industrial microdata</div>
            <div class="rupa-process-line">Risk calibration &middot; Utility modelling &middot; Privacy allocation &middot; DP release &middot; Physical repair</div>
          </div>
          <div class="rupa-badges">
            <span class="rupa-badge">v{}</span>
            <span class="rupa-badge">Research Software</span>
            <span class="rupa-badge mode">Reproducibility Mode</span>
          </div>
        </div>
        """.format(__version__),
        unsafe_allow_html=True,
    )


def _page_header(title: str, description: str) -> None:
    st.markdown(
        '<div class="rupa-page-heading"><div class="rupa-page-title">{}</div>'
        '<div class="rupa-page-description">{}</div></div>'.format(title, description),
        unsafe_allow_html=True,
    )


def _section_header(title: str, note: Optional[str] = None) -> None:
    content = '<div class="rupa-section-label">{}</div>'.format(title)
    if note:
        content += '<div class="rupa-section-note">{}</div>'.format(note)
    st.markdown(content, unsafe_allow_html=True)


def page_overview() -> None:
    _page_header(
        "Overview",
        "A structured research workflow for calibrated, auditable release of mixed-type industrial microdata.",
    )
    _section_header("Scientific workflow", "One configuration connects calibration, mechanisms, post-processing and public release artifacts.")
    st.markdown(
        """
        <div class="rupa-flow">
          <div class="rupa-flow-step"><div class="rupa-flow-index">01</div><div class="rupa-flow-name">Calibration</div></div>
          <div class="rupa-flow-step"><div class="rupa-flow-index">02</div><div class="rupa-flow-name">Risk &amp; Utility</div></div>
          <div class="rupa-flow-step"><div class="rupa-flow-index">03</div><div class="rupa-flow-name">Budget Allocation</div></div>
          <div class="rupa-flow-step"><div class="rupa-flow-index">04</div><div class="rupa-flow-name">DP Perturbation</div></div>
          <div class="rupa-flow-step"><div class="rupa-flow-index">05</div><div class="rupa-flow-name">Physical Repair</div></div>
          <div class="rupa-flow-step"><div class="rupa-flow-index">06</div><div class="rupa-flow-name">Auditable Release</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    _section_header("Workspace status")
    statuses = _status_snapshot()
    columns = st.columns(4)
    for column, name in zip(columns, ("Data", "Configuration", "Validation", "Run")):
        column.metric(name, statuses[name][0])

    _section_header("Research capabilities")
    st.markdown(
        """
        <div class="rupa-feature-grid">
          <div class="rupa-feature"><div class="rupa-feature-title">Risk-aware allocation</div><div class="rupa-feature-copy">NMI-based attribute risk estimation with effective-bin diagnostics.</div></div>
          <div class="rupa-feature"><div class="rupa-feature-title">Mixed-type privacy</div><div class="rupa-feature-copy">Numerical Laplace perturbation and categorical generalized randomized response.</div></div>
          <div class="rupa-feature"><div class="rupa-feature-title">Constraint-aware repair</div><div class="rupa-feature-copy">Public linear-equality post-processing with residual reporting.</div></div>
          <div class="rupa-feature"><div class="rupa-feature-title">Auditable outputs</div><div class="rupa-feature-copy">Hashed public artifacts, run manifest and deterministic research mode.</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    _section_header("Start a reproducible example", "Load a maintained example, then continue through Validation and Run.")
    left, middle, right = st.columns(3)
    if left.button("Load official synthetic example", use_container_width=True):
        try:
            _load_example_into_state("official")
            st.rerun()
        except Exception as exc:
            _friendly_error("Could not load the example", exc)
    if middle.button("Load water-treatment example", use_container_width=True):
        try:
            _load_example_into_state("water")
            st.rerun()
        except Exception as exc:
            _friendly_error("Could not load the example", exc)
    if right.button("Load hazardous-waste synthetic example", use_container_width=True):
        try:
            _load_example_into_state("hazardous_waste")
            st.rerun()
        except Exception as exc:
            _friendly_error("Could not load the example", exc)

    _section_header("危废业务需求", "已接入项目字段清单；尚无实际业务数据，与上方合成示例分开管理。")
    st.caption("31个具名字段 · 4类业务信息 · 不自动推断公开边界、类别域或物理约束")
    if st.button("查看危废字段需求", icon=":material/assignment:"):
        _request_workflow_navigation("02  Data")
        st.rerun()

    st.info(
        "The graphical interface is limited to public or synthetic reproducibility workflows. "
        "Ledger-governed production releases remain available through the official CLI."
    )


def _parse_uploaded_csv(uploaded) -> pd.DataFrame:
    try:
        return pd.read_csv(uploaded)
    except Exception as exc:
        raise ValueError("CSV could not be read") from exc


def _parse_uploaded_yaml(uploaded) -> dict:
    try:
        values = yaml.safe_load(uploaded.getvalue().decode("utf-8-sig"))
    except Exception as exc:
        raise ValueError("YAML could not be read") from exc
    if not isinstance(values, dict):
        raise ValueError("Configuration root must be a mapping")
    return values


def _show_table_profile(label: str, frame: pd.DataFrame) -> None:
    st.markdown("**{}**".format(label))
    c1, c2 = st.columns(2)
    c1.metric("Rows", len(frame))
    c2.metric("Columns", len(frame.columns))
    types = pd.DataFrame(
        {"Column": frame.columns.astype(str), "Detected type": frame.dtypes.astype(str).values}
    )
    st.dataframe(types, hide_index=True, use_container_width=True)


def _render_data_inputs() -> None:
    _section_header("Input source", "Load a maintained example or provide a complete local input set.")
    requirements_tab, example_tab, upload_tab = st.tabs(
        ["危废业务需求（无实际数据）", "Maintained examples", "Upload local files"]
    )
    with requirements_tab:
        _render_hazardous_waste_requirements()
    with example_tab:
        st.caption("Versioned public/synthetic examples for immediate reproducibility checks.")
        c1, c2, c3 = st.columns(3)
        if c1.button("Official synthetic example", use_container_width=True, key="data_official"):
            _load_example_into_state("official")
            st.rerun()
        if c2.button("Water-treatment example", use_container_width=True, key="data_water"):
            _load_example_into_state("water")
            st.rerun()
        if c3.button("Hazardous-waste synthetic example", use_container_width=True, key="data_hazardous_waste"):
            _load_example_into_state("hazardous_waste")
            st.rerun()

    with upload_tab:
        st.caption(
            "Files stay on this computer. Inputs must be synthetic or approved public "
            "demonstration data because the GUI runs in reproducibility mode only."
        )
        calibration_upload = st.file_uploader("Calibration dataset (.csv)", type=["csv"])
        release_upload = st.file_uploader("Release dataset (.csv)", type=["csv"])
        config_upload = st.file_uploader("Configuration (.yaml or .yml)", type=["yaml", "yml"])
        public_confirmation = st.checkbox(
            "I confirm that uploaded inputs are synthetic or approved public demonstration data."
        )
        if st.button("Apply uploaded inputs", disabled=not public_confirmation):
            try:
                if calibration_upload is None or release_upload is None or config_upload is None:
                    raise ValueError("Calibration CSV, release CSV and configuration YAML are all required")
                st.session_state.calibration = _parse_uploaded_csv(calibration_upload)
                st.session_state.release = _parse_uploaded_csv(release_upload)
                st.session_state.config = _parse_uploaded_yaml(config_upload)
                st.session_state.dataset_label = "Uploaded public/synthetic data"
                st.session_state.calibration_name = calibration_upload.name
                st.session_state.release_name = release_upload.name
                st.session_state.config_name = config_upload.name
                st.session_state.release_preview_authorized = False
                st.session_state.pop("yaml_editor", None)
                st.session_state.pop("field_editor", None)
                _invalidate_outcomes()
                st.rerun()
            except Exception as exc:
                _friendly_error("Inputs were not loaded", exc)


def _render_hazardous_waste_requirements() -> None:
    try:
        catalog = load_requirements()
    except (OSError, ValueError) as exc:
        _friendly_error("需求清单无法读取", exc)
        return
    st.subheader("危险废物业务字段需求")
    st.warning(
        "当前只有字段需求，没有实际业务观测数据。本页不是可运行配置，"
        "不会加载校准集或发布集，不会生成隐私发布结果，也不改变当前运行。"
    )
    columns = st.columns(4)
    columns[0].metric("具名需求字段", len(catalog["fields"]))
    columns[1].metric("业务分组", len(catalog["groups"]))
    columns[2].metric("明确数值字段", sum(item["kind"] == "numeric" for item in catalog["fields"]))
    columns[3].metric("已提供业务记录", 0)
    selected_group = st.selectbox(
        "按业务分组查看", ["全部字段"] + catalog["groups"], key="requirements_group"
    )
    rows = requirement_rows(catalog, None if selected_group == "全部字段" else selected_group)
    st.dataframe(
        rows[["字段名称", "数据形态", "当前接入建议", "单位/粒度"]],
        hide_index=True, use_container_width=True,
    )
    with st.expander("查看单个字段的处理要求"):
        selected_name = st.selectbox(
            "选择需求字段", rows["字段名称"].tolist(), key="requirement_field_details"
        )
        detail = rows.loc[rows["字段名称"] == selected_name].iloc[0]
        st.write("**字段含义**：" + detail["字段含义"])
        st.write("**数据形态**：" + detail["数据形态"])
        st.write("**当前接入建议**：" + detail["当前接入建议"])
        st.write("**单位/粒度**：" + detail["单位/粒度"])
        st.write("**建议列名（待确认）**：`" + detail["建议列名（待确认）"] + "`")
        st.write("**来源接口（需求声明）**：" + detail["来源接口（需求声明）"])
        st.caption(detail["原表位置"] + "；完整字段对照可从下方下载。")
    st.caption(
        "字段和接口名称来自需求文件，接入建议是软件映射说明，不代表接口已经接通。"
        "建议英文列名不是原始接口键。原表编号有空缺，不补造缺失字段。"
    )

    with st.expander("接入前需要准备什么", expanded=True):
        st.dataframe(
            pd.DataFrame(CHECKLIST, columns=["待确认事项", "准备要求"]),
            hide_index=True,
            use_container_width=True,
        )
    with st.expander("处理边界与物理约束"):
        st.markdown(
            "- **数值量**：年产废量、运输重量、年处置能力、实际年处置量是Laplace候选，公开边界仍待确认。\n"
            "- **类别**：危废代码虽包含数字，仍是类别；GRR需要事先确定的公开域，高基数效用尚未验证。\n"
            "- **多值**：危险特性、产废种类、许可类别及组合工艺不能直接当作普通单选字段。\n"
            "- **标识与文本**：名称、详细地址、电话、车牌和联单编号默认不进入公开分析表；GPS轨迹不支持。\n"
            "- **保护粒度**：先分别确定产生单位或处置单位的一主体一行年度表；运输明细需先定义汇总规则。\n"
            "- **约束**：不能假定年产废量=运输量=处置量，也不支持容量不等式。需求表缺少完整收支字段，不自动添加等式。\n"
            "- **用途**：用于研究性统计共享，不替代真实联单、实时调度或应急作业记录。"
        )
    left, right = st.columns(2)
    left.download_button(
        "下载字段需求对照表", data=requirements_csv(catalog),
        file_name="hazardous_waste_field_requirements.csv", mime="text/csv",
        icon=":material/download:",
    )
    right.download_button(
        "下载待补配置清单", data=readiness_checklist_csv(),
        file_name="hazardous_waste_readiness_checklist.csv", mime="text/csv",
        icon=":material/download:",
    )
    st.caption("以上下载均为需求文档，不是release_data.csv，也不是可直接运行的YAML配置。")
    with st.expander("需求来源"):
        source = catalog["source"]
        st.write("{} · {} · {}".format(source["filename"], source["sheet"], source["range"]))
        st.code("SHA-256: " + source["sha256"], language="text")
        st.write(source["note"])


def _render_data_preview() -> None:
    if not _ready():
        st.info("Load an example or upload all three input files to continue.")
        return
    config = st.session_state.config
    calibration = st.session_state.calibration
    release = st.session_state.release

    _section_header("Input inspection", "Review dimensions and detected types before formal validation.")
    calibration_tab, release_tab = st.tabs(["Calibration dataset", "Release dataset"])
    with calibration_tab:
        st.caption(
            "Used to estimate risk and utility parameters. Sensitive-target values are "
            "intentionally omitted from the GUI preview."
        )
        st.write("File: `{}`".format(st.session_state.calibration_name))
        _show_table_profile("Calibration profile", calibration)
        st.dataframe(
            sanitized_calibration_preview(calibration, config),
            hide_index=True,
            use_container_width=True,
        )

    with release_tab:
        st.caption("The source table prepared for differentially private release.")
        st.write("File: `{}`".format(st.session_state.release_name))
        _show_table_profile("Release profile", release)
        show_release = st.checkbox(
            "Show local source-record preview",
            value=st.session_state.release_preview_authorized,
            help="Off by default so original release records are not displayed during a demonstration.",
        )
        st.session_state.release_preview_authorized = show_release
        if show_release:
            st.warning("This is a local source preview, not a public RUPA output.")
            st.dataframe(release.head(10), hide_index=True, use_container_width=True)
        else:
            st.info("Original release records are hidden by default.")


def _render_basic_configuration() -> None:
    if not _ready():
        return
    config = st.session_state.config
    privacy = config.get("privacy", {})
    schema = config.get("schema", {})
    adjacency = config.get("adjacency", {})
    columns = list(dict.fromkeys(
        list(st.session_state.calibration.columns) + list(st.session_state.release.columns)
    ))
    target_default = schema.get("sensitive_target", "")
    id_default = adjacency.get("privacy_unit_id", "")
    target_options = list(dict.fromkeys(([target_default] if target_default else []) + columns))
    id_options = list(dict.fromkeys(([id_default] if id_default else []) + columns))

    _section_header("Core parameters", "Frequently adjusted research parameters; advanced settings remain in YAML.")
    with st.form("basic_config_form"):
        b1, b2, b3 = st.columns(3)
        epsilon_total = b1.number_input(
            "Total epsilon", min_value=0.0, value=float(privacy.get("epsilon_total", 5.0)), format="%.6f"
        )
        epsilon_numeric = b2.number_input(
            "Numerical epsilon", min_value=0.0, value=float(privacy.get("epsilon_numeric", 4.5)), format="%.6f"
        )
        epsilon_categorical = b3.number_input(
            "Categorical epsilon", min_value=0.0, value=float(privacy.get("epsilon_categorical", 0.5)), format="%.6f"
        )
        b4, b5, b6 = st.columns(3)
        utility_alpha = b4.number_input(
            "Utility alpha", min_value=0.0, max_value=1.0, value=float(privacy.get("utility_alpha", 0.6))
        )
        repair_alpha = b5.number_input(
            "Repair alpha", min_value=0.0, max_value=1.0, value=float(privacy.get("repair_alpha", 0.98))
        )
        random_seed = b6.number_input(
            "Random seed", min_value=0, step=1, value=int(privacy.get("random_seed", 123) or 0)
        )
        b7, b8 = st.columns(2)
        sensitive_target = b7.selectbox(
            "Sensitive target", target_options, index=target_options.index(target_default) if target_default in target_options else 0
        )
        privacy_unit_id = b8.selectbox(
            "Privacy unit identifier", id_options, index=id_options.index(id_default) if id_default in id_options else 0
        )
        numeric_strategies = ["legacy_rupa", "uniform", "balanced_rupa"]
        numeric_labels = {"legacy_rupa": "Legacy RUPA (reference)",
                          "uniform": "Uniform baseline",
                          "balanced_rupa": "Balanced RUPA (experimental)"}
        current_numeric = privacy.get("numeric_budget_strategy", "legacy_rupa")
        numeric_budget_strategy = st.selectbox(
            "Numerical budget allocation", numeric_strategies,
            index=numeric_strategies.index(current_numeric) if current_numeric in numeric_strategies else 0,
            format_func=lambda value: numeric_labels[value],
            help="Balanced allocation limits concentration using calibration-only priorities. It does not guarantee downstream accuracy.",
        )
        submitted = st.form_submit_button("Apply basic configuration")
    if submitted:
        try:
            st.session_state.config = apply_basic_config(
                config,
                epsilon_total=epsilon_total,
                epsilon_numeric=epsilon_numeric,
                epsilon_categorical=epsilon_categorical,
                utility_alpha=utility_alpha,
                repair_alpha=repair_alpha,
                random_seed=random_seed,
                sensitive_target=sensitive_target,
                privacy_unit_id=privacy_unit_id,
                numeric_budget_strategy=numeric_budget_strategy,
            )
            st.session_state.pop("yaml_editor", None)
            _invalidate_outcomes()
            st.success("Basic values updated. They are not valid until formal validation passes.")
            st.rerun()
        except Exception as exc:
            _friendly_error("Configuration was not updated", exc)

    _section_header("Field contract", "Declare released types, public domains, the sensitive target and the privacy unit.")
    st.caption(
        "Public bounds and public category domains must be specified in advance. "
        "They are never inferred from release records."
    )
    rows = field_rows(st.session_state.config, columns)
    edited = st.data_editor(
        rows,
        disabled=["Field"],
        hide_index=True,
        use_container_width=True,
        key="field_editor",
    )
    if st.button("Apply field configuration"):
        try:
            st.session_state.config = apply_field_rows(st.session_state.config, edited)
            st.session_state.pop("yaml_editor", None)
            _invalidate_outcomes()
            st.success("Field configuration updated. Run validation next.")
            st.rerun()
        except Exception as exc:
            _friendly_error("Field configuration was not updated", exc)

    constraints = st.session_state.config.get("constraints", [])
    _section_header("Public linear constraints", "Only declared public equalities supported by the validated core are shown.")
    if constraints:
        expressions = pd.DataFrame(
            {
                "Constraint": [item.get("name", "") for item in constraints],
                "Public equality": [constraint_expression(item) for item in constraints],
            }
        )
        st.dataframe(expressions, hide_index=True, use_container_width=True)
    else:
        st.info("No public linear equalities are configured.")

    with st.expander("Advanced YAML configuration"):
        yaml_text = st.text_area(
            "Edit YAML",
            value=yaml.safe_dump(st.session_state.config, sort_keys=False, allow_unicode=True),
            height=420,
            key="yaml_editor",
        )
        if st.button("Apply YAML configuration"):
            try:
                parsed = yaml.safe_load(yaml_text)
                if not isinstance(parsed, dict):
                    raise ValueError("Configuration root must be a mapping")
                st.session_state.config = parsed
                _invalidate_outcomes()
                st.success("YAML updated. Run formal validation next.")
                st.rerun()
            except Exception as exc:
                _friendly_error("YAML was not applied", exc)


def _configuration_summary() -> None:
    if not st.session_state.config:
        return
    values = _privacy_values(st.session_state.config)
    _section_header("Configuration summary")
    frame = pd.DataFrame(
        [
            ("Privacy", "Total epsilon", values["epsilon_total"]),
            ("Privacy", "Numerical epsilon", values["epsilon_numeric"]),
            ("Privacy", "Categorical epsilon", values["epsilon_categorical"]),
            ("Utility", "Alpha", values["utility_alpha"]),
            ("Physical repair", "Repair alpha", values["repair_alpha"]),
            ("Execution", "Mode", values["randomness_mode"]),
            ("Execution", "Seed", values["random_seed"]),
        ],
        columns=["Group", "Parameter", "Value"],
    )
    frame["Value"] = frame["Value"].map(str)
    st.dataframe(frame, hide_index=True, use_container_width=True)
    st.warning("Configuration preview does not mean the configuration is valid.")


def page_data() -> None:
    _page_header(
        "Data",
        "Load public or synthetic inputs and inspect their structure without exposing protected values by default.",
    )
    _render_data_inputs()
    _render_data_preview()


def page_configuration() -> None:
    _page_header(
        "Configuration",
        "Review privacy parameters, field-level public metadata and supported public linear constraints.",
    )
    with st.expander("危废需求与当前运行配置的区别"):
        st.write(
            "Data页中的危废需求是待准备字段清单，不是当前运行配置。"
            "只有实际加载的CSV和YAML才会进入下面的编辑器与正式验证；"
            "本轮未根据需求自动设置公开边界、类别域、敏感目标、epsilon或物理约束。"
            "已有危废合成示例仍是演示数据，不代表已经取得这些业务接口的数据。"
        )
    if not _ready():
        st.info("Load an example or all three input files on the Data page first.")
        return
    _render_basic_configuration()
    _configuration_summary()


def page_validation() -> None:
    _page_header(
        "Validation",
        "The button below calls the formal RUPA configuration, data and constraint validators.",
    )
    if not _ready():
        st.info("Load data and configuration first.")
        return
    _configuration_summary()
    _section_header("Formal validation", "No pipeline stage can run until the supported data, privacy and constraint contracts pass.")
    if st.button("Run validation", type="primary"):
        try:
            result = validate_demo(
                st.session_state.config,
                st.session_state.calibration,
                st.session_state.release,
            )
            _record_validation_success(result)
        except Exception as exc:
            _record_validation_failure(exc)
        st.rerun()

    if st.session_state.validation:
        result = st.session_state.validation
        diagnostics = result["constraint_validation"]
        st.success("VALIDATION PASSED | All supported configuration and data contracts were accepted.")
        checks = [
            "Configuration valid",
            "Calibration and release schema valid",
            "Public bounds and category domains valid",
            "Privacy-unit contract valid",
            "Physical constraints valid",
        ]
        st.dataframe(
            pd.DataFrame({"Status": ["PASS"] * len(checks), "Validation check": checks}),
            hide_index=True,
            use_container_width=True,
        )
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Calibration rows", result["calibration_rows"])
        c2.metric("Release rows", result["release_rows"])
        c3.metric("Released attributes", len(result["released_columns"]))
        c4.metric("Public constraints", diagnostics.get("matrix_rows", 0))
        _section_header("Constraint-system diagnostics")
        table = pd.DataFrame(
            [
                ("Privacy unit ID", result["privacy_unit_id"]),
                ("Adjacency", result["adjacency"]),
                ("Constraint decision", diagnostics.get("decision")),
                ("Constraint rank", diagnostics.get("rank")),
                ("Expected rank", diagnostics.get("expected_rank")),
                ("Condition number", diagnostics.get("condition_number")),
                ("Number of constraints", diagnostics.get("matrix_rows")),
            ],
            columns=["Check", "Result"],
        )
        table["Result"] = table["Result"].map(str)
        st.dataframe(table, hide_index=True, use_container_width=True)
    elif st.session_state.validation_error:
        st.error("VALIDATION FAILED")
        with st.expander("Validation error"):
            st.code(st.session_state.validation_error, language="text")
    else:
        st.info("Validation has not been run for the current inputs.")


def page_run() -> None:
    _page_header("Run RUPA", "Execute the validated pipeline and write the formal public run artifacts.")
    st.warning(
        "GUI execution mode: reproducibility only. Do not use this interface for a confidential production release."
    )
    if not _ready():
        st.info("Load inputs first.")
        return
    if not st.session_state.validation:
        st.info("Run formal validation before execution.")
        return
    values = _privacy_values(st.session_state.config)
    _section_header("Execution contract", "The values below are read from the configuration that passed formal validation.")
    c1, c2, c3 = st.columns(3)
    c1.metric("Total epsilon", values["epsilon_total"])
    c2.metric("Random seed", values["random_seed"])
    c3.metric("Repair alpha", values["repair_alpha"])

    _section_header("Pipeline execution", "Progress messages correspond to actual API stages; no simulated progress is shown.")
    if st.button("Run RUPA", type="primary", use_container_width=False):
        try:
            with st.status("RUPA execution", expanded=True) as status:
                def update(stage: str, state: str) -> None:
                    status.write("{}: {}".format(stage, state))

                run = execute_demo(
                    st.session_state.config,
                    st.session_state.calibration,
                    st.session_state.release,
                    output_root=RUNS_ROOT,
                    progress=update,
                )
                _record_run_success(run)
                del run
                status.update(label="Run completed successfully", state="complete", expanded=False)
            st.rerun()
        except Exception as exc:
            _record_run_failure()
            _friendly_error("RUPA execution failed", exc)

    if st.session_state.run_summary:
        summary = st.session_state.run_summary
        _section_header("Completed public run")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Release rows", summary["release_rows"])
        c2.metric("Released attributes", summary["released_attributes"])
        c3.metric("Artifacts", summary["artifact_count"])
        c4.metric("Runtime", "{:.2f} s".format(summary["runtime_seconds"]))
        st.write("Run ID: `{}`".format(summary["run_id"]))


def _public_run_or_message() -> Optional[dict]:
    if not st.session_state.run_directory:
        st.info("No completed run is available. Validate and run RUPA first.")
        return None
    try:
        return load_public_run(Path(st.session_state.run_directory))
    except Exception as exc:
        _friendly_error("Public run could not be verified", exc)
        return None


def _residual_reduction(physical: Mapping) -> Optional[float]:
    states = physical.get("states", {})
    before = states.get("noisy", {}).get("rms")
    after = states.get("final_clipped", {}).get("rms")
    if before in (None, 0) or after is None:
        return None
    return 100.0 * (float(before) - float(after)) / float(before)


def _chart(
    frame: pd.DataFrame,
    value: str,
    *,
    title: str,
    color: str,
) -> None:
    if frame.empty or "feature" not in frame or value not in frame:
        st.info("This public artifact does not contain chartable data.")
        return
    chart_data = frame[["feature", value]].dropna().copy()
    if chart_data.empty or alt is None:
        st.bar_chart(frame.set_index("feature")[[value]])
        return
    height = min(520, max(240, 34 * len(chart_data)))
    chart = (
        alt.Chart(chart_data)
        .mark_bar(color=color, cornerRadiusEnd=2, size=18)
        .encode(
            x=alt.X("{}:Q".format(value), title=title, axis=alt.Axis(grid=True, gridColor="#E7ECF2")),
            y=alt.Y("feature:N", title=None, sort="-x", axis=alt.Axis(labelLimit=220)),
            tooltip=[
                alt.Tooltip("feature:N", title="Attribute"),
                alt.Tooltip("{}:Q".format(value), title=title, format=".6f"),
            ],
        )
        .properties(height=height)
        .configure_view(strokeWidth=0)
        .configure_axis(labelColor="#475467", titleColor="#344054")
    )
    st.altair_chart(chart, use_container_width=True)


def _physical_chart(frame: pd.DataFrame) -> None:
    if frame.empty:
        return
    long = frame.melt(
        id_vars=["Constraint"],
        value_vars=["Before repair RMS", "Final clipped RMS"],
        var_name="State",
        value_name="Residual RMS",
    )
    if alt is None:
        st.bar_chart(frame.set_index("Constraint")[["Before repair RMS", "Final clipped RMS"]])
        return
    chart = (
        alt.Chart(long)
        .mark_bar(cornerRadiusEnd=2)
        .encode(
            x=alt.X("Residual RMS:Q", axis=alt.Axis(grid=True, gridColor="#E7ECF2")),
            y=alt.Y("Constraint:N", title=None, axis=alt.Axis(labelLimit=240)),
            yOffset=alt.YOffset("State:N", title=None),
            color=alt.Color(
                "State:N",
                scale=alt.Scale(
                    domain=["Before repair RMS", "Final clipped RMS"],
                    range=[CHART_COLORS["muted"], CHART_COLORS["secondary"]],
                ),
                legend=alt.Legend(orient="top", title=None),
            ),
            tooltip=["Constraint:N", "State:N", alt.Tooltip("Residual RMS:Q", format=".6g")],
        )
        .properties(height=min(480, max(240, 50 * len(frame))))
        .configure_view(strokeWidth=0)
        .configure_axis(labelColor="#475467", titleColor="#344054")
    )
    st.altair_chart(chart, use_container_width=True)


def _physical_constraint_table(physical: Mapping) -> pd.DataFrame:
    states = physical.get("states", {})
    before = states.get("noisy", {}).get("per_constraint_rms", {})
    after = states.get("final_clipped", {}).get("per_constraint_rms", {})
    rows = []
    for name in sorted(set(before) | set(after)):
        first = float(before.get(name, float("nan")))
        final = float(after.get(name, float("nan")))
        reduction = (
            100.0 * (first - final) / first
            if pd.notna(first) and pd.notna(final) and first != 0.0
            else float("nan")
        )
        rows.append(
            {
                "Constraint": name,
                "Before repair RMS": first,
                "Final clipped RMS": final,
                "Reduction (%)": reduction,
            }
        )
    return pd.DataFrame(rows)


def page_analysis() -> None:
    _page_header(
        "Analysis",
        "Inspect risk, utility, privacy allocation, released data, physical residuals and the public run audit.",
    )
    public_run = _public_run_or_message()
    if public_run is None:
        return
    csv_data = public_run["csv"]
    json_data = public_run["json"]
    config = json_data.get("run_config.json", {})
    physical = json_data.get("physical_metrics.json", {})
    metadata = json_data.get("metadata.json", {})
    risk = csv_data.get("risk_scores.csv", pd.DataFrame())
    utility = csv_data.get("utility_weights.csv", pd.DataFrame())
    allocation = csv_data.get("epsilon_allocation.csv", pd.DataFrame())
    release = csv_data.get("release_data.csv", pd.DataFrame())

    tabs = st.tabs(
        [
            "Overview",
            "Risk",
            "Utility",
            "Epsilon Allocation",
            "Released Data",
            "Constraint Residuals",
            "Audit",
        ]
    )
    with tabs[0]:
        schema = config.get("schema", {})
        reduction = _residual_reduction(physical)
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Released rows", len(release))
        c2.metric("Numerical attributes", len(schema.get("numeric_columns", [])))
        c3.metric("Categorical attributes", len(schema.get("categorical_columns", [])))
        c4.metric("Total epsilon", config.get("privacy", {}).get("epsilon_total", "N/A"))
        c5.metric(
            "Residual reduction",
            "{:.2f}%".format(reduction) if reduction is not None else "N/A",
        )
        st.write("Run ID: `{}`".format(public_run["run_id"]))
        st.caption(metadata.get("release_notice", ""))

    with tabs[1]:
        _section_header("Risk by attribute", "Published calibration diagnostics for each released attribute.")
        if risk.empty:
            st.info("Risk scores were not included in this public run.")
        else:
            st.caption(
                "NMI measures calibration-set association with the target, not an attack "
                "success probability or a differential privacy guarantee."
            )
            columns = [
                name
                for name in (
                    "feature",
                    "augmented_risk",
                    "single_nmi",
                    "joint_penalty",
                    "requested_bins",
                    "effective_bins",
                    "bin_collapse_severity",
                    "bin_warning",
                )
                if name in risk.columns
            ]
            st.dataframe(risk[columns], hide_index=True, use_container_width=True)
            _chart(
                risk,
                "augmented_risk",
                title="Augmented risk",
                color=CHART_COLORS["warning"],
            )
        joint = csv_data.get("joint_risk.csv", pd.DataFrame())
        if not joint.empty:
            with st.expander("Joint-risk diagnostic"):
                st.dataframe(joint.drop(columns=["run_id"], errors="ignore"), hide_index=True, use_container_width=True)

    with tabs[2]:
        _section_header("Utility weights", "Entropy evidence and declared regulatory priorities in the fitted utility weights.")
        st.write(
            "Final utility weights combine normalized entropy weights and normalized regulatory priors."
        )
        st.write("Utility alpha: `{}`".format(config.get("privacy", {}).get("utility_alpha", "N/A")))
        st.caption(
            "Utility weights are allocation priorities, not measured accuracy of the "
            "released data. Raw-dependent utility metrics are withheld from public runs."
        )
        if utility.empty:
            st.info("Utility weights were not included in this public run.")
        else:
            st.dataframe(utility.drop(columns=["run_id"], errors="ignore"), hide_index=True, use_container_width=True)
            _chart(
                utility,
                "utility_weight",
                title="Utility weight",
                color=CHART_COLORS["secondary"],
            )

    with tabs[3]:
        _section_header("Epsilon allocation", "Field-level privacy budgets emitted by the validated allocation stage.")
        if allocation.empty:
            st.info("Allocation details were not included in this public run.")
        else:
            joined = allocation.drop(columns=["run_id"], errors="ignore").copy()
            if not risk.empty:
                joined = joined.merge(risk[["feature", "augmented_risk"]], on="feature", how="left")
            if not utility.empty:
                joined = joined.merge(utility[["feature", "utility_weight"]], on="feature", how="left")
            joined = joined.rename(
                columns={
                    "augmented_risk": "risk",
                    "utility_weight": "utility",
                    "public_sensitivity": "sensitivity",
                }
            )
            order = [name for name in ("feature", "risk", "utility", "epsilon", "sensitivity") if name in joined]
            st.dataframe(joined[order], hide_index=True, use_container_width=True)
            _chart(
                allocation,
                "epsilon",
                title="Allocated epsilon",
                color=CHART_COLORS["primary"],
            )
            schema = config.get("schema", {})
            numeric = set(schema.get("numeric_columns", []))
            categorical = set(schema.get("categorical_columns", []))
            numeric_sum = allocation.loc[allocation["feature"].isin(numeric), "epsilon"].sum()
            categorical_sum = allocation.loc[allocation["feature"].isin(categorical), "epsilon"].sum()
            total_sum = allocation["epsilon"].sum()
            c1, c2, c3 = st.columns(3)
            c1.metric("Sum epsilon numeric", "{:.6f}".format(numeric_sum))
            c2.metric("Sum epsilon categorical", "{:.6f}".format(categorical_sum))
            c3.metric("Sum all fields", "{:.6f}".format(total_sum))
            st.caption(
                "Larger epsilon permits less perturbation and a weaker privacy bound. "
                "Allocation is not evidence that one method outperforms another."
            )

    with tabs[4]:
        _section_header("Final public release", "The protected table written by the formal public artifact writer.")
        st.write("This table is loaded from the formal `release_data.csv` artifact.")
        st.dataframe(release.head(20), hide_index=True, use_container_width=True)
        st.caption("Rows: {} | Columns: {}".format(len(release), len(release.columns)))
        release_path = public_run["run_directory"] / "release_data.csv"
        st.download_button(
            "Download released CSV",
            data=release_path.read_bytes(),
            file_name="release_data.csv",
            mime="text/csv",
        )

    with tabs[5]:
        _section_header("Public linear-constraint residuals", "Residual RMS before repair and after interpolation plus final clipping.")
        constraint_table = _physical_constraint_table(physical)
        if constraint_table.empty:
            st.info("No constraint residual table is available for this run.")
        else:
            st.dataframe(constraint_table, hide_index=True, use_container_width=True)
            _physical_chart(constraint_table)
        stage_table = physical_stage_table(physical)
        if not stage_table.empty:
            _section_header("Residuals across processing stages", "Ordered public aggregate diagnostics from this run.")
            if alt is not None:
                stage_chart = (
                    alt.Chart(stage_table.dropna(subset=["NRMS"]))
                    .mark_line(point=True, color=CHART_COLORS["secondary"])
                    .encode(
                        x=alt.X("Stage:N", sort=stage_table["Stage"].tolist(), title="Processing stage"),
                        y=alt.Y("NRMS:Q", title="Normalized residual RMS", scale=alt.Scale(zero=True)),
                        tooltip=["Stage:N", alt.Tooltip("NRMS:Q", format=".6g")],
                    )
                    .properties(height=240)
                )
                st.altair_chart(stage_chart, use_container_width=True)
            st.dataframe(stage_table.drop(columns=["Order"]), hide_index=True, use_container_width=True)
            exported_table = stage_table.assign(run_id=public_run["run_id"])
            st.download_button(
                "Download residual plot data",
                data=exported_table.to_csv(index=False).encode("utf-8"),
                file_name=public_run["run_id"] + "_constraint_stages.csv",
                mime="text/csv",
            )
            st.caption(
                "This is a processing-stage curve, not a time series or a multi-seed "
                "benchmark. Interpolation and clipping can increase residuals again. "
                "No confidential row-level intermediates are exported."
            )
        st.warning(
            "RUPA reduces residuals for supported public linear equality constraints. "
            "Exact physical consistency is not guaranteed."
        )

    with tabs[6]:
        _section_header("Public run audit", "Run identity, software metadata and manifest-bound public artifacts.")
        audit = pd.DataFrame(
            [
                ("Run ID", public_run["run_id"]),
                ("Timestamp", metadata.get("created_utc")),
                ("Software version", metadata.get("version")),
                ("Execution mode", public_run["inspection"].get("randomness_mode")),
                ("Seed", config.get("privacy", {}).get("random_seed")),
                ("Manifest verification", "PASS"),
                ("Artifact count", public_run["inspection"].get("artifact_count")),
            ],
            columns=["Item", "Value"],
        )
        audit["Value"] = audit["Value"].map(str)
        st.dataframe(audit, hide_index=True, use_container_width=True)
        artifact_table = pd.DataFrame(public_run["manifest"].get("artifacts", []))
        st.dataframe(artifact_table, hide_index=True, use_container_width=True)
        st.caption("Internal audit directories and raw intermediates are not read or displayed by this GUI.")

    st.divider()
    if st.button("Continue to Export →", type="primary", use_container_width=True):
        _request_workflow_navigation("07  Export")
        st.rerun()


def page_export() -> None:
    _page_header(
        "Export & Reproducibility",
        "Download the verified public release or reproduce the run through the official CLI.",
    )
    public_run = _public_run_or_message()
    if public_run is None:
        return
    run_directory = public_run["run_directory"]
    release_path = run_directory / "release_data.csv"
    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            "Download released dataset",
            data=release_path.read_bytes(),
            file_name="release_data.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with c2:
        try:
            package = build_public_run_archive(run_directory)
            st.download_button(
                "Download public run package",
                data=package,
                file_name=public_run["run_id"] + "_public.zip",
                mime="application/zip",
                use_container_width=True,
            )
        except Exception as exc:
            _friendly_error("Public package could not be created", exc)

    _section_header("Package safety", "The export is assembled from the verified manifest whitelist only.")
    st.write(
        "The ZIP is assembled from the verified `manifest.json` whitelist. It does not "
        "recursively copy the output directory."
    )
    st.dataframe(
        pd.DataFrame({"Included public artifact": ["manifest.json"] + public_run["artifact_names"]}),
        hide_index=True,
        use_container_width=True,
    )

    _section_header("Reproduce this run", "Use the same inputs and configuration with the official command-line interface.")
    config = public_run["json"].get("run_config.json", {})
    seed = config.get("privacy", {}).get("random_seed")
    st.write("Fixed seed: `{}`".format(seed))
    commands = reproduction_commands(
        st.session_state.calibration_name,
        st.session_state.release_name,
        st.session_state.config_name,
        "reproduced_run",
    )
    st.code(commands, language="powershell")
    if st.session_state.config:
        st.download_button(
            "Download config.yaml",
            data=yaml.safe_dump(st.session_state.config, sort_keys=False, allow_unicode=True).encode("utf-8"),
            file_name="config.yaml",
            mime="application/x-yaml",
        )
    st.info(
        "Production releases requiring persistent privacy-budget governance must use the official CLI workflow."
    )


def main() -> None:
    if st is None:
        raise RuntimeError("Streamlit is not installed. Install the project with the demo extra.")
    st.set_page_config(
        page_title="RUPA",
        page_icon=":material/shield_lock:",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(RUPA_STYLES, unsafe_allow_html=True)
    init_state()
    _prepare_workflow_navigation()
    page = _render_sidebar()
    _software_header()
    from research_page import render_research_page
    routes = {
        "01  Overview": page_overview,
        "02  Data": page_data,
        "03  Configuration": page_configuration,
        "04  Validation": page_validation,
        "05  Run": page_run,
        "06  Analysis": page_analysis,
        "07  Export": page_export,
        "08  Research": render_research_page,
    }
    routes[page]()


if __name__ == "__main__":
    main()
