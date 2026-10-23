import importlib.util
import logging
import socket
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "demo"))
import resource_paths  # noqa: E402


def load_launcher():
    spec = importlib.util.spec_from_file_location("rupa_windows_launcher", ROOT / "packaging/windows/rupa_launcher.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_source_paths_preserve_existing_gui_layout():
    assert resource_paths.resource_root() == ROOT
    assert resource_paths.user_data_root() == ROOT / "demo"
    assert resource_paths.resource_path("examples/official/config.yaml").is_file()
    assert resource_paths.resource_path(
        "examples/hazardous_waste/config_reproducibility.yaml"
    ).is_file()


def test_windows_spec_includes_synthetic_hazardous_waste_example():
    spec = (ROOT / "packaging/windows/RUPA.spec").read_text(encoding="utf-8")
    assert '("hazardous_waste", "config_reproducibility.yaml")' in spec


def test_frozen_resources_and_writable_outputs_are_separate(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "_internal"), raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    assert resource_paths.resource_root() == tmp_path / "_internal"
    assert resource_paths.user_data_root() == tmp_path / "local" / "RUPA"
    assert resource_paths.resource_path("examples/official/config.yaml") == tmp_path / "_internal/examples/official/config.yaml"


@pytest.mark.parametrize("path", ["../private.csv", str(ROOT / "README.md")])
def test_resource_helper_rejects_escape_paths(path):
    with pytest.raises(ValueError, match="relative and contained"):
        resource_paths.resource_path(path)


def test_launcher_import_does_not_start_a_server():
    module = load_launcher()
    assert callable(module.main)


def test_launcher_selects_alternate_port_when_preferred_port_is_busy():
    module = load_launcher()
    with socket.socket() as blocker:
        blocker.bind(("127.0.0.1", 0))
        busy = blocker.getsockname()[1]
        assert module.available_port(busy, busy) != busy


def test_health_timeout_is_bounded_and_does_not_open_browser(monkeypatch):
    module = load_launcher()
    monkeypatch.setattr(module.webbrowser, "open", lambda *args, **kwargs: pytest.fail("Browser opened before readiness"))
    assert module.wait_for_health("http://127.0.0.1:1", timeout=0.02) is False


def test_startup_failure_writes_traceback_and_requests_a_message(monkeypatch, tmp_path):
    module = load_launcher()
    log_path = tmp_path / "logs" / "startup.log"
    logger = logging.Logger("isolated-launcher-test")
    logger.setLevel(logging.INFO)
    messages = []

    def configure(**options):
        handler = logging.FileHandler(options["filename"], encoding="utf-8")
        logger.addHandler(handler)

    monkeypatch.setattr(module, "logging", SimpleNamespace(
        INFO=logging.INFO,
        basicConfig=configure, info=logger.info, exception=logger.exception,
        error=logger.error, shutdown=lambda: None,
    ))
    monkeypatch.setattr(module, "user_data_root", lambda: tmp_path)
    monkeypatch.setattr(module, "resource_path", lambda name: tmp_path / "missing_bundle" / name)
    monkeypatch.setattr(module, "error_message", lambda path, detail=None: messages.append((path, detail)))
    monkeypatch.setenv("MPLCONFIGDIR", "original-test-value")
    try:
        assert module.main(["--no-browser"]) == 1
        for handler in logger.handlers:
            handler.flush()
        assert messages == [(log_path, "FileNotFoundError")]
        contents = log_path.read_text(encoding="utf-8")
        assert "Traceback" in contents
        assert "Bundled GUI or official example is missing" in contents
    finally:
        for handler in logger.handlers:
            handler.close()
