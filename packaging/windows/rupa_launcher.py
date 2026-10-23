"""Local, reproducibility-only Streamlit launcher for the onedir distribution."""

import argparse
import ctypes
import json
import logging
import multiprocessing
import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path


# Frozen imports come from PYZ, without searching outside the application bundle.
try:
    from resource_paths import resource_path, user_data_root
except ModuleNotFoundError as exc:
    if exc.name != "resource_paths":
        raise
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "demo"))
    from resource_paths import resource_path, user_data_root


def available_port(first=8501, last=8599):
    for port in range(first, last + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as candidate:
            try:
                candidate.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as candidate:
        candidate.bind(("127.0.0.1", 0))
        return candidate.getsockname()[1]


def wait_for_health(url, timeout=120.0, stop=None):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not (stop and stop.is_set()):
        try:
            with opener.open(url + "/_stcore/health", timeout=1.0) as response:
                if response.status == 200 and response.read(128).strip() == b"ok":
                    return True
        except (OSError, ValueError):
            pass
        if stop:
            stop.wait(0.25)
        else:
            time.sleep(0.25)
    return False


def error_message(log_path, detail=None):
    message = "RUPA could not start.\n\nPlease see the diagnostic log:\n" + str(log_path)
    if detail:
        message += "\n\n" + str(detail)
    if os.name == "nt":
        ctypes.windll.user32.MessageBoxW(None, message, "RUPA", 0x10)
    else:
        print(message, file=sys.stderr)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Start the local RUPA research interface")
    parser.add_argument("--no-browser", action="store_true", help="Developer verification only")
    parser.add_argument("--packaging-self-test", type=Path, help="Synthetic-only developer regression JSON")
    args = parser.parse_args(argv)
    base = user_data_root()
    log_path = base / "logs" / "startup.log"
    try:
        for name in ("runs", "logs", "workspace", "cache"):
            (base / name).mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            filename=str(log_path), encoding="utf-8", level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s", force=True,
        )
        # Windowed PyInstaller sets stdout/stderr to None; Streamlit needs streams.
        streams = []
        for name in ("stdout", "stderr"):
            if getattr(sys, name) is None:
                handle = log_path.open("a", encoding="utf-8", buffering=1)
                setattr(sys, name, handle)
                streams.append(handle)
        logging.info("RUPA 0.1.0 launcher; local reproducibility interface only")
        os.environ["MPLCONFIGDIR"] = str(base / "cache" / "matplotlib")
        if args.packaging_self_test:
            from frozen_check import run_check

            run_check(args.packaging_self_test)
            return 0
        gui = resource_path("demo/app.py")
        required = [gui] + [
            resource_path("examples/official/" + name)
            for name in ("calibration.csv", "release.csv", "config.yaml")
        ]
        if any(not path.is_file() for path in required):
            raise FileNotFoundError("Bundled GUI or official example is missing")
        os.chdir(base)
        from streamlit.web import bootstrap

        port = available_port()
        url = "http://127.0.0.1:" + str(port)
        flags = {
            "global.developmentMode": False,
            "server.address": "127.0.0.1", "server.port": port,
            "server.headless": True, "server.showEmailPrompt": False,
            "server.fileWatcherType": "none", "server.runOnSave": False,
            "server.enableStaticServing": False,
            "browser.serverAddress": "127.0.0.1", "browser.serverPort": port,
            "browser.gatherUsageStats": False,
        }
        bootstrap.load_config_options(flags)
        logging.info("Starting %s; writable root=%s", url, base)
        stopped = threading.Event()

        def open_when_ready():
            if not wait_for_health(url, stop=stopped):
                if not stopped.is_set():
                    logging.error("Streamlit health check timed out")
                    error_message(log_path, "The local service did not become ready.")
                    logging.shutdown()
                    os._exit(1)
                return
            (base / "logs" / "last_startup.json").write_text(
                json.dumps({"url": url, "pid": os.getpid(), "ready": True,
                            "mode": "reproducibility", "usage_statistics": False}, indent=2),
                encoding="utf-8",
            )
            logging.info("Health check PASS: %s", url)
            if not args.no_browser:
                opened = webbrowser.open(url, new=2)
                logging.info("Default browser open returned %s", opened)
                if not opened:
                    ctypes.windll.user32.MessageBoxW(
                        None, "RUPA is running. Open:\n" + url, "RUPA", 0x40
                    )

        monitor = threading.Thread(target=open_when_ready, daemon=True)
        monitor.start()
        try:
            bootstrap.run(str(gui), False, [], flags)
        finally:
            stopped.set()
        return 0
    except (Exception, SystemExit) as exc:
        logging.exception("RUPA startup failed")
        error_message(log_path, type(exc).__name__)
        return 1


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
