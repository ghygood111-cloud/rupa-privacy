import json
import hashlib
import importlib
import io
import sys
import zipfile
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest


DEMO_ROOT = Path(__file__).resolve().parents[1] / "demo"
if str(DEMO_ROOT) not in sys.path:
    sys.path.insert(0, str(DEMO_ROOT))

from demo_support import (  # noqa: E402
    apply_basic_config,
    apply_field_rows,
    blank_config,
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
from rupa_privacy.exceptions import PrivacySafetyError  # noqa: E402
from result_presentation import physical_stage_table  # noqa: E402


def test_demo_app_imports_without_starting_streamlit():
    module = importlib.import_module("app")
    assert callable(module.main)
    assert module.PAGES == (
        "01  Overview",
        "02  Data",
        "03  Configuration",
        "04  Validation",
        "05  Run",
        "06  Analysis",
        "07  Export",
        "08  Research",
    )
    for variable in (
        "--rupa-primary",
        "--rupa-bg",
        "--rupa-card",
        "--rupa-border",
        "--rupa-text",
        "--rupa-success",
        "--rupa-warning",
    ):
        assert variable in module.RUPA_STYLES


def test_workflow_prerequisites_keep_forward_pages_behind_completed_steps():
    module = importlib.import_module("app")
    assert module._authorized_workflow_page(
        "05  Run", validation_passed=False, run_completed=False
    ) == "04  Validation"
    assert module._authorized_workflow_page(
        "06  Analysis", validation_passed=False, run_completed=False
    ) == "04  Validation"
    assert module._authorized_workflow_page(
        "06  Analysis", validation_passed=True, run_completed=False
    ) == "05  Run"
    assert module._authorized_workflow_page(
        "07  Export", validation_passed=True, run_completed=True
    ) == "07  Export"


def test_validation_and_run_navigation_only_queue_after_success(monkeypatch):
    module = importlib.import_module("app")
    class SessionState(dict):
        __getattr__ = dict.__getitem__
        __setattr__ = dict.__setitem__

    state = SessionState({
        module.WORKFLOW_PAGE_KEY: "04  Validation",
        module.PENDING_WORKFLOW_PAGE_KEY: None,
        "validation": None,
        "validation_error": None,
        "run_directory": None,
        "run_summary": None,
    })
    monkeypatch.setattr(module, "st", SimpleNamespace(session_state=state))
    adjacency = SimpleNamespace(privacy_unit_id="enterprise_id", type="fixed_roster_replace_one")
    result = {
        "calibration_rows": 4,
        "release_rows": 4,
        "released_columns": ["x"],
        "constraint_validation": {"decision": "PASS"},
        "adjacency": adjacency,
    }

    module._record_validation_failure(ValueError("bad config"))
    assert state[module.PENDING_WORKFLOW_PAGE_KEY] is None
    module._prepare_workflow_navigation()
    assert state[module.WORKFLOW_PAGE_KEY] == "04  Validation"

    module._record_validation_success(result)
    assert state[module.PENDING_WORKFLOW_PAGE_KEY] == "05  Run"
    module._prepare_workflow_navigation()
    assert state[module.WORKFLOW_PAGE_KEY] == "05  Run"
    assert state[module.PENDING_WORKFLOW_PAGE_KEY] is None

    module._record_run_failure()
    assert state[module.PENDING_WORKFLOW_PAGE_KEY] is None
    module._prepare_workflow_navigation()
    assert state[module.WORKFLOW_PAGE_KEY] == "05  Run"

    run = SimpleNamespace(
        run_directory=Path("runs/example"),
        run_id="example",
        runtime_seconds=1.0,
        inspection={"release_rows": 4, "artifact_count": 13},
        schema=SimpleNamespace(released_columns=["x"]),
    )
    module._record_run_success(run)
    assert state[module.PENDING_WORKFLOW_PAGE_KEY] == "06  Analysis"
    module._prepare_workflow_navigation()
    assert state[module.WORKFLOW_PAGE_KEY] == "06  Analysis"

    module._request_workflow_navigation("07  Export")
    module._prepare_workflow_navigation()
    assert state[module.WORKFLOW_PAGE_KEY] == "07  Export"


def _app_test_with_temporary_runs(monkeypatch, tmp_path):
    streamlit_testing = pytest.importorskip("streamlit.testing.v1")
    import demo_support

    monkeypatch.setattr(demo_support, "RUNS_ROOT", tmp_path / "runs")
    return streamlit_testing.AppTest.from_file(
        DEMO_ROOT / "app.py", default_timeout=30
    ).run(timeout=30)


def _app_button(app_test, label):
    return next(button for button in app_test.button if button.label == label)


def _load_official_example_for_navigation_test(app_test):
    _app_button(app_test, "Load official synthetic example").click().run(timeout=30)
    app_test.radio[0].set_value("04  Validation").run(timeout=30)


def test_streamlit_workflow_successfully_advances_without_reexecution(monkeypatch, tmp_path):
    app_test = _app_test_with_temporary_runs(monkeypatch, tmp_path)
    _load_official_example_for_navigation_test(app_test)

    _app_button(app_test, "Run validation").click().run(timeout=30)
    assert app_test.radio[0].value == "05  Run"
    assert app_test.session_state["validation"] is not None

    _app_button(app_test, "Run RUPA").click().run(timeout=60)
    assert app_test.radio[0].value == "06  Analysis"
    run_id = app_test.session_state["run_summary"]["run_id"]
    run_directories = [path for path in (tmp_path / "runs").iterdir() if path.is_dir()]
    assert [path.name for path in run_directories] == [run_id]

    _app_button(app_test, "Continue to Export →").click().run(timeout=30)
    assert app_test.radio[0].value == "07  Export"
    assert app_test.session_state["run_summary"]["run_id"] == run_id
    assert [path.name for path in (tmp_path / "runs").iterdir() if path.is_dir()] == [run_id]
    assert not app_test.exception


def test_streamlit_workflow_failures_stay_on_the_current_step(monkeypatch, tmp_path):
    app_test = _app_test_with_temporary_runs(monkeypatch, tmp_path)
    _load_official_example_for_navigation_test(app_test)

    invalid = deepcopy(app_test.session_state["config"])
    invalid["privacy"]["epsilon_total"] = 6.0
    app_test.session_state["config"] = invalid
    _app_button(app_test, "Run validation").click().run(timeout=30)
    assert app_test.radio[0].value == "04  Validation"
    assert app_test.session_state["validation"] is None
    assert any(error.value == "VALIDATION FAILED" for error in app_test.error)

    app_test = _app_test_with_temporary_runs(monkeypatch, tmp_path)
    _load_official_example_for_navigation_test(app_test)
    _app_button(app_test, "Run validation").click().run(timeout=30)
    assert app_test.radio[0].value == "05  Run"

    invalid = deepcopy(app_test.session_state["config"])
    invalid["privacy"]["epsilon_total"] = 6.0
    app_test.session_state["config"] = invalid
    _app_button(app_test, "Run RUPA").click().run(timeout=30)
    assert app_test.radio[0].value == "05  Run"
    assert app_test.session_state["run_summary"] is None
    assert any(error.value.startswith("RUPA execution failed:") for error in app_test.error)


def test_hazardous_waste_gui_example_runs_through_analysis(monkeypatch, tmp_path):
    app_test = _app_test_with_temporary_runs(monkeypatch, tmp_path)
    _app_button(app_test, "Load hazardous-waste synthetic example").click().run(timeout=30)
    assert app_test.session_state["dataset_label"] == (
        "Hazardous-waste synthetic enterprise-year example"
    )
    assert len(app_test.session_state["config"]["schema"]["released_columns"]) == 18

    app_test.radio[0].set_value("04  Validation").run(timeout=30)
    _app_button(app_test, "Run validation").click().run(timeout=30)
    assert app_test.radio[0].value == "05  Run"
    _app_button(app_test, "Run RUPA").click().run(timeout=60)
    assert app_test.radio[0].value == "06  Analysis"
    assert not app_test.exception
    _app_button(app_test, "Continue to Export →").click().run(timeout=30)
    assert app_test.radio[0].value == "07  Export"


def test_balanced_strategy_can_be_selected_validated_run_and_exported(monkeypatch, tmp_path):
    app_test = _app_test_with_temporary_runs(monkeypatch, tmp_path)
    _app_button(app_test, "Load hazardous-waste synthetic example").click().run(timeout=30)
    app_test.radio[0].set_value("03  Configuration").run(timeout=30)
    selector = next(widget for widget in app_test.selectbox if widget.label == "Numerical budget allocation")
    selector.set_value("balanced_rupa")
    _app_button(app_test, "Apply basic configuration").click().run(timeout=30)
    assert app_test.session_state["config"]["privacy"]["numeric_budget_strategy"] == "balanced_rupa"
    assert app_test.session_state["validation"] is None
    app_test.radio[0].set_value("04  Validation").run(timeout=30)
    _app_button(app_test, "Run validation").click().run(timeout=30)
    assert app_test.radio[0].value == "05  Run"
    _app_button(app_test, "Run RUPA").click().run(timeout=60)
    assert app_test.radio[0].value == "06  Analysis"
    run_id = app_test.session_state["run_summary"]["run_id"]
    _app_button(app_test, "Continue to Export →").click().run(timeout=30)
    assert app_test.radio[0].value == "07  Export"
    assert app_test.session_state["run_summary"]["run_id"] == run_id
    assert not app_test.exception


@pytest.mark.parametrize("key", ["official", "water", "hazardous_waste"])
def test_supported_examples_load_real_data_and_config(key):
    example = load_example(key)
    assert not example["calibration"].empty
    assert not example["release"].empty
    assert example["config"]["privacy"]["randomness_mode"] == "reproducibility"


def test_official_gui_example_uses_distributed_example_directory():
    example = load_example("official")
    for name in ("calibration_path", "release_path", "config_path"):
        assert example[name].parent == DEMO_ROOT.parent / "examples" / "official"


def test_processing_stage_table_preserves_order_and_real_zero():
    physical = {"states": {
        "final_clipped": {"nrms": 0.1, "rms": 3.0},
        "full_projection": {"nrms": 0.0, "rms": 0.0},
        "noisy": {"nrms": 0.8, "rms": 24.0},
        "interpolated": {"nrms": 0.02, "rms": 0.6},
    }}
    table = physical_stage_table(physical)
    assert table["State"].tolist() == ["noisy", "full_projection", "interpolated", "final_clipped"]
    assert table["NRMS"].tolist() == [0.8, 0.0, 0.02, 0.1]
    assert table["Order"].tolist() == [1, 2, 3, 4]


def test_processing_stage_table_does_not_invent_missing_metrics():
    table = physical_stage_table({"states": {"noisy": {"rms": 2.0}}})
    assert len(table) == 1
    assert table["NRMS"].isna().all()
    assert physical_stage_table({}).empty


def test_blank_upload_configuration_does_not_infer_private_domains():
    config = blank_config(["unit_id", "value", "category", "target"])
    assert config["schema"]["public_bounds"] == {}
    assert config["schema"]["public_categories"] == {}

    rows = field_rows(config, ["unit_id", "value", "category", "target"])
    assert rows["Public Min"].isna().all()
    assert rows["Public Max"].isna().all()
    assert (rows["Public Categories"] == "").all()


def test_field_editor_requires_public_values_instead_of_learning_them():
    config = blank_config(["unit_id", "value", "category", "target"])
    rows = field_rows(config, ["unit_id", "value", "category", "target"])
    rows.loc[rows["Field"] == "unit_id", "Privacy Unit ID"] = True
    rows.loc[rows["Field"] == "target", "Sensitive Target"] = True
    rows.loc[rows["Field"] == "value", ["Type", "Release", "Regulatory Prior"]] = [
        "Numeric",
        True,
        1.0,
    ]
    rows.loc[
        rows["Field"] == "category", ["Type", "Release", "Regulatory Prior"]
    ] = ["Categorical", True, 1.0]

    updated = apply_field_rows(config, rows)
    assert updated["schema"]["public_bounds"] == {}
    assert updated["schema"]["public_categories"] == {}


def test_constraint_human_readable_expression_uses_real_coefficients():
    text = constraint_expression(
        {"coefficients": {"inflow": 1.0, "outflow": -1.0, "loss": -0.25}, "rhs": 0.0}
    )
    assert text == "inflow - outflow - 0.25 x loss = 0"


def test_sensitive_target_is_removed_from_default_calibration_preview():
    example = load_example("official")
    target = example["config"]["schema"]["sensitive_target"]
    assert target in example["calibration"].columns
    preview = sanitized_calibration_preview(example["calibration"], example["config"])
    assert target not in preview.columns


def test_basic_gui_config_updates_only_requested_common_values():
    example = load_example("official")
    original = deepcopy(example["config"])
    updated = apply_basic_config(
        original,
        epsilon_total=6.0,
        epsilon_numeric=5.5,
        epsilon_categorical=0.5,
        utility_alpha=0.7,
        repair_alpha=0.9,
        random_seed=456,
        sensitive_target="production",
        privacy_unit_id="enterprise_id",
    )
    assert updated["privacy"]["epsilon_total"] == 6.0
    assert updated["privacy"]["randomness_mode"] == "reproducibility"
    assert updated["constraints"] == original["constraints"]
    assert original["privacy"]["epsilon_total"] == 5.0


def test_demo_executes_existing_official_example_through_public_api(tmp_path):
    example = load_example("official")
    run = execute_demo(
        example["config"],
        example["calibration"],
        example["release"],
        output_root=tmp_path,
    )

    release_path = run.run_directory / "release_data.csv"
    manifest_path = run.run_directory / "manifest.json"
    assert release_path.is_file()
    assert manifest_path.is_file()
    public_run = load_public_run(run.run_directory)
    assert run.schema.sensitive_target not in public_run["csv"]["release_data.csv"].columns
    assert not (run.run_directory / "noisy_data.csv").exists()
    assert not (run.run_directory / "original_data.csv").exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["run_id"] == run.run_id
    assert run.inspection["run_id"] == run.run_id
    assert run.inspection["artifact_count"] == len(manifest["artifacts"])
    assert run.runtime_seconds > 0.0

    release_entry = next(
        item for item in manifest["artifacts"] if item["name"] == "release_data.csv"
    )
    digest = hashlib.sha256(release_path.read_bytes()).hexdigest()
    assert release_entry["sha256"] == digest
    assert len(run.result.noisy_data) == run.inspection["release_rows"]
    assert len(run.result.projected_data) == run.inspection["release_rows"]
    assert len(run.result.repaired_data) == run.inspection["release_rows"]


def test_public_archive_uses_manifest_whitelist_and_excludes_internal_directory(tmp_path):
    example = load_example("official")
    run = execute_demo(
        example["config"], example["calibration"], example["release"], output_root=tmp_path
    )
    internal = tmp_path / ".internal_audit"
    internal.mkdir()
    (internal / "secret.json").write_text('{"private": true}', encoding="utf-8")

    archive_bytes = build_public_run_archive(run.run_directory)
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        names = archive.namelist()
    assert names
    assert all(".internal_audit" not in name for name in names)
    assert all("original_data.csv" not in name for name in names)
    assert any(name.endswith("/release_data.csv") for name in names)


def test_public_archive_rejects_forbidden_manifest_entry(tmp_path):
    example = load_example("official")
    run = execute_demo(
        example["config"], example["calibration"], example["release"], output_root=tmp_path
    )
    forbidden = run.run_directory / "original_data.csv"
    forbidden.write_text("secret\n1\n", encoding="utf-8")
    manifest_path = run.run_directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"].append(
        {
            "name": forbidden.name,
            "sha256": hashlib.sha256(forbidden.read_bytes()).hexdigest(),
            "size_bytes": forbidden.stat().st_size,
        }
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(PrivacySafetyError):
        build_public_run_archive(run.run_directory)


def test_gui_validation_rejects_production_mode():
    example = load_example("official")
    config = deepcopy(example["config"])
    config["privacy"]["randomness_mode"] = "production"
    config["privacy"]["random_seed"] = None
    with pytest.raises(PrivacySafetyError, match="reproducibility mode only"):
        validate_demo(config, example["calibration"], example["release"])


@pytest.mark.parametrize("directory", [
    "C:\\private\\",
    "C:/private/",
    "\\\\server\\private\\",
    "/private/",
    "relative/private/",
])
def test_reproduction_command_does_not_embed_absolute_paths(directory):
    command = reproduction_commands(
        directory + "calibration.csv",
        directory + "release.csv",
        directory + "config.yaml",
        directory + "reproduced_run",
    )
    assert "C:\\private" not in command
    assert "private" not in command
    assert "server" not in command
    assert "calibration.csv" in command
    assert "release.csv" in command
    assert "config.yaml" in command
    assert "--run-id reproduced_run" in command


def test_reproduction_command_empty_names_use_documented_defaults():
    command = reproduction_commands("", ".", "")
    assert "--calibration calibration.csv" in command
    assert "--release release.csv" in command
    assert "--config config.yaml" in command
