"use strict";

const state = {
  month: "",
  storeId: "",
  activeProductTab: "best_sellers",
  productData: null,
  runId: null,
  requestController: null,
  filterTimer: null,
  knowledgeAllowedExtensions: [],
  chatController: null,
  chatSessionId: "",
  chatAnswerText: "",
  chatRenderFrame: null,
  chatTurnComplete: false,
  chatSubtasks: new Map(),
};

const elements = {
  monthFilter: document.querySelector("#month-filter"),
  storeFilter: document.querySelector("#store-filter"),
  refreshButton: document.querySelector("#refresh-button"),
  connectionStatus: document.querySelector("#connection-status"),
  globalError: document.querySelector("#global-error"),
  salesDataThrough: document.querySelector("#sales-data-through"),
  scopeCaption: document.querySelector("#scope-caption"),
  financePeriod: document.querySelector("#finance-period"),
  financeMetrics: document.querySelector("#finance-metrics"),
  financeChart: document.querySelector("#finance-chart"),
  inventorySummary: document.querySelector("#inventory-summary"),
  inventoryList: document.querySelector("#inventory-list"),
  ticketCount: document.querySelector("#ticket-count"),
  ticketList: document.querySelector("#ticket-list"),
  productTabs: document.querySelector("#product-tabs"),
  productList: document.querySelector("#product-list"),
  campaignCount: document.querySelector("#campaign-count"),
  campaignList: document.querySelector("#campaign-list"),
  chatForm: document.querySelector("#chat-form"),
  chatHistory: document.querySelector("#chat-history"),
  newChatButton: document.querySelector("#new-chat-button"),
  newChatDialog: document.querySelector("#new-chat-dialog"),
  chatInput: document.querySelector("#chat-input"),
  chatResponse: document.querySelector("#chat-response"),
  chatQuestion: document.querySelector("#chat-question"),
  chatProgress: document.querySelector("#chat-progress"),
  chatSubtasks: document.querySelector("#chat-subtasks"),
  chatThinking: document.querySelector("#chat-thinking"),
  chatThinkingLabel: document.querySelector("#chat-thinking-label"),
  chatAnswer: document.querySelector("#chat-answer"),
  chatSqlApprovals: document.querySelector("#chat-sql-approvals"),
  chatAnswerStatus: document.querySelector("#chat-answer-status"),
  chatCopyButton: document.querySelector("#chat-copy-button"),
  chatSources: document.querySelector("#chat-sources"),
  chatSubmitLabel: document.querySelector("#chat-submit-label"),
  sqlAutoExecute: document.querySelector("#sql-auto-execute"),
  knowledgeDropZone: document.querySelector("#knowledge-drop-zone"),
  knowledgeFileInput: document.querySelector("#knowledge-file-input"),
  knowledgeFileCount: document.querySelector("#knowledge-file-count"),
  knowledgeUploadStatus: document.querySelector("#knowledge-upload-status"),
  knowledgeFileList: document.querySelector("#knowledge-file-list"),
  knowledgeUploadPolicy: document.querySelector("#knowledge-upload-policy"),
  reviewSyncButton: document.querySelector("#review-sync-button"),
  reviewSyncStatus: document.querySelector("#review-sync-status"),
};

const moneyFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

const numberFormatter = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 0,
});

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatMoney(value) {
  return moneyFormatter.format(Number(value) || 0);
}

function formatCompactMoney(value) {
  const number = Number(value) || 0;
  const absolute = Math.abs(number);
  const sign = number < 0 ? "−" : "";
  if (absolute >= 1_000_000) {
    return `${sign}$${(absolute / 1_000_000).toFixed(1)}M`;
  }
  if (absolute >= 1_000) {
    return `${sign}$${(absolute / 1_000).toFixed(0)}K`;
  }
  return `${sign}$${absolute.toFixed(0)}`;
}

function formatMonth(month) {
  if (!month || !/^\d{4}-\d{2}$/.test(month)) return month || "—";
  const [year, monthNumber] = month.split("-");
  return new Intl.DateTimeFormat("en-US", { month: "long", year: "numeric" }).format(
    new Date(Number(year), Number(monthNumber) - 1, 1),
  );
}

function endpoint(path, options = {}) {
  const query = new URLSearchParams();
  if (options.month && state.month) query.set("month", state.month);
  if (options.store && state.storeId) query.set("store_id", state.storeId);
  const suffix = query.toString();
  return suffix ? `${path}?${suffix}` : path;
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch (_error) {
      // Keep the status-based message when the response is not JSON.
    }
    throw new Error(detail);
  }
  return response.json();
}

function setConnectionStatus(mode, text) {
  elements.connectionStatus.classList.toggle("error", mode === "error");
  elements.connectionStatus.classList.toggle("loading", mode === "loading");
  elements.connectionStatus.lastChild.textContent = ` ${text}`;
}

function showGlobalError(message) {
  elements.globalError.textContent = message;
  elements.globalError.hidden = false;
}

function clearGlobalError() {
  elements.globalError.hidden = true;
  elements.globalError.textContent = "";
}

function renderEmpty(container, message) {
  container.className = "empty-state";
  container.textContent = message;
}

