// Injected by base.html from the backend analyzer registry; the literal
// list is only a fallback for pages served without the injection.
const TOOL_ORDER = window.TOOL_ORDER || [
  "decomposer",
  "base64_images",
  "spectrogram",
  "color_remapping",
  "file",
  "file_anomalies",
  "pdfinfo",
  "pdfid",
  "exiftool",
  "binwalk",
  "foremost",
  "outguess",
  "pngcheck",
  "pcrt",
  "identify",
  "steghide",
  "jpseek",
  "jsteg",
  "openstego",
  "zsteg",
  "strings"
];

function escapeHtml(text) {
  if (typeof text !== "string") return text;
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Translation lookup: window.I18N is injected by base.html; the English
// string doubles as the key and the fallback.
function t(text) {
  return (window.I18N && window.I18N[text]) || text;
}

function capitalize(str) {
  if (typeof str !== "string" || str.length === 0) return str;
  return str.charAt(0).toUpperCase() + str.slice(1);
}

function slideUp(element, duration = 400) {
  element.style.height = element.offsetHeight + "px";
  element.offsetHeight; // force reflow
  element.style.transitionProperty = "height, margin, padding";
  element.style.transitionDuration = duration + "ms";
  element.style.boxSizing = "border-box";
  element.style.overflow = "hidden";
  element.style.height = 0;
  element.style.paddingTop = 0;
  element.style.paddingBottom = 0;
  element.style.marginTop = 0;
  element.style.marginBottom = 0;

  window.setTimeout(() => {
    element.style.display = "none";
    // Optional: reset styles
    element.style.removeProperty("height");
    element.style.removeProperty("padding-top");
    element.style.removeProperty("padding-bottom");
    element.style.removeProperty("margin-top");
    element.style.removeProperty("margin-bottom");
    element.style.removeProperty("overflow");
    element.style.removeProperty("transition-duration");
    element.style.removeProperty("transition-property");
  }, duration);
}

function formatBytes(bytes) {
  if (typeof bytes !== "number" || isNaN(bytes)) return bytes;
  const units = ["B", "KB", "MB", "GB", "TB", "PB"];
  let i = 0;
  while (bytes >= 1024 && i < units.length - 1) {
    bytes /= 1024;
    i++;
  }
  return `${bytes % 1 === 0 ? bytes : bytes.toFixed(2)} ${units[i]}`;
}

/**
 * Alert functions
 */

function showAlert(message, alertType, reset) {
  const resultDiv = document.getElementById("result-analyzers");
  if (reset) {
    resultDiv.innerHTML = "";
  }
  resultDiv.innerHTML += `<div class="alert alert-${escapeHtml(
    alertType
  )}" role="alert">${escapeHtml(message)}</div>`;
}

function showSuccess(message, reset) {
  showAlert(message, "success", reset);
}
function showDanger(message, reset) {
  showAlert(message, "danger", reset);
}
function showWarning(message, reset) {
  showAlert(message, "warning", reset);
}
function showInfo(message, reset) {
  showAlert(message, "info", reset);
}

/**
 * Copy to clipboard
 */

document.addEventListener('click', function (event) {
  // Check if the clicked element is a copy icon
  if (event.target.classList.contains('copy-icon')) {
    const icon = event.target;
    const codeContainer = icon.closest('.code-container');
    const codeBlock = codeContainer ? codeContainer.querySelector('code') : null;

    if (codeBlock) {
      const textToCopy = codeBlock.textContent;
      navigator.clipboard.writeText(textToCopy).then(() => {
        icon.classList.remove('fa-copy');
        icon.classList.add('fa-check');
        setTimeout(() => {
          icon.classList.remove('fa-check');
          icon.classList.add('fa-copy');
        }, 1500);
      });
    }
  }
});

/**
 * Image preview functions
 */

// Reference the modal elements
const modal = document.getElementById("image-modal-container");
const modalImage = document.getElementById("modal-image");

let currentImages = [];
let currentIndex = -1;

function updateCurrentImages() {
  currentImages = Array.from(document.querySelectorAll(".results_img img"));
}

// Function to handle image click (open modal)
function openImageModal(src) {
  updateCurrentImages();
  currentIndex = currentImages.findIndex((img) => img.src === src);
  if (currentIndex !== -1) {
    modalImage.src = currentImages[currentIndex].src;
    modalImage.alt = currentImages[currentIndex].alt || "";
    modal.classList.add("modal-visible");
    modal.classList.remove("modal-hidden");
  }
}

function closeImageModal() {
  modal.classList.remove("modal-visible");
  modal.classList.add("modal-hidden");
  currentIndex = -1;
}

// Handle dynamic images added with innerHTML
document.addEventListener("click", function (e) {
  const img = e.target.closest(".results_img img");
  if (img) {
    openImageModal(img.src);
  }
});

// Click on modal image to download and close
modalImage.addEventListener("click", function () {
  const link = document.createElement("a");
  link.href = modalImage.src;
  link.download = modalImage.src.split("/").pop();
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  closeImageModal();
});

// Optional: Close modal if user clicks outside the image
modal.addEventListener("click", function (e) {
  if (e.target === modal) {
    closeImageModal();
  }
});

// Keyboard support
document.addEventListener("keydown", function (e) {
  if (!modal.classList.contains("modal-visible")) return;

  if (e.key === "Escape") {
    closeImageModal();
  } else if (e.key === "ArrowLeft") {
    // Show previous image
    if (currentIndex > 0) {
      currentIndex--;
      modalImage.src = currentImages[currentIndex].src;
    }
  } else if (e.key === "ArrowRight") {
    // Show next image
    if (currentIndex < currentImages.length - 1) {
      currentIndex++;
      modalImage.src = currentImages[currentIndex].src;
    }
  }
});

// Build the type-appropriate original-file preview shown in the info panel.
// The upload can now be any file, so branch on the backend-detected kind:
// image -> <img>, video -> player, audio -> player, everything else -> a
// download file card. The default is ALWAYS the file card, never a bare <img>,
// so an unknown or non-image upload cannot render a broken image.
function renderMainPreview(infoData) {
  const src = escapeHtml(infoData.image_path);
  const rawName =
    (Array.isArray(infoData.names) && infoData.names[0]) ||
    String(infoData.image_path || "").split("/").pop();
  const fileName = escapeHtml(rawName);

  if (infoData.kind === "image") {
    return `<img src="${src}" alt="${t("Analyzed file")}" decoding="async" fetchpriority="low"/>`;
  }
  if (infoData.kind === "video") {
    // #t=0.1 nudges the browser to render a poster frame instead of a blank box.
    return `<video controls preload="metadata" playsinline src="${src}#t=0.1"></video>`;
  }
  if (infoData.kind === "audio") {
    return `<audio controls preload="metadata" src="${src}"></audio>`;
  }
  const icon = infoData.kind === "pdf" ? "fa-file-pdf" : "fa-file";
  return (
    `<div class="file-card">` +
    `<i class="fa ${icon} file-card-icon"></i>` +
    `<span class="file-card-name"><code>${fileName}</code></span>` +
    `<a href="${src}" class="btn btn-primary mt-2" download>` +
    `<i class="fa fa-download"></i> ${t("Download file")}</a>` +
    `</div>`
  );
}

async function fetchImageInfo(submission_hash) {
  let infoData;
  try {
    const infoResp = await fetch(`/infos/${submission_hash}`);
    if (!infoResp.ok) throw new Error(`HTTP ${infoResp.status}`);
    infoData = await infoResp.json();
  } catch (error) {
    // The info panel is auxiliary: a transient failure must not break the page.
    console.error("Failed to load image info:", error);
    return;
  }

  const resultInfosDiv = document.getElementById("result-infos");
  resultInfosDiv.innerHTML = ""; // Clear previous info

  const mainImgLeft = document.createElement("div");
  const mainImgRight = document.createElement("div");
  const tableInfos = document.createElement("table");
  mainImgLeft.id = "main-img-left";
  mainImgRight.id = "main-img-right";
  resultInfosDiv.appendChild(mainImgLeft);
  resultInfosDiv.appendChild(mainImgRight);
  mainImgRight.appendChild(tableInfos);

  mainImgLeft.innerHTML += `<div id="main_image">${renderMainPreview(infoData)}</div>`;
  tableInfos.innerHTML += `<tr><td><i class="fa fa-backward-step"></i> ${t("First upload:")}</td><td>${infoData.first_submission_date}</td></tr>`;
  tableInfos.innerHTML += `<tr><td><i class="fa fa-history"></i> ${t("Last upload:")}</td><td>${infoData.last_submission_date}</td></tr>`;
  if (Array.isArray(infoData.names)) {
    const nameList = infoData.names
      .map((name) => `<code>${escapeHtml(name)}</code>`)
      .join(", ");
    tableInfos.innerHTML += `<tr><td><i class="fa fa-list"></i> ${t("Name(s):")}</td><td>${nameList}</td></tr>`;
  }
  tableInfos.innerHTML += `<tr><td><i class="fa fa-balance-scale"></i> ${t("Size:")}</td><td>${formatBytes(
    infoData.size
  )}</td></tr>`;
  tableInfos.innerHTML += `<tr><td><i class="fa fa-upload"></i> ${t("Upload count:")}</td><td>${infoData.upload_count}</td></tr>`;
  if (Array.isArray(infoData.passwords) && infoData.passwords.length > 0) {
    await displayPasswordsWithRemoval(tableInfos, infoData.passwords, submission_hash, infoData);
  }

  // Fetch removal status and update removal UI
  await updateRemovalUI(submission_hash, infoData);
}

async function displayPasswordsWithRemoval(tableInfos, passwords, submission_hash, infoData) {
  const tr = document.createElement("tr");
  const tdLabel = document.createElement("td");
  const tdContent = document.createElement("td");

  tdLabel.innerHTML = `<i class="fa fa-key"></i> ${t("Common password(s):")}`;
  tr.appendChild(tdLabel);
  tr.appendChild(tdContent);
  tableInfos.appendChild(tr);

  // Clear existing password timer if any
  if (passwordTimerIntervals[submission_hash]) {
    clearInterval(passwordTimerIntervals[submission_hash]);
    delete passwordTimerIntervals[submission_hash];
  }

  const uploadTime = infoData.submission_date * 1000;
  const currentTime = new Date().getTime();
  const ageSeconds = Math.floor((currentTime - uploadTime) / 1000);
  const REMOVAL_MIN_AGE_SECONDS = infoData.removal_min_age_seconds || 300;

  for (const pwd of passwords) {
    const passwordSpan = document.createElement("span");
    passwordSpan.className = "password-item";
    passwordSpan.innerHTML = `<code>${escapeHtml(pwd)}</code>`;

    // Check if this password can be removed
    const canRemove = ageSeconds >= REMOVAL_MIN_AGE_SECONDS;

    if (canRemove) {
      const deleteIcon = document.createElement("i");
      deleteIcon.className = "fas fa-times password-delete-icon";
      deleteIcon.title = t("Remove password");
      deleteIcon.dataset.submissionHash = submission_hash;
      deleteIcon.dataset.password = pwd;
      deleteIcon.style.cursor = "pointer";
      deleteIcon.style.marginLeft = "5px";
      deleteIcon.style.color = "#ff4d4d";

      deleteIcon.addEventListener("click", async function() {
        await handlePasswordRemoval(submission_hash, deleteIcon);
      });

      passwordSpan.appendChild(deleteIcon);
    }

    tdContent.appendChild(passwordSpan);
    tdContent.appendChild(document.createTextNode(" "));
  }

  // Set up timer to refresh when passwords become eligible for removal
  if (ageSeconds < REMOVAL_MIN_AGE_SECONDS) {
    const remainingSeconds = REMOVAL_MIN_AGE_SECONDS - ageSeconds;
    passwordTimerIntervals[submission_hash] = setInterval(async () => {
      const newUploadTime = infoData.submission_date * 1000;
      const newCurrentTime = new Date().getTime();
      const newAgeSeconds = Math.floor((newCurrentTime - newUploadTime) / 1000);

      if (newAgeSeconds >= REMOVAL_MIN_AGE_SECONDS) {
        // Time has elapsed, refresh the password display
        clearInterval(passwordTimerIntervals[submission_hash]);
        delete passwordTimerIntervals[submission_hash];

        // Re-fetch info and refresh display
        const infoResp = await fetch(`/infos/${submission_hash}`);
        const newInfoData = await infoResp.json();

        // Clear and rebuild password row
        tr.remove();
        await displayPasswordsWithRemoval(tableInfos, newInfoData.passwords, submission_hash, newInfoData);
      }
    }, Math.min(remainingSeconds * 1000, 1000)); // Check every second or at the exact time
  }
}

async function checkPasswordRemovalEligibility(submission_hash, password, infoData) {
  try {
    // Check age constraint using submission date, not first_submission_date
    const uploadTime = infoData.submission_date * 1000; // Convert to milliseconds
    const currentTime = new Date().getTime();
    const ageSeconds = Math.floor((currentTime - uploadTime) / 1000);
    const REMOVAL_MIN_AGE_SECONDS = infoData.removal_min_age_seconds || 300;

    if (ageSeconds < REMOVAL_MIN_AGE_SECONDS) {
      return false;
    }
    return true;
  } catch (error) {
    console.error("Error checking password removal eligibility:", error);
    return false;
  }
}

async function handlePasswordRemoval(submission_hash, iconElement) {
  try {
    iconElement.style.pointerEvents = "none";
    iconElement.style.opacity = "0.5";

    const response = await fetch(`/remove_password/${submission_hash}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
    });

    if (response.ok) {
      // Remove the password item from display
      const passwordSpan = iconElement.closest(".password-item");
      if (passwordSpan) {
        passwordSpan.style.transition = "opacity 0.3s";
        passwordSpan.style.opacity = "0";
        setTimeout(() => passwordSpan.remove(), 300);
      }
    } else {
      // Silently fail - just re-enable the icon
      iconElement.style.pointerEvents = "auto";
      iconElement.style.opacity = "1";
    }
  } catch (error) {
    console.error("Password removal error:", error);
    iconElement.style.pointerEvents = "auto";
    iconElement.style.opacity = "1";
  }
}

/**
 * Image removal functionality
 */

let removalTimerIntervals = {};
let passwordTimerIntervals = {};

async function updateRemovalUI(submission_hash, infoData) {
  const resultRemovalDiv = document.getElementById("result-removal");
  resultRemovalDiv.innerHTML = "";

  try {

    // Extract upload timestamp from first_submission_date
    const uploadTime = new Date(infoData.first_submission_date).getTime();
    const currentTime = new Date().getTime();
    const ageSeconds = Math.floor((currentTime - uploadTime) / 1000);
    const REMOVAL_MIN_AGE_SECONDS = infoData.removal_min_age_seconds || 300;

    const removalContainer = document.createElement("div");
    removalContainer.className = "card removal-card";
    resultRemovalDiv.appendChild(removalContainer);

    if (ageSeconds < REMOVAL_MIN_AGE_SECONDS) {
      const remainingSeconds = REMOVAL_MIN_AGE_SECONDS - ageSeconds;
      removalContainer.innerHTML = `
        <h3><i class="fa fa-trash"></i> ${t("Remove Image")}</h3>
        <p>${t("Available in {s} seconds").replace("{s}", `<span id="removal-countdown">${remainingSeconds}</span>`)}</p>
        <button class="btn btn-primary" disabled id="remove-btn">${t("Remove Image")}</button>
      `;

      // Clear existing interval if any
      if (removalTimerIntervals[submission_hash]) {
        clearInterval(removalTimerIntervals[submission_hash]);
      }

      // Start countdown timer
      removalTimerIntervals[submission_hash] = setInterval(() => {
        const countdownEl = document.getElementById("removal-countdown");
        if (countdownEl) {
          const current = parseInt(countdownEl.textContent);
          if (current > 1) {
            countdownEl.textContent = current - 1;
          } else {
            clearInterval(removalTimerIntervals[submission_hash]);
            updateRemovalUI(submission_hash, infoData);
          }
        }
      }, 1000);
    } else {
      // Check for multiple IPs - we'll do this by attempting removal
      removalContainer.innerHTML = `
        <h3><i class="fa fa-trash"></i> ${t("Remove Image")}</h3>
        <button class="btn btn-primary" id="remove-btn">${t("Remove Image")}</button>
        <p id="removal-status"></p>
      `;

      const removeBtn = document.getElementById("remove-btn");
      removeBtn.addEventListener("click", async () => {
        removeBtn.disabled = true;
        const statusEl = document.getElementById("removal-status");

        try {
          const response = await fetch(`/remove/${submission_hash}`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
            },
          });

          const data = await response.json();

          if (response.ok) {
            statusEl.innerHTML = `<span class="text-success"><i class="fa fa-check"></i> ${t("Image successfully removed")}</span>`;
            removeBtn.style.display = "none";
            setTimeout(() => { document.location = '/'; }, 2000);
          } else if (response.status === 403) {
            if (data.error.includes("multiple IP")) {
              statusEl.innerHTML = `<span class="text-danger"><i class="fa fa-warning"></i> ${escapeHtml(data.error)}</span>`;
            } else {
              statusEl.innerHTML = `<span class="text-danger"><i class="fa fa-warning"></i> ${escapeHtml(data.error)}</span>`;
            }
            removeBtn.disabled = false;
          } else {
            statusEl.innerHTML = `<span class="text-danger"><i class="fa fa-exclamation-circle"></i> ${t("Error:")} ${escapeHtml(data.error)}</span>`;
            removeBtn.disabled = false;
          }
        } catch (error) {
          statusEl.innerHTML = `<span class="text-danger"><i class="fa fa-exclamation-circle"></i> ${t("Network error occurred")}</span>`;
          removeBtn.disabled = false;
          console.error("Removal error:", error);
        }
      });
    }
  } catch (error) {
    console.error("Error updating removal UI:", error);
  }
}

/**
 * Parsing results from the server
 */

const WIKI_TOOLS = window.WIKI_TOOLS || [];
const LANG_PREFIX = window.LANG_PREFIX || "";

// Analyzer heading: links to the tool's wiki guide when one exists.
function analyzerTitle(tool) {
  if (tool === "file_anomalies") {
    return t("File anomaly inspection (magic number and terminator analysis)");
  }
  const knownTitles = {
    binwalk: "Binwalk (embedded file and signature scanning)",
    base64_images: "Base64 image detection (embedded images)",
    color_remapping: "Color remapping",
    decomposer: "Decomposer (image bit-plane analysis)",
    exiftool: "ExifTool metadata",
    file: "File (file type identification)",
    foremost: "Foremost (file carving and recovery analysis)",
    identify: "Identify (image format and properties)",
    jpseek: "JPSeek (JPHide steganography extraction)",
    jsteg: "JSteg (JPEG coefficient steganography analysis)",
    openstego: "OpenStego (image steganography extraction)",
    outguess: "OutGuess (JPEG steganography analysis)",
    pdfid: "PDFiD (PDF suspicious keyword scan)",
    pdfinfo: "PDFInfo (PDF metadata inspection)",
    pcrt: "PCRT (PNG repair and trailing data recovery)",
    pngcheck: "Pngcheck (PNG chunk and CRC validation)",
    spectrogram: "Spectrogram (audio frequency visualization)",
    steghide: "Steghide (file steganography extraction)",
    strings: "Strings (hexadecimal and text search)",
    zsteg: "zsteg (PNG/BMP bit-plane steganography analysis)",
  };
  const label = t(knownTitles[tool] || capitalize(tool.replace("_", " ")));
  if (WIKI_TOOLS.includes(tool)) {
    return `<a class="analyzer-title-link" href="${LANG_PREFIX}/wiki/tools/${tool}"
      title="${t("Learn more")}">${label} <i class="fa fa-book-open fa-2xs"></i></a>`;
  }
  return label;
}

// Spinner shown between upload and the first results.
function renderAnalyzing() {
  const resultDiv = document.getElementById("result-analyzers");
  if (resultDiv.querySelector(".analyzer")) return; // results already streaming in
  resultDiv.innerHTML =
    `<div class="analyzing" role="status" aria-live="polite">` +
    `<span class="spinner" aria-hidden="true"></span>` +
    `<p class="mb-0">${t("Analyzing your file…")}</p></div>`;
}

function renderHexRow(row) {
  const start = Number(row.offset);
  return `<div class="hex-row" role="row" data-start="${Number.isFinite(start) ? start : 0}"
    data-search-hex="${escapeHtml(row.hex || "").toLowerCase()}"
    data-search-ascii="${escapeHtml(row.ascii || "").toLowerCase()}"
    data-search-offset="0x${escapeHtml(row.offset_hex || "").toLowerCase()}">
    <span class="hex-offset" role="cell">${escapeHtml(row.offset_hex || "")}</span>
    <span class="hex-bytes" role="cell">${escapeHtml(row.hex || "")}</span>
    <span class="hex-ascii" role="cell">${escapeHtml(row.ascii || "")}</span>
  </div>`;
}

function getHexCellForSelection(node) {
  const element = node?.nodeType === Node.ELEMENT_NODE ? node : node?.parentElement;
  return element?.closest(".hex-bytes, .hex-ascii") || null;
}

function getSelectionOffsetInCell(node, offset, cell) {
  if (node?.nodeType === Node.TEXT_NODE && node.parentElement === cell) {
    return Math.max(0, Math.min(offset, node.textContent.length));
  }
  try {
    const prefix = document.createRange();
    prefix.selectNodeContents(cell);
    prefix.setEnd(node, offset);
    return prefix.toString().length;
  } catch {
    return 0;
  }
}

document.addEventListener("copy", (event) => {
  const selection = window.getSelection();
  if (!selection || selection.isCollapsed) return;
  const anchorCell = getHexCellForSelection(selection.anchorNode);
  const focusCell = getHexCellForSelection(selection.focusNode);
  if (!anchorCell || !focusCell) return;
  const selectedType = anchorCell.classList.contains("hex-bytes") ? "hex-bytes" : "hex-ascii";
  if (!focusCell.classList.contains(selectedType)) return;
  const workspace = anchorCell.closest(".strings-workspace");
  if (!workspace || workspace !== focusCell.closest(".strings-workspace")) return;

  const cells = Array.from(workspace.querySelectorAll(`.hex-grid .${selectedType}`));
  const anchorIndex = cells.indexOf(anchorCell);
  const focusIndex = cells.indexOf(focusCell);
  if (anchorIndex < 0 || focusIndex < 0) return;

  const anchorOffset = getSelectionOffsetInCell(selection.anchorNode, selection.anchorOffset, anchorCell);
  const focusOffset = getSelectionOffsetInCell(selection.focusNode, selection.focusOffset, focusCell);
  const forward = anchorIndex < focusIndex || (anchorIndex === focusIndex && anchorOffset <= focusOffset);
  const firstIndex = forward ? anchorIndex : focusIndex;
  const lastIndex = forward ? focusIndex : anchorIndex;
  const firstOffset = forward ? anchorOffset : focusOffset;
  const lastOffset = forward ? focusOffset : anchorOffset;
  const selectedText = cells.slice(firstIndex, lastIndex + 1).map((cell, relativeIndex) => {
    const text = cell.textContent || "";
    if (firstIndex === lastIndex) return text.slice(firstOffset, lastOffset);
    if (relativeIndex === 0) return text.slice(firstOffset);
    if (relativeIndex === lastIndex - firstIndex) return text.slice(0, lastOffset);
    return text;
  }).join("\n");

  if (!event.clipboardData) return;
  event.clipboardData.setData("text/plain", selectedText);
  event.preventDefault();
});

const STRINGS_RENDER_BATCH_SIZE = 200;

function appendStringBatch(list) {
  const strings = list._allStrings || [];
  const start = Number(list.dataset.renderedCount || 0);
  const end = Math.min(start + STRINGS_RENDER_BATCH_SIZE, strings.length);
  const fragment = document.createDocumentFragment();
  for (let index = start; index < end; index++) {
    const item = strings[index];
    const offset = item.offset ? Number.parseInt(item.offset, 16) : NaN;
    const offsetLabel = item.offset ? "0x" + item.offset : "—";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "strings-item";
    button.dataset.offset = Number.isFinite(offset) ? String(offset) : "";
    button.dataset.searchText = String(item.text || "").toLowerCase();
    button.dataset.searchOffset = offsetLabel.toLowerCase();
    const offsetSpan = document.createElement("span");
    offsetSpan.className = "strings-item-offset";
    offsetSpan.textContent = offsetLabel;
    const textSpan = document.createElement("span");
    textSpan.className = "strings-item-text";
    textSpan.textContent = item.text || "";
    button.append(offsetSpan, textSpan);
    fragment.appendChild(button);
  }
  list.insertBefore(fragment, list.querySelector(".strings-load-more"));
  list.dataset.renderedCount = String(end);
  const button = list.querySelector(".strings-load-more");
  if (button) {
    button.textContent = t("Show more strings") + " (" + end + " / " + strings.length + ")";
    button.hidden = end >= strings.length;
  }
  const count = list.closest(".extracted-strings-pane")?.querySelector(".strings-search-count");
  if (count && !count.dataset.searchActive) count.textContent = end + " / " + strings.length;
}

document.addEventListener("click", (event) => {
  const button = event.target.closest(".strings-load-more");
  if (!button) return;
  const list = button.closest(".strings-list");
  if (list) appendStringBatch(list);
});

function renderStringsOutput(data, submissionHash = "") {
  const rows = Array.isArray(data.hex_rows) ? data.hex_rows : [];
  const strings = Array.isArray(data.strings) ? data.strings : [];
  const hexRows = rows.map(renderHexRow).join("");
  const stringRows = strings.slice(0, STRINGS_RENDER_BATCH_SIZE).map((item) => {
    const offset = item.offset ? Number.parseInt(item.offset, 16) : NaN;
    const offsetLabel = item.offset ? `0x${item.offset}` : "—";
    return `<button type="button" class="strings-item" data-offset="${Number.isFinite(offset) ? offset : ""}"
      data-search-text="${escapeHtml(item.text || "").toLowerCase()}"
      data-search-offset="${escapeHtml(offsetLabel).toLowerCase()}">
      <span class="strings-item-offset">${escapeHtml(offsetLabel)}</span>
      <span class="strings-item-text">${escapeHtml(item.text || "")}</span>
    </button>`;
  }).join("");
  const previewNote = data.preview_truncated
    ? `<div class="strings-view-note hex-preview-note">${t("Showing the first 4096 bytes")} · ${escapeHtml(formatBytes(Number(data.file_size) || 0))}</div>`
    : "";
  const truncationNote = data.strings_truncated
    ? `<div class="strings-view-note">${t("String output was truncated")}</div>`
    : "";

  return `<div class="strings-view-intro">${t("WinHex-style byte and string view")}</div>
    ${previewNote}${truncationNote}
    <div class="strings-workspace" data-submission-hash="${escapeHtml(submissionHash)}" data-needs-full-load="${data.preview_truncated ? "true" : "false"}">
      <section class="strings-pane hex-pane" aria-label="${t("Hex view")}">
        <div class="strings-pane-heading">${t("Hex view")} <span>${t("Offset")} · ${t("Hex bytes")} · ${t("ASCII")}</span></div>
        <div class="strings-search-row">
          <input type="search" class="strings-search-input hex-search-input" aria-label="${t("Search hex bytes, ASCII, or offset")}" placeholder="${t("Search hex bytes, ASCII, or offset")}" autocomplete="off">
          <button type="button" class="strings-search-nav" data-direction="previous" aria-label="${t("Previous match")}" disabled>${t("Previous match")}</button>
          <button type="button" class="strings-search-nav" data-direction="next" aria-label="${t("Next match")}" disabled>${t("Next match")}</button>
          <span class="strings-search-count" aria-live="polite">${rows.length} / ${rows.length}</span>
        </div>
        <div class="hex-grid" role="table" aria-label="${t("Hex view")}">
          <div class="hex-row hex-grid-heading" role="row"><span role="columnheader">${t("Offset")}</span><span role="columnheader">${t("Hex bytes")}</span><span role="columnheader">${t("ASCII")}</span></div>
          ${hexRows || `<div class="strings-empty">${t("No bytes to display")}</div>`}
          <div class="strings-empty search-empty" hidden>${t("No matches found.")}</div>
        </div>
      </section>
      <section class="strings-pane extracted-strings-pane" aria-label="${t("Extracted strings")}">
        <div class="strings-pane-heading">${t("Extracted strings")} <span>${strings.length}</span></div>
        <div class="strings-search-row">
          <input type="search" class="strings-search-input extracted-search-input" aria-label="${t("Search extracted strings or offset")}" placeholder="${t("Search extracted strings or offset")}" autocomplete="off">
          <button type="button" class="strings-search-nav" data-direction="previous" aria-label="${t("Previous match")}" disabled>${t("Previous match")}</button>
          <button type="button" class="strings-search-nav" data-direction="next" aria-label="${t("Next match")}" disabled>${t("Next match")}</button>
          <span class="strings-search-count" aria-live="polite">${strings.length} / ${strings.length}</span>
        </div>
        <p class="strings-pane-hint">${t("Select a string to locate its bytes in the hex view.")}</p>
        <div class="strings-list" data-rendered-count="${Math.min(strings.length, STRINGS_RENDER_BATCH_SIZE)}">${stringRows || `<div class="strings-empty">${t("No printable strings found.")}</div>`}<button type="button" class="strings-load-more"${strings.length <= STRINGS_RENDER_BATCH_SIZE ? " hidden" : ""}>${t("Show more strings")} (${Math.min(strings.length, STRINGS_RENDER_BATCH_SIZE)} / ${strings.length})</button><div class="strings-empty search-empty" hidden>${t("No matches found.")}</div></div>
      </section>
    </div>`;
}

function renderLegacyStringsOutput(lines, preview, submissionHash = "") {
  const rows = Array.isArray(preview?.hex_rows) ? preview.hex_rows : [];
  const bytes = [];
  for (const row of rows) {
    for (const pair of String(row.hex || "").match(/[0-9a-fA-F]{2}/g) || []) {
      bytes.push(Number.parseInt(pair, 16));
    }
  }

  let searchFrom = 0;
  const strings = lines.map((line) => {
    const text = typeof line === "string" ? line : String(line ?? "");
    const needle = Array.from(new TextEncoder().encode(text));
    let offset = -1;
    if (needle.length) {
      for (let start = searchFrom; start <= bytes.length - needle.length; start++) {
        if (needle.every((value, index) => bytes[start + index] === value)) {
          offset = start;
          searchFrom = start + needle.length;
          break;
        }
      }
      if (offset < 0) {
        for (let start = 0; start <= bytes.length - needle.length; start++) {
          if (needle.every((value, index) => bytes[start + index] === value)) {
            offset = start;
            break;
          }
        }
      }
    }
    return { offset: offset >= 0 ? offset.toString(16).toUpperCase() : "", text };
  });

  return renderStringsOutput({
    ...(preview || {}),
    hex_rows: rows,
    strings,
    strings_truncated: false,
  }, submissionHash);
}

const legacyHexPreviewCache = new Map();

function loadLegacyHexPreview(submissionHash) {
  if (legacyHexPreviewCache.has(submissionHash)) {
    return legacyHexPreviewCache.get(submissionHash);
  }
  const request = fetch(`/hex-preview/${encodeURIComponent(submissionHash)}`)
    .then((response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    })
    .catch((error) => {
      legacyHexPreviewCache.delete(submissionHash);
      throw error;
    });
  legacyHexPreviewCache.set(submissionHash, request);
  return request;
}

async function loadHexWindow(workspace, offset, isCurrent = () => true) {
  const submissionHash = workspace?.dataset.submissionHash;
  if (!submissionHash) return false;
  if (workspace.dataset.fullPreviewLoaded === "true") return true;
  if (workspace._fullPreviewPromise) {
    const loaded = await workspace._fullPreviewPromise;
    if (loaded) return true;
  }
  const response = await fetch(`/hex-preview/${encodeURIComponent(submissionHash)}?offset=${encodeURIComponent(offset)}`);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const preview = await response.json();
  if (!isCurrent()) return false;
  const grid = workspace.querySelector(".hex-grid");
  if (!grid) return false;
  grid.querySelectorAll(".hex-row:not(.hex-grid-heading)").forEach((row) => row.remove());
  const empty = grid.querySelector(":scope > .strings-empty:not(.search-empty)");
  empty?.remove();
  grid.insertAdjacentHTML("beforeend", (preview.hex_rows || []).map(renderHexRow).join(""));

  const summary = workspace.closest(".analyzer")?.querySelector(".hex-preview-note");
  if (summary && Number(preview.preview_start) > 0) {
    summary.textContent = `${t("Showing bytes around offset")} 0x${Number(offset).toString(16).toUpperCase()} · ${formatBytes(Number(preview.file_size) || 0)}`;
  }
  const displayed = workspace.querySelector(".strings-pane-heading span");
  if (displayed && Number(preview.preview_start) > 0) {
    displayed.textContent = `${t("Window at offset")} 0x${Number(preview.preview_start).toString(16).toUpperCase()}`;
  }
  return true;
}

function loadFullHexPreview(workspace) {
  if (!workspace?.dataset.submissionHash) return Promise.resolve(false);
  if (workspace.dataset.fullPreviewLoaded === "true") return Promise.resolve(true);
  if (workspace._fullPreviewPromise) return workspace._fullPreviewPromise;

  const submissionHash = workspace.dataset.submissionHash;
  workspace._fullPreviewPromise = fetch(`/hex-preview/${encodeURIComponent(submissionHash)}?full=1`)
    .then((response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    })
    .then((preview) => {
      if (!workspace.isConnected) return false;
      const grid = workspace.querySelector(".hex-grid");
      if (!grid) return false;
      grid.querySelectorAll(".hex-row:not(.hex-grid-heading)").forEach((row) => row.remove());
      grid.querySelector(":scope > .strings-empty:not(.search-empty)")?.remove();
      grid.insertAdjacentHTML("beforeend", (preview.hex_rows || []).map(renderHexRow).join(""));
      workspace.dataset.fullPreviewLoaded = "true";
      workspace.dataset.needsFullLoad = "false";
      workspace.closest(".analyzer")?.querySelector(".hex-preview-note")?.remove();

      const heading = workspace.querySelector(".hex-pane .strings-pane-heading span");
      if (heading) heading.textContent = `${t("Offset")} · ${t("Hex bytes")} · ${t("ASCII")}`;
      const count = workspace.querySelector(".hex-pane .strings-search-count");
      const rowCount = (preview.hex_rows || []).length;
      if (count) count.textContent = `${rowCount} / ${rowCount}`;

      const search = workspace.querySelector(".hex-search-input");
      if (search?.value.trim()) updateStringsSearch(search);
      return true;
    })
    .catch((error) => {
      workspace._fullPreviewPromise = null;
      console.error("Failed to load the complete hex view:", error);
      return false;
    });
  return workspace._fullPreviewPromise;
}

function getStringsSearchMatches(container, query, hexSearch) {
  if (!query) return [];

  const matches = [];
  const seen = new Set();
  const addMatch = (offset, rows, item = null) => {
    const safeOffset = Number.isFinite(offset) ? offset : Number.MAX_SAFE_INTEGER;
    const key = item ? `string:${item.dataset.offset}:${item.dataset.searchText}` : `hex:${safeOffset}`;
    if (seen.has(key)) return;
    seen.add(key);
    matches.push({ offset: safeOffset, rows, item });
  };

  if (!hexSearch) {
    for (const item of container.querySelectorAll(".strings-item")) {
      if (item.dataset.searchText.includes(query) || item.dataset.searchOffset.includes(query)) {
        addMatch(item.dataset.offset ? Number(item.dataset.offset) : NaN, [], item);
      }
    }
    return matches.sort((a, b) => a.offset - b.offset);
  }

  const rows = Array.from(container.querySelectorAll(".hex-row:not(.hex-grid-heading)"));
  const asciiChars = [];
  const asciiOffsets = [];
  const hexBytes = [];
  const byteOffsets = [];
  for (const [rowIndex, row] of rows.entries()) {
    const rowStart = Number(row.dataset.start) || 0;
    const rowAscii = row.dataset.searchAscii || "";
    for (let charIndex = 0; charIndex < rowAscii.length; charIndex++) {
      const char = rowAscii[charIndex];
      asciiChars.push(char);
      asciiOffsets.push({ offset: rowStart + charIndex, rowIndex });
    }
    const bytes = (row.dataset.searchHex || "").match(/[0-9a-f]{2}/g) || [];
    for (let byteIndex = 0; byteIndex < bytes.length; byteIndex++) {
      hexBytes.push(bytes[byteIndex]);
      byteOffsets.push({ offset: rowStart + byteIndex, rowIndex });
    }
  }

  const addStreamMatches = (stream, offsets, needle) => {
    if (!needle) return;
    for (let position = 0; position <= stream.length - needle.length; position++) {
      let found = true;
      for (let index = 0; index < needle.length; index++) {
        if (stream[position + index] !== needle[index]) {
          found = false;
          break;
        }
      }
      if (!found) continue;
      const first = offsets[position];
      const last = offsets[position + needle.length - 1];
      if (!first || !last) continue;
      const affectedRows = [];
      for (let rowIndex = first.rowIndex; rowIndex <= last.rowIndex; rowIndex++) affectedRows.push(rows[rowIndex]);
      addMatch(first.offset, affectedRows);
    }
  };

  addStreamMatches(asciiChars, asciiOffsets, Array.from(query));

  const compactHexQuery = query.replace(/[\s,:-]/g, "");
  if (/^[0-9a-f]+$/i.test(compactHexQuery) && compactHexQuery.length > 0 && compactHexQuery.length % 2 === 0) {
    const queryBytes = compactHexQuery.match(/[0-9a-f]{2}/g) || [];
    addStreamMatches(hexBytes, byteOffsets, queryBytes);
  }

  for (const [rowIndex, row] of rows.entries()) {
    if (row.dataset.searchOffset.includes(query)) {
      addMatch(Number(row.dataset.start), [row]);
    }
  }

  return matches.sort((a, b) => a.offset - b.offset);
}

function focusStringsSearchMatch(container, index) {
  const matches = container._searchMatches || [];
  if (!matches.length) return;
  const match = matches[index];
  container._searchIndex = index;
  const workspace = container.closest(".strings-workspace");
  workspace?.querySelectorAll(".is-search-current, .is-search-located").forEach((item) => {
    item.classList.remove("is-search-current", "is-search-located");
  });
  if (match.item) match.item.classList.add("is-search-current");

  let byteRow = null;
  if (!match.item && Number.isFinite(match.offset) && match.offset < Number.MAX_SAFE_INTEGER) {
    const rowStart = Math.floor(match.offset / 16) * 16;
    byteRow = workspace?.querySelector(`.hex-row[data-start="${rowStart}"]`);
    if (!byteRow && workspace?.dataset.submissionHash) {
      loadHexWindow(workspace, match.offset, () => container._searchMatches?.[container._searchIndex] === match).then((loaded) => {
        if (!loaded || container._searchMatches?.[container._searchIndex] !== match) return;
        const targetRow = workspace.querySelector(`.hex-row[data-start="${rowStart}"]`);
        if (targetRow) {
          targetRow.classList.add("is-search-current");
          targetRow.scrollIntoView({ block: "nearest" });
        }
      }).catch((error) => console.error("Failed to load the matching hex window:", error));
    }
  }
  if (byteRow) byteRow.classList.add("is-search-current");
  const target = match.item || byteRow;
  target?.scrollIntoView({ block: "nearest" });

  if (match.item) {
    const stringByteRow = workspace?.querySelector(`.hex-row[data-start="${Math.floor(match.offset / 16) * 16}"]`);
    if (stringByteRow) {
      stringByteRow.classList.add("is-search-located");
      stringByteRow.scrollIntoView({ block: "nearest" });
    }
  }

  const count = container.querySelector(".strings-search-count");
  if (count) count.textContent = `${index + 1} / ${matches.length}${container._matchesTruncated ? "+" : ""}`;
}

function updateStringsSearch(input) {
  const hexSearch = input.classList.contains("hex-search-input");
  const container = input.closest(hexSearch ? ".hex-pane" : ".extracted-strings-pane");
  if (!container) return;
  container.closest(".strings-workspace")?.querySelectorAll(".is-search-current, .is-search-located").forEach((item) => {
    item.classList.remove("is-search-current", "is-search-located");
  });

  const query = input.value.trim().toLowerCase();
  const items = hexSearch
    ? Array.from(container.querySelectorAll(".hex-row:not(.hex-grid-heading)"))
    : Array.from(container.querySelectorAll(".strings-item"));
  const matches = getStringsSearchMatches(container, query, hexSearch);
  container._searchMatches = matches;
  container._searchIndex = -1;
  container._matchesTruncated = false;
  const requestId = (container._searchRequestId || 0) + 1;
  container._searchRequestId = requestId;

  const empty = container.querySelector(".search-empty");
  if (empty) empty.hidden = !query || matches.length > 0;
  const count = container.querySelector(".strings-search-count");
  if (count) count.textContent = query ? `0 / ${matches.length}` : `${items.length} / ${items.length}`;
  container.querySelectorAll(".strings-search-nav").forEach((button) => {
    button.disabled = matches.length === 0;
  });
  if (matches.length) focusStringsSearchMatch(container, 0);

  const workspace = container.closest(".strings-workspace");
  const submissionHash = workspace?.dataset.submissionHash;
  const compactHexQuery = query.replace(/[\s,:-]/g, "");
  if (hexSearch && query && submissionHash && /^[0-9a-f]+$/i.test(compactHexQuery) && compactHexQuery.length % 2 === 0) {
    window.clearTimeout(container._fullSearchTimer);
    container._fullSearchTimer = window.setTimeout(async () => {
      try {
        const params = new URLSearchParams({ q: query });
        const response = await fetch(`/hex-search/${encodeURIComponent(submissionHash)}?${params}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const result = await response.json();
        if (container._searchRequestId !== requestId || input.value.trim().toLowerCase() !== query) return;
        const knownOffsets = new Set(container._searchMatches.map((match) => match.offset));
        for (const offset of result.matches || []) {
          const numericOffset = Number(offset);
          if (!knownOffsets.has(numericOffset)) {
            container._searchMatches.push({ offset: numericOffset, rows: [], item: null });
            knownOffsets.add(numericOffset);
          }
        }
        container._searchMatches.sort((a, b) => a.offset - b.offset);
        container._matchesTruncated = Boolean(result.truncated);
        const fullCount = container._searchMatches.length;
        if (count) count.textContent = `0 / ${fullCount}${result.truncated ? "+" : ""}`;
        container.querySelectorAll(".strings-search-nav").forEach((button) => {
          button.disabled = fullCount === 0;
        });
        if (empty) empty.hidden = fullCount > 0;
        if (fullCount) focusStringsSearchMatch(container, 0);
      } catch (error) {
        console.error("Failed to search the complete file:", error);
      }
    }, 180);
  }
}

