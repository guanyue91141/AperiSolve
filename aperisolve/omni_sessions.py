"""Lease recent project sessions so independent tasks can resume them safely."""

# ruff: noqa: RUF001 -- Chinese task instructions use Chinese punctuation.

import contextlib
import fcntl
import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
from urllib.parse import quote

from .omni_store import ACTIVE, process_alive, read_state, task_path

DEFAULT_SESSION_MAX_AGE = 3600
LOG_TAIL_BYTES = 64 * 1024
MAX_DIRECTORY_NAME_BYTES = 255


@dataclass
class SessionLease:
    """Hold a process-scoped lock until the runner and its CLI have finished."""

    session_id: str
    cwd: Path
    source_task: str | None
    lock: BinaryIO

    def close(self) -> None:
        """Release the lease, including when execution fails or is cancelled."""
        self.lock.close()


def _session_record(task: Path, state: dict) -> tuple[str, Path] | None:
    """Read current metadata or recover a legacy session from its terminal event."""
    if state.get("session_id") and state.get("session_cwd"):
        session_id, cwd = state.get("session_id"), state.get("session_cwd")
    else:
        session_id, cwd = None, None
        with contextlib.suppress(OSError):
            with (task / "grok.log.txt").open("rb") as stream:
                stream.seek(max(0, os.fstat(stream.fileno()).st_size - LOG_TAIL_BYTES))
                lines = stream.read().decode("utf-8", errors="replace").splitlines()
            for line in reversed(lines):
                with contextlib.suppress(ValueError, TypeError):
                    event = json.loads(line)
                    if isinstance(event, dict) and event.get("type") == "end":
                        session_id, cwd = event.get("sessionId"), event.get("cwd")
                        break
    try:
        session_id = str(uuid.UUID(session_id))
        if not isinstance(cwd, str) or not Path(cwd).is_absolute():
            return None
    except (ValueError, TypeError, AttributeError):
        return None
    return session_id, Path(cwd)


def _stored_session_exists(session_id: str, cwd: Path) -> bool:
    """Skip deleted sessions instead of attempting a broken resume."""
    store = Path(os.environ.get("GROK_HOME", str(Path.home() / ".grok"))) / "sessions"
    encoded = quote(str(cwd), safe="")
    folders = (
        [store / encoded] if len(encoded.encode()) <= MAX_DIRECTORY_NAME_BYTES else store.glob("*")
    )
    return any(
        (folder / session_id / "summary.json").is_file()
        and (folder / session_id / "chat_history.jsonl").is_file()
        for folder in folders
    )


def _try_lock(root: Path, session_id: str) -> BinaryIO | None:
    """Atomically claim a session across detached runners and server restarts."""
    folder = root / ".sessions"
    folder.mkdir(exist_ok=True)
    lock = (folder / (session_id + ".lock")).open("ab")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        return None
    return lock


def _recent_sessions(
    root: Path,
    task: Path,
    cli: str,
    max_age: float,
) -> tuple[list[tuple[float, str, Path, str]], set[str]]:
    """Order project-owned sessions by last task completion, without topic filtering."""
    candidates = []
    busy = set()
    cutoff = time.time() - max_age
    for entry in root.iterdir():
        if entry == task:
            continue
        try:
            previous = task_path(root, entry.name)
            state = read_state(previous)
            if Path(state.get("grok_cli", "")).resolve() != Path(cli).resolve():
                continue
            record = _session_record(previous, state)
            session_id = state.get("session_id") or (record[0] if record else None)
            if state["status"] in ACTIVE:
                if session_id and (
                    process_alive(state.get("runner")) or process_alive(state.get("process"))
                ):
                    busy.add(session_id)
                continue
            used_at = state.get("ended_at") or state["created_at"]
            if record and used_at >= cutoff:
                candidates.append((used_at, *record, previous.name))
        except (OSError, ValueError, TypeError, KeyError):
            continue
    return sorted(candidates, key=lambda item: item[0], reverse=True), busy


def claim_session(root: Path, task: Path, cli: str, max_age: float) -> SessionLease:
    """Resume the latest idle session, or create one when every candidate is busy."""
    candidates, busy = _recent_sessions(root, task, cli, max_age) if max_age > 0 else ([], set())
    for _, session_id, cwd, source_task in candidates:
        if session_id in busy or not cwd.is_dir() or not _stored_session_exists(session_id, cwd):
            continue
        lock = _try_lock(root, session_id)
        if lock is not None:
            return SessionLease(session_id, cwd, source_task, lock)
    session_id = str(uuid.uuid4())
    lock = _try_lock(root, session_id)
    if lock is None:
        msg = "Could not lease a new Grok session"
        raise RuntimeError(msg)
    return SessionLease(session_id, task, None, lock)


def resume_prompt(task: Path, state: dict) -> str:
    """Append only the new problem and absolute input/output locations."""
    attachments = "\n".join(f"- {task / item['path']}" for item in state["uploads"]) or "（无附件）"
    instructions = state["instructions"]
    instruction_section = f"用户解题说明：\n{instructions}\n" if instructions.strip() else ""
    return (
        "这是全新题目；复用已有 skills，旧题答案不适用于本题\n"
        f"新题目录（绝对路径）：{task}\n"
        f"新题附件（绝对路径）：\n{attachments}\n"
        f"flag 输出（绝对路径）：{task / 'flag-re.txt'}\n"
        f"解题过程输出（绝对路径）：{task / 'solution.txt'}\n" + instruction_section
    )
