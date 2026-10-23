"""The business catalog must not masquerade as observations or run state."""

import csv
import io
import sys
from copy import deepcopy
from pathlib import Path

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demo"
if str(DEMO) not in sys.path:
    sys.path.insert(0, str(DEMO))

from hazardous_waste_requirements import (  # noqa: E402
    CHECKLIST,
    KIND_LABELS,
    load_requirements,
    readiness_checklist_csv,
    requirement_rows,
    requirements_csv,
)


def test_catalog_preserves_named_fields_and_marks_missing_observations():
    catalog = load_requirements()
    assert catalog["status"] == "requirements_only_no_observations"
    assert catalog["kind"] == "business_requirements_not_pipeline_configuration"
    assert catalog["source"]["sheet"] == "Sheet1"
    assert catalog["source"]["range"] == "A1:F45"
    assert len(catalog["source"]["sha256"]) == 64
    fields = catalog["fields"]
    assert len(fields) == 31
    assert len({item["key"] for item in fields}) == 31
    assert {item["group"] for item in fields} == set(catalog["groups"])
    assert {item["number"] for item in fields} == (
        set(range(1, 41)) - {5, 9, 10, 11, 13, 14, 15, 20, 32}
    )
    assert {item["kind"] for item in fields} <= set(KIND_LABELS)
    assert not {"schema", "privacy", "constraints", "calibration", "release"} & set(catalog)
    for item in fields:
        assert not {"public_bounds", "public_categories", "values", "epsilon"} & set(item)
        assert "C{}".format(item["source_row"]) in set(
            requirement_rows(catalog)["原表位置"].str.split("!").str[-1]
        )


def test_numeric_candidates_and_unsupported_fields_are_not_misclassified():
    fields = {item["name"]: item for item in load_requirements()["fields"]}
    assert {name for name, item in fields.items() if item["kind"] == "numeric"} == {
        "年产废量", "运输重量", "年处置能力", "实际年处置量"
    }
    assert fields["危险废物代码"]["kind"] == "categorical"
    assert fields["联系人及电话"]["kind"] == "identifier"
    assert fields["GPS轨迹数据"]["kind"] == "trajectory"
    for name in ("危险特性标识", "主要产废种类", "许可处置类别", "主要处置工艺"):
        assert fields[name]["kind"] == "multivalue"


@pytest.mark.parametrize("index,count", [(0, 8), (1, 7), (2, 8), (3, 8)])
def test_business_group_filter(index, count):
    catalog = load_requirements()
    group = catalog["groups"][index]
    frame = requirement_rows(catalog, group)
    assert len(frame) == count
    assert set(frame["业务分组"]) == {group}


def test_requirement_downloads_are_documents_not_observational_data():
    catalog = load_requirements()
    payload = requirements_csv(catalog)
    assert payload.startswith(b"\xef\xbb\xbf")
    frame = pd.read_csv(io.BytesIO(payload))
    pd.testing.assert_frame_equal(frame, requirement_rows(catalog))
    assert len(frame) == 31
    assert "来源接口（需求声明）" in frame
    assert "字段含义" in frame
    checklist = list(csv.DictReader(io.StringIO(readiness_checklist_csv().decode("utf-8-sig"))))
    assert len(checklist) == len(CHECKLIST)
    assert all(row["作者填写"] == row["证据或来源"] == "" for row in checklist)


def test_catalog_does_not_depend_on_original_excel_or_current_directory(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert len(load_requirements()["fields"]) == 31


def _app(monkeypatch, tmp_path):
    testing = pytest.importorskip("streamlit.testing.v1")
    import demo_support

    monkeypatch.setattr(demo_support, "RUNS_ROOT", tmp_path / "runs")
    return testing.AppTest.from_file(DEMO / "app.py", default_timeout=30).run()


def _button(app, label):
    return next(button for button in app.button if button.label == label)


def test_requirements_can_be_opened_without_data_and_do_not_unlock_execution(monkeypatch, tmp_path):
    app = _app(monkeypatch, tmp_path)
    _button(app, "查看危废字段需求").click().run()
    assert app.radio[0].value == "02  Data"
    assert app.tabs[0].label == "危废业务需求（无实际数据）"
    assert len(app.dataframe[0].value) == 31
    assert any("没有实际业务观测数据" in warning.value for warning in app.warning)
    next(item for item in app.selectbox if item.label == "选择需求字段").set_value(
        "GPS轨迹数据"
    ).run()
    assert any("当前不支持轨迹隐私机制" in item.value for item in app.markdown)
    for key in ("calibration", "release", "config", "validation", "run_directory", "run_summary"):
        assert app.session_state[key] is None
    next(item for item in app.selectbox if item.label == "按业务分组查看").set_value(
        "危险废物产生单位"
    ).run()
    assert len(app.dataframe[0].value) == 7
    app.radio[0].set_value("05  Run").run()
    assert app.radio[0].value == "04  Validation"
    assert not any(button.label == "Run RUPA" for button in app.button)
    assert not (tmp_path / "runs").exists()
    assert not app.exception


def test_requirements_browsing_preserves_completed_official_run(monkeypatch, tmp_path):
    app = _app(monkeypatch, tmp_path)
    _button(app, "Load official synthetic example").click().run()
    app.radio[0].set_value("04  Validation").run()
    _button(app, "Run validation").click().run()
    _button(app, "Run RUPA").click().run(timeout=60)
    assert app.radio[0].value == "06  Analysis"
    before = {key: deepcopy(app.session_state[key]) for key in (
        "calibration", "release", "config", "validation", "run_directory", "run_summary"
    )}
    app.radio[0].set_value("02  Data").run()
    assert app.tabs[0].label == "危废业务需求（无实际数据）"
    for key, value in before.items():
        if isinstance(value, pd.DataFrame):
            pd.testing.assert_frame_equal(app.session_state[key], value)
        else:
            assert app.session_state[key] == value
    catalog = load_requirements()
    assert requirements_csv(catalog)
    assert readiness_checklist_csv()
    assert len(list((tmp_path / "runs").iterdir())) == 1
    app.radio[0].set_value("06  Analysis").run()
    assert app.session_state["run_summary"]["run_id"] == before["run_summary"]["run_id"]
    assert not app.exception


def test_configuration_explains_requirements_without_creating_a_configuration(monkeypatch, tmp_path):
    app = _app(monkeypatch, tmp_path)
    app.radio[0].set_value("03  Configuration").run()
    assert any("待准备字段清单" in item.value for item in app.markdown)
    assert app.session_state["config"] is None
    assert not app.exception


def test_distribution_resource_lists_include_requirements_catalog():
    relative = "demo/assets/hazardous_waste_requirements.json"
    assert relative in (ROOT / "MANIFEST.in").read_text(encoding="utf-8")
    spec = (ROOT / "packaging/windows/RUPA.spec").read_text(encoding="utf-8")
    assert relative in spec
    assert '"hazardous_waste_requirements.py"' in spec
    assert '"hazardous_waste_requirements"' in spec