function moveStringsSearch(container, direction) {
  const matches = container?._searchMatches || [];
  if (!matches.length) return;
  const current = Number.isInteger(container._searchIndex) ? container._searchIndex : 0;
  const next = (current + direction + matches.length) % matches.length;
  focusStringsSearchMatch(container, next);
}

document.addEventListener("input", (event) => {
  const input = event.target;
  if (input instanceof HTMLInputElement && input.matches(".strings-search-input")) updateStringsSearch(input);
});

document.addEventListener("click", (event) => {
  const button = event.target.closest(".strings-search-nav");
  if (!button || button.disabled) return;
  const container = button.closest(".hex-pane, .extracted-strings-pane");
  moveStringsSearch(container, button.dataset.direction === "previous" ? -1 : 1);
});

document.addEventListener("keydown", (event) => {
  const input = event.target;
  if (!(input instanceof HTMLInputElement) || !input.matches(".strings-search-input") || event.key !== "Enter") return;
  event.preventDefault();
  const container = input.closest(input.classList.contains("hex-search-input") ? ".hex-pane" : ".extracted-strings-pane");
  moveStringsSearch(container, event.shiftKey ? -1 : 1);
});

function renderFileAnomalies(data) {
  const signatures = Array.isArray(data.signatures) ? data.signatures : [];
  const anomalies = Array.isArray(data.anomalies) ? data.anomalies : [];
  const terminator = data.terminator || {};
  const signatureRows = signatures.map((item) => `<tr>
    <td>${escapeHtml(item.offset_hex || "")}</td>
    <td>${escapeHtml(item.name || "")}</td>
    <td><code>${escapeHtml(item.signature || "")}</code></td>
    <td><span class="signature-location ${item.location === "header" ? "is-header" : "is-embedded"}">${item.location === "header" ? "文件头" : "嵌入数据"}</span></td>
  </tr>`).join("");
  const terminatorStatus = terminator.status === "found"
    ? "已找到"
    : terminator.status === "missing"
      ? "缺失"
      : "不适用";
  const terminatorPosition = terminator.offset_hex
    ? `<span>${escapeHtml(terminator.offset_hex)} → ${escapeHtml(terminator.end_hex || "")}</span>`
    : "";
  const anomalyCards = anomalies.map((item) => `<article class="file-anomaly-card severity-${escapeHtml(item.severity || "warning")}">
    <div class="file-anomaly-title">${escapeHtml(t(item.title || ""))}</div>
    <div class="file-anomaly-range"><span>起始偏移 ${escapeHtml(item.start_hex || "")}</span><span>结束偏移 ${escapeHtml(item.end_hex || "")}</span></div>
    <p>${escapeHtml(t(item.detail || ""))}</p>
  </article>`).join("");

  return `<div class="file-inspection-summary">
      <strong>${escapeHtml(data.summary || "")}</strong>
      <span>文件大小：${escapeHtml(formatBytes(Number(data.size) || 0))}</span>
    </div>
    <section class="file-inspection-section">
      <h3>常见魔数匹配</h3>
      ${signatureRows
        ? `<div class="table-container"><table class="signature-table"><thead><tr><th>偏移</th><th>匹配格式</th><th>特征字节</th><th>位置</th></tr></thead><tbody>${signatureRows}</tbody></table></div>`
        : `<div class="strings-empty">未检测到常见文件魔数。</div>`}
    </section>
    <section class="file-inspection-section">
      <h3>结束标记</h3>
      <div class="terminator-row"><span><code>${escapeHtml(terminator.name || "—")}</code></span><span class="terminator-status status-${escapeHtml(terminator.status || "not_applicable")}">${terminatorStatus}</span>${terminatorPosition}</div>
    </section>
    <section class="file-inspection-section">
      <h3>异常信息 <span class="anomaly-count">${anomalies.length}</span></h3>
      ${anomalyCards || `<div class="strings-empty">未发现结构异常。</div>`}
      <p class="file-range-help">字节偏移从 0 开始，结束偏移不包含在范围内。</p>
    </section>`;
}

