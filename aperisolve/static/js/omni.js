/* Full-mode uploads and task history stay on the homepage. */
(() => {
  "use strict";
  const mode = document.getElementById("omni-mode");
  if (!mode) return;
  const input = document.getElementById("image");
  const instructions = document.getElementById("omni-instructions");
  const submit = document.querySelector("#upload-form button[type=submit]");
  const browse = document.getElementById("browse-btn");
  const dragMessage = document.getElementById("drag-msg");
  const initialDragMessage = dragMessage.textContent;
  const initialSubmit = submit.innerHTML;
  const initialBrowse = browse.innerHTML;
  const message = document.getElementById("omni-upload-message");
  const sidebar = document.getElementById("omni-history");
  const historyToggle = document.getElementById("omni-history-open");
  const historyClose = document.getElementById("omni-history-close");
  const list = document.getElementById("omni-task-list");
  const historyMessage = document.getElementById("omni-history-message");
  const previous = document.getElementById("omni-prev");
  const next = document.getElementById("omni-next");
  const statuses = {preparing: "准备中", running: "运行中", stopping: "停止中",
    completed: "已完成", no_flag: "未找到 flag", failed: "失败", stopped: "已停止"};
  const active = new Set(["preparing", "running", "stopping"]);
  let uploading = false;
  let page = 1;
  let generation = 0;
  let refreshing = false;
  let socket;
  let socketRetry;
  let socketRetryDelay = 1000;
  let taskTotal = 0;
  const rows = new Map();

  const api = (id = "", action = "") => `/api/omni/tasks${id ? `/${id}` : ""}${action ? `/${action}` : ""}`;
  async function json(url, options) {
    const response = await fetch(url, {cache: "no-store", ...options});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `请求失败（${response.status}）`);
    return data;
  }
  function notify(text, failed = false) {
    message.hidden = false;
    message.className = `alert mt-3 ${failed ? "alert-danger" : "alert-success"}`;
    message.textContent = text;
  }
  function setBusy(value) {
    uploading = value;
    submit.disabled = mode.disabled = input.disabled = browse.disabled = value;
  }
  function syncMode() {
    input.multiple = mode.checked;
    input.required = !mode.checked;
    document.getElementById("original-analysis-options").hidden = mode.checked;
    document.getElementById("omni-instructions-group").hidden = !mode.checked;
    if (!mode.checked && input.files.length > 1) input.value = "";
    if (!input.files.length) dragMessage.textContent = mode.checked
      ? "📂 文件可选：拖放或粘贴多个文件到这里"
      : initialDragMessage;
    submit.innerHTML = mode.checked ? '<i class="fa fa-play me-2" aria-hidden="true"></i>创建任务' : initialSubmit;
    browse.innerHTML = mode.checked ? '<i class="fa fa-folder-open me-2" aria-hidden="true"></i>选择多个文件' : initialBrowse;
  }
  mode.addEventListener("change", syncMode);
  window.OmniUI = {
    enabled: () => mode.checked,
    busy: () => uploading,
    submit() {
      if (uploading) return;
      if (!input.files.length && !instructions.value.trim()) {
        notify("请上传文件，或填写解题说明后再创建任务。", true);
        return;
      }
      const data = new FormData();
      for (const file of input.files) data.append("files", file);
      data.append("instructions", instructions.value);
      const xhr = new XMLHttpRequest();
      xhr.open("POST", api());
      const progress = document.getElementById("progress-container");
      const bar = document.getElementById("progress-bar");
      progress.classList.remove("d-none");
      bar.style.width = "0%";
      bar.textContent = "0%";
      setBusy(true);
      notify(input.files.length
        ? "正在上传附件，上传完成后自动开始后台解题。不会跳转页面。"
        : "正在创建仅包含解题说明的任务。不会跳转页面。");
      xhr.upload.onprogress = (event) => {
        if (!event.lengthComputable) return;
        const percent = Math.round(event.loaded / event.total * 100);
        bar.style.width = `${percent}%`;
        bar.textContent = percent === 100
          ? (input.files.length ? "附件已上传，正在创建任务…" : "正在创建任务…")
          : `${percent}%`;
      };
      xhr.onload = () => {
        let result;
        try { result = JSON.parse(xhr.responseText); } catch { result = {}; }
        if (xhr.status === 202 && result.task_id) {
          bar.style.width = "100%";
          bar.textContent = "任务已创建";
          notify(`任务已创建（${result.task_id.slice(0, 8)}），请点击左上角“更多”查看进度。`);
          input.value = "";
          syncMode();
          if (!sidebar.hidden) loadTask(result.task_id, true);
        } else {
          notify(result.error || `创建任务失败（${xhr.status}），请重试。`, true);
          progress.classList.add("d-none");
        }
      };
      xhr.onerror = () => {
        notify("上传连接中断。请先点击“更多”查看，确认是否已创建任务，再决定是否重试。", true);
        progress.classList.add("d-none");
      };
      xhr.onloadend = () => setBusy(false);
      xhr.send(data);
    },
  };
  syncMode();

  function duration(task) {
    const seconds = Math.max(0, Math.floor(((task.ended_at || Date.now() / 1000) - (task.started_at || task.created_at))));
    return `${Math.floor(seconds / 3600)}时 ${Math.floor(seconds / 60) % 60}分 ${seconds % 60}秒`;
  }
  function fileUrl(id, action, path, tail = false, solver = "grok") {
    return `${api(id, action)}?${new URLSearchParams({path, solver, ...(tail ? {tail: "1"} : {})})}`;
  }
  function createRow(task) {
    const node = document.createElement("article");
    node.className = "omni-task";
    node.dataset.taskId = task.id;
    // Only static markup goes through innerHTML; user content uses textContent.
    node.innerHTML = `<div class="omni-task-header"><div class="omni-task-heading"><span class="omni-task-title"></span><span class="omni-task-status"></span></div>
      <button type="button" class="btn btn-sm btn-outline-light omni-expand" aria-expanded="false">展开</button></div>
      <span class="omni-task-meta"></span>
      <span class="omni-task-flag-group"><code class="omni-task-flag"></code></span>
      <div class="omni-task-body" hidden>
      <p class="omni-task-error" role="status"></p><div class="omni-task-actions">
      <div class="omni-solver-buttons" role="group" aria-label="切换解题分支"></div>
      <div class="omni-preview-buttons" role="group" aria-label="当前分支文件与操作">
        <button type="button" class="btn btn-outline-light omni-preview-button" data-file="log" aria-pressed="true">进度</button>
        <button type="button" class="btn btn-outline-light omni-preview-button" data-file="solution.txt" aria-pressed="false">教程</button>
        <button type="button" class="btn btn-outline-light omni-preview-button" data-file="prompt.txt" aria-pressed="false">TXT</button>
        <button type="button" class="btn btn-outline-light omni-preview-button" data-file="flag-re.txt" aria-pressed="false">flag</button>
      </div></div>
      <p class="omni-preview-note text-muted small" role="status"></p><pre class="omni-preview" tabindex="0"></pre></div>`;
    const row = {node, task, selected: "grok.log.txt", selectedFile: "log", selectedSolver: "grok", expanded: false, loading: false, previewVersion: 0, solverButtonNodes: new Map()};
    row.output = node.querySelector(".omni-preview");
    row.note = node.querySelector(".omni-preview-note");
    const body = node.querySelector(".omni-task-body");
    row.solverButtons = node.querySelector(".omni-solver-buttons");
    row.previewButtons = node.querySelector(".omni-preview-buttons");
    row.stop = document.createElement("button");
    row.stop.type = "button";
    row.stop.className = "btn btn-sm btn-danger omni-stop";
    row.stop.addEventListener("click", async () => {
      const solverId = row.selectedSolver;
      const solver = row.task.solvers?.find((item) => item.id === solverId);
      if (!solver || !active.has(solver.status)) return;
      if (!window.confirm(`确定停止“${solver.name || solverId}”分支吗？其他分支会继续运行。`)) return;
      row.stop.disabled = true;
      row.stop.textContent = "正在停止…";
      try {
        const result = await json(api(row.task.id, `stop/${encodeURIComponent(solverId)}`), {method: "POST"});
        updateRow(row, result);
        await loadDetails(row);
      } catch (error) {
        row.node.querySelector(".omni-task-error").textContent = error.message;
      } finally {
        row.stop.disabled = false;
        const selectedSolver = row.task.solvers?.find((item) => item.id === row.selectedSolver);
        row.stop.textContent = `停止 ${selectedSolver?.name || "当前分支"}`;
      }
    });
    row.previewButtons.append(row.stop);
    const expand = node.querySelector(".omni-expand");
    expand.addEventListener("click", () => {
      row.expanded = !row.expanded;
      body.hidden = !row.expanded;
      expand.textContent = row.expanded ? "收起" : "展开";
      expand.setAttribute("aria-expanded", String(row.expanded));
      if (row.expanded) loadDetails(row);
    });
    node.querySelectorAll(".omni-preview-button").forEach((button) => button.addEventListener("click", () => {
      row.selectedFile = button.dataset.file;
      row.selected = row.selectedFile === "log"
        ? (row.selectedSolver === "grok" ? "grok.log.txt" : "log.txt")
        : row.selectedFile;
      node.querySelectorAll(".omni-preview-button").forEach((item) => {
        item.setAttribute("aria-pressed", String(item === button));
      });
      loadPreview(row);
    }));
    return row;
  }
  function setText(node, value) {
    if (node.textContent !== value) node.textContent = value;
  }
  function updateRow(row, task) {
    row.task = task;
    setText(row.node.querySelector(".omni-task-title"), task.uploads.map((file) => file.name).join(" · ") || "仅说明任务");
    const status = row.node.querySelector(".omni-task-status");
    setText(status, statuses[task.status] || task.status);
    status.dataset.status = task.status;
    setText(row.node.querySelector(".omni-task-meta"), `${task.id.slice(0, 8)} · ${new Date(task.created_at * 1000).toLocaleString()} · ${duration(task)}`);
    setText(row.node.querySelector(".omni-task-flag"), task.flag || "");
    setText(row.node.querySelector(".omni-task-error"), task.error || "");
    const solvers = task.solvers || [];
    if (!solvers.some((solver) => solver.id === row.selectedSolver)) row.selectedSolver = "grok";
    for (const solver of solvers) {
      let button = row.solverButtonNodes.get(solver.id);
      if (!button) {
        button = document.createElement("button");
        button.type = "button";
        button.className = "btn btn-sm";
        button.addEventListener("click", () => {
          row.selectedSolver = solver.id;
          row.selected = row.selectedFile === "log"
            ? (solver.id === "grok" ? "grok.log.txt" : "log.txt")
            : row.selectedFile;
          updateRow(row, row.task);
          if (row.expanded) loadPreview(row);
        });
        row.solverButtonNodes.set(solver.id, button);
      }
      const selected = solver.id === row.selectedSolver;
      const shortName = solver.id === "grok" ? "G"
        : solver.id.startsWith("pi-") ? "P"
          : solver.id === "codex" ? "C" : solver.name;
      const label = `${shortName} · ${statuses[solver.status] || solver.status}`;
      button.classList.toggle("omni-solver-selected", selected);
      button.textContent = label;
      button.title = `${solver.name} · ${statuses[solver.status] || solver.status}`;
      button.setAttribute("aria-label", `${solver.name} · ${statuses[solver.status] || solver.status}`);
      button.setAttribute("aria-pressed", String(selected));
      row.solverButtons.append(button);

    }
    for (const [solverId, button] of row.solverButtonNodes) {
      if (!solvers.some((solver) => solver.id === solverId)) {
        button.remove();
        row.solverButtonNodes.delete(solverId);
      }
    }
    const selectedSolver = solvers.find((solver) => solver.id === row.selectedSolver);
    row.stop.hidden = !active.has(selectedSolver?.status);
    row.stop.textContent = `停止 ${selectedSolver?.name || "当前分支"}`;
    row.stop.setAttribute("aria-label", `停止 ${selectedSolver?.name || "当前分支"} 分支`);
    row.node.querySelectorAll(".omni-preview-button").forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.file === row.selectedFile));
    });
  }
  async function loadPreview(row) {
    const path = row.selected;
    if (!path) return;
    const version = ++row.previewVersion;
    row.output.textContent = "正在读取…";
    try {
      const data = await json(fileUrl(row.task.id, "text", path, path === "grok.log.txt" || path === "log.txt", row.selectedSolver));
      if (version !== row.previewVersion || sidebar.hidden || !row.expanded) return;
      const atEnd = row.output.scrollTop + row.output.clientHeight >= row.output.scrollHeight - 30;
      row.output.textContent = data.text || (path === "flag-re.txt" ? "（空）" : "（内容为空，运行中任务会自动更新）");
      row.note.textContent = data.truncated ? "内容超过 256 KiB，仅预览" + (data.tail ? "末尾" : "开头") + "部分。" : "";
      if (atEnd && path === "grok.log.txt") row.output.scrollTop = row.output.scrollHeight;
    } catch (error) {
      if (version !== row.previewVersion || sidebar.hidden || !row.expanded) return;
      if (path === "flag-re.txt" && error.message.includes("404")) {
        row.output.textContent = "（空）";
        row.note.textContent = "";
      } else if ((path === "solution.txt" || path === "log.txt") && error.message.includes("404")) {
        row.output.textContent = "（解题记录尚未生成）";
        row.note.textContent = "该分支运行后会在这里显示进度与产物。";
      } else {
        row.output.textContent = "";
        row.note.textContent = `预览暂不可用：${error.message}`;
      }
    }
  }
  async function loadDetails(row) {
    if (row.loading) return;
    row.loading = true;
    try {
      const task = await json(api(row.task.id));
      if (sidebar.hidden || !row.expanded) return;
      updateRow(row, task);
      await loadPreview(row);
    } catch (error) {
      row.node.querySelector(".omni-task-error").textContent = error.message;
    } finally { row.loading = false; }
  }
  function renderPager(pageSize = 20) {
    previous.disabled = page <= 1;
    next.disabled = page * pageSize >= taskTotal;
    setText(document.getElementById("omni-page"), `第 ${page} / ${Math.max(1, Math.ceil(taskTotal / pageSize))} 页`);
  }
  async function loadTask(taskId, insertIfNew = false) {
    if (sidebar.hidden) return;
    const current = generation;
    try {
      const task = await json(api(taskId));
      if (sidebar.hidden || current !== generation) return;
      let row = rows.get(taskId);
      if (!row && insertIfNew && page === 1) {
        row = createRow(task);
        rows.set(taskId, row);
        list.insertBefore(row.node, list.firstChild);
        taskTotal++;
        setText(historyMessage, "");
        renderPager();
      }
      if (row) updateRow(row, task);
    } catch (error) {
      setText(historyMessage, `更新失败：${error.message}`);
    }
  }
  function handleSocketMessage(message) {
    let event;
    try { event = JSON.parse(message.data); } catch { return; }
    if (event.type === "ready") {
      socketRetryDelay = 1000;
      return;
    }
    if (!event.task_id) return;
    if (event.type === "task_created") {
      if (page === 1) loadTask(event.task_id, true);
      else setText(historyMessage, "有新任务，请回到第 1 页查看。");
      return;
    }
    const row = rows.get(event.task_id);
    if (!row) return;
    if (event.type === "task_changed") loadTask(event.task_id);
    if (event.type === "log_changed" && row.expanded && row.selectedFile === "log") {
      loadPreview(row);
    }
  }
  function connectSocket() {
    if (sidebar.hidden || socket) return;
    const url = new URL("/api/omni/tasks/ws", window.location.href);
    url.protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const connection = new WebSocket(url);
    socket = connection;
    connection.addEventListener("message", handleSocketMessage);
    connection.addEventListener("close", () => {
      if (socket !== connection) return;
      socket = null;
      if (sidebar.hidden) return;
      socketRetry = setTimeout(() => {
        socketRetry = null;
        connectSocket();
      }, socketRetryDelay);
      socketRetryDelay = Math.min(socketRetryDelay * 2, 30000);
    });
  }
  function closeSocket() {
    clearTimeout(socketRetry);
    socketRetry = null;
    const connection = socket;
    socket = null;
    if (connection && connection.readyState < WebSocket.CLOSING) connection.close();
  }
  async function refresh() {
    if (sidebar.hidden || refreshing) return;
    refreshing = true;
    const current = generation;
    try {
      const result = await json(`${api()}?page=${page}`);
      if (sidebar.hidden || current !== generation) return;
      taskTotal = result.total;
      setText(historyMessage, result.total ? "" : "暂无深度分析任务，请在首页勾选“深度分析”后提交。");
      const ids = new Set(result.tasks.map((task) => task.id));
      for (const [id, row] of rows) {
        if (!ids.has(id)) { row.node.remove(); rows.delete(id); }
      }
      for (const [index, task] of result.tasks.entries()) {
        let row = rows.get(task.id);
        if (!row) { row = createRow(task); rows.set(task.id, row); }
        updateRow(row, task);
        if (list.children[index] !== row.node) list.insertBefore(row.node, list.children[index] || null);
        if (row.expanded) await loadDetails(row);
      }
      renderPager(result.page_size);
    } catch (error) { setText(historyMessage, `加载失败：${error.message}`); }
    finally { refreshing = false; }
  }
  function setHistoryOpen(open) {
    if (open === !sidebar.hidden) return;
    const restoreFocus = sidebar.contains(document.activeElement);
    sidebar.hidden = !open;
    historyToggle.setAttribute("aria-expanded", String(open));
    document.body.classList.toggle("omni-history-visible", open);
    generation++;
    if (open) {
      historyClose.focus({preventScroll: true});
      connectSocket();
      refresh();
    } else {
      closeSocket();
      if (restoreFocus) historyToggle.focus({preventScroll: true});
    }
  }
  historyToggle.addEventListener("click", () => setHistoryOpen(sidebar.hidden));
  historyClose.addEventListener("click", () => setHistoryOpen(false));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !sidebar.hidden && !event.defaultPrevented) {
      event.preventDefault();
      setHistoryOpen(false);
    }
  });
  previous.addEventListener("click", () => { page--; generation++; refresh(); });
  next.addEventListener("click", () => { page++; generation++; refresh(); });
})();