function formatFileSize(bytes) {
  const value = Number(bytes) || 0;
  if (value >= 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  if (value >= 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${value} B`;
}

function setUploadStatus(mode, message) {
  elements.knowledgeUploadStatus.hidden = false;
  elements.knowledgeUploadStatus.className = `upload-status ${mode}`;
  elements.knowledgeUploadStatus.textContent = message;
}

function renderKnowledgeFiles(data) {
  const policy = data.upload_policy;
  state.knowledgeAllowedExtensions = policy.allowed_extensions;
  elements.knowledgeFileInput.accept = policy.allowed_extensions.join(",");
  elements.knowledgeUploadPolicy.textContent = `${policy.allowed_extensions
    .map((extension) => extension.slice(1).toUpperCase())
    .join(", ")} · One file · Up to ${formatFileSize(policy.max_file_size_bytes)}`;
  elements.knowledgeFileCount.textContent = `${data.count} files`;
  elements.knowledgeFileList.className = "knowledge-file-list";
  if (!data.files.length) {
    renderEmpty(elements.knowledgeFileList, "No knowledge files have been uploaded yet");
    return;
  }

  elements.knowledgeFileList.innerHTML = data.files
    .map(
      (file) => `
        <article class="knowledge-file-row">
          <span class="file-type-badge">${escapeHtml(
            file.original_filename.split(".").pop().toUpperCase(),
          )}</span>
          <div class="knowledge-file-copy">
            <strong title="${escapeHtml(file.original_filename)}">${escapeHtml(
              file.original_filename,
            )}</strong>
            <span>${escapeHtml(formatFileSize(file.file_size))} · ${escapeHtml(
              new Date(file.created_at).toLocaleString("en-US"),
            )}</span>
          </div>
          <div class="knowledge-file-actions">
            <a href="/api/knowledge/files/${encodeURIComponent(file.file_id)}/download">Download</a>
            <button type="button" data-delete-file-id="${escapeHtml(file.file_id)}">Delete</button>
          </div>
        </article>
      `,
    )
    .join("");
}

async function loadKnowledgeFiles() {
  try {
    const data = await fetchJson("/api/knowledge/files");
    renderKnowledgeFiles(data);
  } catch (error) {
    elements.knowledgeFileCount.textContent = "Unavailable";
    renderEmpty(elements.knowledgeFileList, `Knowledge files could not be loaded: ${error.message}`);
  }
}

async function uploadKnowledgeFile(file) {
  if (!file) return;
  const extension = file.name.includes(".")
    ? `.${file.name.split(".").pop().toLowerCase()}`
    : "";
  if (
    state.knowledgeAllowedExtensions.length &&
    !state.knowledgeAllowedExtensions.includes(extension)
  ) {
    setUploadStatus(
      "error",
      `Allowed file types: ${state.knowledgeAllowedExtensions.join(", ")}`,
    );
    return;
  }

  elements.knowledgeDropZone.classList.add("is-uploading");
  setUploadStatus("loading", `Validating and uploading ${file.name}…`);
  const formData = new FormData();
  formData.append("file", file, file.name);

  try {
    const data = await fetchJson("/api/knowledge/files", {
      method: "POST",
      body: formData,
    });
    setUploadStatus(
      "success",
      `${data.file.original_filename} was stored as ${data.knowledge.chunk_count} knowledge chunks`,
    );
    await loadKnowledgeFiles();
  } catch (error) {
    setUploadStatus("error", `Upload failed: ${error.message}`);
  } finally {
    elements.knowledgeDropZone.classList.remove("is-uploading");
    elements.knowledgeFileInput.value = "";
  }
}

function acceptDroppedFiles(files) {
  if (!files || files.length === 0) return;
  if (files.length > 1) {
    setUploadStatus("error", "Only one file can be uploaded at a time");
    return;
  }
  uploadKnowledgeFile(files[0]);
}

async function deleteKnowledgeFile(fileId) {
  if (!window.confirm("Delete this knowledge file?")) return;
  try {
    await fetchJson(`/api/knowledge/files/${encodeURIComponent(fileId)}`, {
      method: "DELETE",
    });
    setUploadStatus("success", "The file was deleted");
    await loadKnowledgeFiles();
  } catch (error) {
    setUploadStatus("error", `Delete failed: ${error.message}`);
  }
}

async function syncCustomerReviews() {
  elements.reviewSyncButton.disabled = true;
  elements.reviewSyncStatus.hidden = false;
  elements.reviewSyncStatus.className = "upload-status loading";
  elements.reviewSyncStatus.textContent = "Synchronizing customer reviews, support tickets and campaigns…";

  try {
    const data = await fetchJson("/api/knowledge/reviews/sync", { method: "POST" });
    elements.reviewSyncStatus.className = "upload-status success";
    elements.reviewSyncStatus.textContent =
      `Synced ${data.reviews_synced_count} customer reviews, ` +
      `${data.tickets_synced_count} support tickets and ` +
      `${data.campaigns_synced_count} campaigns into the knowledge base`;
  } catch (error) {
    elements.reviewSyncStatus.className = "upload-status error";
    elements.reviewSyncStatus.textContent = `Synchronization failed: ${error.message}`;
  } finally {
    elements.reviewSyncButton.disabled = false;
  }
}

function resizeChatInput() {
  elements.chatInput.style.height = "auto";
  const height = Math.min(elements.chatInput.scrollHeight, 150);
  elements.chatInput.style.height = `${height}px`;
  elements.chatInput.style.overflowY = elements.chatInput.scrollHeight > 150 ? "auto" : "hidden";
}

function resetConversationUi() {
  state.chatAnswerText = "";
  state.chatTurnComplete = false;
  if (state.chatRenderFrame !== null) {
    window.cancelAnimationFrame(state.chatRenderFrame);
    state.chatRenderFrame = null;
  }
  elements.chatHistory.replaceChildren();
  elements.chatResponse.hidden = true;
  elements.chatQuestion.textContent = "";
  elements.chatProgress.replaceChildren();
  state.chatSubtasks.clear();
  elements.chatSubtasks.replaceChildren();
  elements.chatSubtasks.hidden = true;
  elements.chatAnswer.replaceChildren();
  elements.chatSqlApprovals.replaceChildren();
  elements.chatSqlApprovals.hidden = true;
  elements.chatSources.replaceChildren();
  elements.chatSources.hidden = true;
  elements.chatCopyButton.hidden = true;
  setThinking("", false);
}

async function createChatSession({ clearUi = false } = {}) {
  const data = await fetchJson("/api/sessions", { method: "POST" });
  state.chatSessionId = data.session_id;
  if (clearUi) resetConversationUi();
  return state.chatSessionId;
}

async function ensureChatSession() {
  if (!state.chatSessionId) await createChatSession();
  return state.chatSessionId;
}

function archiveCompletedTurn() {
  if (!state.chatTurnComplete || elements.chatResponse.hidden) return;
  const archived = elements.chatResponse.cloneNode(true);
  archived.removeAttribute("id");
  archived.removeAttribute("aria-live");
  archived.hidden = false;
  archived.classList.add("chat-turn--archived");
  archived.querySelector(".chat-trace")?.remove();
  archived.querySelector(".answer-actions")?.remove();
  archived.querySelectorAll("[id]").forEach((node) => node.removeAttribute("id"));
  archived.querySelector("[aria-labelledby]")?.removeAttribute("aria-labelledby");
  elements.chatHistory.append(archived);
}

function prepareChatResponse(question) {
  state.chatAnswerText = "";
  state.chatTurnComplete = false;
  elements.chatResponse.hidden = false;
  elements.chatQuestion.textContent = question;
  elements.chatProgress.replaceChildren();
  state.chatSubtasks.clear();
  elements.chatSubtasks.replaceChildren();
  elements.chatSubtasks.hidden = true;
  elements.chatAnswer.replaceChildren();
  elements.chatAnswer.classList.remove("is-streaming");
  elements.chatSqlApprovals.replaceChildren();
  elements.chatSqlApprovals.hidden = true;
  elements.chatSources.replaceChildren();
  elements.chatSources.hidden = true;
  elements.chatCopyButton.hidden = true;
  elements.chatAnswerStatus.textContent = "Thinking";
  elements.chatAnswerStatus.classList.add("is-streaming");
  setThinking("Connecting to the model…");
}

async function startNewChat() {
  const oldSessionId = state.chatSessionId;
  if (state.chatController) state.chatController.abort();
  state.chatSessionId = "";
  elements.newChatButton.disabled = true;
  try {
    if (oldSessionId) {
      const response = await fetch(`/api/sessions/${encodeURIComponent(oldSessionId)}`, {
        method: "DELETE",
      });
      if (!response.ok && response.status !== 404) {
        throw new Error(`Could not delete the previous session (${response.status})`);
      }
    }
    await createChatSession({ clearUi: true });
    elements.chatInput.focus();
  } catch (error) {
    showGlobalError(`New chat could not be created: ${error.message}`);
  } finally {
    elements.newChatButton.disabled = false;
  }
}

function confirmNewChat() {
  if (elements.newChatButton.disabled || elements.newChatDialog.open) return;
  elements.newChatDialog.returnValue = "";
  elements.newChatDialog.showModal();
}

function renderChatAnswer() {
  state.chatRenderFrame = null;
  if (window.ChatRenderer?.renderMarkdown) {
    elements.chatAnswer.innerHTML = window.ChatRenderer.renderMarkdown(state.chatAnswerText);
    return;
  }
  elements.chatAnswer.innerHTML = `<p>${escapeHtml(state.chatAnswerText).replaceAll("\n", "<br>")}</p>`;
}

function scheduleChatAnswerRender() {
  if (state.chatRenderFrame !== null) return;
  state.chatRenderFrame = window.requestAnimationFrame(renderChatAnswer);
}

function appendChatActivity(kind, label, message) {
  const item = document.createElement("div");
  item.className = `chat-progress-item ${kind}`;
  const dot = document.createElement("i");
  dot.setAttribute("aria-hidden", "true");
  const copy = document.createElement("span");
  const heading = document.createElement("b");
  heading.textContent = label;
  copy.append(heading, document.createTextNode(String(message || "")));
  item.append(dot, copy);
  elements.chatProgress.append(item);
}

const SUBTASK_STATUS_LABELS = {
  pending: "Pending",
  running: "In progress",
  completed: "Completed",
  blocked: "Blocked",
  empty: "Completed · no data",
};

function normalizedSubtaskStatus(value) {
  const status = String(value || "pending");
  return Object.hasOwn(SUBTASK_STATUS_LABELS, status) ? status : "pending";
}

function buildSubtaskRow(task) {
  const status = normalizedSubtaskStatus(task.status);
  const row = document.createElement("div");
  row.className = `subtask-row is-${status}`;
  row.dataset.subtaskId = task.id;

  const copy = document.createElement("span");
  copy.className = "subtask-copy";
  const title = document.createElement("strong");
  title.textContent = task.question || task.id;
  const meta = document.createElement("small");
  meta.textContent = [task.id, task.agent, task.skill].filter(Boolean).join(" · ");
  copy.append(title, meta);

  const stateCopy = document.createElement("span");
  stateCopy.className = "subtask-state";
  const label = document.createElement("small");
  label.className = "subtask-state-label";
  label.textContent = SUBTASK_STATUS_LABELS[status];
  const indicator = document.createElement("span");
  indicator.className = "subtask-check";
  indicator.setAttribute("aria-hidden", "true");
  stateCopy.append(label, indicator);
  row.append(copy, stateCopy);
  return row;
}

function updateSubtaskProgressCount() {
  const finished = [...state.chatSubtasks.values()].filter((task) =>
    ["completed", "blocked", "empty"].includes(normalizedSubtaskStatus(task.status)),
  ).length;
  const count = elements.chatSubtasks.querySelector(".subtask-heading span");
  if (count) count.textContent = `${finished}/${state.chatSubtasks.size} finished`;
}

function renderSubtasks(items) {
  const tasks = Array.isArray(items)
    ? items.filter((item) => item && typeof item === "object" && item.id)
    : [];
  state.chatSubtasks.clear();
  tasks.forEach((item) => {
    const task = { ...item, status: normalizedSubtaskStatus(item.status) };
    state.chatSubtasks.set(String(task.id), task);
  });
  elements.chatSubtasks.replaceChildren();
  elements.chatSubtasks.hidden = state.chatSubtasks.size === 0;
  if (!state.chatSubtasks.size) return;

  const heading = document.createElement("div");
  heading.className = "subtask-heading";
  const title = document.createElement("strong");
  title.textContent = "Subtasks";
  const count = document.createElement("span");
  heading.append(title, count);

  const list = document.createElement("div");
  list.className = "subtask-list";
  state.chatSubtasks.forEach((task) => list.append(buildSubtaskRow(task)));
  elements.chatSubtasks.append(heading, list);
  updateSubtaskProgressCount();
}

function updateSubtaskStatus(data) {
  const taskId = String(data?.subtask_id || "");
  if (!taskId) return;
  const previous = state.chatSubtasks.get(taskId) || {
    id: taskId,
    question: String(data?.question || taskId),
    agent: String(data?.agent || ""),
    skill: String(data?.skill || ""),
  };
  const status = normalizedSubtaskStatus(data?.status);
  const task = { ...previous, status };
  state.chatSubtasks.set(taskId, task);

  const row = [...elements.chatSubtasks.querySelectorAll(".subtask-row")]
    .find((item) => item.dataset.subtaskId === taskId);
  if (!row) {
    renderSubtasks([...state.chatSubtasks.values()]);
    return;
  }
  row.className = `subtask-row is-${status}`;
  const label = row.querySelector(".subtask-state-label");
  if (label) label.textContent = SUBTASK_STATUS_LABELS[status];
  updateSubtaskProgressCount();
}

function setThinking(message, visible = true) {
  elements.chatThinking.hidden = !visible;
  if (message) elements.chatThinkingLabel.textContent = message;
}

function safeSourceUrl(value) {
  try {
    const url = new URL(String(value || ""), window.location.origin);
    if (!['http:', 'https:'].includes(url.protocol)) return null;
    return url.href;
  } catch (_error) {
    return null;
  }
}

function renderChatSources(sources) {
  elements.chatSources.replaceChildren();
  if (!Array.isArray(sources) || sources.length === 0) {
    elements.chatSources.hidden = true;
    return;
  }

  const heading = document.createElement("div");
  heading.className = "sources-heading";
  const title = document.createElement("strong");
  title.textContent = "References";
  const count = document.createElement("span");
  count.textContent = `${sources.length} cited source${sources.length === 1 ? "" : "s"}`;
  heading.append(title, count);

  const list = document.createElement("div");
  list.className = "source-list";
  sources.forEach((source, index) => {
    const href = safeSourceUrl(source.download_url);
    const entry = document.createElement(href ? "a" : "div");
    if (href) entry.href = href;
    entry.className = "source-entry";

    const number = document.createElement("span");
    number.className = "source-index";
    number.textContent = String(index + 1).padStart(2, "0");
    const copy = document.createElement("span");
    copy.className = "source-copy";
    const filename = document.createElement("strong");
    filename.textContent = source.filename || source.citation || "Knowledge source";
    const detail = document.createElement("small");
    const similarity = Number(source.similarity);
    detail.textContent = [
      source.citation,
      Number.isFinite(similarity) ? `${Math.round(similarity * 100)}% match` : "",
    ].filter(Boolean).join(" · ");
    copy.append(filename, detail);
    const open = document.createElement("span");
    open.className = "source-open";
    open.textContent = href ? "↗" : "";
    entry.append(number, copy, open);
    list.append(entry);
  });
  elements.chatSources.append(heading, list);
  elements.chatSources.hidden = false;
}

function renderSqlApproval(data) {
  const approvalId = String(data?.approval_id || "");
  const sql = String(data?.sql || "").trim();
  if (!approvalId || !sql) return;

  const card = document.createElement("article");
  card.className = "sql-approval-card";
  card.dataset.approvalId = approvalId;
  card.dataset.runId = String(data?.run_id || "");

  const heading = document.createElement("div");
  heading.className = "sql-approval-heading";
  const title = document.createElement("strong");
  title.textContent = "SQL query approval required";
  const agent = document.createElement("span");
  agent.textContent = `${String(data?.agent || "specialist").toUpperCase()} AGENT`;
  heading.append(title, agent);

  const warning = document.createElement("p");
  warning.className = "sql-approval-warning";
  warning.textContent = String(
    data?.message ||
      "No dedicated skill matched this request. The Agent-generated query may fail, take a long time, or consume additional tokens.",
  );

  const purpose = document.createElement("p");
  purpose.className = "sql-approval-purpose";
  purpose.textContent = data?.purpose ? `Purpose: ${String(data.purpose)}` : "";
  purpose.hidden = !data?.purpose;

  const sqlLabel = document.createElement("span");
  sqlLabel.className = "sql-approval-label";
  sqlLabel.textContent = "Complete SQL to execute (including the row-limit guard)";
  const pre = document.createElement("pre");
  const code = document.createElement("code");
  code.textContent = sql;
  pre.append(code);

  const parameters = data?.parameters && typeof data.parameters === "object"
    ? data.parameters
    : {};
  const parameterKeys = Object.keys(parameters);
  const parameterBlock = document.createElement("div");
  parameterBlock.className = "sql-approval-parameters";
  parameterBlock.hidden = parameterKeys.length === 0;
  const parameterLabel = document.createElement("span");
  parameterLabel.className = "sql-approval-label";
  parameterLabel.textContent = "Bound parameters";
  const parameterPre = document.createElement("pre");
  const parameterCode = document.createElement("code");
  parameterCode.textContent = JSON.stringify(parameters, null, 2);
  parameterPre.append(parameterCode);
  parameterBlock.append(parameterLabel, parameterPre);

  const decisionStatus = document.createElement("p");
  decisionStatus.className = "sql-approval-decision-status";
  decisionStatus.setAttribute("role", "status");

  const body = document.createElement("div");
  body.className = "sql-approval-body";
  body.append(
    warning,
    purpose,
    sqlLabel,
    pre,
    parameterBlock,
    decisionStatus,
  );

  const actions = document.createElement("div");
  actions.className = "sql-approval-actions";
  const cancel = document.createElement("button");
  cancel.type = "button";
  cancel.className = "sql-approval-cancel";
  cancel.dataset.sqlDecision = "cancel";
  cancel.textContent = "Cancel";
  const execute = document.createElement("button");
  execute.type = "button";
  execute.className = "sql-approval-execute";
  execute.dataset.sqlDecision = "execute";
  execute.textContent = "Execute";
  actions.append(cancel, execute);

  card.append(
    heading,
    body,
    actions,
  );
  elements.chatSqlApprovals.append(card);
  elements.chatSqlApprovals.hidden = false;
  elements.chatAnswerStatus.textContent = "Awaiting approval";
  elements.chatAnswerStatus.classList.remove("is-streaming");
  setThinking("Waiting for your SQL execution decision…");
  appendChatActivity("approval", "SQL approval", "Waiting for approval of the Agent-generated read-only query");
}

async function submitSqlApproval(card, decision) {
  const approvalId = String(card?.dataset?.approvalId || "");
  const runId = String(card?.dataset?.runId || "");
  if (!approvalId || !runId || !["execute", "cancel"].includes(decision)) return;
  const buttons = [...card.querySelectorAll("button[data-sql-decision]")];
  const status = card.querySelector(".sql-approval-decision-status");
  buttons.forEach((button) => { button.disabled = true; });
  if (status) status.textContent = decision === "execute" ? "Submitting approval…" : "Cancelling the query…";
  try {
    await fetchJson(`/api/chat/sql-approvals/${encodeURIComponent(approvalId)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision, run_id: runId }),
    });
    card.classList.add(decision === "execute" ? "is-approved" : "is-cancelled");
    if (status) {
      status.textContent = decision === "execute"
        ? "Approved. The read-only query is now running."
        : "Cancelled. The database query will not be executed.";
    }
    elements.chatAnswerStatus.textContent = decision === "execute" ? "Querying" : "Query cancelled";
    setThinking(decision === "execute" ? "Running the approved SQL…" : "Supervisor is preparing the cancellation response…");
    appendChatActivity(
      decision === "execute" ? "tool-start" : "approval",
      "SQL approval",
      decision === "execute" ? "The user approved execution" : "The user declined execution",
    );
  } catch (error) {
    buttons.forEach((button) => { button.disabled = false; });
    if (status) status.textContent = `Could not submit the decision: ${error.message}`;
  }
}