// Clicking an extracted string focuses its row after the full byte view loads.
document.addEventListener("click", async (event) => {
  const stringItem = event.target.closest(".strings-item");
  if (!stringItem) return;
  const offset = Number(stringItem.dataset.offset);
  const pane = stringItem.closest(".strings-workspace");
  if (!pane || !Number.isFinite(offset)) return;
  pane.querySelectorAll(".hex-row.is-selected").forEach((row) => row.classList.remove("is-selected"));
  let byteRow = pane.querySelector(`.hex-row[data-start="${Math.floor(offset / 16) * 16}"]`);
  if (!byteRow && pane.dataset.submissionHash) {
    await loadHexWindow(pane, offset);
    byteRow = pane.querySelector(`.hex-row[data-start="${Math.floor(offset / 16) * 16}"]`);
  }
  if (byteRow) {
    byteRow.classList.add("is-selected");
    byteRow.scrollIntoView({ block: "nearest" });
    pane.querySelector(".strings-selection-note")?.remove();
  } else if (!pane.dataset.fullPreviewLoaded) {
    let notice = pane.querySelector(".strings-selection-note");
    if (!notice) {
      notice = document.createElement("div");
      notice.className = "strings-selection-note";
      pane.querySelector(".hex-pane").appendChild(notice);
    }
    notice.textContent = t("Unable to load the complete hex view.");
  }
});

