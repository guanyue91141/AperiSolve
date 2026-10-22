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
  const dialog = document.getElementById("omni-history");
  const list = document.getElementById("omni-task-list");
  const historyMessage = document.getElementById("omni-history-message");
  const previous = document.getElementById("omni-prev");
  const next = document.getElementById("omni-next");
  const statuses = {preparing: "准备中", running: "运行中", stopping: "停止中",
    completed: "已找到 flag", no_flag: "未找到 flag", failed: "失败", stopped: "已停止"};
  const active = new Set(["preparing", "running", "stopping"]);
  let uploading = false;
  let page = 1;
  let refreshTimer;
  let generation = 0;
  let refreshing = false;
  const rows = new Map();

  const api = (id = "", action = "") => `/api/omni/tasks${id ? `/${id}` : ""}${action ? `/${action}` : ""}`;
  async function copyText(text) {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
        return;
      }
    } catch {}
    const field = document.createElement("textarea");
    field.value = text;
    field.setAttribute("readonly", "");
    field.style.position = "fixed";
    field.style.opacity = "0";
    document.body.append(field);
    field.select();
    const copied = document.execCommand("copy");
    field.remove();
    if (!copied) throw new Error("clipboard copy unavailable");
  }
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
    document.getElementById("original-analysis-options").hidden = mode.checked;
    document.getElementById("omni-instructions-group").hidden = !mode.checked;
    if (!mode.checked && input.files.length > 1) input.value = "";
    if (!input.files.length) dragMessage.textContent = mode.checked
      ? "📂 拖放多个文件到这里，或点击选择文件（不限制文件类型与上传大小）"
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
      if (!input.files.length) { notify("请至少选择一个文件。", true); return; }
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
      notify("正在上传附件，上传完成后自动开始后台解题。不会跳转页面。");
      xhr.upload.onprogress = (event) => {
        if (!event.lengthComputable) return;
        const percent = Math.round(event.loaded / event.total * 100);
        bar.style.width = `${percent}%`;
        bar.textContent = percent === 100 ? "附件已上传，正在创建任务…" : `${percent}%`;
      };
      xhr.onload = () => {
        let result;
        try { result = JSON.parse(xhr.responseText); } catch { result = {}; }
        if (xhr.status === 202 && result.task_id) {
          bar.style.width = "100%";
          bar.textContent = "任务已创建";
          notify(`任务已创建（${result.task_id.slice(0, 8)}），请点击左上角“任务记录”查看进度。`);
          input.value = "";
          syncMode();
          if (dialog.open) refresh();
        } else {
          notify(result.error || `创建任务失败（${xhr.status}），请重试。`, true);
          progress.classList.add("d-none");
        }
      };
      xhr.onerror = () => {
        notify("上传连接中断。请先查看任务记录，确认是否已创建任务，再决定是否重试。", true);
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
  function fileUrl(id, action, path, tail = false) {
    return `${api(id, action)}?${new URLSearchParams({path, ...(tail ? {tail: "1"} : {})})}`;
  }
  function createRow(task) {
    const node = document.createElement("details");
    node.className = "omni-task";
    node.dataset.taskId = task.id;
    // Only static markup goes through innerHTML; user content uses textContent.
    node.innerHTML = `<summary><span class="omni-task-title"></span><span class="omni-task-status"></span>
      <span class="omni-task-meta"></span><span class="omni-task-hint"></span>
      <span class="omni-task-flag-group"><code class="omni-task-flag"></code><button type="button" class="btn btn-sm btn-outline-light omni-copy-flag" hidden>复制</button></span></summary>
      <div class="omni-task-body"><strong>解题说明</strong><pre class="omni-instructions"></pre>
      <p class="omni-task-error" role="status"></p><div class="omni-task-actions">
      <button type="button" class="btn btn-outline-danger omni-stop">停止任务</button>
      <div class="omni-preview-buttons" role="group" aria-label="任务文本">
        <button type="button" class="btn btn-outline-light omni-preview-button" data-path="grok.log.txt" aria-pressed="true">日志</button>
        <button type="button" class="btn btn-outline-light omni-preview-button" data-path="prompt.txt" aria-pressed="false">提示词</button>
        <button type="button" class="btn btn-outline-light omni-preview-button" data-path="flag-re.txt" aria-pressed="false">flag</button>
      </div></div>
      <p class="omni-preview-note text-muted small" role="status"></p><pre class="omni-preview" tabindex="0"></pre></div>`;
    const row = {node, task, selected: "grok.log.txt", loading: false, previewVersion: 0};
    row.output = node.querySelector(".omni-preview");
    row.note = node.querySelector(".omni-preview-note");
    row.stop = node.querySelector(".omni-stop");
    node.addEventListener("toggle", () => { if (node.open) loadDetails(row); });
    node.querySelectorAll(".omni-preview-button").forEach((button) => button.addEventListener("click", () => {
      row.selected = button.dataset.path;
      node.querySelectorAll(".omni-preview-button").forEach((item) => {
        item.setAttribute("aria-pressed", String(item === button));
      });
      loadPreview(row);
    }));
    const copyFlag = node.querySelector(".omni-copy-flag");
    copyFlag.addEventListener("click", async (event) => {
      event.preventDefault();
      event.stopPropagation();
      try {
        await copyText(row.task.flag);
        copyFlag.textContent = "已复制";
        setTimeout(() => { copyFlag.textContent = "复制"; }, 1500);
      } catch {
        copyFlag.textContent = "复制失败";
        setTimeout(() => { copyFlag.textContent = "复制"; }, 2000);
      }
    });
    row.stop.addEventListener("click", async () => {
      row.stop.disabled = true;
      row.stop.textContent = "正在停止…";
      try {
        const result = await json(api(task.id, "stop"), {method: "POST"});
        updateRow(row, result);
        await loadDetails(row);
      } catch (error) {
        row.node.querySelector(".omni-task-error").textContent = error.message;
      } finally { row.stop.disabled = false; row.stop.textContent = "停止任务"; }
    });
    return row;
  }
  function updateRow(row, task) {
    row.task = task;
    row.node.querySelector(".omni-task-title").textContent = task.uploads.map((file) => file.name).join(" · ");
    const status = row.node.querySelector(".omni-task-status");
    status.textContent = statuses[task.status] || task.status;
    status.dataset.status = task.status;
    row.node.querySelector(".omni-task-meta").textContent = `${task.id.slice(0, 8)} · ${new Date(task.created_at * 1000).toLocaleString()} · ${duration(task)}`;
    row.node.querySelector(".omni-task-hint").textContent = task.instructions.slice(0, 150) || "未填写解题说明";
    row.node.querySelector(".omni-task-flag").textContent = task.flag || "";
    row.node.querySelector(".omni-copy-flag").hidden = !task.flag;
    row.node.querySelector(".omni-instructions").textContent = task.instructions || "（无）";
    row.node.querySelector(".omni-task-error").textContent = task.error || "";
    row.stop.hidden = !active.has(task.status);
  }
  async function loadPreview(row) {
    const path = row.selected;
    if (!path) return;
    const version = ++row.previewVersion;
    row.output.textContent = "正在读取…";
    try {
      const data = await json(fileUrl(row.task.id, "text", path, path === "grok.log.txt"));
      if (version !== row.previewVersion || !dialog.open || !row.node.open) return;
      const atEnd = row.output.scrollTop + row.output.clientHeight >= row.output.scrollHeight - 30;
      row.output.textContent = data.text || (path === "flag-re.txt" ? "（空）" : "（内容为空，运行中任务会自动更新）");
      row.note.textContent = data.truncated ? "内容超过 256 KiB，仅预览" + (data.tail ? "末尾" : "开头") + "部分。" : "";
      if (atEnd && path === "grok.log.txt") row.output.scrollTop = row.output.scrollHeight;
    } catch (error) {
      if (version !== row.previewVersion || !dialog.open || !row.node.open) return;
      if (path === "flag-re.txt" && error.message.includes("404")) {
        row.output.textContent = "（空）";
        row.note.textContent = "";
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
      if (!dialog.open || !row.node.open) return;
      updateRow(row, task);
      await loadPreview(row);
    } catch (error) {
      row.node.querySelector(".omni-task-error").textContent = error.message;
    } finally { row.loading = false; }
  }
  async function refresh() {
    if (!dialog.open || refreshing) return;
    refreshing = true;
    const current = generation;
    try {
      const result = await json(`${api()}?page=${page}`);
      if (!dialog.open || current !== generation) return;
      historyMessage.textContent = result.total ? "" : "暂无全能任务，请在首页勾选全能模式后提交。";
      const ids = new Set(result.tasks.map((task) => task.id));
      for (const [id, row] of rows) {
        if (!ids.has(id)) { row.node.remove(); rows.delete(id); }
      }
      for (const [index, task] of result.tasks.entries()) {
        let row = rows.get(task.id);
        if (!row) { row = createRow(task); rows.set(task.id, row); }
        updateRow(row, task);
        if (list.children[index] !== row.node) list.insertBefore(row.node, list.children[index] || null);
        if (row.node.open) await loadDetails(row);
      }
      previous.disabled = page <= 1;
      next.disabled = page * result.page_size >= result.total;
      document.getElementById("omni-page").textContent = `第 ${page} / ${Math.max(1, Math.ceil(result.total / result.page_size))} 页`;
    } catch (error) { historyMessage.textContent = `更新失败：${error.message}`; }
    finally {
      refreshing = false;
      clearTimeout(refreshTimer);
      if (dialog.open) refreshTimer = setTimeout(refresh, 3000);
    }
  }
  document.getElementById("omni-history-open").addEventListener("click", () => {
    if (!dialog.open) dialog.showModal();
    generation++;
    refresh();
  });
  document.getElementById("omni-history-close").addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => { generation++; clearTimeout(refreshTimer); });
  previous.addEventListener("click", () => { page--; generation++; refresh(); });
  next.addEventListener("click", () => { page++; generation++; refresh(); });
})();
