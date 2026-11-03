"""Detached full-mode supervisor. No request or RQ worker owns its lifetime."""

# ruff: noqa: RUF001 -- Chinese interface copy uses Chinese punctuation.

import concurrent.futures
import contextlib
import json
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import TextIO

from .omni_events import publish_event
from .omni_prompts import pi_prompt
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

LOG_EVENT_INTERVAL = 0.25
TOOL_EVENTS = frozenset({"tool_call", "tool_call_update"})


def format_event(line: str) -> str:
    """Make text deltas readable and omit native/ACP tool calls and results."""
    try:
        event = json.loads(line)
        if not isinstance(event, dict):
            event = {}
    except (ValueError, TypeError):
        return line
    update = (
        event.get("params", {}).get("update", {}) if isinstance(event.get("params"), dict) else {}
    )
    update = event.get("update", update)
    if event.get("type") in TOOL_EVENTS or (
        isinstance(update, dict) and update.get("sessionUpdate") in TOOL_EVENTS
    ):
        return ""
    if event.get("type") in {"text", "thought"} and isinstance(event.get("data"), str):
        return event["data"]
    if isinstance(update, dict):
        content = update.get("content", {})
        if isinstance(content, dict) and isinstance(content.get("text"), str):
            return content["text"]
    if isinstance(event.get("text"), str):
        return event["text"] + "\n"
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
            output = format_event(line)
            if not output:
                continue
            log.write(output)
            log.flush()
            if time.monotonic() - last_log_event >= LOG_EVENT_INTERVAL:
                publish_event(task.name, "log_changed", solver="grok")
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
    """Finish the Grok branch without ending active parallel Pi branches."""
    with locked(task):
        state = read_state(task)
        solver = state.get("solvers", {}).get("grok", {})
        if solver.get("status") not in {"running", "stopping"}:
            return
        status, error = _outcome(task, state, exit_code)
        if solver.get("status") == "stopping":
            status, error = "stopped", ""
        solver.update(status=status, ended_at=time.time(), exit_code=exit_code, error=error)
        solver["session_confirmed"] = session_confirmed
        if status == "completed":
            with contextlib.suppress(OSError):
                solver["flag"] = preview(task, "flag-re.txt")["text"].strip()
        state.update(exit_code=exit_code, session_confirmed=session_confirmed)
        _update_overall(state)
        write_state(task, state)
    publish_event(task.name, "task_changed")
    publish_event(task.name, "log_changed", solver="grok")


def _update_overall(state: dict) -> None:
    statuses = [solver.get("status") for solver in state.get("solvers", {}).values()]
    if any(status in {"preparing", "running", "stopping"} for status in statuses):
        state["status"] = "running"
        return
    state["status"] = (
        "completed"
        if "completed" in statuses
        else "no_flag"
        if "no_flag" in statuses
        else "stopped"
        if "stopped" in statuses
        else "failed"
    )
    state["ended_at"] = time.time()


def _pi_event_text(line: str) -> str:  # noqa: C901, PLR0911 -- Each event family has one small renderer.
    """Show Pi text deltas and tool names without dumping tool arguments/results."""
    try:
        event = json.loads(line)
    except (ValueError, TypeError):
        return line
    if not isinstance(event, dict):
        return ""
    if event.get("type") == "message_update":
        update = event.get("assistantMessageEvent", {})
        if update.get("type") in {"text_delta", "thinking_delta"}:
            return str(update.get("delta", ""))
    if event.get("type") == "tool_execution_start":
        return f"\n[Pi 正在使用工具：{event.get('toolName', '未知')}]\n"
    if event.get("type") == "agent_start":
        return "\nPi 开始分析。\n"
    if event.get("type") == "agent_settled":
        return "\nPi 分析已结束。\n"
    if event.get("type") == "message_end":
        message = event.get("message", {})
        if message.get("stopReason") == "error":
            return f"\nPi 错误：{message.get('errorMessage', '未知错误')}\n"
    if event.get("type") == "error":
        return f"\nPi 错误：{event.get('message', event.get('error', '未知错误'))}\n"
    return ""


def _codex_event_text(line: str) -> str:
    """Render Codex progress without exposing command arguments or tool output."""
    try:
        event = json.loads(line)
    except ValueError:
        return line
    if not isinstance(event, dict):
        return ""
    kind = event.get("type")
    item = event.get("item", {})
    if kind == "item.completed" and item.get("type") in {"agent_message", "reasoning"}:
        return str(item.get("text", "")) + "\n"
    if kind == "item.started" and item.get("type") == "command_execution":
        return "[Codex 正在执行命令]\n"
    if kind in {"error", "turn.failed"}:
        return f"Codex 错误：{event.get('message') or event.get('error')}\n"
    return ""


