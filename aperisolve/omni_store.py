"""Disk-backed full-mode tasks and Linux process identities.

Kept independent of Flask so detached runners can keep working across web restarts.
"""

# ruff: noqa: RUF001 -- Chinese interface copy uses Chinese punctuation.

import contextlib
import fcntl
import json
import os
import re
import signal
import stat
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path
from typing import BinaryIO

ACTIVE = frozenset({"preparing", "running", "stopping"})
TERMINAL = frozenset({"completed", "no_flag", "failed", "stopped"})
PREVIEW_BYTES = 256 * 1024
MAX_TASK_FILES = 2000


def task_path(root: Path, task_id: str) -> Path:
    """Resolve only generated task IDs, never symlinked task directories."""
    if not re.fullmatch(r"[0-9a-f]{32}", task_id):
        raise FileNotFoundError(task_id)
    path = root / task_id
    if path.is_symlink() or not path.is_dir():
        raise FileNotFoundError(task_id)
    return path


@contextlib.contextmanager
def locked(task: Path) -> Iterator[None]:
    """Serialize state transitions across the web and runner processes."""
    with (task / ".aperisolve" / "lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def read_state(task: Path) -> dict:
    """Read an atomically replaced state snapshot."""
    return json.loads((task / ".aperisolve" / "task.json").read_text(encoding="utf-8"))


def write_state(task: Path, state: dict) -> None:
    """Atomically publish state; callers hold the task lock."""
    folder = task / ".aperisolve"
    fd, name = tempfile.mkstemp(prefix="state-", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(state, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        Path(name).replace(folder / "task.json")
    finally:
        with contextlib.suppress(FileNotFoundError):
            Path(name).unlink()


def process_identity(pid: int) -> dict | None:
    """Record the kernel start time, rejecting zombies and reused PIDs."""
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(") ", 1)[1].split()
        if fields[0] in {"Z", "X"}:
            return None
        return {
            "pid": pid,
            "start": fields[19],
            "group": int(fields[2]),
            "boot": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        }
    except (OSError, ValueError, IndexError):
        return None


def process_alive(identity: dict | None) -> bool:
    """Match both the PID and its birth time."""
    return bool(identity and process_identity(identity["pid"]) == identity)


def signal_group(identity: dict | None, sig: int) -> None:
    """Signal a task-owned session, including descendants after its leader exits.

    A live session holds its numeric ID, so that ID cannot be reused until every
    member exits. Check a member's session and start time before signalling it.
    """
    if not identity or identity["group"] != identity["pid"]:
        return
    if identity.get("boot") != Path("/proc/sys/kernel/random/boot_id").read_text().strip():
        return
    group = identity["group"]
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / "stat").read_text().rsplit(") ", 1)[1].split()
            if (
                int(fields[2]) == group
                and int(fields[3]) == group
                and int(fields[19]) >= int(identity["start"])
            ):
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(group, sig)
                return
        except (OSError, ValueError, IndexError):
            continue


def reconcile(task: Path) -> dict:
    """Turn an unexpectedly lost runner into an explicit failed task."""
    with locked(task):
        state = read_state(task)
        if state["status"] in ACTIVE and not process_alive(state.get("runner")):
            # Startup writes the runner identity before releasing this lock.
            signal_group(state.get("process"), signal.SIGKILL)
            stopped = state["status"] == "stopping"
            state.update(status="stopped" if stopped else "failed", ended_at=time.time())
            state["error"] = "" if stopped else "后台解题进程异常退出；已保留任务文件和日志。"
            write_state(task, state)
        return state


def open_task_file(task: Path, relative: str) -> BinaryIO:
    """Open a regular task file with no symlink traversal, even during renames."""
    parts = relative.split("/")
    if not parts or any(part in {"", ".", "..", ".aperisolve"} or "\x00" in part for part in parts):
        raise FileNotFoundError(relative)
    fd = os.open(task, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        file_fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        if not stat.S_ISREG(os.fstat(file_fd).st_mode):
            os.close(file_fd)
            raise FileNotFoundError(relative)
        return os.fdopen(file_fd, "rb")
    finally:
        os.close(fd)


def preview(task: Path, relative: str, *, tail: bool = False) -> dict:
    """Read bounded UTF-8 text, including logs while they are being written."""
    if not relative.lower().endswith(".txt"):
        raise FileNotFoundError(relative)
    with open_task_file(task, relative) as stream:
        size = os.fstat(stream.fileno()).st_size
        if tail:
            stream.seek(max(0, size - PREVIEW_BYTES))
        content = stream.read(PREVIEW_BYTES)
    return {
        "path": relative,
        "text": content.decode("utf-8", errors="replace"),
        "truncated": size > PREVIEW_BYTES,
        "size": size,
        "tail": tail,
    }


def public_state(task: Path, state: dict, *, detail: bool = False) -> dict:
    """Expose display data without internal process configuration."""
    result = {
        key: state.get(key)
        for key in (
            "id",
            "status",
            "created_at",
            "started_at",
            "ended_at",
            "instructions",
            "uploads",
            "error",
            "exit_code",
        )
    }
    result["flag"] = ""
    if state["status"] == "completed":
        with contextlib.suppress(OSError):
            result["flag"] = preview(task, "flag-re.txt")["text"].strip()
    if detail:
        files = []
        for folder, dirs, names in os.walk(task, followlinks=False):
            dirs[:] = sorted(
                d for d in dirs if d != ".aperisolve" and not (Path(folder) / d).is_symlink()
            )
            for name in sorted(names):
                path = Path(folder) / name
                try:
                    if path.is_symlink() or not path.is_file():
                        continue
                    files.append(
                        {
                            "path": path.relative_to(task).as_posix(),
                            "size": path.stat().st_size,
                            "text": path.suffix.lower() == ".txt",
                        },
                    )
                except OSError:
                    continue  # Tools may rename or remove files during a snapshot.
                if len(files) >= MAX_TASK_FILES:
                    break
            if len(files) >= MAX_TASK_FILES:
                break
        result.update(files=files, files_truncated=len(files) >= MAX_TASK_FILES)
    return result