function renderDecomposerFrameImages(images) {
  const preferredOrder = ["Superimposed", "Red", "Green", "Blue", "Alpha", "Grayscale"];
  const channels = [
    ...preferredOrder.filter((channel) => Array.isArray(images?.[channel])),
    ...Object.keys(images || {}).filter((channel) => !preferredOrder.includes(channel)),
  ];
  return channels.map((channel) => {
    const heading = channel === "Superimposed" ? "" : `<h3>${t(channel)}</h3>`;
    const planes = (images[channel] || []).map((src, bit) =>
      `<div class="results_img"><img src="${escapeHtml(src)}" alt="Decomposer ${escapeHtml(channel)} bit ${bit}" loading="lazy" decoding="async"></div>`
    ).join("");
    return `${heading}${planes}`;
  }).join("");
}

async function loadGifFrameSelector(analyzer, submissionHash) {
  const picker = analyzer.querySelector(".gif-frame-picker");
  if (!picker || picker.dataset.loading === "true" || picker.dataset.loaded === "true") return;
  picker.dataset.loading = "true";
  try {
    const response = await fetch(`/gif-frames/${encodeURIComponent(submissionHash)}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const { frame_count: frameCount } = await response.json();
    if (!Number.isInteger(frameCount) || frameCount < 2) {
      picker.dataset.loaded = "true";
      return;
    }

    picker.hidden = false;
    picker.dataset.frameCount = String(frameCount);
    const frames = picker.querySelector(".gif-frame-list");
    const fragment = document.createDocumentFragment();
    for (let index = 0; index < frameCount; index++) {
      const option = document.createElement("button");
      option.type = "button";
      option.className = `gif-frame-option${index === 0 ? " is-active" : ""}`;
      option.dataset.frameIndex = String(index);
      option.setAttribute("aria-pressed", index === 0 ? "true" : "false");
      option.setAttribute("aria-label", `选择第 ${index + 1} 帧`);
      const preview = document.createElement("img");
      preview.src = `/gif-frame-preview/${encodeURIComponent(submissionHash)}/${index}`;
      preview.alt = "";
      preview.loading = "lazy";
      preview.decoding = "async";
      const label = document.createElement("span");
      label.textContent = String(index + 1);
      option.append(preview, label);
      fragment.appendChild(option);
    }
    frames.replaceChildren(fragment);
    picker.querySelector(".gif-frame-position").textContent = `第 1 / ${frameCount} 帧`;
    picker.dataset.loaded = "true";
  } catch (error) {
    console.error("Failed to load GIF frame selector:", error);
  } finally {
    delete picker.dataset.loading;
  }
}

document.addEventListener("click", async (event) => {
  const option = event.target.closest(".gif-frame-option");
  if (!option || option.disabled) return;
  const picker = option.closest(".gif-frame-picker");
  const analyzer = option.closest(".a-decomposer");
  const selectedIndex = Number(option.dataset.frameIndex);
  if (!picker || !analyzer || !Number.isInteger(selectedIndex)) return;
  if (option.classList.contains("is-active")) return;

  const submissionHash = analyzer.dataset.submissionHash;
  const frameCount = Number(picker.dataset.frameCount);
  const position = picker.querySelector(".gif-frame-position");
  const results = analyzer.querySelector(".decomposer-frame-results");
  picker.setAttribute("aria-busy", "true");
  picker.querySelectorAll(".gif-frame-option").forEach((button) => { button.disabled = true; });
  position.textContent = `正在加载第 ${selectedIndex + 1} 帧…`;
  try {
    const response = await fetch(
      `/decomposer-frame/${encodeURIComponent(submissionHash)}/${selectedIndex}`,
      { method: "POST" }
    );
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
    results.innerHTML = renderDecomposerFrameImages(data.images);
    picker.querySelectorAll(".gif-frame-option").forEach((button) => {
      const active = Number(button.dataset.frameIndex) === selectedIndex;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    });
    position.textContent = `第 ${selectedIndex + 1} / ${frameCount} 帧`;
  } catch (error) {
    console.error("Failed to decompose selected GIF frame:", error);
    position.textContent = `第 ${selectedIndex + 1} 帧加载失败：${error.message}`;
  } finally {
    picker.removeAttribute("aria-busy");
    picker.querySelectorAll(".gif-frame-option").forEach((button) => { button.disabled = false; });
  }
});

function parseResult(result, legacyStringsPreview = null, submissionHash = "") {
  const resultDiv = document.getElementById("result-analyzers");
  resultDiv.innerHTML = "";
  const twoColumnTools = new Set([
    "file_anomalies",
    "exiftool",
    "binwalk",
    "foremost",
    "pngcheck",
    "pcrt",
    "identify",
    "openstego",
    "zsteg",
  ]);
  let twoColumnGrid = null;

  for (const tool of TOOL_ORDER) {
    if (!Object.keys(result).includes(tool)) {
      // Skip if the tool is not in the result
      continue;
    }

    const analyzer = document.createElement("div");
    analyzer.className = `analyzer a-${escapeHtml(tool)}`;
    analyzer.id = `analyzer-${tool}`;
    if (tool === "decomposer" && submissionHash) {
      analyzer.dataset.submissionHash = submissionHash;
    }
    if (twoColumnTools.has(tool)) {
      if (!twoColumnGrid) {
        twoColumnGrid = document.createElement("div");
        twoColumnGrid.className = "analyzer-grid-two-col";
        resultDiv.appendChild(twoColumnGrid);
      }
      twoColumnGrid.appendChild(analyzer);
    } else {
      resultDiv.appendChild(analyzer);
    }

    const ok = result[tool]["status"] === "ok";
    const badge = ok
      ? `<span class="analyzer-badge badge-ok"><i class="fa fa-check"></i> ${t("Success")}</span>`
      : `<span class="analyzer-badge badge-empty"><i class="fa fa-minus"></i> ${t("No result")}</span>`;
    let analyzerHtml = `<div class="analyzer-header"><h2>${analyzerTitle(tool)}</h2>${badge}</div>`;
    if (tool === "decomposer" && submissionHash) {
      analyzerHtml += `<section class="gif-frame-picker" hidden aria-label="GIF 帧选择"><div class="gif-frame-picker-heading"><strong>选择帧</strong><span class="gif-frame-position" aria-live="polite"></span></div><div class="gif-frame-list" role="list"></div></section>`;
    }

    // Parse text output
    if (tool === "base64_images" && result[tool]["output"] && typeof result[tool]["output"] === "object") {
      const output = result[tool]["output"];
      analyzerHtml += `<div class="table-container"><table><tr><td>${t("Images found")}</td><td>${escapeHtml(output.images_found)}</td></tr><tr><td>${t("Detected formats")}</td><td>${escapeHtml(output.formats)}</td></tr></table></div>`;
      const details = result[tool]["image_details"] || [];
      if (details.length) {
        analyzerHtml += `<div class="embedded-image-results">`;
        for (const image of details) {
          analyzerHtml += `<figure class="embedded-image-card"><a href="${escapeHtml(image.download)}" target="_blank" rel="noopener"><img src="${escapeHtml(image.preview)}" alt="${escapeHtml(image.format)} embedded Base64 image" loading="lazy" decoding="async"></a><figcaption><strong>${escapeHtml(image.format)} · ${escapeHtml(image.width)}×${escapeHtml(image.height)}</strong><span>${t("Base64 offset")} 0x${Number(image.base64_offset).toString(16).toUpperCase()} · ${t("Decoded image offset")} 0x${Number(image.decoded_image_offset).toString(16).toUpperCase()}</span><a href="${escapeHtml(image.download)}" download>${t("Download extracted image")}</a></figcaption></figure>`;
        }
        analyzerHtml += `</div>`;
      }
    } else if (tool === "strings" && Array.isArray(result[tool]["output"])) {
      analyzerHtml += renderLegacyStringsOutput(result[tool]["output"], legacyStringsPreview, submissionHash);
      // Keep large files windowed; fetching the entire file here would create
      // tens of thousands of DOM rows and freeze the page.
    } else if (tool === "strings" && result[tool]["output"] && typeof result[tool]["output"] === "object") {
      analyzerHtml += renderStringsOutput(result[tool]["output"], submissionHash);
      // Keep large files windowed; fetching the entire file here would create
      // tens of thousands of DOM rows and freeze the page.
    } else if (tool === "file_anomalies" && result[tool]["output"] && typeof result[tool]["output"] === "object") {
      analyzerHtml += renderFileAnomalies(result[tool]["output"]);
    } else if (typeof result[tool]["output"] === "string") {
      const output = escapeHtml(result[tool]["output"]);
      analyzerHtml += `<div class="alert alert-success" role="alert">${output}</div>`;
    } else if (Array.isArray(result[tool]["output"])) {
      if (result[tool]["output"].length > 0) {
        var code_content = `<div class="code-container position-relative mb-2">`;
        code_content += `<pre class="mb-0"><code>`;
        code_content += result[tool]["output"].map(line => escapeHtml(line)).join('\n').trim();
        code_content += `</code></pre>`;
        code_content += `<i class="fas fa-copy copy-icon"></i>`;
        code_content += `</div>`;
        analyzerHtml += code_content;
      }
    } else if (typeof result[tool]["output"] === "object") {
      var table_content = `<div class="table-container">`;
      table_content += `<table>`;
      for (const key in result[tool]["output"]) {
        const fieldLabel = tool === "exiftool" ? t(key) : key;
        table_content += `<tr><td>${escapeHtml(fieldLabel)}</td>`;
        table_content += `<td>${escapeHtml(
          result[tool]["output"][key]
        )}</td></tr>`;
      }
      table_content += `</table>`;
      analyzerHtml += table_content;
    }

    // Parse images, downloads, ...
    if (result[tool]["status"] === "ok") {
      if ("images" in result[tool] && tool !== "base64_images") {
        // Channel labels come from the analyzer's own dict keys. Only the
        // decomposer/color_remapping RGB(A) sets get the canonical
        // Superimposed,Red,Green,Blue,(Alpha) ordering; every other analyzer
        // (e.g. the spectrogram's {Spectrogram, Waveform}) iterates its keys
        // as-is — which also fixes a 2-key dict previously rendering nothing.
        const imageKeys = Object.keys(result[tool]["images"]);
        const RGBA = ["Superimposed", "Red", "Green", "Blue", "Alpha"];
        const RGB = ["Superimposed", "Red", "Green", "Blue"];
        let channels = imageKeys;
        if (imageKeys.length === RGBA.length && RGBA.every((c) => imageKeys.includes(c))) {
          channels = RGBA;
        } else if (imageKeys.length === RGB.length && RGB.every((c) => imageKeys.includes(c))) {
          channels = RGB;
        }

        if (tool === "decomposer") {
          analyzerHtml += `<div class="decomposer-frame-results">`;
        }

        let title_h3 = "";
        for (const channel of channels) {
          const images = result[tool]["images"][channel];
          if (images) {
            title_h3 = capitalize(escapeHtml(channel));
            if (title_h3 != "Color Remapping"){
              analyzerHtml += `<h3>${t(title_h3)}</h3>`;
            }
            for (const image of images) {
              analyzerHtml += `<div class='results_img'><img src='${escapeHtml(
                image
              )}' alt='${escapeHtml(tool + " " + channel)}' loading='lazy' decoding='async'/></div>`;
            }
          }
        }
        if (tool === "decomposer") {
          analyzerHtml += `</div>`;
        }
      }

      if ("image" in result[tool]) {
        // Parse image output
        analyzerHtml += `<div class='results_img'><img src='${escapeHtml(
          result[tool]["image"]
        )}' alt='${escapeHtml(tool)}' loading='lazy' decoding='async'/></div>`;
      }

      if ("png_images" in result[tool]) {
        for (const image of result[tool]["png_images"]) {
          analyzerHtml += `<div class='results_img'><img src='${escapeHtml(image)}' alt='${escapeHtml(tool)}' loading='lazy' decoding='async'/></div>`;
        }
      }

      if ("download" in result[tool]) {
        // Parse download link
        analyzerHtml += `<br/><a href="${escapeHtml(
          result[tool]["download"]
        )}" target="_blank" class="btn btn-primary mt-2"><i class="fa fa-download"></i> ${t("Download file")}</a>`;
      }
    }

    // Render error and note inside the analyzer's own section (previously
    // these were appended as detached alerts, disconnected from the heading).
    if (result[tool]["error"] && (/[^\s]/.test(result[tool]["error"]))) {
      analyzerHtml +=
        `<div class="alert alert-danger mb-0" role="alert">` +
        `<pre class="mb-0">${escapeHtml(result[tool]["error"].trim())}</pre></div>`;
    }

    if (result[tool]["note"] && (/[^\s]/.test(result[tool]["note"]))) {
      analyzerHtml +=
        `<div class="alert alert-info mb-0 mt-2" role="alert">` +
        `${escapeHtml(result[tool]["note"].trim())}</div>`;
    }

    // Assemble once so a result with dozens of images does not repeatedly
    // parse the growing analyzer subtree or restart image requests.
    analyzer.innerHTML = analyzerHtml;
    if (tool === "decomposer" && submissionHash) {
      loadGifFrameSelector(analyzer, submissionHash);
    }
    if (tool === "strings" && result[tool]["output"] && typeof result[tool]["output"] === "object") {
      const list = analyzer.querySelector(".strings-list");
      if (list) {
        const output = result[tool]["output"];
        list._allStrings = Array.isArray(output)
          ? output.map((text) => ({ offset: "", text: String(text ?? "") }))
          : Array.isArray(output.strings)
            ? output.strings
            : [];
      }
    }
  }
}

