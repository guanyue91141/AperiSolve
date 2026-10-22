"""Detached full-mode supervisor. No request or RQ worker owns its lifetime."""

# ruff: noqa: RUF001 -- Chinese interface copy uses Chinese punctuation.

import contextlib
import json
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import TextIO

from .omni_events import publish_event
from .omni_sessions import DEFAULT_SESSION_MAX_AGE, SessionLease, claim_session, resume_prompt
from .omni_store import (
    locked,
    preview,
    process_identity,
    read_state,
    signal_group,
    task_path,
    write_state,
)

MAX_TOOL_DETAIL_BYTES = 8 * 1024
MAX_SUMMARY_FIELD_BYTES = 1024
LOG_EVENT_INTERVAL = 0.25


def _compact_tool_value(value: object) -> object:
    """Keep small tool results; summarize large payloads before writing logs."""
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) <= MAX_TOOL_DETAIL_BYTES:
        return value
    summary: dict[str, object] = {"filtered": True, "original_bytes": len(encoded)}
    if isinstance(value, dict):
        for key in ("type", "exit_code", "signal", "timed_out", "truncated", "description"):
            item = value.get(key)
            if (
                isinstance(item, (str, int, float, bool))
                and len(str(item).encode("utf-8")) <= MAX_SUMMARY_FIELD_BYTES
            ):
                summary[key] = item
    return summary


def format_event(line: str) -> str:
    """Make ACP text deltas readable while retaining other tool events."""
    try:
        event = json.loads(line)
        if not isinstance(event, dict):
            event = {}
    except (ValueError, TypeError):
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


def _stream_output(child: subprocess.Popen, task: Path, session_id: str, log: TextIO) -> bool:
    """Log one invocation and confirm that Grok persisted the expected session."""
    confirmed = False
    last_log_event = time.monotonic()
    if child.stdout is not None:
        for raw in child.stdout:
            line = raw.decode("utf-8", errors="replace")
            with contextlib.suppress(ValueError, TypeError):
                event = json.loads(line)
                if isinstance(event, dict) and event.get("type") == "end":
                    confirmed = event.get("sessionId") == session_id
            log.write(format_event(line))
            log.flush()
            if time.monotonic() - last_log_event >= LOG_EVENT_INTERVAL:
                publish_event(task.name, "log_changed")
                last_log_event = time.monotonic()
        child.stdout.close()
    return confirmed


def _launch_cli(task: Path, state: dict, lease: SessionLease) -> subprocess.Popen:
    """Keep the native session directory and pass this task's absolute prompt path."""
    if lease.source_task:
        (task / "prompt.txt").write_text(resume_prompt(task, state), encoding="utf-8")
    session_args = (
        ["--resume", lease.session_id] if lease.source_task else ["--session-id", lease.session_id]
    )
    state.update(
        session_id=lease.session_id,
        session_cwd=str(lease.cwd),
        resumed_from_task=lease.source_task,
        session_confirmed=False,
    )
    return subprocess.Popen(  # noqa: S603 -- Configured local CLI, with generated session IDs.
        [
            state["grok_cli"],
            "--cwd",
            str(lease.cwd),
            *session_args,
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


def _finish_task(task: Path, exit_code: int, *, session_confirmed: bool) -> None:
    """Persist the terminal result without overwriting a completed stop request."""
    with locked(task):
        state = read_state(task)
        if state["status"] not in {"running", "stopping"}:
            return
        status, error = _outcome(task, state, exit_code)
        state.update(
            status=status,
            ended_at=time.time(),
            exit_code=exit_code,
            error=error,
            session_confirmed=session_confirmed,
        )
        write_state(task, state)
    publish_event(task.name, "task_changed")
    publish_event(task.name, "log_changed")


def run(root: Path, task_id: str) -> None:
    """Run Grok and persist its terminal state, even without a web server."""
    task = task_path(root, task_id)
    child = None
    identity = None
    lease = None
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
            lease = claim_session(
                root,
                task,
                state["grok_cli"],
                state.get("session_max_age", DEFAULT_SESSION_MAX_AGE),
            )
            # Persist the child identity under the same lock used by stop.
            child = _launch_cli(task, state, lease)
            identity = process_identity(child.pid)
            state.update(status="running", started_at=time.time(), process=identity)
            write_state(task, state)

        publish_event(task_id, "task_changed")
        with (task / "grok.log.txt").open("a", encoding="utf-8", buffering=1) as log:
            log.write("Grok 已启动，工作目录：" + str(task) + "\n")
            log.write(
                ("复用空闲会话：" if lease.source_task else "新建会话：")
                + lease.session_id
                + "，会话目录："
                + str(lease.cwd)
                + "\n",
            )
            log.flush()
            publish_event(task_id, "log_changed")
            session_confirmed = _stream_output(child, task, lease.session_id, log)
            exit_code = child.wait()
            # Do not leave tool grandchildren running after the agent has exited.
            signal_group(identity, signal.SIGKILL)
            log.write(f"\nGrok 已退出，退出码：{exit_code}\n")

        _finish_task(task, exit_code, session_confirmed=session_confirmed)
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
    finally:
        if lease is not None:
            lease.close()


if __name__ == "__main__":
    run(Path(sys.argv[1]), sys.argv[2])
