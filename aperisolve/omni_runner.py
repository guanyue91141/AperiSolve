"""Detached full-mode supervisor. No request or RQ worker owns its lifetime."""

# ruff: noqa: RUF001 -- Chinese interface copy uses Chinese punctuation.

import contextlib
import json
import signal
import subprocess
import sys
import time
from pathlib import Path

from .omni_store import (
    locked,
    preview,
    process_identity,
    read_state,
    signal_group,
    task_path,
    write_state,
)
from .omni_events import publish_event

MAX_TOOL_DETAIL_BYTES = 8 * 1024


def _compact_tool_value(value: object) -> object:
    """Keep small tool results; summarize large payloads before writing logs."""
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) <= MAX_TOOL_DETAIL_BYTES:
        return value
    summary: dict[str, object] = {"filtered": True, "original_bytes": len(encoded)}
    if isinstance(value, dict):
        for key in ("type", "exit_code", "signal", "timed_out", "truncated", "description"):
            item = value.get(key)
            if isinstance(item, (str, int, float, bool)) and len(str(item).encode("utf-8")) <= 1024:
                summary[key] = item
    return summary


def format_event(line: str) -> str:
    """Make ACP text deltas readable while retaining other tool events."""
    try:
        event = json.loads(line)
    except (ValueError, TypeError):
        return line
    if not isinstance(event, dict):
        return line
    if event.get("type") in {"text", "thought"} and isinstance(event.get("data"), str):
        return event["data"]
    update = (
        event.get("params", {}).get("update", {}) if isinstance(event.get("params"), dict) else {}
    )
    update = event.get("update", update)
    if isinstance(update, dict):
        content = update.get("content", {})
        if isinstance(content, dict) and isinstance(content.get("text"), str):
            return content["text"]
    if isinstance(event.get("text"), str):
        return event["text"] + "\n"
    if event.get("type") == "tool_call_update":
        event = event.copy()
        for key in ("content", "rawOutput"):
            if key in event:
                event[key] = _compact_tool_value(event[key])
        return json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
    return line


def _outcome(task: Path, state: dict, exit_code: int) -> tuple[str, str]:
    """Separate tool success from a verified, nonempty result file."""
    if state["status"] == "stopping":
        return "stopped", ""
    if exit_code != 0:
        return "failed", f"Grok 退出码为 {exit_code}，请查看运行日志。"
    with contextlib.suppress(OSError):
        if preview(task, "flag-re.txt")["text"].strip():
            return "completed", ""
    return "no_flag", ""


def run(root: Path, task_id: str) -> None:
    """Run Grok and persist its terminal state, even without a web server."""
    task = task_path(root, task_id)
    child = None
    identity = None
    try:
        with locked(task):
            state = read_state(task)
            if state["status"] == "stopping":
                state.update(status="stopped", ended_at=time.time())
                write_state(task, state)
                publish_event(task_id, "task_changed")
                return
            if state["status"] != "preparing":
                return
            # Persist the child identity under the same lock used by stop.
            child = subprocess.Popen(  # noqa: S603 -- Configured local CLI; shell is never used.
                [
                    state["grok_cli"],
                    "--cwd",
                    str(task),
                    "--prompt-file",
                    str(task / "prompt.txt"),
                    "--always-approve",
                    "--no-plan",
                    "--output-format",
                    "streaming-json",
                ],
                cwd=task,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            identity = process_identity(child.pid)
            state.update(status="running", started_at=time.time(), process=identity)
            write_state(task, state)

        publish_event(task_id, "task_changed")
        with (task / "grok.log.txt").open("a", encoding="utf-8", buffering=1) as log:
            log.write("Grok 已启动，工作目录：" + str(task) + "\n")
            log.flush()
            publish_event(task_id, "log_changed")
            last_log_event = time.monotonic()
            if child.stdout is not None:
                for raw in child.stdout:
                    log.write(format_event(raw.decode("utf-8", errors="replace")))
                    log.flush()
                    if time.monotonic() - last_log_event >= 0.25:
                        publish_event(task_id, "log_changed")
                        last_log_event = time.monotonic()
                child.stdout.close()
            exit_code = child.wait()
            # Do not leave tool grandchildren running after the agent has exited.
            signal_group(identity, signal.SIGKILL)
            log.write(f"\nGrok 已退出，退出码：{exit_code}\n")

        with locked(task):
            state = read_state(task)
            if state["status"] not in {"running", "stopping"}:
                return
            status, error = _outcome(task, state, exit_code)
            state.update(status=status, ended_at=time.time(), exit_code=exit_code, error=error)
            write_state(task, state)
        publish_event(task_id, "task_changed")
        publish_event(task_id, "log_changed")
    except Exception as exc:  # noqa: BLE001 -- Last supervisor boundary must persist every failure.
        signal_group(identity, signal.SIGKILL)
        if child is not None:
            with contextlib.suppress(Exception):
                child.wait(timeout=5)
        with locked(task):
            state = read_state(task)
            if state["status"] in {"preparing", "running", "stopping"}:
                stopped = state["status"] == "stopping"
                state.update(
                    status="stopped" if stopped else "failed",
                    ended_at=time.time(),
                    error="" if stopped else str(exc),
                )
                write_state(task, state)
        publish_event(task_id, "task_changed")
        publish_event(task_id, "log_changed")


if __name__ == "__main__":
    run(Path(sys.argv[1]), sys.argv[2])