async function renderResultData(resultData, submissionHash) {
  const results = resultData?.results;
  const legacyStrings = results?.strings;
  let preview = null;
  if (legacyStrings?.status === "ok" && Array.isArray(legacyStrings.output)) {
    try {
      preview = await loadLegacyHexPreview(submissionHash);
    } catch (error) {
      console.error("Failed to load legacy Strings hex preview:", error);
    }
  }
  parseResult(results, preview, submissionHash);
}

// Poll status of a submission. Polls are sequential (the next one is only
// scheduled after the current one finishes, so they can never stack), back
// off gently, and give up after a hard cap instead of hammering forever.
const POLL_START_INTERVAL_MS = 1000;
const POLL_MAX_INTERVAL_MS = 10000;
const POLL_MAX_TOTAL_MS = 15 * 60 * 1000; // longer than any RQ job timeout

function scheduleNextPoll(submission_hash, startedAt, interval, submittedKeyword = "") {
  if (Date.now() - startedAt > POLL_MAX_TOTAL_MS) {
    showDanger(t("❌ The analysis is taking too long. Please reload the page to check again."), true);
    return;
  }
  const next = Math.min(interval * 1.2, POLL_MAX_INTERVAL_MS);
  setTimeout(() => pollStatus(submission_hash, startedAt, next, submittedKeyword), interval);
}

