"""Opt-in Harness-Bench adapter for protocol v1; no provider or agent loop."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent


def run_task(workspace: Path, prompt: str, *, timeout: int, allow_tools: bool, fixture: Path | None = None) -> dict[str, Any]:
    args = [sys.executable, "-m", "nexa_code.host", "--cwd", str(workspace)]
    if fixture:
        args += ["--fixture", str(fixture.resolve())]
    with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as diagnostics:
        process = subprocess.Popen(
            args, cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=diagnostics, text=True, env={**os.environ, "PYTHONPATH": str(ROOT)}
        )
        events: queue.Queue[dict[str, Any]] = queue.Queue()

        def read() -> None:
            assert process.stdout
            for line in process.stdout:
                try:
                    value = json.loads(line)
                    if not isinstance(value, dict) or value.get("version") != 1:
                        raise ValueError("Invalid engine protocol version")
                    events.put(value)
                except ValueError as error:
                    events.put({"type": "error", "message": str(error)})

        threading.Thread(target=read, daemon=True).start()
        try:
            return drive(process, events, prompt, timeout, allow_tools)
        finally:
            if process.poll() is None:
                send(process, "exit")
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=3)
            for stream in (process.stdin, process.stdout):
                if stream:
                    stream.close()


def send(process: subprocess.Popen[str], kind: str, **payload: Any) -> None:
    assert process.stdin
    process.stdin.write(json.dumps({"version": 1, "request_id": uuid.uuid4().hex, "type": kind, **payload}) + "\n")
    process.stdin.flush()


def drive(process: subprocess.Popen[str], events: queue.Queue[dict[str, Any]], prompt: str, timeout: int, allow_tools: bool) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    awaiting_mode = False
    while time.monotonic() < deadline:
        try:
            event = events.get(timeout=0.2)
        except queue.Empty:
            if process.poll() is not None:
                raise RuntimeError(f"Engine exited before a result: {process.returncode}")
            continue
        kind = event["type"]
        if kind == "error":
            raise RuntimeError(event["message"])
        if kind == "ready":
            if allow_tools:
                send(process, "set_mode", mode="bypass", confirmed=True)
                awaiting_mode = True
            else:
                send(process, "message", content=prompt)
        elif kind == "request_completed" and awaiting_mode:
            awaiting_mode = False
            send(process, "message", content=prompt)
        elif kind == "permission_request":
            send(process, "cancel")
            return {
                "status": "waiting_approval",
                "error": "Use --allow-tools only for a disposable benchmark workspace with explicitly authorized side effects",
            }
        elif kind == "done":
            return event
    send(process, "cancel")
    raise TimeoutError(f"Benchmark task exceeded {timeout} seconds")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--harness-path", type=Path, default=os.environ.get("HARNESS_BENCH_PATH"))
    parser.add_argument("--tasks", type=int, default=5)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--tag")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--run-live", action="store_true", help="Explicitly authorize provider/network usage")
    parser.add_argument("--allow-tools", action="store_true", help="Explicitly enable bypass in each disposable benchmark session")
    parser.add_argument("--output", type=Path, default=Path("benchmark_results.json"))
    args = parser.parse_args()
    if not args.run_live or args.harness_path is None:
        parser.error("Specify --run-live and --harness-path; credentials come from environment, never copied files")
    sys.path.insert(0, str(args.harness_path.resolve(strict=True)))
    tasks = importlib.import_module("harness_bench.tasks").ALL_TASKS
    selected = [task for task in tasks if not args.tag or args.tag in task.tags][args.start : args.start + args.tasks]
    results: list[dict[str, Any]] = []
    for task in selected:
        start = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="nexa-bench-") as directory:
            workspace = Path(directory)
            task.setup(workspace)
            try:
                event = run_task(workspace, task.prompt, timeout=args.timeout, allow_tools=args.allow_tools)
                if event["status"] != "completed":
                    raise RuntimeError(str(event.get("error") or event["status"]))
                result = task.verifier(workspace)
                passed, message = result.passed, result.message
            except Exception as error:  # noqa: BLE001 - Record a failed benchmark task and continue the selected suite.
                passed, message = False, str(error)
            results.append({"id": task.id, "name": task.name, "passed": passed, "message": message, "elapsed": time.monotonic() - start})
            args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"{task.id}: {'PASS' if passed else 'FAIL'} ({results[-1]['elapsed']:.1f}s)")
    print(f"{sum(item['passed'] for item in results)}/{len(results)} passed. Results: {args.output}")
    return 0 if all(item["passed"] for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
