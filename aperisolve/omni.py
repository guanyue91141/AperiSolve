"""Independent multi-file CTF submission API."""

# ruff: noqa: RUF001 -- Chinese interface copy uses Chinese punctuation.

import contextlib
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import BinaryIO, Protocol

from flask import (
    Blueprint,
    Flask,
    Request,
    Response,
    abort,
    current_app,
    jsonify,
    request,
    send_file,
)
from flask_sock import Sock

from .omni_events import publish_event, subscribe_events
from .omni_sessions import DEFAULT_SESSION_MAX_AGE
from .omni_store import (
    ACTIVE,
    locked,
    open_task_file,
    preview,
    process_alive,
    process_identity,
    public_state,
    read_state,
    reconcile,
    signal_group,
    task_path,
    write_state,
)

omni_bp = Blueprint("omni", __name__, url_prefix="/api/omni/tasks")
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class WebSocket(Protocol):
    """Minimal Flask-Sock connection surface used by the task stream."""

    def send(self, data: str) -> None:
        """Send a task notification."""
        ...

    def receive(self, timeout: float | None = None) -> str | None:
        """Observe client disconnects while waiting for notifications."""
        ...


class OmniRequest(Request):
    """Remove byte and multipart-count limits only for the full-mode upload."""

    @Request.max_content_length.getter
    def max_content_length(self) -> int | None:
        """Keep the original limit everywhere except the independent batch upload."""
        if self.method == "POST" and self.path == "/api/omni/tasks":
            return None
        return super().max_content_length

    @Request.max_form_parts.getter
    def max_form_parts(self) -> int | None:
        """Accept any number of full-mode attachments."""
        if self.method == "POST" and self.path == "/api/omni/tasks":
            return None
        return super().max_form_parts


def configure_omni(app: Flask) -> None:
    """Register the API without changing the original image pipeline."""
    app.request_class = OmniRequest
    app.config["OMNI_DATA_FOLDER"] = Path(os.getenv("OMNI_DATA_FOLDER", str(PROJECT_ROOT / "data")))
    app.config["GROK_CLI"] = os.getenv("GROK_CLI", str(Path.home() / ".local/bin/grok"))
    app.config["OMNI_SKILL_PATH"] = os.getenv(
        "OMNI_SKILL_PATH",
        str(Path.home() / ".grok/skills/ctf-router/SKILL.md"),
    )
    app.config["OMNI_SESSION_MAX_AGE"] = max(
        0,
        int(os.getenv("OMNI_SESSION_MAX_AGE") or DEFAULT_SESSION_MAX_AGE),
    )
    app.register_blueprint(omni_bp)
    app.config["SOCK_SERVER_OPTIONS"] = {"ping_interval": 25, "max_message_size": 4096}
    sock = Sock(app)

    @sock.route("/api/omni/tasks/ws")
    def task_updates(ws: WebSocket) -> None:
        """Push task invalidations over one socket while the records panel is open."""
        subscription = subscribe_events()
        try:
            ws.send('{"type":"ready"}')
            while True:
                # Receive with a short timeout to notice browser closes even when idle.
                ws.receive(timeout=0.1)
                message = subscription.get_message(timeout=0.4)
                if message and message.get("type") == "message":
                    data = message["data"]
                    ws.send(data.decode("utf-8") if isinstance(data, bytes) else data)
        finally:
            subscription.close()


def _root() -> Path:
    return Path(current_app.config["OMNI_DATA_FOLDER"]).resolve()


def _task(task_id: str) -> Path:
    try:
        return task_path(_root(), task_id)
    except OSError:
        abort(404)


def launch_runner(root: Path, task_id: str, log: BinaryIO) -> subprocess.Popen:
    """Detach the supervisor from web-server signals and reap it when possible."""
    process = subprocess.Popen(  # noqa: S603 -- Fixed Python module, generated ID, no shell.
        [sys.executable, "-m", "aperisolve.omni_runner", str(root), task_id],
        cwd=PROJECT_ROOT,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        close_fds=True,
    )
    threading.Thread(target=process.wait, daemon=True).start()
    return process