const resultEtags = new Map();

async function fetchResultSnapshot(submissionHash) {
  const headers = {};
  const etag = resultEtags.get(submissionHash);
  if (etag) headers["If-None-Match"] = etag;
  const response = await fetch(`/result/${submissionHash}`, { headers });
  if (response.status === 304) return { unchanged: true };
  const nextEtag = response.headers.get("ETag");
  if (nextEtag) resultEtags.set(submissionHash, nextEtag);
  return response.json();
}

async function renderKeywordMatches(submissionHash, submittedKeyword = "") {
  const keyword =
    submittedKeyword ||
    sessionStorage.getItem(`aperisolveKeyword:${submissionHash}`) ||
    "";
  if (!keyword) return;
  try {
    const params = new URLSearchParams({ q: keyword });
    const response = await fetch(`/keyword-search/${encodeURIComponent(submissionHash)}?${params}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    const infos = document.getElementById("result-infos");
    if (!infos) return;
    infos.querySelector(".keyword-results")?.remove();
    const section = document.createElement("section");
    section.className = "keyword-results card p-3 mb-3";
    const title = document.createElement("h2");
    title.className = "h5 mb-2";
    title.textContent = `${t("Keyword matches")}: ${keyword}`;
    section.appendChild(title);
    if (!data.matches?.length) {
      const empty = document.createElement("p");
      empty.className = "mb-0 text-light-emphasis";
      empty.textContent = t("No matches found in the uploaded file or analysis results.");
      section.appendChild(empty);
    } else {
      const list = document.createElement("ul");
      list.className = "mb-0";
      for (const match of data.matches) {
        const item = document.createElement("li");
        const link = document.createElement("a");
        const targetTool = match.tool === "original" ? "strings" : match.tool;
        link.href = `#analyzer-${encodeURIComponent(targetTool)}`;
        const matchLabel = match.tool === "original"
          ? t("Original file")
          : capitalize(String(match.tool).replace(/_/g, " "));
        const encodings = match.encodings.map((encoding) => t(encoding)).join(", ");
        link.textContent = `${matchLabel} · ${encodings}`;
        if (match.tool === "original") {
          const firstOffset = Object.values(match.offsets || {}).flat()[0];
          if (Number.isFinite(firstOffset)) link.dataset.keywordOffset = String(firstOffset);
        }
        item.appendChild(link);
        list.appendChild(item);
      }
      section.appendChild(list);
    }
    infos.prepend(section);
  } catch (error) {
    console.error("Failed to search keyword matches:", error);
  }
}

