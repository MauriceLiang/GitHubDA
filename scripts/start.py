"""Start the API, worker, and Streamlit UI as one local stack."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from dotenv import dotenv_values, set_key


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT_ROOT / ".env"
ENV_EXAMPLE = PROJECT_ROOT / ".env.example"
SAMPLE_API_KEY = "replace-with-a-long-random-local-secret"
SERVICE_START_TIMEOUT_SECONDS = 30
WORKER_START_TIMEOUT_SECONDS = 30
SHUTDOWN_TIMEOUT_SECONDS = 10


def ensure_api_key() -> None:
    if not ENV_FILE.exists():
        shutil.copyfile(ENV_EXAMPLE, ENV_FILE)

    configured_key = os.environ.get("INTERNAL_API_KEY") or dotenv_values(ENV_FILE).get("INTERNAL_API_KEY")
    if configured_key and configured_key != SAMPLE_API_KEY:
        return

    generated_key = secrets.token_urlsafe(32)
    set_key(str(ENV_FILE), "INTERNAL_API_KEY", generated_key, quote_mode="never")
    os.chmod(ENV_FILE, 0o600)
    os.environ["INTERNAL_API_KEY"] = generated_key
    print("已在 .env 中生成本机 INTERNAL_API_KEY。", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="一键启动 GitHubDA API、Worker 和 Streamlit 前端")
    parser.add_argument("--api-host", default="127.0.0.1", help="FastAPI 监听地址，默认仅本机可访问")
    parser.add_argument("--api-port", type=int, default=8000, help="FastAPI 端口，默认 8000")
    parser.add_argument("--frontend-host", default="127.0.0.1", help="Streamlit 监听地址，默认仅本机可访问")
    parser.add_argument("--frontend-port", type=int, default=8501, help="Streamlit 端口，默认 8501")
    return parser.parse_args()


def run_migrations() -> None:
    print("正在检查并升级数据库结构…", flush=True)
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=PROJECT_ROOT, check=True)


def start_process(name: str, command: list[str], env: dict[str, str]) -> subprocess.Popen[bytes]:
    print(f"正在启动 {name}…", flush=True)
    return subprocess.Popen(command, cwd=PROJECT_ROOT, env=env, start_new_session=True)


def wait_for_http(
    name: str,
    url: str,
    process: subprocess.Popen[bytes],
    stop: threading.Event,
) -> None:
    deadline = time.monotonic() + SERVICE_START_TIMEOUT_SECONDS
    while time.monotonic() < deadline and not stop.is_set():
        if process.poll() is not None:
            raise RuntimeError(f"{name} 在启动完成前退出，退出码 {process.returncode}")
        try:
            with urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except (OSError, URLError):
            pass
        stop.wait(0.5)

    if stop.is_set():
        raise RuntimeError("启动过程已中断")
    raise RuntimeError(f"等待 {name} 就绪超时：{url}")


def wait_for_worker(
    api: subprocess.Popen[bytes],
    worker: subprocess.Popen[bytes],
    api_url: str,
    api_key: str,
    stop: threading.Event,
) -> None:
    url = f"{api_url}/api/v1/system/status"
    request = Request(url, headers={"X-Internal-Api-Key": api_key})
    deadline = time.monotonic() + WORKER_START_TIMEOUT_SECONDS
    while time.monotonic() < deadline and not stop.is_set():
        for name, process in (("FastAPI", api), ("Worker", worker)):
            if process.poll() is not None:
                raise RuntimeError(f"{name} 在 Worker 就绪前退出，退出码 {process.returncode}")
        try:
            with urlopen(request, timeout=1) as response:
                status = json.load(response).get("data", {}).get("worker")
                if status == "ok":
                    print("Worker 心跳正常。", flush=True)
                    return
        except (OSError, URLError, ValueError):
            pass
        stop.wait(0.5)

    if stop.is_set():
        raise RuntimeError("启动过程已中断")
    raise RuntimeError(f"等待 Worker 心跳超时：{url}")


def stop_processes(processes: list[tuple[str, subprocess.Popen[bytes]]]) -> None:
    running = [(name, process) for name, process in processes if process.poll() is None]
    for _name, process in reversed(running):
        try:
            os.killpg(process.pid, signal.SIGINT)
        except ProcessLookupError:
            pass

    deadline = time.monotonic() + SHUTDOWN_TIMEOUT_SECONDS
    for name, process in running:
        try:
            process.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            print(f"{name} 未及时退出，正在强制停止。", flush=True)
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()


def main() -> int:
    args = parse_args()
    stop = threading.Event()
    processes: list[tuple[str, subprocess.Popen[bytes]]] = []
    failed = False

    def request_stop(_signum: int, _frame: object) -> None:
        stop.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    try:
        ensure_api_key()
        run_migrations()

        child_env = os.environ.copy()
        child_env["PYTHONUNBUFFERED"] = "1"
        api_url = f"http://127.0.0.1:{args.api_port}"
        api = start_process(
            "FastAPI",
            [
                sys.executable,
                "-m",
                "uvicorn",
                "backend.app.main:app",
                "--host",
                args.api_host,
                "--port",
                str(args.api_port),
            ],
            child_env,
        )
        processes.append(("FastAPI", api))
        wait_for_http("FastAPI", f"{api_url}/healthz", api, stop)
        print("FastAPI 健康检查通过。", flush=True)

        worker = start_process(
            "Worker",
            [sys.executable, "-m", "backend.app.worker.main"],
            child_env,
        )
        processes.append(("Worker", worker))
        api_key = os.environ.get("INTERNAL_API_KEY") or dotenv_values(ENV_FILE).get("INTERNAL_API_KEY") or ""
        wait_for_worker(api, worker, api_url, api_key, stop)

        frontend_env = child_env.copy()
        frontend_env["API_BASE_URL"] = api_url
        frontend = start_process(
            "Streamlit",
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                "frontend/app.py",
                "--server.address",
                args.frontend_host,
                "--server.port",
                str(args.frontend_port),
                "--server.headless",
                "true",
            ],
            frontend_env,
        )
        processes.append(("Streamlit", frontend))
        wait_for_http(
            "Streamlit",
            f"http://127.0.0.1:{args.frontend_port}/",
            frontend,
            stop,
        )

        print(f"GitHubDA 已启动：前端 http://127.0.0.1:{args.frontend_port}，API {api_url}/docs", flush=True)
        while not stop.wait(0.25):
            for name, process in processes:
                return_code = process.poll()
                if return_code is not None:
                    raise RuntimeError(f"{name} 已退出，退出码 {return_code}")
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        if not stop.is_set():
            failed = True
            print(f"GitHubDA 启动失败：{exc}", file=sys.stderr, flush=True)
    finally:
        if processes:
            print("正在停止 GitHubDA 服务…", flush=True)
            stop_processes(processes)

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