def _run_pi(task: Path, solver_id: str) -> None:  # noqa: C901, PLR0912, PLR0915 -- Worker owns a single process lifecycle.
    """Run one Pi solver with its own cwd, session store, log, and artifacts."""
    child = None
    identity = None
    last_error = ""
    try:
        with locked(task):
            state = read_state(task)
            solver = state["solvers"][solver_id]
            if solver["status"] != "preparing":
                return
            workspace = Path(solver["workspace"])
            is_codex = solver_id == "codex"
            label = "Codex" if is_codex else "Pi"
            prompt = pi_prompt(task, workspace, state["uploads"], state["instructions"], 1)
            if is_codex:
                prompt = prompt.replace("并行分支 Pi 1", "并行分支 Codex")
                prompt = f"使用 ctf-router 技能：{state['skill_path']}，按技能说明执行。\n" + prompt
            (workspace / "prompt.txt").write_text(prompt, encoding="utf-8")
            command = (
                [
                    state["codex_cli"],
                    "exec",
                    "--json",
                    "--skip-git-repo-check",
                    "--sandbox",
                    "workspace-write",
                    "--cd",
                    str(workspace),
                    "-",
                ]
                if is_codex
                else [
                    state["pi_cli"],
                    "--mode",
                    "json",
                    "--session-dir",
                    str(workspace / "sessions"),
                    "--session-id",
                    f"aperisolve-{task.name}-{solver_id}",
                    "--skill",
                    state["skill_path"],
                    "--approve",
                    "@prompt.txt",
                ]
            )
            prompt_input = (workspace / "prompt.txt").open("rb") if is_codex else subprocess.DEVNULL
            try:
                child = subprocess.Popen(  # noqa: S603 -- Configured CLI and generated task paths.
                    command,
                    cwd=workspace,
                    stdin=prompt_input,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            finally:
                if is_codex:
                    prompt_input.close()
            identity = process_identity(child.pid)
            solver.update(status="running", started_at=time.time(), process=identity)
            write_state(task, state)
        publish_event(task.name, "task_changed")
        log_path = workspace / "log.txt"
        last_log_event = time.monotonic()
        with log_path.open("a", encoding="utf-8", buffering=1) as log:
            log.write(f"{label} 启动，工作目录：{workspace}\n")
            if child.stdout is not None:
                for raw in child.stdout:
                    line = raw.decode("utf-8", errors="replace")
                    try:
                        event = json.loads(line)
                        if not is_codex and event.get("type") == "message_end":
                            message = event.get("message", {})
                            if message.get("role") == "assistant":
                                last_error = (
                                    message.get("errorMessage", "")
                                    if message.get("stopReason") == "error"
                                    else ""
                                )
                        if is_codex and event.get("type") == "turn.completed":
                            last_error = ""
                        if is_codex and event.get("type") in {"error", "turn.failed"}:
                            last_error = str(
                                event.get("message") or event.get("error") or "Codex 运行失败",
                            )
                    except (ValueError, AttributeError):
                        pass
                    text = _codex_event_text(line) if is_codex else _pi_event_text(line)
                    if text:
                        log.write(text)
                        log.flush()
                        if time.monotonic() - last_log_event >= LOG_EVENT_INTERVAL:
                            publish_event(task.name, "log_changed", solver=solver_id)
                            last_log_event = time.monotonic()
                child.stdout.close()
            exit_code = child.wait()
        publish_event(task.name, "log_changed", solver=solver_id)
        signal_group(identity, signal.SIGKILL)
        flag_path = workspace / "flag-re.txt"
        has_flag = flag_path.is_file() and flag_path.stat().st_size > 0
        status = (
            "completed"
            if exit_code == 0 and not last_error and has_flag
            else "no_flag"
            if exit_code == 0 and not last_error
            else "failed"
        )
        error = last_error or (
            "" if exit_code == 0 else f"{label} CLI 退出码为 {exit_code}，请查看该分支日志。"
        )
        with locked(task):
            state = read_state(task)
            solver = state["solvers"][solver_id]
            if solver.get("status") == "stopping":
                status, error = "stopped", ""
            solver.update(status=status, ended_at=time.time(), exit_code=exit_code, error=error)
            if status == "completed":
                solver["flag"] = flag_path.read_text(encoding="utf-8").strip()
            _update_overall(state)
            write_state(task, state)
        publish_event(task.name, "task_changed")
    except Exception as exc:  # noqa: BLE001 -- Persist worker failures for task observers.
        signal_group(identity, signal.SIGKILL)
        if child is not None:
            with contextlib.suppress(Exception):
                child.wait(timeout=5)
        with locked(task):
            state = read_state(task)
            solver = state["solvers"][solver_id]
            stopped = solver.get("status") == "stopping"
            solver.update(
                status="stopped" if stopped else "failed",
                ended_at=time.time(),
                error="" if stopped else str(exc),
            )
            _update_overall(state)
            write_state(task, state)
        publish_event(task.name, "task_changed")


def _run_grok(root: Path, task_id: str) -> None:
    """Run the existing Grok branch concurrently with Pi workers."""
    task = task_path(root, task_id)
    child = None
    identity = None
    lease = None
    try:
        with locked(task):
            state = read_state(task)
            if state.get("solvers", {}).get("grok", {}).get("status") != "preparing":
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
            state["solvers"]["grok"].update(
                status="running",
                started_at=time.time(),
                process=identity,
            )
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
            publish_event(task_id, "log_changed", solver="grok")
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
            solver = state.get("solvers", {}).get("grok", {})
            if solver.get("status") in {"preparing", "running", "stopping"}:
                stopped = solver.get("status") == "stopping"
                solver.update(
                    status="stopped" if stopped else "failed",
                    ended_at=time.time(),
                    error="" if stopped else str(exc),
                )
                _update_overall(state)
                write_state(task, state)
        publish_event(task_id, "task_changed")
        publish_event(task_id, "log_changed", solver="grok")
    finally:
        if lease is not None:
            lease.close()


def run(root: Path, task_id: str) -> None:
    """Run Grok alongside all Pi workers under one detachable supervisor."""
    task = task_path(root, task_id)
    state = read_state(task)
    pi_ids = [
        solver_id
        for solver_id in state.get("solvers", {})
        if solver_id.startswith("pi-") or solver_id == "codex"
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(pi_ids))) as pool:
        futures = [pool.submit(_run_pi, task, solver_id) for solver_id in pi_ids]
        _run_grok(root, task_id)
        for future in futures:
            future.result()


if __name__ == "__main__":
    run(Path(sys.argv[1]), sys.argv[2])