function handleChatEvent(eventName, data) {
  const message = String(data?.message || "");
  if (eventName === "status") {
    setThinking(message || "Working on your request");
    appendChatActivity("status", "Status", message);
  } else if (eventName === "reasoning") {
    const effort = data?.effort ? ` (${data.effort})` : "";
    setThinking(data?.active === false ? "Reasoning is disabled" : "Reasoning over the request…");
    appendChatActivity("reasoning", `Reasoning${effort}`, message);
  } else if (eventName === "skills") {
    const items = Array.isArray(data?.items) ? data.items : [];
    if (items.length) {
      items.forEach((item) => appendChatActivity("skill", "Skill", String(item)));
    } else {
      appendChatActivity("skill", "Skills", message);
    }
  } else if (eventName === "subtasks") {
    renderSubtasks(data?.items);
  } else if (eventName === "subtask_status") {
    updateSubtaskStatus(data);
    if (message) setThinking(message, data?.status === "running");
  } else if (eventName === "tool_start") {
    appendChatActivity("tool-start", "Tool call", message || String(data?.name || "Tool started"));
  } else if (eventName === "tool_end") {
    appendChatActivity("tool-end", "Tool result", message || String(data?.name || "Tool completed"));
  } else if (eventName === "validation") {
    const agent = String(data?.agent || "Specialist");
    const label = data?.valid === true ? "Evidence validated" : "Evidence rejected";
    appendChatActivity("validation", `${agent} · ${label}`, message);
  } else if (eventName === "sources") {
    renderChatSources(data?.items);
  } else if (eventName === "sql_approval") {
    renderSqlApproval(data);
  } else if (eventName === "sql_auto_execute") {
    const detail = message || "Running validated SQL automatically without an approval prompt.";
    elements.chatAnswerStatus.textContent = "Querying";
    setThinking(detail);
    appendChatActivity("tool-start", "Automatic SQL execution", detail);
  } else if (eventName === "token") {
    const text = String(data?.text || "");
    if (!text) return;
    state.chatAnswerText += text;
    elements.chatAnswer.classList.add("is-streaming");
    elements.chatAnswerStatus.textContent = "Streaming";
    elements.chatAnswerStatus.classList.add("is-streaming");
    setThinking("", false);
    scheduleChatAnswerRender();
  } else if (eventName === "done") {
    if (typeof data?.answer === "string" && data.answer && !state.chatAnswerText) {
      state.chatAnswerText = data.answer;
    }
    if (state.chatRenderFrame !== null) window.cancelAnimationFrame(state.chatRenderFrame);
    renderChatAnswer();
    renderChatSources(data?.sources);
    elements.chatAnswer.classList.remove("is-streaming");
    elements.chatAnswerStatus.textContent = "Complete";
    elements.chatAnswerStatus.classList.remove("is-streaming");
    elements.chatCopyButton.hidden = !state.chatAnswerText;
    state.chatTurnComplete = true;
    setThinking("", false);
  } else if (eventName === "error") {
    throw new Error(message || "The assistant could not complete this request.");
  }
}

