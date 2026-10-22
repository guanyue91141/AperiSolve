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
from typing import BinaryIO

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
    app.register_blueprint(omni_bp)


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
def create_task() -> tuple[Response, int]:
    """Save a batch and start its own Grok process; never enqueue image analysis."""
    cli = shutil.which(current_app.config["GROK_CLI"])
    skill = Path(current_app.config["OMNI_SKILL_PATH"]).expanduser().resolve()
    if not cli or not skill.is_file():
        return jsonify(error="Grok CLI 或 ctf-router 技能不可用，请检查本机配置。"), 503
    uploads = request.files.getlist("files")
    if not uploads or any(not upload.filename for upload in uploads):
        return jsonify(error="请至少选择一个文件。"), 400
    instructions = request.form.get("instructions", "")
    root = _root()
    task_id = uuid.uuid4().hex
    task = root / task_id
    saved = False
    try:
        (task / "uploads").mkdir(parents=True)
        (task / ".aperisolve").mkdir()
        names = []
        for upload in uploads:
            name = upload.filename.replace("\\", "/").rsplit("/", 1)[-1]
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
        prompt = (
            "这是用户提交的 CTF 解题任务，请直接完成解题。\n"
            f"任务工作目录：{task}\n"
            f"必须先读取 ctf-router 技能：{skill}\n"
            "按技能要求读取 references/catalog.md，选择 1-3 个相关技能，再读取对应的 "
            ".library/<name>/SKILL.md 执行，说明实际使用的技能路径。\n"
            "所有解题文件和临时产物写在当前任务目录内。附件位于：\n"
            + "\n".join(f"- {item['path']}" for item in names)
            + instruction_section
            + "\n\n找到并验证 flag 后，将 flag 原文写入当前任务根目录的 flag-re.txt，"
            "每行一个 flag，不要写说明或 Markdown。解题过程另存 solution.txt。"
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
        }
        with locked(task):
            write_state(task, state)
            saved = True
            with (task / "grok.log.txt").open("ab", buffering=0) as log:
                process = launch_runner(root, task_id, log)
            state["runner"] = process_identity(process.pid)
            write_state(task, state)
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
    response = jsonify(public_state(task, reconcile(task), detail=True))
    response.headers["Cache-Control"] = "no-store"
    return response


@omni_bp.get("/<task_id>/text")
def get_text(task_id: str) -> Response:
    """Preview a bounded portion of an uploaded or generated TXT file."""
    try:
        result = preview(
            _task(task_id), request.args.get("path", ""), tail=request.args.get("tail") == "1",
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
    return jsonify(public_state(task, state))