document.addEventListener("click", async (event) => {
  const link = event.target.closest("a[data-keyword-offset]");
  if (!link) return;
  const offset = Number(link.dataset.keywordOffset);
  const workspace = document.querySelector(".strings-workspace");
  if (!workspace || !Number.isFinite(offset)) return;
  event.preventDefault();
  document.getElementById("analyzer-strings")?.scrollIntoView({
    behavior: "smooth",
    block: "start",
  });
  try {
    await loadHexWindow(workspace, offset);
    const rowStart = Math.floor(offset / 16) * 16;
    const row = workspace.querySelector(`.hex-row[data-start="${rowStart}"]`);
    row?.classList.add("is-search-current");
    row?.scrollIntoView({ behavior: "smooth", block: "center" });
  } catch (error) {
    console.error("Failed to locate keyword in the hex view:", error);
  }
});

async function pollStatus(submission_hash, startedAt, interval, submittedKeyword = "") {
  if (!window.location.pathname.endsWith(`/${submission_hash}`)) {
    window.history.pushState({}, "", `/${submission_hash}`);
  }
  startedAt = startedAt || Date.now();
  interval = interval || POLL_START_INTERVAL_MS;
  renderAnalyzing();

  let statusData;
  try {
    const statusResp = await fetch(`/status/${submission_hash}`);
    statusData = await statusResp.json();
  } catch (error) {
    // Network blip: keep the spinner and retry instead of dying silently.
    console.dir(error);
    scheduleNextPoll(submission_hash, startedAt, interval, submittedKeyword);
    return;
  }

  if (statusData.status === "completed") {
    let resultData;
    try {
      resultData = await fetchResultSnapshot(submission_hash);
    } catch (error) {
      console.dir(error);
      scheduleNextPoll(submission_hash, startedAt, interval, submittedKeyword);
      return;
    }
    await fetchImageInfo(submission_hash);
    await renderKeywordMatches(submission_hash, submittedKeyword);
    if (resultData.unchanged) return;
    if ("error" in resultData) {
      showWarning(`❌ ${resultData.error}`, true);
    } else if ("results" in resultData) {
      await renderResultData(resultData, submission_hash);
    }
  } else if (statusData.status === "error") {
    showDanger(t("❌ Error during the analysis."), true);
  } else {
    // Render partial results while the analysis is still running.
    try {
      const resultData = await fetchResultSnapshot(submission_hash);
      if (resultData.unchanged) {
        scheduleNextPoll(submission_hash, startedAt, interval, submittedKeyword);
        return;
      }
      if ("results" in resultData) {
        await fetchImageInfo(submission_hash);
        await renderResultData(resultData, submission_hash);
      } else {
        renderAnalyzing();
      }
    } catch (error) {
      renderAnalyzing();
      console.dir(error);
    }
    scheduleNextPoll(submission_hash, startedAt, interval, submittedKeyword);
  }
}