function parseSseFrame(frame) {
  let eventName = "message";
  const dataLines = [];
  for (const line of frame.replaceAll("\r", "").split("\n")) {
    if (line.startsWith("event:")) eventName = line.slice(6).trim();
    if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
  }
  if (!dataLines.length) return;
  const data = JSON.parse(dataLines.join("\n"));
  handleChatEvent(eventName, data);
}

async function submitChat(question) {
  const cleanQuestion = String(question || "").trim();
  if (!cleanQuestion) return;
  const autoExecuteSql = elements.sqlAutoExecute.checked;
  try {
    await ensureChatSession();
  } catch (error) {
    showGlobalError(`Chat session could not be created: ${error.message}`);
    return;
  }
  if (state.chatController) state.chatController.abort();
  const controller = new AbortController();
  state.chatController = controller;
  archiveCompletedTurn();
  prepareChatResponse(cleanQuestion);

  const submitButton = elements.chatForm.querySelector('button[type="submit"]');
  submitButton.disabled = true;
  elements.sqlAutoExecute.disabled = true;
  elements.chatSubmitLabel.textContent = "Working";

  try {
    let response;
    for (let attempt = 0; attempt < 2; attempt += 1) {
      response = await fetch("/api/chat/stream", {
        method: "POST",
        headers: { "Accept": "text/event-stream", "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: state.chatSessionId,
          message: cleanQuestion,
          auto_execute_sql: autoExecuteSql,
        }),
        signal: controller.signal,
      });
      if (response.status !== 404 || attempt > 0) break;
      await createChatSession({ clearUi: true });
      prepareChatResponse(cleanQuestion);
    }
    if (!response.ok || !response.body) {
      let message = `Chat request failed (${response.status})`;
      try {
        const body = await response.json();
        message = body.detail || message;
      } catch (_error) {
        // Retain the status-based error for non-JSON responses.
      }
      throw new Error(message);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      const frames = buffer.replaceAll("\r\n", "\n").split("\n\n");
      buffer = frames.pop() || "";
      frames.filter((frame) => frame.trim()).forEach(parseSseFrame);
      if (done) break;
    }
    if (buffer.trim()) parseSseFrame(buffer);
  } catch (error) {
    if (error.name === "AbortError") return;
    elements.chatAnswer.classList.remove("is-streaming");
    elements.chatAnswerStatus.textContent = "Failed";
    elements.chatAnswerStatus.classList.remove("is-streaming");
    state.chatAnswerText = `The assistant could not complete this request.\n\n${error.message}`;
    state.chatTurnComplete = false;
    renderChatAnswer();
    appendChatActivity("error", "Error", error.message);
    setThinking("", false);
  } finally {
    if (state.chatController === controller) {
      state.chatController = null;
      submitButton.disabled = false;
      elements.sqlAutoExecute.disabled = false;
      elements.chatSubmitLabel.textContent = "Send";
    }
  }
}