@omni_bp.post("")
def create_task() -> tuple[Response, int]:  # noqa: PLR0915 -- One upload/save/launch boundary.
    """Save a batch and start its own Grok process; never enqueue image analysis."""
    cli = shutil.which(current_app.config["GROK_CLI"])
    skill = Path(current_app.config["OMNI_SKILL_PATH"]).expanduser().resolve()
    if not cli or not skill.is_file():
        return jsonify(error="Grok CLI 或 ctf-router 技能不可用，请检查本机配置。"), 503
    instructions = request.form.get("instructions", "")
    uploads = [upload for upload in request.files.getlist("files") if upload.filename]
    if not uploads and not instructions.strip():
        return jsonify(error="请上传文件，或填写解题说明后再创建任务。"), 400
    root = _root()
    task_id = uuid.uuid4().hex
    task = root / task_id
    saved = False
    try:
        (task / "uploads").mkdir(parents=True)
        (task / ".aperisolve").mkdir()
        names = []
        for upload in uploads:
            name = (upload.filename or "attachment").replace("\\", "/").rsplit("/", 1)[-1]
            name = "".join(c for c in name if c.isprintable())
            if name in {"", ".", ".."}:
                name = "attachment"
            # Bound filesystem component length in UTF-8, preserving the extension.
            original_suffix = Path(name).suffix
            suffix = original_suffix.encode("utf-8")[:24].decode("utf-8", errors="ignore")
            stem = name[: -len(original_suffix)] if original_suffix else name
            stem = stem.encode("utf-8")[:180].decode("utf-8", errors="ignore") or "attachment"
            candidate = stem + suffix
            index = 2
            while (task / "uploads" / candidate).exists():
                candidate = f"{stem}_{index}{suffix}"
                index += 1
            destination = task / "uploads" / candidate
            upload.save(destination)
            names.append(
                {
                    "name": upload.filename,
                    "path": f"uploads/{candidate}",
                    "size": destination.stat().st_size,
                },
            )
        (task / "instructions.txt").write_text(instructions, encoding="utf-8")
        instruction_section = (
            "\n\n以下是用户的解题说明原文，请结合附件理解并遵守其中的 flag 格式要求：\n"
            + instructions
            if instructions.strip()
            else ""
        )
        attachment_section = (
            "附件（绝对路径）：\n" + "\n".join(f"- {task / str(item['path'])}" for item in names)
            if names
            else "本任务没有上传附件，请根据用户提供的解题说明/任务文本独立完成解题。\n"
        )
        prompt = (
            "这是用户提交的 CTF 解题任务，请直接完成解题。\n"
            f"任务工作目录：{task}\n"
            f"必须先读取 ctf-router 技能：{skill}\n"
            "按技能要求读取 references/catalog.md，选择 1-3 个相关技能，再读取对应的 "
            ".library/<name>/SKILL.md 执行，说明实际使用的技能路径。\n"
            "可以安装任意解题所需工具，并在当前任务环境中使用。\n"
            "所有解题文件和临时产物写在当前任务目录内。\n"
            + attachment_section
            + instruction_section
            + f"\n\n找到并验证 flag 后，将 flag 原文写入 {task / 'flag-re.txt'}，"
            f"每行一个 flag，不要写说明或 Markdown。解题过程另存 {task / 'solution.txt'}。"
            "若未找到，记录原因，不要编造 flag，也不要将未验证的猜测写入 flag-re.txt。"
            "这是无人值守任务，请根据已有信息自主推进，将缺失信息和错误写入日志。\n"
        )
        (task / "prompt.txt").write_text(prompt, encoding="utf-8")
        state = {
            "id": task_id,
            "status": "preparing",
            "created_at": time.time(),
            "started_at": None,
            "ended_at": None,
            "instructions": instructions,
            "uploads": names,
            "error": "",
            "exit_code": None,
            "grok_cli": cli,
            "session_max_age": current_app.config["OMNI_SESSION_MAX_AGE"],
        }
        with locked(task):
            write_state(task, state)
            saved = True
            with (task / "grok.log.txt").open("ab", buffering=0) as log:
                process = launch_runner(root, task_id, log)
            state["runner"] = process_identity(process.pid)
            write_state(task, state)
        publish_event(task_id, "task_created")
        return jsonify(task_id=task_id, status="preparing"), 202
    except OSError as exc:
        if saved:
            with locked(task):
                state = read_state(task)
                state.update(status="failed", error=str(exc), ended_at=time.time())
                write_state(task, state)
        else:
            shutil.rmtree(task, ignore_errors=True)
        return jsonify(error=f"无法保存或启动任务：{exc}"), 503


