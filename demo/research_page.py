"""Optional two-view research screen; reference workflow is unchanged."""
from pathlib import Path
import streamlit as st
from demo_support import RUNS_ROOT
from research_support import execute_research, load_research_run, research_archive


def render_research_page():
    st.header("Two-view Research")
    st.warning("Experimental research mode · 仅用于合成或已确认公开的数据，不用于保密生产发布。")
    st.write("数值预算的一半用于逐行扰动，另一半用于受保护总量；仅用这两个受保护视图和公开约束重建行表。类别字段继续使用 GRR。")
    if st.session_state.get("calibration") is None or st.session_state.get("release") is None:
        st.info("请先在 Overview 加载官方、危废或水处理案例，再打开本页。")
        return
    config = st.session_state.config
    values = config.get("privacy", {})
    for col, label, value in zip(st.columns(4),
        ["Row numerical ε", "Total-query ε", "Categorical ε", "Total ε"],
        [values.get("epsilon_numeric", 0) * .5, values.get("epsilon_numeric", 0) * .5,
         values.get("epsilon_categorical", 0), values.get("epsilon_total", 0)]):
        col.metric(label, "{:.6g}".format(value))
    strategy = st.radio("Total-view allocation", ["hybrid_workload", "hybrid_uniform"],
        format_func=lambda value: {"hybrid_workload": "Task-directed + risk cap", "hybrid_uniform": "Uniform comparator"}[value],
        horizontal=True, key="research_strategy")
    st.caption("本模式固定数值预算 1:1、逐行数值与类别均匀分配；原流程的 numeric strategy 和 repair alpha 不用于本模式。")
    if st.button("Run two-view research", type="primary"):
        st.session_state.pop("research_run_directory", None)
        try:
            with st.status("Two-view workflow", expanded=True) as status:
                run = execute_research(config, st.session_state.calibration, st.session_state.release,
                    RUNS_ROOT, strategy, progress=lambda name, state: status.write(name + ": " + state))
                st.session_state.research_run_directory = str(run["folder"])
                status.update(label="Research run completed", state="complete", expanded=False)
        except Exception as exc:
            st.error("Research run failed: " + str(exc))
    folder = st.session_state.get("research_run_directory")
    if not folder:
        return
    try:
        run = load_research_run(Path(folder))
    except Exception as exc:
        st.error("Research artifacts could not be verified: " + str(exc))
        return
    st.subheader("Research result")
    st.write("Run ID: `" + run["run_id"] + "`")
    st.caption("Completed strategy: " + run["metadata"]["strategy"] + " | " + str(run["metadata"]["rows"]) + " rows")
    st.dataframe(run["data"].head(10), hide_index=True, use_container_width=True)
    st.subheader("Composed field budgets")
    st.dataframe(run["allocation"].drop(columns="run_id"), hide_index=True, use_container_width=True)
    st.bar_chart(run["allocation"].set_index("feature")[["row_view_epsilon", "total_view_epsilon"]])
    diagnostic = run["diagnostics"]
    c1, c2, c3 = st.columns(3)
    c1.metric("Before reconstruction RMS", "{:.6g}".format(diagnostic["before_reconstruction_rms"]) if diagnostic["before_reconstruction_rms"] is not None else "No constraints")
    c2.metric("After reconstruction RMS", "{:.6g}".format(diagnostic["after_reconstruction_rms"]) if diagnostic["after_reconstruction_rms"] is not None else "No constraints")
    c3.metric("Composed epsilon", "{:.6g}".format(diagnostic["composed_epsilon"]))
    st.warning("总量改善不等于每条原始记录、方差或相关性被保留；任务预算也并非所有误差指标都优于均匀预算。此处不显示原始记录对照。")
    a, b = st.columns(2)
    a.download_button("Download research CSV", (run["folder"] / "release_data.csv").read_bytes(),
        file_name="release_data.csv", mime="text/csv")
    b.download_button("Download research package", research_archive(run["folder"]),
        file_name=run["run_id"] + ".zip", mime="application/zip")
    st.caption(str(run["folder"]))