async function loadStores() {
  const data = await fetchJson("/api/dashboard/stores");
  const fragment = document.createDocumentFragment();

  for (const store of data.stores) {
    const option = document.createElement("option");
    option.value = store.store_id;
    option.textContent =
      store.store_type === "online"
        ? "Online"
        : `${store.store_location}`;
    fragment.append(option);
  }

  elements.storeFilter.append(fragment);
}

function renderFinance(data) {
  const metrics = data.metrics;
  const metricCards = [
    {
      ...metrics.refund_adjusted_revenue,
      context: "Completed refunds deducted for this month",
    },
    {
      ...metrics.estimated_gross_profit,
      context: "Based on matched product costs",
    },
    {
      ...metrics.estimated_profit,
      context:
        data.scope.type === "company"
          ? "After operating expenses and allocated campaign spend"
          : "After this store's operating expenses",
      highlight: true,
    },
  ];

  elements.financeMetrics.className = "metric-grid";
  elements.financeMetrics.innerHTML = metricCards
    .map(
      (metric) => `
        <article class="metric-card${metric.highlight ? " highlight" : ""}">
          <span class="metric-label">${escapeHtml(metric.label)}</span>
          <strong class="metric-value${metric.value < 0 ? " negative" : ""}">
            ${escapeHtml(formatMoney(metric.value))}
          </strong>
          <span class="metric-context">${escapeHtml(metric.context)}</span>
        </article>
      `,
    )
    .join("");

  elements.financePeriod.textContent = `${formatMonth(data.period.month)}${
    data.period.is_complete ? " · Complete month" : " · Partial data"
  }`;
  elements.salesDataThrough.textContent = data.period.sales_data_through;
  elements.scopeCaption.textContent = `${data.scope.label} · ${
    data.period.is_complete ? "Complete calendar month" : "Partial month"
  }`;

  if (!state.month) {
    state.month = data.period.month;
    elements.monthFilter.value = data.period.month;
  }
  elements.monthFilter.max = data.period.sales_data_through.slice(0, 7);
  renderFinanceChart(data.trend);
}