/**
 * Drag and drop functionality
 */

const dropZone = document.getElementById("drop-zone");
const fileInput = document.getElementById("image");
const browseBtn = document.getElementById("browse-btn");
const dragMsg = document.getElementById("drag-msg");

function showFilename(filename) {
  dragMsg.textContent = "📄 " + (fileInput.files.length
    ? Array.from(fileInput.files, (file) => file.name).join(" · ")
    : filename);
}

if (browseBtn) {
  // Clicking the button triggers file input
  browseBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    fileInput.click();
  });
  dropZone.addEventListener("click", () => {
    fileInput.click();
  });
  dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropZone.style.boxShadow = "0 0 20px #9fef00";
  });
  dropZone.addEventListener("dragleave", () => {
    dropZone.style.boxShadow = "";
  });

  // Drag events
  ["dragenter", "dragover"].forEach((eventName) => {
    dropZone.addEventListener(eventName, (e) => {
      e.preventDefault();
      dropZone.classList.add("dragover");
    });
  });

  ["dragleave", "drop"].forEach((eventName) => {
    dropZone.addEventListener(eventName, (e) => {
      e.preventDefault();
      dropZone.classList.remove("dragover");
    });
  });

  // Drop file
  dropZone.addEventListener("drop", (e) => {
    const files = e.dataTransfer.files;
    if (window.OmniUI?.busy()) return;
    if (!window.OmniUI?.enabled() && files.length > 1) {
      showDanger("普通模式仅支持单文件；请勾选全能模式后上传多个文件。", true);
      return;
    }
    if (files.length > 0) {
      fileInput.files = files; // Attach files to the hidden input
      showFilename(fileInput.files[0].name);
    }
  });

  fileInput.addEventListener("change", () => {
    if (fileInput.files.length > 0) {
      showFilename(fileInput.files[0].name);
    }
  });

  // File upload Form submission

  document
    .getElementById("upload-form")
    .addEventListener("submit", function (e) {
      e.preventDefault();

      if (window.OmniUI?.enabled()) {
        window.OmniUI.submit();
        return;
      }

      const fileInput = document.getElementById("image");
      const passwordInput = document.getElementById("password");
      const deepCheckbox = document.getElementById("deep");
      const keywordInput = document.getElementById("keyword");
      const progressContainer = document.getElementById("progress-container");
      const progressBar = document.getElementById("progress-bar");

      if (!fileInput.files.length) {
        showDanger(t("Please select a file."), true);
        return;
      }

      const formData = new FormData();
      formData.append("image", fileInput.files[0]);
      formData.append("password", passwordInput.value);
      formData.append("deep", deepCheckbox.checked);
      const keyword = keywordInput?.value.trim() || "";
      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/upload", true);

      xhr.upload.addEventListener("loadstart", () => {
        progressContainer.classList.remove("d-none");
        progressBar.style.width = "0%";
        progressBar.textContent = "0%";
      });

      xhr.upload.addEventListener("progress", (e) => {
        if (e.lengthComputable) {
          const percent = Math.round((e.loaded / e.total) * 100);
          progressBar.style.width = percent + "%";
          progressBar.textContent = percent + "%";
        }
      });

      xhr.onload = () => {
        if (xhr.status === 200) {
          try {
            const response = JSON.parse(xhr.responseText);
            if (response.submission_hash) {
              if (keyword) {
                sessionStorage.setItem(`aperisolveKeyword:${response.submission_hash}`, keyword);
              } else {
                sessionStorage.removeItem(`aperisolveKeyword:${response.submission_hash}`);
              }
              pollStatus(response.submission_hash, undefined, undefined, keyword);
            } else {
              showDanger(
                t("❌ Invalid server response: missing submission_hash."),
                true
              );
            }
          } catch (e) {
            showDanger(t("❌ Invalid server response."), true);
          }
        } else if (xhr.status == 413) {
          showDanger(t("❌ File too large. Please upload a smaller file."), true);
        } else {
          showDanger(`${t("❌ HTTP error")} ${xhr.status}`, true);
        }
        progressBar.style.width = "100%";
        progressBar.textContent = t("Upload complete");
        const uploadForm = document.getElementById("upload-form");
        slideUp(uploadForm);
      };

      xhr.onerror = () => {
        showDanger(t("❌ An error occurred during the transfer"), true);
      };

      xhr.send(formData);
    });
}

/**
 * Wiki search
 *
 * Lazy-fetches /wiki/search.json on the first keystroke, then does dependency-free
 * tokenized substring ranking (title > description > heading > body). No-op off
 * the wiki (the input/results elements only exist there).
 */
function initWikiSearch() {
  const input = document.getElementById("wiki-search");
  const box = document.getElementById("wiki-search-results");
  if (!input || !box) return;
  let index = null;

  async function ensureIndex() {
    if (index) return index;
    const resp = await fetch(`${LANG_PREFIX}/wiki/search.json`);
    index = (await resp.json()).pages;
    return index;
  }

  function score(haystack, terms) {
    const hay = (haystack || "").toLowerCase();
    return terms.reduce((s, term) => s + (hay.includes(term) ? 1 : 0), 0);
  }

  function render(hits) {
    if (!hits.length) {
      box.innerHTML = `<div class="wiki-search-empty">${t("No results")}</div>`;
      return;
    }
    box.innerHTML = hits
      .slice(0, 8)
      .map((hit) => {
        const anchor = hit.heading ? `#${hit.heading.id}` : "";
        const label = hit.heading
          ? `${escapeHtml(hit.page.title)} <span class="wiki-search-sep">&rsaquo;</span> ${escapeHtml(hit.heading.title)}`
          : escapeHtml(hit.page.title);
        return `<a class="wiki-search-hit" href="${LANG_PREFIX}${hit.page.path}${anchor}">${label}</a>`;
      })
      .join("");
  }

  async function run() {
    const terms = input.value.toLowerCase().split(/\s+/).filter(Boolean);
    if (!terms.length) {
      box.innerHTML = "";
      return;
    }
    const pages = await ensureIndex();
    const hits = [];
    for (const page of pages) {
      const pageScore =
        score(page.title, terms) * 5 +
        score(page.description, terms) * 2 +
        score(page.text, terms);
      if (pageScore) hits.push({ page, score: pageScore + 3 });
      for (const heading of page.headings) {
        const headingScore = score(heading.title, terms) * 4;
        if (headingScore) hits.push({ page, heading, score: headingScore });
      }
    }
    hits.sort((a, b) => b.score - a.score);
    render(hits);
  }

  let debounce;
  input.addEventListener("input", () => {
    clearTimeout(debounce);
    debounce = setTimeout(run, 120);
  });
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".wiki-search")) box.innerHTML = "";
  });
}
initWikiSearch();

/* Cheatsheet "Tell → Tool" table: instant row filter (opt-in via #tell-tool-filter). */
(function initTellToolFilter() {
  const input = document.getElementById("tell-tool-filter");
  if (!input) return;
  const scope = input.closest(".wiki-article") || document;
  const table = Array.from(scope.querySelectorAll("table")).find(
    (t) => input.compareDocumentPosition(t) & Node.DOCUMENT_POSITION_FOLLOWING
  );
  if (!table) return;
  const rows = Array.from(table.querySelectorAll("tbody tr"));
  input.addEventListener("input", () => {
    const q = input.value.trim().toLowerCase();
    rows.forEach((row) => {
      row.hidden = !!q && row.textContent.toLowerCase().indexOf(q) === -1;
    });
  });
})();

