"""Full-mode isolation, lifecycle, cancellation and bounded file previews."""

import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import BinaryIO

import pytest
from flask import Flask
from flask.testing import FlaskClient
from werkzeug.datastructures import FileStorage
from werkzeug.test import TestResponse

from aperisolve import omni
from aperisolve.app import create_app
from aperisolve.models import Image, Submission
from aperisolve.omni_runner import format_event
from aperisolve.omni_store import (
    PREVIEW_BYTES,
    locked,
    process_alive,
    process_identity,
    read_state,
    write_state,
)


@pytest.fixture
def omni_app(app: Flask, tmp_path: Path) -> Flask:
    """Use a fake CLI which really runs in a detached OS process."""
    cli = tmp_path / "grok-test"
    cli.write_text(
        "#!/usr/bin/python3\n"
        "import json, os, pathlib, signal, subprocess, sys, time\n"
        "p = pathlib.Path.cwd()\n"
        "text = (p / 'instructions.txt').read_text()\n"
        "(p / 'invocation.txt').write_text(json.dumps({'cwd': str(p), 'args': sys.argv[1:]}))\n"
        "print(json.dumps({'update': {'content': {'text': '正在解题\\n'}}}), flush=True)\n"
        "if 'hold' in text:\n"
        "    signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "    child = subprocess.Popen([sys.executable, '-c', "
        "'import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(90)'])\n"
        "    (p / 'child.pid').write_text(str(child.pid))\n"
        "    time.sleep(90)\n"
        "if 'slow' in text: time.sleep(2)\n"
        "if 'fail' in text: sys.exit(7)\n"
        "if 'none' not in text: (p / 'flag-re.txt').write_text('exp{omni_test}\\n')\n"
        "(p / 'solution.txt').write_text('已验证测试附件。')\n",
        encoding="utf-8",
    )
    cli.chmod(0o755)
    skill = tmp_path / "SKILL.md"
    skill.write_text("test skill", encoding="utf-8")
    app.config.update(
        OMNI_DATA_FOLDER=tmp_path / "data", GROK_CLI=str(cli), OMNI_SKILL_PATH=str(skill),
    )
    return app


def post(
    client: FlaskClient,
    instructions: str = "flag的格式为 exp{XXXX}",
    files: list[tuple[io.BytesIO, str]] | None = None,
) -> TestResponse:
    """Create a single task with multiple independent upload fields."""
    return client.post(
        "/api/omni/tasks",
        data={
            "files": files if files is not None else [(io.BytesIO(b"challenge"), "题目.bin")],
            "instructions": instructions,
        },
    )


def wait_task(
    client: FlaskClient, task_id: str, *, statuses: set[str] | None = None, timeout: float = 12,
) -> dict:
    """Poll real process state with a bounded test deadline."""
    expected = statuses or {"completed", "no_flag", "failed", "stopped"}
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/api/omni/tasks/{task_id}")
        assert response.status_code == 200
        task = response.json
        if task["status"] in expected:
            return task
        time.sleep(0.05)
    pytest.fail(f"Task {task_id} did not reach {expected}: {task}")


def fake_launch(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Path, str]]:
    """Record launch without running a model for upload-only scenarios."""
    calls = []

    def launch(root: Path, task_id: str, _log: BinaryIO) -> SimpleNamespace:
        calls.append((root, task_id))
        return SimpleNamespace(pid=os.getpid())

    monkeypatch.setattr(omni, "launch_runner", launch)
    return calls


def test_real_grok_streaming_text_is_readable() -> None:
    """Display native Grok text events without a JSON wrapper."""
    assert format_event('{"type":"text","data":"正在解题"}\n') == "正在解题"
    assert format_event('{"type":"thought","data":"检查附件"}\n') == "检查附件"
    assert format_event("connection failed\n") == "connection failed\n"


def test_multifile_names_prompt_and_original_pipeline_isolation(
    omni_app: Flask, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep attachments and exact instructions separate from image submissions."""
    calls = fake_launch(monkeypatch)
    client = omni_app.test_client()
    text = "flag的格式为 exp{XXXX}\n保留原文 $() `test`"
    response = post(
        client,
        text,
        [
            (io.BytesIO(b"first"), "../../题目.txt"),
            (io.BytesIO(b"second"), "题目.txt"),
            (io.BytesIO(b"uploaded"), "flag-re.txt"),
            (io.BytesIO(b"raw"), "noextension"),
        ],
    )
    assert response.status_code == 202
    task_id = response.json["task_id"]
    task = omni_app.config["OMNI_DATA_FOLDER"] / task_id
    assert (task / "uploads/题目.txt").read_bytes() == b"first"
    assert (task / "uploads/题目_2.txt").read_bytes() == b"second"
    assert (task / "uploads/flag-re.txt").read_bytes() == b"uploaded"
    assert not (task / "flag-re.txt").exists()
    assert (task / "uploads/noextension").read_bytes() == b"raw"
    assert (task / "instructions.txt").read_text() == text
    prompt = (task / "prompt.txt").read_text()
    assert text in prompt
    assert "ctf-router" in prompt
    assert omni_app.config["OMNI_SKILL_PATH"] in prompt
    assert "uploads/题目_2.txt" in prompt
    assert len(calls) == 1
    assert "Location" not in response.headers
    with omni_app.app_context():
        assert Submission.query.count() == Image.query.count() == 0


def test_large_upload_bypasses_only_omni_request_limit(
    omni_app: Flask, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Allow large full-mode files without changing the original upload cap."""
    fake_launch(monkeypatch)
    omni_app.config["MAX_CONTENT_LENGTH"] = 1024
    client = omni_app.test_client()
    blob = b"a" * (17 * 1024 * 1024)
    response = post(client, files=[(io.BytesIO(blob), "large.dat")])
    assert response.status_code == 202
    task = omni_app.config["OMNI_DATA_FOLDER"] / response.json["task_id"]
    assert (task / "uploads/large.dat").stat().st_size == len(blob)
    original = client.post("/upload", data={"image": (io.BytesIO(blob), "large.dat")})
    assert original.status_code == 413
    assert omni_app.config["MAX_CONTENT_LENGTH"] == 1024


def test_two_identical_batches_create_independent_tasks(
    omni_app: Flask, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every submission starts a fresh task without deduplication."""
    calls = fake_launch(monkeypatch)
    client = omni_app.test_client()
    first = post(client).json["task_id"]
    second = post(client).json["task_id"]
    assert first != second
    assert len(calls) == 2


def test_missing_files_and_missing_cli_do_not_start(
    omni_app: Flask, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject unusable submissions before spawning a runner."""
    calls = fake_launch(monkeypatch)
    client = omni_app.test_client()
    assert client.post("/api/omni/tasks", data={}).status_code == 400
    assert post(client, files=[(io.BytesIO(b"x"), "")]).status_code == 400
    omni_app.config["GROK_CLI"] = "/does-not-exist"
    assert post(client).status_code == 503
    assert not calls


def test_save_failure_does_not_launch(omni_app: Flask, monkeypatch: pytest.MonkeyPatch) -> None:
    """Clean up partial uploads when disk writes fail."""
    calls = fake_launch(monkeypatch)

    def fail(*_args: object, **_kwargs: object) -> None:
        message = "No space left on device"
        raise OSError(message)

    monkeypatch.setattr(FileStorage, "save", fail)
    response = post(omni_app.test_client())
    assert response.status_code == 503
    assert "No space" in response.json["error"]
    assert not calls
    assert list(omni_app.config["OMNI_DATA_FOLDER"].iterdir()) == []


@pytest.mark.parametrize(
    ("instructions", "status", "exit_code"),
    [
        ("flag的格式为 exp{XXXX}", "completed", 0),
        ("none", "no_flag", 0),
        ("fail", "failed", 7),
    ],
)
def test_real_runner_output_and_exit_states(
    omni_app: Flask, instructions: str, status: str, exit_code: int,
) -> None:
    """Exercise CLI arguments, working directory and terminal outcomes."""
    client = omni_app.test_client()
    response = post(client, instructions)
    assert response.status_code == 202
    task_id = response.json["task_id"]
    task = wait_task(client, task_id)
    assert task["status"] == status
    assert task["exit_code"] == exit_code
    folder = omni_app.config["OMNI_DATA_FOLDER"] / task_id
    invocation = json.loads((folder / "invocation.txt").read_text())
    assert invocation["cwd"] == str(folder)
    args = invocation["args"]
    assert args[args.index("--cwd") + 1] == str(folder)
    assert args[args.index("--prompt-file") + 1] == str(folder / "prompt.txt")
    assert "--always-approve" in args
    assert "--no-plan" in args
    assert "--max-turns" not in args
    assert "--timeout" not in args
    assert "正在解题" in (folder / "grok.log.txt").read_text()
    assert task["flag"] == ("exp{omni_test}" if status == "completed" else "")


def test_parallel_tasks_and_new_app_keep_running(omni_app: Flask) -> None:
    """Run batches concurrently and reconnect through another Flask app."""
    client = omni_app.test_client()
    ids = [post(client, "slow").json["task_id"] for _ in range(2)]
    tasks = [wait_task(client, task_id, statuses={"running"}) for task_id in ids]
    assert all(task["status"] == "running" for task in tasks)

    fresh = create_app()
    fresh.config.update(OMNI_DATA_FOLDER=omni_app.config["OMNI_DATA_FOLDER"])
    assert all(wait_task(fresh.test_client(), task_id)["status"] == "completed" for task_id in ids)


def test_runner_survives_submitter_exit(omni_app: Flask) -> None:
    """Keep detached work alive after its submitting process exits."""
    config = {
        key: str(omni_app.config[key])
        for key in (
            "OMNI_DATA_FOLDER",
            "GROK_CLI",
            "OMNI_SKILL_PATH",
        )
    }
    script = (
        "import io,json; from aperisolve.app import create_app; a=create_app(); "
        f"a.config.update({config!r}); "
        "r=a.test_client().post('/api/omni/tasks', data={'instructions':'slow', "
        "'files':(io.BytesIO(b'x'),'x.bin')}); print(json.dumps(r.json))"
    )
    result = subprocess.run(  # noqa: S603 -- Fixed Python helper and generated test paths.
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=omni.PROJECT_ROOT,
        check=True,
        timeout=10,
    )
    task_id = json.loads(result.stdout)["task_id"]
    assert wait_task(omni_app.test_client(), task_id)["status"] == "completed"


def test_stop_kills_stubborn_descendants_and_preserves_files(omni_app: Flask) -> None:
    """Kill an entire stubborn tool session while retaining its artifacts."""
    client = omni_app.test_client()
    task_id = post(client, "hold").json["task_id"]
    folder = omni_app.config["OMNI_DATA_FOLDER"] / task_id
    child_identity = None
    try:
        wait_task(client, task_id, statuses={"running"})
        deadline = time.monotonic() + 5
        while not (folder / "child.pid").exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        child_identity = process_identity(int((folder / "child.pid").read_text()))
        state = read_state(folder)
        response = client.post(f"/api/omni/tasks/{task_id}/stop")
        assert response.status_code == 200
        assert response.json["status"] == "stopped"
        assert not process_alive(state["process"])
        deadline = time.monotonic() + 2
        while process_alive(child_identity) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not process_alive(child_identity)
        assert (folder / "uploads/题目.bin").exists()
        assert (folder / "grok.log.txt").exists()
        assert client.post(f"/api/omni/tasks/{task_id}/stop").json["status"] == "stopped"
    finally:
        client.post(f"/api/omni/tasks/{task_id}/stop")


def test_previews_downloads_and_path_boundaries(
    omni_app: Flask, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """Bound text reads and reject traversal, symlinks and nonregular files."""
    fake_launch(monkeypatch)
    client = omni_app.test_client()
    task_id = post(client).json["task_id"]
    folder = omni_app.config["OMNI_DATA_FOLDER"] / task_id
    (folder / "result.txt").write_text("中文 <script>alert(1)</script>")
    (folder / "huge.txt").write_bytes(b"a" * (PREVIEW_BYTES + 1))
    outside = tmp_path / "private.txt"
    outside.write_text("private")
    (folder / "escape.txt").symlink_to(outside)
    (folder / "escape-dir").symlink_to(tmp_path, target_is_directory=True)
    os.mkfifo(folder / "pipe.txt")
    base = f"/api/omni/tasks/{task_id}"
    response = client.get(base + "/text", query_string={"path": "result.txt"})
    assert response.json["text"] == "中文 <script>alert(1)</script>"
    assert response.headers["Cache-Control"] == "no-store"
    assert client.get(base + "/text?path=huge.txt").json["truncated"]
    assert len(client.get(base + "/text?path=huge.txt").json["text"]) == PREVIEW_BYTES
    downloaded = client.get(base + "/download?path=result.txt")
    assert downloaded.data.decode() == response.json["text"]
    assert "attachment" in downloaded.headers["Content-Disposition"]
    for path in [
        "../private.txt",
        "/etc/passwd",
        "escape.txt",
        "escape-dir/private.txt",
        ".aperisolve/task.json",
        "pipe.txt",
        "uploads/题目.bin",
        "bad\x00.txt",
    ]:
        assert client.get(base + "/text", query_string={"path": path}).status_code == 404
    for path in ["../private.txt", "escape.txt", "escape-dir/private.txt", ".aperisolve/task.json"]:
        assert client.get(base + "/download", query_string={"path": path}).status_code == 404
    assert client.get("/api/omni/tasks/not-a-task").status_code == 404


def test_stale_runner_pid_identity_and_terminal_stop(
    omni_app: Flask, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject reused PIDs and keep terminal states stable."""
    fake_launch(monkeypatch)
    client = omni_app.test_client()
    task_id = post(client).json["task_id"]
    folder = omni_app.config["OMNI_DATA_FOLDER"] / task_id
    with locked(folder):
        state = read_state(folder)
        state["runner"]["start"] = "0"
        write_state(folder, state)
    response = client.get(f"/api/omni/tasks/{task_id}")
    assert response.json["status"] == "failed"
    assert client.post(f"/api/omni/tasks/{task_id}/stop").json["status"] == "failed"


def test_records_paginate_and_home_has_no_detail_navigation(
    omni_app: Flask, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep records paginated inside the homepage dialog."""
    fake_launch(monkeypatch)
    client = omni_app.test_client()
    ids = [post(client).json["task_id"] for _ in range(21)]
    first = client.get("/api/omni/tasks").json
    second = client.get("/api/omni/tasks?page=2").json
    assert first["total"] == 21
    assert len(first["tasks"]) == 20
    assert len(second["tasks"]) == 1
    assert first["tasks"][0]["id"] == ids[-1]
    assert second["tasks"][0]["id"] == ids[0]
    home = client.get("/").get_data(as_text=True)
    assert 'id="omni-mode"' in home
    assert 'id="omni-history"' in home
    assert "全能任务记录" in home
    assert client.get(f"/omni/tasks/{ids[0]}").status_code == 404