function renderFinanceChart(points) {
  if (!Array.isArray(points) || points.length === 0) {
    renderEmpty(elements.financeChart, "No trend data is available for this scope");
    return;
  }

  const width = 820;
  const height = 238;
  const margin = { top: 15, right: 15, bottom: 34, left: 58 };
  const chartWidth = width - margin.left - margin.right;
  const chartHeight = height - margin.top - margin.bottom;
  const values = points.flatMap((item) => [
    Number(item.refund_adjusted_revenue) || 0,
    Number(item.estimated_gross_profit) || 0,
  ]);
  const minimum = Math.min(0, ...values);
  const maximum = Math.max(0, ...values);
  const span = maximum - minimum || 1;
  const paddedMaximum = maximum + span * 0.08;
  const paddedMinimum = minimum - span * 0.04;
  const paddedSpan = paddedMaximum - paddedMinimum || 1;

  const x = (index) =>
    margin.left + (index * chartWidth) / Math.max(points.length - 1, 1);
  const y = (value) =>
    margin.top + ((paddedMaximum - value) / paddedSpan) * chartHeight;
  const pathFor = (key) =>
    points
      .map((item, index) => {
        const command = index === 0 ? "M" : "L";
        return `${command}${x(index).toFixed(1)},${y(Number(item[key]) || 0).toFixed(1)}`;
      })
      .join(" ");

  const grid = Array.from({ length: 4 }, (_, index) => {
    const ratio = index / 3;
    const yPosition = margin.top + ratio * chartHeight;
    const value = paddedMaximum - ratio * paddedSpan;
    return `
      <line x1="${margin.left}" y1="${yPosition}" x2="${width - margin.right}" y2="${yPosition}" stroke="#dfe3dc" stroke-width="1" />
      <text x="${margin.left - 10}" y="${yPosition + 4}" text-anchor="end" fill="#66706a" font-size="10">${escapeHtml(formatCompactMoney(value))}</text>
    `;
  }).join("");

  const xLabels = points
    .map((item, index) => {
      const label = index % 2 === 0 || index === points.length - 1;
      if (!label) return "";
      return `<text x="${x(index)}" y="${height - 9}" text-anchor="middle" fill="#66706a" font-size="9">${escapeHtml(item.month.slice(5))}</text>`;
    })
    .join("");

  const circles = (key, color, label) =>
    points
      .map(
        (item, index) => `
          <circle cx="${x(index)}" cy="${y(Number(item[key]) || 0)}" r="3" fill="${color}" stroke="#f8f9f5" stroke-width="2">
            <title>${escapeHtml(`${item.month} ${label}：${formatMoney(item[key])}`)}</title>
          </circle>
        `,
      )
      .join("");

  const description = points
    .map(
      (item) =>
        `${item.month}: revenue ${formatMoney(item.refund_adjusted_revenue)}, gross profit ${formatMoney(item.estimated_gross_profit)}`,
    )
    .join("；");

  elements.financeChart.className = "line-chart";
  elements.financeChart.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-labelledby="finance-chart-title finance-chart-desc">
      <title id="finance-chart-title">Twelve-month financial trend</title>
      <desc id="finance-chart-desc">${escapeHtml(description)}</desc>
      ${grid}
      <line x1="${margin.left}" y1="${y(0)}" x2="${width - margin.right}" y2="${y(0)}" stroke="#aeb7b0" stroke-width="1" />
      <path d="${pathFor("refund_adjusted_revenue")}" fill="none" stroke="#167d5a" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />
      <path d="${pathFor("estimated_gross_profit")}" fill="none" stroke="#c7812c" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />
      ${circles("refund_adjusted_revenue", "#167d5a", "refund-adjusted revenue")}
      ${circles("estimated_gross_profit", "#c7812c", "estimated gross profit")}
      ${xLabels}
    </svg>
  `;
}

function renderActionCenter(data) {
  const inventory = data.inventory;
  const tickets = data.support_tickets;

  elements.inventorySummary.className = "action-summary";
  elements.inventorySummary.innerHTML = `
    <strong>${numberFormatter.format(inventory.critical_count)}</strong>
    <span>critical items</span>
    <strong>${numberFormatter.format(inventory.additional_reorder_count)}</strong>
    <span>items need replenishment</span>
  `;

  if (inventory.top_items.length === 0) {
    renderEmpty(elements.inventoryList, "No urgent inventory items in this scope");
  } else {
    elements.inventoryList.className = "compact-list";
    elements.inventoryList.innerHTML = inventory.top_items
      .map(
        (item) => `
          <article class="inventory-row">
            <i class="severity-dot ${escapeHtml(item.severity)}" aria-hidden="true"></i>
            <div>
              <span class="row-title">${escapeHtml(item.product_name)}</span>
              <span class="row-subtitle">${escapeHtml(item.store_location)} · ${escapeHtml({ critical: "Critical", high: "High", warning: "Warning" }[item.severity] || item.severity)}</span>
            </div>
            <span class="stock-value">
              <strong>${numberFormatter.format(item.stock_quantity)}</strong>
              Reorder level ${numberFormatter.format(item.reorder_level)}
            </span>
          </article>
        `,
      )
      .join("");
  }

  elements.ticketCount.textContent = `${numberFormatter.format(
    tickets.unresolved_high_priority_count,
  )} unresolved`;

  if (tickets.oldest.length === 0) {
    renderEmpty(elements.ticketList, "No unresolved high-priority tickets");
  } else {
    elements.ticketList.className = "ticket-list";
    elements.ticketList.innerHTML = tickets.oldest
      .map(
        (ticket) => `
          <article class="ticket-row">
            <span class="age-box">
              <strong>${numberFormatter.format(ticket.open_days)}</strong>
              <small>days open</small>
            </span>
            <div>
              <span class="row-title">${escapeHtml(ticket.notes || ticket.issue_category)}</span>
              <span class="row-subtitle">${escapeHtml(ticket.issue_category)} · ${escapeHtml(ticket.resolution_status)} · ${escapeHtml(ticket.submission_date)}</span>
            </div>
          </article>
        `,
      )
      .join("");
  }
}

const productTabLabels = {
  best_sellers: "Ranked by net units · selected month",
  top_rated: "Ranked by average rating · company-wide lifetime reviews",
  high_return_rate: "Ranked by completed-return rate for the selected sales cohort",
  lowest_rated: "Ranked by average rating · company-wide lifetime reviews",
};

function productMetrics(tab, item) {
  if (tab === "best_sellers") {
    return [
      [`${numberFormatter.format(item.net_units)} units`, "Net units"],
      [formatMoney(item.refund_adjusted_revenue), "Refund-adjusted revenue"],
    ];
  }
  if (tab === "high_return_rate") {
    return [
      [`${Number(item.return_rate_percent).toFixed(1)}%`, "Completed-return rate"],
      [`${item.returned_units} / ${item.sold_units} units`, "Returned / sold"],
    ];
  }
  return [
    [`★ ${Number(item.average_rating).toFixed(2)}`, "Average rating"],
    [`${numberFormatter.format(item.review_count)} reviews`, "Eligible reviews"],
  ];
}

function renderProducts(data) {
  state.productData = data;
  renderProductTab();
}

function renderProductTab() {
  if (!state.productData) return;
  const items = state.productData[state.activeProductTab] || [];
  const tabs = elements.productTabs.querySelectorAll(".tab");
  tabs.forEach((button) => {
    const isActive = button.dataset.tab === state.activeProductTab;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-pressed", String(isActive));
  });

  if (items.length === 0) {
    renderEmpty(elements.productList, "Not enough data for this ranking");
    return;
  }

  elements.productList.className = "rank-list";
  elements.productList.innerHTML = `
    <p class="rank-basis">${escapeHtml(productTabLabels[state.activeProductTab])}</p>
    ${items
      .map((item, index) => {
        const [primary, secondary] = productMetrics(state.activeProductTab, item);
        return `
          <article class="rank-row">
            <span class="rank-number">${String(index + 1).padStart(2, "0")}</span>
            <div>
              <span class="row-title">${escapeHtml(item.product_name)}</span>
              <span class="row-subtitle">${escapeHtml(item.product_category)}</span>
            </div>
            <span class="rank-metric">
              <strong>${escapeHtml(primary[0])}</strong>
              <span>${escapeHtml(primary[1])}</span>
            </span>
            <span class="rank-metric secondary">
              <strong>${escapeHtml(secondary[0])}</strong>
              <span>${escapeHtml(secondary[1])}</span>
            </span>
          </article>
        `;
      })
      .join("")}
  `;
}

function renderMarketing(data) {
  elements.campaignCount.textContent = `${numberFormatter.format(
    data.active_campaign_count,
  )} campaigns`;

  if (!data.campaigns.length) {
    renderEmpty(elements.campaignList, "No active campaigns overlap the selected month");
    return;
  }

  elements.campaignList.className = "campaign-list";
  elements.campaignList.innerHTML = data.campaigns
    .map((campaign) => {
      const roi = Number(campaign.roi) || 0;
      return `
        <article class="campaign-row">
          <div>
            <span class="row-title">${escapeHtml(campaign.campaign_name)}</span>
            <span class="row-subtitle">${escapeHtml(campaign.campaign_type)} · Budget ${escapeHtml(formatMoney(campaign.budget))}</span>
          </div>
          <span aria-label="Conversion rate ${escapeHtml(campaign.conversion_rate)}%">
            ${escapeHtml(Number(campaign.conversion_rate).toFixed(1))}%
          </span>
          <span class="${roi >= 0 ? "roi-positive" : "roi-negative"}" aria-label="ROI ${escapeHtml(roi)}%">
            ${roi >= 0 ? "+" : ""}${escapeHtml(roi.toFixed(0))}%
          </span>
        </article>
      `;
    })
    .join("");
}

function panelError(panel, message) {
  if (panel === "finance") {
    elements.financePeriod.textContent = "—";
    elements.salesDataThrough.textContent = "—";
    elements.scopeCaption.textContent = "—";
    elements.financeMetrics.innerHTML = "";
    renderEmpty(elements.financeMetrics, message);
    renderEmpty(elements.financeChart, "The trend chart is temporarily unavailable");
  } else if (panel === "action") {
    elements.ticketCount.textContent = "—";
    renderEmpty(elements.inventorySummary, message);
    renderEmpty(elements.inventoryList, "Inventory data is temporarily unavailable");
    renderEmpty(elements.ticketList, "Ticket data is temporarily unavailable");
  } else if (panel === "products") {
    state.productData = null;
    renderEmpty(elements.productList, message);
  } else if (panel === "marketing") {
    elements.campaignCount.textContent = "—";
    renderEmpty(elements.campaignList, message);
  }
}

async function loadDashboard() {
  if (state.requestController) state.requestController.abort();
  state.requestController = new AbortController();
  const { signal } = state.requestController;
  const requestedMonth = state.month;
  const requestedStore = state.storeId;
  const isStale = () =>
    signal.aborted ||
    requestedMonth !== state.month ||
    requestedStore !== state.storeId ||
    state.requestController.signal !== signal;
  let responseAccepted = false;

  clearGlobalError();
  elements.refreshButton.classList.add("is-loading");
  elements.refreshButton.disabled = true;
  setConnectionStatus("loading", "Refreshing data");
  state.runId = null;

  try {
    const createdRun = await fetchJson("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_type: "business_performance" }),
      signal,
    });
    if (isStale()) return;

    state.runId = createdRun.run_id;
    const data = await fetchJson(`/api/runs/${state.runId}/execute`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        month: state.month || null,
        store_id: state.storeId || null,
      }),
      signal,
    });
    if (isStale()) return;

    responseAccepted = true;

    renderFinance(data.result.finance);
    renderActionCenter(data.result.action_center);
    renderProducts(data.result.products);
    renderMarketing(data.result.marketing);

    setConnectionStatus("ok", "Supabase connected");
  } catch (error) {
    if (!responseAccepted && isStale()) return;
    if (signal.aborted || state.requestController.signal !== signal) return;

    const message = error instanceof Error ? error.message : String(error);

    setConnectionStatus("error", "Business analysis failed");
    showGlobalError(`Business analysis failed: ${message}`);

    panelError("finance", "Financial data is temporarily unavailable");
    panelError("action", "Action data is temporarily unavailable");
    panelError("products", "Product rankings are temporarily unavailable");
    panelError("marketing", "Campaign data is temporarily unavailable");
  } finally {
    if (
      responseAccepted ||
      (!isStale() && state.requestController.signal === signal)
    ) {
      elements.refreshButton.classList.remove("is-loading");
      elements.refreshButton.disabled = false;
    }
  }
}

function scheduleDashboardLoad() {
  if (state.filterTimer) window.clearTimeout(state.filterTimer);
  state.filterTimer = window.setTimeout(() => {
    state.filterTimer = null;
    loadDashboard();
  }, 300);
}

elements.productTabs.addEventListener("click", (event) => {
  const button = event.target.closest("[data-tab]");
  if (!button) return;
  state.activeProductTab = button.dataset.tab;
  renderProductTab();
});

elements.storeFilter.addEventListener("change", () => {
  state.storeId = elements.storeFilter.value;
  scheduleDashboardLoad();
});

elements.monthFilter.addEventListener("change", () => {
  state.month = elements.monthFilter.value;
  scheduleDashboardLoad();
});

elements.refreshButton.addEventListener("click", loadDashboard);

elements.knowledgeDropZone.addEventListener("click", () => {
  elements.knowledgeFileInput.click();
});

elements.knowledgeDropZone.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    elements.knowledgeFileInput.click();
  }
});

elements.knowledgeFileInput.addEventListener("change", () => {
  acceptDroppedFiles(elements.knowledgeFileInput.files);
});

for (const eventName of ["dragenter", "dragover"]) {
  elements.knowledgeDropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    elements.knowledgeDropZone.classList.add("is-dragging");
  });
}

for (const eventName of ["dragleave", "drop"]) {
  elements.knowledgeDropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    elements.knowledgeDropZone.classList.remove("is-dragging");
  });
}

elements.knowledgeDropZone.addEventListener("drop", (event) => {
  acceptDroppedFiles(event.dataTransfer.files);
});

elements.knowledgeDropZone.addEventListener("paste", (event) => {
  const files = event.clipboardData?.files;
  if (files?.length) {
    event.preventDefault();
    acceptDroppedFiles(files);
  }
});

document.addEventListener("paste", (event) => {
  if (event.defaultPrevented) return;
  const files = event.clipboardData?.files;
  if (files?.length) {
    event.preventDefault();
    acceptDroppedFiles(files);
  }
});

elements.knowledgeFileList.addEventListener("click", (event) => {
  const button = event.target.closest("[data-delete-file-id]");
  if (button) deleteKnowledgeFile(button.dataset.deleteFileId);
});

elements.reviewSyncButton.addEventListener("click", syncCustomerReviews);
elements.newChatButton.addEventListener("click", confirmNewChat);
elements.newChatDialog.addEventListener("close", () => {
  if (elements.newChatDialog.returnValue === "confirm") startNewChat();
});

elements.chatInput.addEventListener("input", resizeChatInput);
elements.chatInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    elements.chatForm.requestSubmit();
  }
});

elements.chatForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const question = elements.chatInput.value;
  if (!question.trim()) return;
  elements.chatInput.value = "";
  resizeChatInput();
  submitChat(question);
});

document.querySelectorAll(".prompt-chip").forEach((button) => {
  button.addEventListener("click", () => {
    elements.chatInput.value = button.textContent.trim();
    resizeChatInput();
    elements.chatForm.requestSubmit();
  });
});

elements.chatSqlApprovals.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-sql-decision]");
  if (!button) return;
  const card = button.closest(".sql-approval-card");
  submitSqlApproval(card, String(button.dataset.sqlDecision || ""));
});

elements.chatCopyButton.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(state.chatAnswerText);
    elements.chatCopyButton.textContent = "Copied";
    window.setTimeout(() => {
      elements.chatCopyButton.textContent = "Copy";
    }, 1400);
  } catch (_error) {
    elements.chatCopyButton.textContent = "Copy failed";
  }
});

async function initialise() {
  try {
    await createChatSession({ clearUi: true });
  } catch (error) {
    showGlobalError(`Chat session initialization failed: ${error.message}`);
  }
  loadKnowledgeFiles();
  try {
    await loadStores();
    await loadDashboard();
  } catch (error) {
    setConnectionStatus("error", "Database connection failed");
    showGlobalError(`Dashboard initialization failed: ${error.message}`);
    elements.refreshButton.classList.remove("is-loading");
    elements.refreshButton.disabled = false;
  }
}

initialise();