@omni_bp.get("")
def list_tasks() -> Response:
    """Return newest tasks, with a stable page size of twenty."""
    page = max(1, request.args.get("page", 1, type=int))
    root = _root()
    snapshots = []
    if root.exists():
        for path in root.iterdir():
            try:
                task = task_path(root, path.name)
                state = read_state(task)
                snapshots.append((state["created_at"], task))
            except (OSError, ValueError, KeyError):
                continue
    snapshots.sort(key=lambda row: row[0], reverse=True)
    tasks = []
    for _, task in snapshots[(page - 1) * 20 : page * 20]:
        with contextlib.suppress(OSError, ValueError):
            tasks.append(public_state(task, reconcile(task)))
    response = jsonify(tasks=tasks, page=page, total=len(snapshots), page_size=20)
    response.headers["Cache-Control"] = "no-store"
    return response


@omni_bp.get("/<task_id>")
def get_task(task_id: str) -> Response:
    """Return one expanded record for the homepage dialog."""
    task = _task(task_id)
    response = jsonify(public_state(task, reconcile(task)))
    response.headers["Cache-Control"] = "no-store"
    return response


@omni_bp.get("/<task_id>/text")
def get_text(task_id: str) -> Response:
    """Preview a bounded portion of an uploaded or generated TXT file."""
    try:
        result = preview(
            _task(task_id),
            request.args.get("path", ""),
            tail=request.args.get("tail") == "1",
        )
    except OSError:
        abort(404)
    response = jsonify(result)
    response.headers["Cache-Control"] = "no-store"
    return response


@omni_bp.get("/<task_id>/download")
def download_file(task_id: str) -> Response:
    """Download a regular file inside this task only."""
    relative = request.args.get("path", "")
    try:
        stream = open_task_file(_task(task_id), relative)
    except OSError:
        abort(404)
    response = send_file(
        stream,
        mimetype="application/octet-stream",
        as_attachment=True,
        download_name=relative.rsplit("/", 1)[-1],
    )
    response.call_on_close(stream.close)
    response.headers["Cache-Control"] = "no-store"
    return response


@omni_bp.post("/<task_id>/stop")
def stop_task(task_id: str) -> Response:
    """Stop the Grok session with a bounded grace period, retaining all files."""
    task = _task(task_id)
    with locked(task):
        state = read_state(task)
        if state["status"] not in ACTIVE:
            return jsonify(public_state(task, state))
        state["status"] = "stopping"
        write_state(task, state)
        identity = state.get("process")
        signal_group(identity, signal.SIGTERM)
    publish_event(task_id, "task_changed")
    deadline = time.monotonic() + 5
    while process_alive(identity) and time.monotonic() < deadline:
        time.sleep(0.1)
    signal_group(identity, signal.SIGKILL)
    # SIGKILL is asynchronous: do not claim completion until the kernel has
    # actually removed the process (or made it a zombie awaiting the runner).
    deadline = time.monotonic() + 1
    while process_alive(identity) and time.monotonic() < deadline:
        time.sleep(0.01)
    with locked(task):
        state = read_state(task)
        if state["status"] == "stopping" and not process_alive(identity):
            state.update(status="stopped", ended_at=time.time(), error="")
            write_state(task, state)
    publish_event(task_id, "task_changed")
    return jsonify(public_state(task, state))
