"use strict";

const appConfig = Object.freeze(window.APP_CONFIG);

const state = {
  month: "",
  financeChartView: "trend",
  financeTrend: [],
  storeId: "",
  activeProductTab: "best_sellers",
  productData: null,
  candidateIssues: [],
  sharedDateRange: { start: "", end: "" },
  productDateRange: { start: "", end: "" },
  campaignDateRange: { start: "", end: "" },
  campaigns: [],
  selectedCampaignId: "",
  reviewProducts: [],
  reviewSelectedProductId: "",
  reviewOverviewController: null,
  reviewDetailController: null,
  runId: null,
  requestController: null,
  filterTimer: null,
  maxMonth: "",
  knowledgeAllowedExtensions: [],
  chatController: null,
  chatSessionId: "",
  chatAnswerText: "",
  chatRenderFrame: null,
  chatTurnComplete: false,
  chatSubtasks: new Map(),
};

const elements = {
  sidebar: document.querySelector("#sidebar"),
  sidebarToggle: document.querySelector("#sidebar-toggle"),
  sidebarBackdrop: document.querySelector("#sidebar-backdrop"),
  pageTitle: document.querySelector("#page-title"),
  pageSections: document.querySelectorAll("[data-page]"),
  pageLinks: document.querySelectorAll("[data-page-link]"),
  knowledgeOpen: document.querySelector("#knowledge-open"),
  knowledgeDialog: document.querySelector("#knowledge-dialog"),
  knowledgeClose: document.querySelector("#knowledge-close"),
  assistantOpen: document.querySelector("#assistant-open"),
  assistantPanel: document.querySelector("#assistant-panel"),
  assistantClose: document.querySelector("#assistant-close"),
  assistantDockToggle: document.querySelector("#assistant-dock-toggle"),
  assistantResizeHandle: document.querySelector("#assistant-resize-handle"),
  yearFilter: document.querySelector("#year-filter"),
  monthFilter: document.querySelector("#month-filter"),
  storeFilter: document.querySelector("#store-filter"),
  refreshButton: document.querySelector("#refresh-button"),
  connectionStatus: document.querySelector("#connection-status"),
  globalError: document.querySelector("#global-error"),
  financePeriod: document.querySelector("#finance-period"),
  financeStoreLabel: document.querySelector("#finance-store-label"),
  financePeriodToggle: document.querySelector("#finance-period-toggle"),
  financeFilters: document.querySelector("#finance-filters"),
  financeMetrics: document.querySelector("#finance-metrics"),
  financeChart: document.querySelector("#finance-chart"),
  financeChartSubtitle: document.querySelector("#finance-chart-subtitle"),
  financeChartLegend: document.querySelector("#finance-chart-legend"),
  overviewCategoryChart: document.querySelector("#overview-category-chart"),
  overviewCategoryPeriod: document.querySelector("#overview-category-period"),
  businessRiskCount: document.querySelector("#business-risk-count"),
  businessRiskList: document.querySelector("#business-risk-list"),
  reviewHotspotList: document.querySelector("#review-hotspot-list"),
  inventoryRiskSummary: document.querySelector("#inventory-risk-summary"),
  inventoryList: document.querySelector("#inventory-list"),
  productTabs: document.querySelector("#product-tabs"),
  productStartDate: document.querySelector("#product-start-date"),
  productEndDate: document.querySelector("#product-end-date"),
  productDateApply: document.querySelector("#product-date-apply"),
  productList: document.querySelector("#product-list"),
  productChart: document.querySelector("#product-chart"),
  productRevenueChart: document.querySelector("#product-revenue-chart"),
  productRevenuePeriod: document.querySelector("#product-revenue-period"),
  productCategoryChart: document.querySelector("#product-category-chart"),
  productCategoryPeriod: document.querySelector("#product-category-period"),
  productChartTitle: document.querySelector("#product-chart-title"),
  productTable: document.querySelector("#product-table"),
  productTableNote: document.querySelector("#product-table-note"),
  productReviews: document.querySelector("#product-reviews"),
  reviewScopeNote: document.querySelector("#review-scope-note"),
  reviewSummaryMetrics: document.querySelector("#review-summary-metrics"),
  reviewHighList: document.querySelector("#review-high-list"),
  reviewLowList: document.querySelector("#review-low-list"),
  reviewProductSelect: document.querySelector("#review-product-select"),
  reviewRatingFilter: document.querySelector("#review-rating-filter"),
  reviewProductSummary: document.querySelector("#review-product-summary"),
  reviewComments: document.querySelector("#review-comments"),
  campaignList: document.querySelector("#campaign-list"),
  campaignChart: document.querySelector("#campaign-chart"),
  campaignTable: document.querySelector("#campaign-table"),
  campaignPanel: document.querySelector("#campaign-performance"),
  campaignStartDate: document.querySelector("#campaign-start-date"),
  campaignEndDate: document.querySelector("#campaign-end-date"),
  campaignDateApply: document.querySelector("#campaign-date-apply"),
  campaignDetail: document.querySelector("#campaign-detail"),
  campaignDetailTitle: document.querySelector("#campaign-detail-title"),
  campaignDetailStart: document.querySelector("#campaign-detail-start"),
  campaignDetailEnd: document.querySelector("#campaign-detail-end"),
  campaignDetailCount: document.querySelector("#campaign-detail-count"),
  campaignDetailAxisStart: document.querySelector("#campaign-detail-axis-start"),
  campaignDetailAxisEnd: document.querySelector("#campaign-detail-axis-end"),
  chatForm: document.querySelector("#chat-form"),
  chatConversation: document.querySelector("#chat-conversation"),
  chatWelcome: document.querySelector("#chat-welcome"),
  chatHistory: document.querySelector("#chat-history"),
  chatSessionTitle: document.querySelector("#chat-session-title"),
  chatHistoryToggle: document.querySelector("#chat-history-toggle"),
  chatSessionHistory: document.querySelector("#chat-session-history"),
  newChatButton: document.querySelector("#new-chat-button"),
  newChatDialog: document.querySelector("#new-chat-dialog"),
  chatInput: document.querySelector("#chat-input"),
  chatResponse: document.querySelector("#chat-response"),
  chatQuestion: document.querySelector("#chat-question"),
  chatTrace: document.querySelector(".chat-trace"),
  chatTraceSummary: document.querySelector(".chat-trace > summary"),
  chatTraceContent: document.querySelector(".trace-content"),
  chatAnswerCard: document.querySelector(".chat-answer-card"),
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

const mobileNavigation = window.matchMedia("(max-width: 540px)");

function updateSidebarState() {
  const isMobile = mobileNavigation.matches;
  const isOpen = isMobile
    ? document.body.classList.contains("sidebar-open")
    : !document.body.classList.contains("sidebar-collapsed");
  elements.sidebarToggle.setAttribute("aria-expanded", String(isOpen));
  elements.sidebarToggle.setAttribute(
    "aria-label",
    isOpen ? (isMobile ? "Close navigation" : "Collapse navigation") : "Open navigation",
  );
  elements.sidebarBackdrop.hidden = !isMobile || !isOpen;
  elements.sidebar.inert = !isOpen;
}

elements.sidebarToggle.addEventListener("click", () => {
  document.body.classList.toggle(
    mobileNavigation.matches ? "sidebar-open" : "sidebar-collapsed",
  );
  updateSidebarState();
  if (document.body.classList.contains("assistant-docked")) setAssistantDockWidth(assistantDockWidth);
});

elements.sidebarBackdrop.addEventListener("click", () => {
  document.body.classList.remove("sidebar-open");
  updateSidebarState();
  elements.sidebarToggle.focus();
});

elements.sidebar.addEventListener("pointermove", (event) => {
  const bounds = elements.sidebar.getBoundingClientRect();
  elements.sidebar.style.setProperty("--sidebar-hover-x", `${event.clientX - bounds.left}px`);
  elements.sidebar.style.setProperty("--sidebar-hover-y", `${event.clientY - bounds.top}px`);
});
elements.sidebar.addEventListener("pointerleave", () => {
  elements.sidebar.style.removeProperty("--sidebar-hover-x");
  elements.sidebar.style.removeProperty("--sidebar-hover-y");
});

elements.sidebar.querySelectorAll(".sidebar-link").forEach((link) => {
  link.addEventListener("pointermove", (event) => {
    const bounds = link.getBoundingClientRect();
    link.style.setProperty("--hover-x", `${event.clientX - bounds.left}px`);
    link.style.setProperty("--hover-y", `${event.clientY - bounds.top}px`);
  });
  link.addEventListener("pointerleave", () => {
    link.style.removeProperty("--hover-x");
    link.style.removeProperty("--hover-y");
  });
  link.addEventListener("click", () => {
    if (mobileNavigation.matches) {
      document.body.classList.remove("sidebar-open");
      updateSidebarState();
    }
  });
});

for (const button of [elements.knowledgeOpen, elements.knowledgeDropZone, elements.assistantOpen, elements.productDateApply, elements.campaignDateApply]) {
  button.addEventListener("pointermove", (event) => {
    const bounds = button.getBoundingClientRect();
    button.style.setProperty("--hover-x", `${event.clientX - bounds.left}px`);
    button.style.setProperty("--hover-y", `${event.clientY - bounds.top}px`);
  });
  button.addEventListener("pointerleave", () => {
    button.style.removeProperty("--hover-x");
    button.style.removeProperty("--hover-y");
  });
}

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && document.body.classList.contains("sidebar-open")) {
    document.body.classList.remove("sidebar-open");
    updateSidebarState();
    elements.sidebarToggle.focus();
  }
});

mobileNavigation.addEventListener("change", () => {
  document.body.classList.remove("sidebar-open");
  updateSidebarState();
});

updateSidebarState();

const pageTitles = {
  overview: "Business overview",
  "action-center": "Business Action Center",
  "product-performance": "Product performance",
  "campaign-performance": "Campaign performance",
};

function showCurrentPage() {
  const requestedPage = window.location.hash.slice(1);
  const currentPage = Object.hasOwn(pageTitles, requestedPage) ? requestedPage : "overview";
  elements.pageTitle.textContent = pageTitles[currentPage];
  elements.pageSections.forEach((section) => {
    section.hidden = section.dataset.page !== currentPage;
  });
  elements.pageLinks.forEach((link) => {
    const isCurrent = link.dataset.pageLink === currentPage;
    link.classList.toggle("active", isCurrent);
    if (isCurrent) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  window.requestAnimationFrame(() => window.scrollTo(0, 0));
}

window.addEventListener("hashchange", showCurrentPage);
showCurrentPage();

elements.chatInput.maxLength = appConfig.maxChatMessageLength;


const moneyFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

const numberFormatter = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 0,
});

const firstOperatingYear = 2020;
const narrowChatLayout = window.matchMedia("(max-width: 760px)");
let activitySizingInitialized = false;
let activityResizeObserver = null;

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
    return `${sign}$${Number((absolute / 1_000_000).toFixed(2))}M`;
  }
  if (absolute >= 1_000) {
    return `${sign}$${Number((absolute / 1_000).toFixed(2))}K`;
  }
  return `${sign}$${Number(absolute.toFixed(2))}`;
}

function formatMonth(month) {
  if (!month || !/^\d{4}-\d{2}$/.test(month)) return month || "—";
  const [year, monthNumber] = month.split("-");
  return new Intl.DateTimeFormat("en-US", { month: "long", year: "numeric" }).format(
    new Date(Number(year), Number(monthNumber) - 1, 1),
  );
}

function formatShortDate(value, includeDay = false) {
  const match = /^(\d{4})-(\d{2})(?:-(\d{2}))?$/.exec(value || "");
  if (!match) return value || "—";
  const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3] || 1)));
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    ...(includeDay ? { day: "numeric" } : {}),
    year: "numeric",
    timeZone: "UTC",
  }).format(date);
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
  elements.chatWelcome.hidden = false;
  elements.chatResponse.hidden = true;
  elements.chatAnswerCard.hidden = true;
  elements.chatAnswerCard.classList.remove("is-approval-only");
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
  elements.chatSessionTitle.textContent = "New Chat";
  if (clearUi) resetConversationUi();
  return state.chatSessionId;
}

async function loadChatSessions() {
  const sessions = await fetchJson("/api/sessions");
  elements.chatSessionHistory.replaceChildren();
  sessions.filter((session) => session.message_count > 0).forEach((session) => {
    const date = new Date(session.updated_at);
    const ageDays = Math.floor((Date.now() - date.getTime()) / 86400000);
    const button = document.createElement("button");
    button.type = "button";
    button.className = "chat-session-item";
    button.dataset.sessionId = session.session_id;
    button.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5.5A3.5 3.5 0 0 1 7.5 2H20v15H7.5A3.5 3.5 0 0 0 4 20.5v-15Z"/><path d="M4 5.5A3.5 3.5 0 0 0 .5 9v11A3.5 3.5 0 0 1 4 16.5h16M9 7h6M9 11h6"/></svg><span><strong>${escapeHtml(session.title || "New Chat")}</strong></span><time>${ageDays < 1 ? "today" : ageDays < 7 ? `${ageDays}d` : date.toLocaleDateString(undefined, { month: "short", day: "numeric" })}</time>`;
    elements.chatSessionHistory.append(button);
  });
}

async function openChatSession(sessionId) {
  const session = await fetchJson(`/api/sessions/${encodeURIComponent(sessionId)}`);
  state.chatSessionId = session.session_id;
  resetConversationUi();
  elements.chatSessionTitle.textContent = session.title || "New Chat";
  elements.chatWelcome.hidden = session.messages.length > 0;
  session.messages.forEach((message) => {
    const card = document.createElement("article");
    card.className = `chat-history-message ${message.role}`;
    card.innerHTML = `<span class="message-label">${message.role === "user" ? "You" : "Assistant"}</span><div>${window.ChatRenderer?.renderMarkdown ? window.ChatRenderer.renderMarkdown(message.content) : escapeHtml(message.content)}</div>`;
    elements.chatHistory.append(card);
  });
  elements.chatSessionHistory.hidden = true;
  elements.chatHistoryToggle.setAttribute("aria-expanded", "false");
}

function closeChatHistory() {
  elements.chatSessionHistory.hidden = true;
  elements.chatHistoryToggle.setAttribute("aria-expanded", "false");
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

  archived.querySelector(".answer-actions")?.remove();
  archived.querySelectorAll("[id]").forEach((node) => node.removeAttribute("id"));
  archived.querySelector("[aria-labelledby]")?.removeAttribute("aria-labelledby");
  elements.chatHistory.append(archived);
}

function prepareChatResponse(question) {
  state.chatAnswerText = "";
  state.chatTurnComplete = false;
  elements.chatTrace.open = true;
  elements.chatTraceContent.scrollTop = 0;
  elements.chatWelcome.hidden = true;
  elements.chatResponse.hidden = false;
  elements.chatAnswerCard.hidden = true;
  elements.chatAnswerCard.classList.remove("is-approval-only");
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
  window.requestAnimationFrame(() => {
    elements.chatConversation.scrollTop = elements.chatConversation.scrollHeight;
  });
}

async function startNewChat() {
  const oldSessionId = state.chatSessionId;
  if (state.chatController) state.chatController.abort();
  state.chatSessionId = "";
  closeChatHistory();
  elements.newChatButton.disabled = true;
  try {
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
  if (!state.chatAnswerText.trim()) return;
  const followAnswer = elements.chatConversation.scrollHeight -
    elements.chatConversation.scrollTop - elements.chatConversation.clientHeight < 80;
  elements.chatAnswerCard.hidden = false;
  elements.chatAnswerCard.classList.remove("is-approval-only");
  if (window.ChatRenderer?.renderMarkdown) {
    elements.chatAnswer.innerHTML = window.ChatRenderer.renderMarkdown(state.chatAnswerText);
  } else {
    elements.chatAnswer.innerHTML = `<p>${escapeHtml(state.chatAnswerText).replaceAll("\n", "<br>")}</p>`;
  }
  if (followAnswer) elements.chatConversation.scrollTop = elements.chatConversation.scrollHeight;
}

function scheduleChatAnswerRender() {
  if (state.chatRenderFrame !== null) return;
  state.chatRenderFrame = window.requestAnimationFrame(renderChatAnswer);
}

function isActivityNearBottom() {
  const distanceFromBottom =
    elements.chatTraceContent.scrollHeight -
    elements.chatTraceContent.scrollTop -
    elements.chatTraceContent.clientHeight;
  return distanceFromBottom < 64;
}

function scrollActivityToBottom() {
  elements.chatTraceContent.scrollTop = elements.chatTraceContent.scrollHeight;
}

function updateActivityContent(update) {
  const shouldAutoScroll = isActivityNearBottom();

  update();

  if (shouldAutoScroll) scrollActivityToBottom();
}

function syncActivityHeight() {
  const shouldStayAtBottom = isActivityNearBottom();

  if (narrowChatLayout.matches || elements.chatResponse.hidden) {
    elements.chatTrace.style.removeProperty("--activity-panel-height");
    elements.chatTrace.style.removeProperty("--activity-content-max-height");
  } else {
    const responseHeight = elements.chatAnswerCard.getBoundingClientRect().height;
    const headerHeight = elements.chatTraceSummary.getBoundingClientRect().height;
    const traceBorderHeight =
      elements.chatTrace.offsetHeight - elements.chatTrace.clientHeight;
    const contentHeight = Math.max(
      0,
      Math.floor(responseHeight - headerHeight - traceBorderHeight),
    );

    elements.chatTrace.style.setProperty(
      "--activity-panel-height",
      `${Math.round(responseHeight)}px`,
    );
    elements.chatTrace.style.setProperty(
      "--activity-content-max-height",
      `${contentHeight}px`,
    );
  }

  if (shouldStayAtBottom) scrollActivityToBottom();
}

function initializeActivitySizing() {
  if (activitySizingInitialized) return;
  activitySizingInitialized = true;

  if (typeof ResizeObserver === "function") {
    activityResizeObserver = new ResizeObserver(syncActivityHeight);
    activityResizeObserver.observe(elements.chatAnswerCard);
  }
  narrowChatLayout.addEventListener("change", syncActivityHeight);
  syncActivityHeight();
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
  updateActivityContent(() => elements.chatProgress.append(item));
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
  updateActivityContent(() => {
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
  });
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
  updateActivityContent(() => {
    row.className = `subtask-row is-${status}`;
    const label = row.querySelector(".subtask-state-label");
    if (label) label.textContent = SUBTASK_STATUS_LABELS[status];
    updateSubtaskProgressCount();
  });
}

function setThinking(message, visible = true) {
  elements.chatThinking.hidden = !visible;
  if (message) elements.chatThinkingLabel.textContent = message;
}

function safeSourceUrl(value) {
  if (value === null || value === undefined) return null;
  const candidate = String(value).trim();
  if (!candidate) return null;

  try {
    const url = new URL(candidate, window.location.origin);
    if (!['http:', 'https:'].includes(url.protocol)) return null;
    return url.href;
  } catch (_error) {
    return null;
  }
}

function groupChatSources(sources) {
  const entries = [];
  const knowledgeFiles = new Map();

  sources.forEach((source) => {
    if (!source || typeof source !== "object") return;
    if (source.file_id === null || source.file_id === undefined) {
      entries.push({ kind: "source", source });
      return;
    }

    const key = String(source.file_id);
    let group = knowledgeFiles.get(key);
    if (!group) {
      group = {
        kind: "knowledge-file",
        file_id: source.file_id,
        filename: source.filename,
        download_url: source.download_url,
        chunks: [],
      };
      knowledgeFiles.set(key, group);
      entries.push(group);
    }
    if (!group.filename && source.filename) group.filename = source.filename;
    if (!group.download_url && source.download_url) group.download_url = source.download_url;
    group.chunks.push({
      chunk_index: source.chunk_index,
      citation: source.citation,
      similarity: source.similarity,
    });
  });

  return entries;
}

async function downloadChatSource(source, trigger, status) {
  const href = safeSourceUrl(source.download_url);
  if (!href) return;

  const idleLabel = status.textContent;
  trigger.disabled = true;
  status.textContent = "Downloading…";
  try {
    const response = await fetch(href, { credentials: "same-origin" });
    if (!response.ok) throw new Error(`Download failed (${response.status})`);

    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    const download = document.createElement("a");
    download.href = objectUrl;
    download.download = String(source.filename || "knowledge-source");
    download.hidden = true;
    document.body.append(download);
    download.click();
    download.remove();
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
    status.textContent = "Downloaded";
    window.setTimeout(() => {
      if (status.isConnected) status.textContent = idleLabel;
    }, 1400);
  } catch (error) {
    console.error("Reference download failed", error);
    status.textContent = "Download failed · retry";
  } finally {
    trigger.disabled = false;
  }
}

function renderChatSources(sources) {
  elements.chatSources.replaceChildren();
  if (!Array.isArray(sources) || sources.length === 0) {
    elements.chatSources.hidden = true;
    return;
  }

  const entries = groupChatSources(sources);

  const heading = document.createElement("div");
  heading.className = "sources-heading";
  const title = document.createElement("strong");
  title.textContent = "References";
  const count = document.createElement("span");
  count.textContent = `${entries.length} cited source${entries.length === 1 ? "" : "s"}`;
  heading.append(title, count);

  const list = document.createElement("div");
  list.className = "source-list";
  entries.forEach((entryData, index) => {
    const isKnowledgeFile = entryData.kind === "knowledge-file";
    const source = isKnowledgeFile ? entryData : entryData.source;
    const href = safeSourceUrl(source.download_url);
    const entry = document.createElement(href ? "button" : "div");
    if (href) entry.type = "button";
    entry.className = "source-entry";

    const number = document.createElement("span");
    number.className = "source-index";
    number.textContent = String(index + 1).padStart(2, "0");
    const copy = document.createElement("span");
    copy.className = "source-copy";
    const filename = document.createElement("strong");
    filename.textContent = source.filename || source.citation || "Knowledge source";
    const detail = document.createElement("small");
    if (isKnowledgeFile) {
      const chunkDetails = source.chunks.map((chunk) => {
        const similarity = Number(chunk.similarity);
        const chunkLabel = chunk.chunk_index === null || chunk.chunk_index === undefined
          ? String(chunk.citation || "evidence")
          : `#${chunk.chunk_index}`;
        return Number.isFinite(similarity)
          ? `${chunkLabel} ${Math.round(similarity * 100)}%`
          : chunkLabel;
      });
      detail.textContent = `${source.chunks.length} evidence chunk${source.chunks.length === 1 ? "" : "s"} · ${chunkDetails.join(", ")}`;
      detail.title = source.chunks
        .map((chunk) => String(chunk.citation || `#${chunk.chunk_index}`))
        .join(", ");
    } else {
      const similarity = Number(source.similarity);
      detail.textContent = [
        source.citation,
        Number.isFinite(similarity) ? `${Math.round(similarity * 100)}% match` : "",
      ].filter(Boolean).join(" · ");
    }
    copy.append(filename, detail);
    const open = document.createElement("span");
    open.className = "source-open";
    open.textContent = href ? "Download" : "";
    if (href) {
      entry.addEventListener("click", (event) => {
        event.preventDefault();
        downloadChatSource(source, entry, open);
      });
    }
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

  if (!state.chatAnswerText.trim()) {
    elements.chatAnswerCard.hidden = false;
    elements.chatAnswerCard.classList.add("is-approval-only");
  }

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
  if (data?.session_title) elements.chatSessionTitle.textContent = data.session_title;
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
    if (!state.chatAnswerText.trim()) {
      state.chatAnswerText = "The assistant did not return an answer.";
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

async function submitChat(question, { abortExisting = true } = {}) {
  const cleanQuestion = String(question || "").trim();
  if (!cleanQuestion) return;
  const autoExecuteSql = elements.sqlAutoExecute.checked;
  try {
    await ensureChatSession();
  } catch (error) {
    showGlobalError(`Chat session could not be created: ${error.message}`);
    return;
  }
  if (state.chatController) {
    if (!abortExisting) return;
    state.chatController.abort();
  }
  const controller = new AbortController();
  state.chatController = controller;
  setRiskAskAgentButtonsDisabled(true);
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
      setRiskAskAgentButtonsDisabled(false);
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
  updateFinanceStoreLabel();
}

function updateFinanceStoreLabel() {
  elements.financeStoreLabel.textContent =
    elements.storeFilter.selectedOptions[0]?.textContent?.trim() || "All stores";
}

function populateOperatingYears(maxYear) {
  const fragment = document.createDocumentFragment();
  for (let year = maxYear; year >= firstOperatingYear; year -= 1) {
    const option = document.createElement("option");
    option.value = String(year);
    option.textContent = String(year);
    fragment.append(option);
  }
  elements.yearFilter.replaceChildren(fragment);
}

function constrainOperatingMonth(year, preferredMonth) {
  const [maxYearText, maxMonthText] = state.maxMonth.split("-");
  const maxYear = Number(maxYearText);
  const maxMonth = Number(maxMonthText);
  const selectedYear = Number(year);
  const preferredMonthNumber = Number(preferredMonth);
  const allowedMonth =
    selectedYear === maxYear && preferredMonthNumber > maxMonth
      ? String(maxMonth).padStart(2, "0")
      : preferredMonth;

  for (const option of elements.monthFilter.options) {
    option.disabled = selectedYear === maxYear && Number(option.value) > maxMonth;
  }

  elements.monthFilter.value = allowedMonth;
  return allowedMonth;
}

function syncOperatingMonthFilters() {
  const selectedMatch = /^(\d{4})-(\d{2})$/.exec(state.month);
  const maximumMatch = /^(\d{4})-(\d{2})$/.exec(state.maxMonth);
  if (!selectedMatch || !maximumMatch) return;

  const selectedYear = selectedMatch[1];
  const selectedMonth = selectedMatch[2];
  const maxYear = Number(maximumMatch[1]);

  populateOperatingYears(maxYear);
  elements.yearFilter.value = selectedYear;
  constrainOperatingMonth(selectedYear, selectedMonth);
  elements.yearFilter.disabled = false;
  elements.monthFilter.disabled = false;
}

function updateOperatingMonthFromFilters() {
  const year = elements.yearFilter.value;
  const month = constrainOperatingMonth(year, elements.monthFilter.value);
  if (!year || !month) return;

  const selectedMonth = `${year}-${month}`;
  if (selectedMonth === state.month) return;

  state.month = selectedMonth;
  scheduleDashboardLoad();
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
  updateMetricContextVisibility();

  elements.financePeriod.textContent = `${formatMonth(data.period.month)}${
    data.period.is_complete ? " · Complete month" : " · Partial data"
  }`;

  state.maxMonth = data.period.sales_data_through.slice(0, 7);
  if (!state.month) state.month = data.period.month;
  syncOperatingMonthFilters();
  state.financeTrend = data.trend;
  renderFinanceChart(state.financeTrend);
  elements.overviewCategoryPeriod.textContent = formatMonth(data.period.month);
  renderCategoryShare(elements.overviewCategoryChart, data.category_share);
}

function updateMetricContextVisibility() {
  elements.financeMetrics.querySelectorAll(".metric-context").forEach((context) => {
    context.hidden = false;
    context.hidden = context.scrollWidth > context.clientWidth + 1;
  });
}

let lastMetricGridWidth = -1;
if ("ResizeObserver" in window) {
  new ResizeObserver(([entry]) => {
    if (entry.contentRect.width === lastMetricGridWidth) return;
    lastMetricGridWidth = entry.contentRect.width;
    updateMetricContextVisibility();
  }).observe(elements.financeMetrics);
} else {
  window.addEventListener("resize", updateMetricContextVisibility);
}

function enableChartValues(container, points, series, geometry, formatLabel) {
  const svg = container.querySelector("svg");
  if (!svg || !points.length) return;

  const namespace = "http://www.w3.org/2000/svg";
  const marker = document.createElementNS(namespace, "g");
  marker.setAttribute("class", "chart-hover-marker");
  marker.setAttribute("hidden", "");
  const guide = document.createElementNS(namespace, "line");
  guide.setAttribute("class", "chart-hover-guide");
  guide.setAttribute("y1", String(geometry.margin.top));
  guide.setAttribute("y2", String(geometry.height - geometry.margin.bottom));
  marker.appendChild(guide);
  const dots = series.map(({ color }) => {
    const dot = document.createElementNS(namespace, "circle");
    dot.setAttribute("r", "5");
    dot.setAttribute("fill", color);
    dot.setAttribute("class", "chart-hover-dot");
    if (geometry.showDots !== false) marker.appendChild(dot);
    return dot;
  });
  svg.appendChild(marker);

  const tooltip = document.createElement("div");
  tooltip.className = "chart-tooltip";
  tooltip.hidden = true;
  container.appendChild(tooltip);
  const announcement = document.createElement("span");
  announcement.className = "sr-only";
  announcement.setAttribute("aria-live", "polite");
  container.appendChild(announcement);
  svg.setAttribute("tabindex", "0");
  svg.setAttribute("aria-keyshortcuts", "ArrowLeft ArrowRight");

  let activeIndex = -1;
  const show = (index, announce = false) => {
    if (index < 0 || index >= points.length) return;
    const point = points[index];
    const position = geometry.x(index);
    guide.setAttribute("x1", String(position));
    guide.setAttribute("x2", String(position));
    const details = series.map(({ key, name, color }, seriesIndex) => {
      const value = finiteNumber(point[key]);
      dots[seriesIndex].setAttribute("cx", String(position));
      dots[seriesIndex].setAttribute("cy", String(geometry.y(value)));
      return { name, color, value };
    });
    marker.removeAttribute("hidden");
    tooltip.hidden = false;
    if (activeIndex !== index) {
      tooltip.innerHTML = `<strong>${escapeHtml(formatLabel(point))}</strong>${details.map(({ name, color, value }) => `<span><i style="background:${color}"></i>${escapeHtml(name)}<b>${escapeHtml(formatMoney(value))}</b></span>`).join("")}`;
      activeIndex = index;
    }
    const svgRect = svg.getBoundingClientRect();
    const containerRect = container.getBoundingClientRect();
    const tooltipWidth = tooltip.offsetWidth;
    const tooltipHeight = tooltip.offsetHeight;
    const xPixels = svgRect.left - containerRect.left + position * svgRect.width / geometry.width;
    const yPixels = svgRect.top - containerRect.top + Math.min(...details.map(({ value }) => geometry.y(value))) * svgRect.height / geometry.height;
    tooltip.style.left = `${Math.max(tooltipWidth / 2 + 4, Math.min(containerRect.width - tooltipWidth / 2 - 4, xPixels))}px`;
    tooltip.style.top = `${Math.max(4, yPixels - tooltipHeight - 12)}px`;
    if (announce) {
      announcement.textContent = `${formatLabel(point)}. ${details.map(({ name, value }) => `${name}: ${formatMoney(value)}`).join(". ")}`;
    }
  };
  const hide = () => {
    marker.setAttribute("hidden", "");
    tooltip.hidden = true;
    activeIndex = -1;
  };

  svg.addEventListener("pointermove", (event) => {
    const rect = svg.getBoundingClientRect();
    const graphX = (event.clientX - rect.left) * geometry.width / rect.width;
    const index = points.reduce((nearest, _, candidate) =>
      Math.abs(geometry.x(candidate) - graphX) < Math.abs(geometry.x(nearest) - graphX) ? candidate : nearest, 0);
    show(index);
  });
  svg.addEventListener("pointerleave", hide);
  svg.addEventListener("focus", () => show(0, true));
  svg.addEventListener("blur", hide);
  svg.addEventListener("keydown", (event) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    show(Math.max(0, Math.min(points.length - 1, activeIndex + (event.key === "ArrowRight" ? 1 : -1))), true);
  });
}

function renderFinanceChart(points) {
  const stacked = state.financeChartView === "stacked";
  elements.financeChart.setAttribute("aria-label", stacked
    ? "Twelve-month stacked sales and refunds with estimated gross profit"
    : "Twelve-month refund-adjusted revenue and estimated gross profit trend");
  elements.financeChartSubtitle.textContent = stacked
    ? "Monthly sales split into kept revenue and refunds, with gross profit"
    : "Refund-adjusted revenue and estimated gross profit";
  elements.financeChartLegend.classList.toggle("is-stacked", stacked);
  elements.financeChartLegend.innerHTML = stacked
    ? '<span><i class="revenue-dot"></i>Kept revenue</span><span><i class="refund-dot"></i>Refunds</span><span><i class="profit-dot"></i>Gross profit</span>'
    : '<span><i class="revenue-dot"></i>Revenue</span><span><i class="profit-dot"></i>Gross profit</span>';
  if (!Array.isArray(points) || points.length === 0) {
    renderEmpty(elements.financeChart, "No trend data is available for this scope");
    return;
  }

  const width = 820;
  const height = 238;
  const margin = { top: 15, right: 15, bottom: 34, left: 58 };
  const chartWidth = width - margin.left - margin.right;
  const chartHeight = height - margin.top - margin.bottom;
  const chartPoints = points.map((item) => ({
    ...item,
    sales_before_refunds: finiteNumber(item.refund_adjusted_revenue) + finiteNumber(item.completed_refunds),
  }));
  const values = chartPoints.flatMap((item) => [
    Number(item.refund_adjusted_revenue) || 0,
    Number(item.estimated_gross_profit) || 0,
    ...(stacked ? [item.sales_before_refunds] : []),
  ]);
  const minimum = Math.min(0, ...values);
  const maximum = Math.max(0, ...values);
  const roughStep = (maximum - minimum || Math.max(Math.abs(maximum), 1)) / 4;
  const magnitude = 10 ** Math.floor(Math.log10(roughStep));
  const step = [1, 2, 5, 10].find((multiple) => multiple * magnitude >= roughStep) * magnitude;
  const axisMaximum = Math.ceil(maximum / step) * step + step;
  const axisMinimum = Math.min(0, Math.floor(minimum / step) * step);
  const axisSpan = axisMaximum - axisMinimum;

  const x = (index) => stacked
    ? margin.left + ((index + .5) * chartWidth) / chartPoints.length
    : margin.left + (index * chartWidth) / Math.max(chartPoints.length - 1, 1);
  const y = (value) =>
    margin.top + ((axisMaximum - value) / axisSpan) * chartHeight;
  const pathFor = (key) =>
    points
      .map((item, index) => {
        const command = index === 0 ? "M" : "L";
        return `${command}${x(index).toFixed(1)},${y(Number(item[key]) || 0).toFixed(1)}`;
      })
      .join(" ");

  const grid = Array.from({ length: Math.round(axisSpan / step) + 1 }, (_, index) => {
    const value = axisMaximum - index * step;
    const yPosition = y(value);
    return `
      <line x1="${margin.left}" y1="${yPosition}" x2="${width - margin.right}" y2="${yPosition}" stroke="#dfe3dc" stroke-width="1" />
      <text x="${margin.left - 10}" y="${yPosition + 4}" text-anchor="end" fill="#66706a" font-size="10">${escapeHtml(formatCompactMoney(value))}</text>
    `;
  }).join("");

  const xLabels = points
    .map((item, index) => {
      const label = index % 2 === 0 || index === points.length - 1;
      if (!label) return "";
      return `<text x="${x(index)}" y="${height - 9}" text-anchor="middle" fill="#66706a" font-size="9">${escapeHtml(formatShortDate(item.month).split(" ")[0])}</text>`;
    })
    .join("");

  const revenuePath = pathFor("refund_adjusted_revenue");
  const revenueArea = `${revenuePath} L${x(points.length - 1).toFixed(1)},${y(0).toFixed(1)} L${x(0).toFixed(1)},${y(0).toFixed(1)} Z`;
  const barWidth = Math.min(39, chartWidth / chartPoints.length * .58);
  const bars = chartPoints.map((item, index) => {
    const kept = Math.max(0, finiteNumber(item.refund_adjusted_revenue));
    const refunds = Math.max(0, finiteNumber(item.completed_refunds));
    const negativeRevenue = Math.min(0, finiteNumber(item.refund_adjusted_revenue));
    const left = x(index) - barWidth / 2;
    const segment = (top, bottom, color) => {
      const segmentHeight = y(bottom) - y(top);
      if (segmentHeight <= 0) return "";
      const shape = `x="${left.toFixed(1)}" y="${y(top).toFixed(1)}" width="${barWidth.toFixed(1)}" height="${segmentHeight.toFixed(1)}" rx="2"`;
      return `<rect ${shape} fill="${color}" fill-opacity=".53" /><rect ${shape} fill="url(#finance-bar-grain)" fill-opacity=".16" pointer-events="none" />`;
    };
    return segment(kept, 0, "#167d5a") + segment(kept + refunds, kept, "#d48679") + segment(0, negativeRevenue, "#ad584e");
  }).join("");

  const description = chartPoints
    .map(
      (item) =>
        `${item.month}: ${stacked ? `sales before refunds ${formatMoney(item.sales_before_refunds)}, ` : ""}revenue ${formatMoney(item.refund_adjusted_revenue)}, ${stacked ? `refunds ${formatMoney(item.completed_refunds)}, ` : ""}gross profit ${formatMoney(item.estimated_gross_profit)}`,
    )
    .join("；");

  elements.financeChart.className = "line-chart";
  elements.financeChart.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-labelledby="finance-chart-title finance-chart-desc">
      <title id="finance-chart-title">Twelve-month ${stacked ? "sales and refunds" : "financial trend"}</title>
      <desc id="finance-chart-desc">${escapeHtml(description)}</desc>
      <defs>
        <linearGradient id="finance-revenue-gradient" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#167d5a" stop-opacity=".22" /><stop offset="100%" stop-color="#167d5a" stop-opacity="0" /></linearGradient>
        <filter id="finance-grain-filter"><feTurbulence type="fractalNoise" baseFrequency=".72" numOctaves="3" seed="4" stitchTiles="stitch" /><feColorMatrix type="saturate" values="0" /></filter>
        <pattern id="finance-bar-grain" patternUnits="userSpaceOnUse" width="64" height="64"><rect width="64" height="64" filter="url(#finance-grain-filter)" /></pattern>
      </defs>
      ${grid}
      <line x1="${margin.left}" y1="${y(0)}" x2="${width - margin.right}" y2="${y(0)}" stroke="#aeb7b0" stroke-width="1" />
      ${stacked ? bars : `<path d="${revenueArea}" fill="url(#finance-revenue-gradient)" /><path d="${revenuePath}" fill="none" stroke="#167d5a" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />`}
      <path d="${pathFor("estimated_gross_profit")}" fill="none" stroke="${stacked ? "#1686d9" : "#c7812c"}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />
      ${xLabels}
    </svg>
  `;
  enableChartValues(
    elements.financeChart,
    chartPoints,
    stacked
      ? [
          { key: "sales_before_refunds", name: "Sales before refunds", color: "#789783" },
          { key: "refund_adjusted_revenue", name: "Kept revenue", color: "#167d5a" },
          { key: "completed_refunds", name: "Refunds", color: "#d48679" },
          { key: "estimated_gross_profit", name: "Gross profit", color: "#1686d9" },
        ]
      : [
          { key: "refund_adjusted_revenue", name: "Revenue", color: "#167d5a" },
          { key: "estimated_gross_profit", name: "Gross profit", color: "#c7812c" },
        ],
    { width, height, margin, x, y, showDots: !stacked },
    (point) => formatMonth(point.month),
  );
}

function renderCategoryShare(container, rows) {
  const categories = (Array.isArray(rows) ? rows : [])
    .map((row) => ({ category: String(row.category || "Uncategorized"), revenue: finiteNumber(row.revenue) }));
  const positive = categories
    .filter((row) => row.revenue > 0)
    .sort((a, b) => b.revenue - a.revenue);
  const total = positive.reduce((sum, row) => sum + row.revenue, 0);
  if (!total) {
    renderEmpty(container, "No category revenue for this period");
    return;
  }
  const slices = positive.length > 4
    ? [...positive.slice(0, 4), { category: "Others", revenue: positive.slice(4).reduce((sum, row) => sum + row.revenue, 0) }]
    : positive;
  const colors = ["#167d5a", "#85ae87", "#c7812c", "#6d85a6", "#b7bdba"];
  let offset = 0;
  const stops = slices.map((row, index) => {
    const start = offset;
    offset += (row.revenue / total) * 100;
    return `${colors[index]} ${start.toFixed(2)}% ${offset.toFixed(2)}%`;
  });
  container.className = "category-chart";
  container.innerHTML = `
    <div class="category-donut" role="img" aria-label="${escapeHtml(slices.map((row) => `${row.category} ${(row.revenue / total * 100).toFixed(1)} percent`).join(", "))}" style="background:conic-gradient(${stops.join(",")})">
      <div class="category-donut-center"><span>${categories.some((row) => row.revenue < 0) ? "Positive revenue" : "Total revenue"}</span><strong>${escapeHtml(formatCompactMoney(total))}</strong></div>
    </div>
    <ul class="category-legend">${slices.map((row, index) => `<li><span class="category-label" title="${escapeHtml(row.category)}"><i style="background:${colors[index]}"></i><span>${escapeHtml(row.category)}</span></span><strong>${(row.revenue / total * 100).toFixed(1)}%</strong><small>${escapeHtml(formatMoney(row.revenue))}</small></li>`).join("")}</ul>
    ${categories.some((row) => row.revenue < 0) ? '<p class="category-note">Negative net categories are excluded from shares.</p>' : ""}
  `;
}

function renderProductRevenueTrend(rows) {
  const points = Array.isArray(rows) ? rows : [];
  if (!points.length) {
    renderEmpty(elements.productRevenueChart, "No revenue in this period");
    return;
  }
  const width = 600;
  const height = 220;
  const margin = { top: 18, right: 12, bottom: 30, left: 55 };
  const chartHeight = height - margin.top - margin.bottom;
  const values = points.map((row) => finiteNumber(row.revenue));
  const minimum = Math.min(0, ...values);
  const maximum = Math.max(0, ...values);
  const span = maximum - minimum || 1;
  const upper = maximum + span * .08;
  const lower = minimum - span * .04;
  const x = (index) => margin.left + index * (width - margin.left - margin.right) / Math.max(points.length - 1, 1);
  const y = (value) => margin.top + (upper - value) / (upper - lower) * chartHeight;
  const path = points.map((row, index) => `${index ? "L" : "M"}${x(index).toFixed(1)},${y(finiteNumber(row.revenue)).toFixed(1)}`).join(" ");
  const area = `${path} L${x(points.length - 1).toFixed(1)},${y(0).toFixed(1)} L${x(0).toFixed(1)},${y(0).toFixed(1)} Z`;
  const useDay = points.length > 1 && (new Date(points.at(-1).date) - new Date(points[0].date)) / 86_400_000 <= 90;
  const labels = points.map((row, index) => {
    if (index !== 0 && index !== points.length - 1 && index % Math.max(1, Math.ceil(points.length / 5))) return "";
    return `<text x="${x(index)}" y="${height - 8}" text-anchor="middle">${escapeHtml(formatShortDate(row.date, useDay))}</text>`;
  }).join("");
  const grid = Array.from({ length: 4 }, (_, index) => {
    const lineY = margin.top + index * chartHeight / 3;
    return `<line x1="${margin.left}" x2="${width - margin.right}" y1="${lineY}" y2="${lineY}" stroke="#dfe3dc" stroke-dasharray="2 3" /><text x="${margin.left - 8}" y="${lineY + 4}" text-anchor="end">${escapeHtml(formatCompactMoney(upper - index * (upper - lower) / 3))}</text>`;
  }).join("");
  elements.productRevenueChart.className = "line-chart";
  elements.productRevenueChart.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Revenue trend: ${escapeHtml(points.map((row) => `${row.date} ${formatMoney(row.revenue)}`).join(", "))}">
    <defs><linearGradient id="product-revenue-gradient" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#167d5a" stop-opacity=".22" /><stop offset="100%" stop-color="#167d5a" stop-opacity="0" /></linearGradient></defs>
    ${grid}<path d="${area}" fill="url(#product-revenue-gradient)" /><path d="${path}" fill="none" stroke="#167d5a" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />${points.length === 1 ? `<circle cx="${x(0)}" cy="${y(values[0])}" r="4" fill="#167d5a" />` : ""}${labels}</svg>`;
  enableChartValues(
    elements.productRevenueChart,
    points,
    [{ key: "revenue", name: "Revenue", color: "#167d5a" }],
    { width, height, margin, x, y },
    (point) => formatShortDate(point.date, useDay),
  );
}

function finiteNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function fixedNumber(value, digits = 2) {
  return finiteNumber(value).toFixed(digits);
}

function issueScopeLabel(issue) {
  const scope = issue && typeof issue.scope === "object" ? issue.scope : {};
  return scope.label ||
    (scope.type === "company" ? "Company-wide" : scope.store_id || "Current scope");
}

function issuePeriodLabel(issue) {
  const period = issue && typeof issue.period === "object" ? issue.period : {};
  return period.snapshot_date
    ? `Snapshot ${period.snapshot_date}`
    : period.data_through
      ? `Data through ${period.data_through}`
    : period.month || "Current period";
}

function issueContext(issue) {
  return `${issueScopeLabel(issue)} · ${issuePeriodLabel(issue)}`;
}

function genericEvidence(evidence) {
  if (!evidence || typeof evidence !== "object") {
    return ["Structured evidence is unavailable"];
  }
  const labels = {
    current_value: "Current value",
    baseline_value: "Baseline value",
    change_pct: "Change",
    affected_ratio: "Affected",
    critical_count: "Critical",
  };
  const items = Object.entries(evidence)
    .filter(([, value]) => ["string", "number", "boolean"].includes(typeof value))
    .slice(0, 3)
    .map(([key, value]) => `${labels[key] || key.replaceAll("_", " ")}: ${value}`);
  return items.length ? items : ["Structured evidence is available"];
}

function issueEvidenceLines(issue) {
  const evidence = issue && typeof issue.evidence === "object" ? issue.evidence : {};
  if (issue.issue_type === "profit_deterioration") {
    return [
      `Gross profit decreased ${Math.abs(finiteNumber(evidence.change_pct)).toFixed(2)}%`,
      `${formatMoney(evidence.baseline_value)} → ${formatMoney(evidence.current_value)}`,
      `vs ${evidence.baseline_period || "previous period"}`,
    ];
  }
  if (issue.issue_type === "refund_pressure") {
    return [
      `Completed refunds increased ${fixedNumber(evidence.change_pct)}%`,
      `+${formatMoney(Math.abs(finiteNumber(evidence.absolute_increase)))}`,
      `${formatMoney(evidence.baseline_value)} → ${formatMoney(evidence.current_value)}`,
    ];
  }
  if (issue.issue_type === "inventory_replenishment_risk") {
    return [
      `${numberFormatter.format(finiteNumber(evidence.affected_inventory_count))} of ${numberFormatter.format(finiteNumber(evidence.total_inventory_count))} inventory records need replenishment`,
      `${fixedNumber(evidence.affected_ratio)}% affected`,
      `${numberFormatter.format(finiteNumber(evidence.critical_count))} critical records`,
    ];
  }
  if (issue.issue_type === "campaign_inefficiency") {
    return [
      `${numberFormatter.format(finiteNumber(evidence.negative_roi_campaign_count))} of ${numberFormatter.format(finiteNumber(evidence.active_campaign_count))} active campaigns have negative reported ROI`,
      `${fixedNumber(evidence.negative_roi_ratio, 1)}% affected`,
      `Lowest reported lifecycle ROI: ${fixedNumber(evidence.lowest_reported_roi)}%`,
    ];
  }
  if (issue.issue_type === "customer_experience_deterioration") {
    const ratingChange = finiteNumber(evidence.average_rating_change);
    const ratioChange = finiteNumber(evidence.low_rating_ratio_change_pp);
    return [
      `Average rating: ${fixedNumber(evidence.previous_average_rating)} → ${fixedNumber(evidence.average_rating)} (${ratingChange > 0 ? "+" : ""}${ratingChange.toFixed(2)})`,
      `1–2 star share: ${fixedNumber(evidence.previous_low_rating_ratio)}% → ${fixedNumber(evidence.low_rating_ratio)}% (${ratioChange > 0 ? "+" : ""}${ratioChange.toFixed(2)}pp)`,
      `${numberFormatter.format(finiteNumber(evidence.review_count))} reviews`,
    ];
  }
  if (issue.issue_type === "support_ticket_backlog") {
    return [
      `${numberFormatter.format(finiteNumber(evidence.unresolved_high_priority_count))} unresolved high-priority tickets`,
      `Oldest ticket open ${numberFormatter.format(finiteNumber(evidence.oldest_open_days))} days`,
      `Data through ${evidence.data_through || "latest available date"}`,
    ];
  }
  return genericEvidence(evidence);
}

function candidatePromptText(value, maxLength = 160) {
  const text = String(value ?? "").replace(/\s+/g, " ").trim();
  return text.length <= maxLength
    ? text
    : `${text.slice(0, Math.max(0, maxLength - 3)).trimEnd()}...`;
}

function candidateIssueRepresentativeLines(issue) {
  const evidence = issue && typeof issue.evidence === "object" ? issue.evidence : {};
  if (issue?.issue_type === "inventory_replenishment_risk") {
    const items = Array.isArray(evidence.representative_items)
      ? evidence.representative_items.slice(0, 3)
      : [];
    return items
      .filter((item) => item && typeof item === "object")
      .map((item) => {
        const name = candidatePromptText(item.product_name || "Unknown product", 100);
        const location = candidatePromptText(item.store_location || "Unknown location", 80);
        return `Representative item: ${name} at ${location}, stock ${numberFormatter.format(finiteNumber(item.stock_quantity))}, reorder level ${numberFormatter.format(finiteNumber(item.reorder_level))}`;
      });
  }
  if (issue?.issue_type === "campaign_inefficiency") {
    const campaigns = Array.isArray(evidence.representative_campaigns)
      ? evidence.representative_campaigns.slice(0, 3)
      : [];
    return campaigns
      .filter((campaign) => campaign && typeof campaign === "object")
      .map((campaign) => {
        const name = candidatePromptText(
          campaign.campaign_name || campaign.campaign_id || "Unknown campaign",
          120,
        );
        return `Representative campaign: ${name}, reported lifecycle ROI ${fixedNumber(campaign.reported_roi)}%`;
      });
  }
  if (issue?.issue_type === "support_ticket_backlog") {
    const tickets = Array.isArray(evidence.representative_tickets)
      ? evidence.representative_tickets.slice(0, 3)
      : [];
    return tickets
      .filter((ticket) => ticket && typeof ticket === "object")
      .map((ticket) => {
        const category = candidatePromptText(ticket.issue_category || "Support request", 120);
        return `Representative ticket: ${category}, open ${numberFormatter.format(finiteNumber(ticket.open_days))} days`;
      });
  }
  return [];
}

function buildCandidateIssuePrompt(issue) {
  if (!issue || typeof issue !== "object" || Array.isArray(issue)) return "";

  const scope = issue.scope && typeof issue.scope === "object" ? issue.scope : {};
  const period = issue.period && typeof issue.period === "object" ? issue.period : {};
  const title = candidatePromptText(issue.title || issue.issue_type || "Business risk", 160);
  const severity = candidatePromptText(issue.severity || "unknown", 20).toUpperCase();
  const scopeType = scope.type === "company" ? "company scope" : scope.type === "store" ? "store scope" : "current scope";
  const storeSuffix = scope.type === "store" && scope.store_id
    ? ` (store ${candidatePromptText(scope.store_id, 60)})`
    : "";
  const scopeLine = `${candidatePromptText(issueScopeLabel(issue), 160)} — ${scopeType}${storeSuffix}`;
  const periodLine = period.snapshot_date
    ? `Latest available inventory snapshot on ${candidatePromptText(period.snapshot_date, 40)}`
    : period.month
      ? `Operating month ${candidatePromptText(period.month, 40)}`
      : period.data_through
        ? `Data through ${candidatePromptText(period.data_through, 40)}`
        : candidatePromptText(issuePeriodLabel(issue), 160);
  const evidenceLines = [
    ...issueEvidenceLines(issue).slice(0, 4),
    ...candidateIssueRepresentativeLines(issue),
  ].slice(0, 7).map((line) => candidatePromptText(line, 240));
  const inventoryCaution = period.snapshot_date
    ? "Inventory evidence is from the latest available snapshot. Do not interpret this snapshot as the selected financial operating month or as a proven cause of historical financial performance."
    : "";

  const buildPrompt = () => [
    "Investigate this newly selected dashboard risk.",
    "",
    `Risk: ${title}`,
    `Severity: ${severity}`,
    `Scope: ${scopeLine}`,
    `Period: ${periodLine}`,
    "",
    "Confirmed deterministic evidence:",
    ...evidenceLines.map((line) => `- ${line}`),
    ...(inventoryCaution ? ["", inventoryCaution] : []),
    "",
    "Please investigate using available business data and tools.",
    "",
    "Explain:",
    "1. What happened?",
    "2. What may explain it?",
    "3. What should be investigated or done next?",
    "",
    "Treat the evidence above as confirmed deterministic data.",
    "Clearly distinguish hypotheses from established facts.",
    "Do not present inferred causes as confirmed facts.",
  ].join("\n");

  let prompt = buildPrompt();
  while (prompt.length > 2000 && evidenceLines.length > 1) {
    evidenceLines.pop();
    prompt = buildPrompt();
  }
  return prompt;
}

function candidateIssueAskButton(issue, issueIndex) {
  if (!issue || typeof issue !== "object" || !Number.isInteger(issueIndex) || issueIndex < 0) {
    return "";
  }
  const title = issue.title || issue.issue_type || "business risk";
  return `<button class="risk-ask-agent-button" type="button" data-ask-agent data-issue-index="${issueIndex}" aria-label="Ask Agent to investigate ${escapeHtml(title)}"${state.chatController ? " disabled" : ""}>Ask Agent</button>`;
}

function setRiskAskAgentButtonsDisabled(disabled) {
  [elements.businessRiskList, elements.inventoryRiskSummary].forEach((container) => {
    container?.querySelectorAll("[data-ask-agent]").forEach((button) => {
      button.disabled = Boolean(disabled);
    });
  });
}

function candidateIssueFromElement(element) {
  const rawIndex = String(element?.dataset?.issueIndex ?? "");
  if (!/^\d+$/.test(rawIndex)) return null;
  const issueIndex = Number(rawIndex);
  if (!Number.isSafeInteger(issueIndex)) return null;
  const issue = state.candidateIssues[issueIndex];
  return issue && typeof issue === "object" ? issue : null;
}

async function askAgentAboutIssue(issue) {
  if (!issue || typeof issue !== "object" || state.chatController) return;
  const prompt = buildCandidateIssuePrompt(issue);
  if (!prompt) return;

  setRiskAskAgentButtonsDisabled(true);
  setAssistantOpen(true);
  try {
    await submitChat(prompt, { abortExisting: false });
  } finally {
    if (!state.chatController) setRiskAskAgentButtonsDisabled(false);
  }
}

function renderDetectedRisks(candidateIssues) {
  state.candidateIssues = candidateIssues;
  const indexedIssues = candidateIssues.map((issue, issueIndex) => ({ issue, issueIndex }));
  const hasInventoryIssue = indexedIssues.some(
    ({ issue }) => issue.issue_type === "inventory_replenishment_risk",
  );
  const visibleIssues = indexedIssues.filter(
    ({ issue }) => issue.issue_type !== "inventory_replenishment_risk",
  );
  elements.businessRiskCount.className = candidateIssues.length
    ? "alert-badge"
    : "soft-badge";
  elements.businessRiskCount.textContent = candidateIssues.length
    ? `${candidateIssues.length} total ${candidateIssues.length === 1 ? "risk" : "risks"}`
    : "No material risks";

  if (visibleIssues.length === 0) {
    if (hasInventoryIssue) {
      elements.businessRiskList.hidden = true;
      elements.businessRiskList.replaceChildren();
      return;
    }
    elements.businessRiskList.hidden = false;
    renderEmpty(
      elements.businessRiskList,
      "No material business risks detected for the selected period.",
    );
    return;
  }

  elements.businessRiskList.hidden = false;
  elements.businessRiskList.className = "risk-list";
  elements.businessRiskList.innerHTML = visibleIssues
    .map(({ issue, issueIndex }) => {
      const severity = issue.severity === "high" ? "high" : "medium";
      const supportButton = issue.issue_type === "support_ticket_backlog"
        ? `<button class="risk-details-button" type="button" data-support-risk>View support tickets</button>`
        : "";
      return `
        <article class="risk-card ${severity}${issue.issue_type === "support_ticket_backlog" ? " risk-card-clickable" : ""}" data-issue-index="${issueIndex}" ${issue.issue_type === "support_ticket_backlog" ? "tabindex=\"0\" data-support-risk-card" : ""}>
          <div class="risk-card-header">
            <span class="severity-badge ${severity}">${escapeHtml(severity.toUpperCase())}</span>
            <span class="risk-context">${escapeHtml(issueContext(issue))}</span>
          </div>
          <strong class="risk-title">${escapeHtml(issue.title || issue.issue_type || "Business risk")}</strong>
          <div class="risk-evidence">
            ${issueEvidenceLines(issue)
              .map((line) => `<span>${escapeHtml(line)}</span>`)
              .join("")}
          </div>
          <div class="risk-card-actions">
            ${issue.issue_type === "customer_experience_deterioration"
              ? `<a class="review-investigate" href="#product-performance" data-review-investigate>See products and customer comments</a>`
              : ""}
            ${supportButton}
            ${candidateIssueAskButton(issue, issueIndex)}
          </div>
        </article>
      `;
    })
    .join("");
}

function expandSupportTicketCard(card, issue, issueIndex) {
  const tickets = Array.isArray(issue?.evidence?.representative_tickets)
    ? issue.evidence.representative_tickets
    : [];
  card.classList.add("risk-card-expanded");
  card.innerHTML = `
    <div class="risk-card-header">
      <div class="support-ticket-expanded-title">
        <span class="severity-badge high">HIGH</span>
        <strong>${escapeHtml(issue.title || "High-priority support backlog")}</strong>
      </div>
      <button class="risk-details-button" type="button" data-support-risk-collapse>Collapse</button>
    </div>
    <div class="support-ticket-inline-list">
      ${tickets.length
    ? tickets.map((ticket) => `
      <article class="support-ticket-item">
        <div class="support-ticket-item-header">
          <strong>${escapeHtml(ticket.issue_category || "Support request")}</strong>
          <span>${escapeHtml(ticket.resolution_status || "unknown")}</span>
        </div>
        <div class="support-ticket-item-meta">
          <span>Submitted ${escapeHtml(ticket.submission_date || "—")}</span>
          <span>${numberFormatter.format(finiteNumber(ticket.open_days))} days open</span>
        </div>
        ${ticket.notes ? `<p>${escapeHtml(ticket.notes)}</p>` : ""}
      </article>
    `).join("")
    : `<p class="loading-copy">No representative ticket details available.</p>`}
    </div>
    <div class="risk-card-actions">
      ${candidateIssueAskButton(issue, issueIndex)}
    </div>
  `;
}

function renderInventorySection(inventory, inventoryIssue, inventoryIssueIndex) {
  const criticalCount = finiteNumber(inventory.critical_count);
  const additionalCount = finiteNumber(inventory.additional_reorder_count);
  const affectedCount = criticalCount + additionalCount;
  const totalCount = finiteNumber(inventory.total_inventory_count);
  const affectedRatio = finiteNumber(inventory.affected_ratio);
  const topItems = Array.isArray(inventory.top_items) ? inventory.top_items : [];

  if (inventoryIssue) {
    const severity = inventoryIssue.severity === "high" ? "high" : "medium";
    elements.inventoryRiskSummary.className = `risk-card ${severity} inventory-risk-card`;
    elements.inventoryRiskSummary.dataset.issueIndex = String(inventoryIssueIndex);
    elements.inventoryRiskSummary.innerHTML = `
      <div class="risk-card-header">
        <span class="severity-badge ${severity}">${escapeHtml(severity.toUpperCase())}</span>
        <span class="risk-context">${escapeHtml(issueContext(inventoryIssue))}</span>
      </div>
      <strong class="risk-title">${escapeHtml(inventoryIssue.title || "Inventory replenishment risk")}</strong>
      <div class="inventory-risk-metrics">
        <span><strong>${numberFormatter.format(affectedCount)} / ${numberFormatter.format(totalCount)}</strong> records</span>
        <span><strong>${fixedNumber(affectedRatio)}%</strong> affected</span>
        <span><strong>${numberFormatter.format(criticalCount)}</strong> critical</span>
      </div>
      <div class="risk-card-actions">
        ${candidateIssueAskButton(inventoryIssue, inventoryIssueIndex)}
      </div>
    `;
  } else if (affectedCount > 0) {
    elements.inventoryRiskSummary.className = "inventory-risk-summary";
    delete elements.inventoryRiskSummary.dataset.issueIndex;
    elements.inventoryRiskSummary.innerHTML = `
      <div class="inventory-replenishment-copy">
        <strong>${numberFormatter.format(affectedCount)} items need replenishment</strong>
        <span>${fixedNumber(affectedRatio)}% affected · No portfolio-level inventory risk detected</span>
      </div>
    `;
  } else {
    elements.inventoryRiskSummary.className = "inventory-risk-summary";
    delete elements.inventoryRiskSummary.dataset.issueIndex;
    elements.inventoryRiskSummary.innerHTML = `
      <div class="inventory-replenishment-copy">
        <strong>No inventory replenishment items detected</strong>
        <span>${numberFormatter.format(totalCount)} inventory records checked</span>
      </div>
    `;
  }

  if (affectedCount === 0 || topItems.length === 0) {
    renderEmpty(elements.inventoryList, "No inventory replenishment items detected.");
    return;
  }

  elements.inventoryList.className = "compact-list";
  elements.inventoryList.innerHTML = `
    <p class="inventory-list-label">Top affected items</p>
    ${topItems
      .map(
        (item) => `
          <article class="inventory-row">
            <i class="severity-dot ${escapeHtml(item.severity)}" aria-hidden="true"></i>
            <div>
              <span class="row-title">${escapeHtml(item.product_name || "Unknown product")}</span>
              <span class="row-subtitle">${escapeHtml(item.store_location || "Unknown location")} · ${escapeHtml({ critical: "Critical", high: "High", warning: "Warning" }[item.severity] || item.severity || "Needs replenishment")}</span>
            </div>
            <span class="stock-value">
              <strong>Stock: ${numberFormatter.format(finiteNumber(item.stock_quantity))}</strong>
              Reorder level ${numberFormatter.format(finiteNumber(item.reorder_level))}
            </span>
          </article>
        `,
      )
      .join("")}
  `;
}

function renderBusinessActionCenter(data, candidateIssues) {
  const actionCenter = data && typeof data === "object" ? data : {};
  const issues = Array.isArray(candidateIssues)
    ? candidateIssues.filter((issue) => issue && typeof issue === "object")
    : [];
  const inventoryIssueIndex = issues.findIndex(
    (issue) => issue.issue_type === "inventory_replenishment_risk",
  );
  const inventoryIssue = inventoryIssueIndex >= 0 ? issues[inventoryIssueIndex] : null;

  renderDetectedRisks(issues);
  renderInventorySection(
    actionCenter.inventory || {},
    inventoryIssue,
    inventoryIssueIndex,
  );
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
  if (!state.sharedDateRange.start && data?.period) {
    setSharedDateRange(data.period.start_date || "", data.period.end_date || "");
  }
  renderProductTab();
  const periodLabel = `${formatShortDate(data.period.start_date, true)} – ${formatShortDate(data.period.end_date, true)}`;
  elements.productRevenuePeriod.textContent = periodLabel;
  elements.productCategoryPeriod.textContent = periodLabel;
  renderProductRevenueTrend(data.revenue_trend);
  renderCategoryShare(elements.productCategoryChart, data.category_share);
}

function setSharedDateRange(start, end) {
  state.sharedDateRange = { start, end };
  state.productDateRange = { start, end };
  state.campaignDateRange = { start, end };
  elements.productStartDate.value = start;
  elements.productEndDate.value = end;
  elements.campaignStartDate.value = start;
  elements.campaignEndDate.value = end;
}

function exclusiveDateForRange(end) {
  const exclusiveEnd = new Date(`${end}T00:00:00Z`);
  exclusiveEnd.setUTCDate(exclusiveEnd.getUTCDate() + 1);
  return exclusiveEnd.toISOString().slice(0, 10);
}

async function applySharedDateRange(start, end, source) {
  if (!start || !end || start > end) {
    showGlobalError("Choose a valid shared date range.");
    return;
  }
  const exclusiveEnd = exclusiveDateForRange(end);
  const productQuery = new URLSearchParams({
    start_date: start,
    end_date: exclusiveEnd,
  });
  if (state.storeId) productQuery.set("store_id", state.storeId);
  const reviewQuery = new URLSearchParams({ start_date: start, end_date: exclusiveEnd });
  const campaignQuery = new URLSearchParams({ start_date: start, end_date: exclusiveEnd });
  elements.productDateApply.disabled = true;
  elements.campaignDateApply.disabled = true;
  if (state.reviewOverviewController) state.reviewOverviewController.abort();
  clearGlobalError();
  try {
    const [productData, reviewData, campaignData] = await Promise.all([
      fetchJson(`/api/dashboard/product-performance?${productQuery}`),
      fetchJson(`/api/dashboard/product-reviews?${reviewQuery}`),
      fetchJson(`/api/dashboard/marketing-performance?${campaignQuery}`),
    ]);
    setSharedDateRange(start, end);
    renderProducts(productData);
    renderReviewOverview(reviewData);
    renderMarketing(campaignData);
  } catch (error) {
    showGlobalError(`${source} shared date range failed: ${error.message}`);
  } finally {
    elements.productDateApply.disabled = false;
    elements.campaignDateApply.disabled = false;
  }
}

function applyProductDateRange() {
  return applySharedDateRange(
    elements.productStartDate.value,
    elements.productEndDate.value,
    "Product",
  );
}

function productChartMetric(tab, item) {
  if (tab === "best_sellers") return { value: finiteNumber(item.net_units), label: `${numberFormatter.format(finiteNumber(item.net_units))} units` };
  if (tab === "high_return_rate") return { value: finiteNumber(item.return_rate_percent), label: `${fixedNumber(item.return_rate_percent, 1)}%` };
  return { value: finiteNumber(item.average_rating), label: `${fixedNumber(item.average_rating, 2)} / 5` };
}

function renderProductInsights(items) {
  const tab = state.activeProductTab;
  elements.productChartTitle.textContent = `${elements.productTabs.querySelector(".tab.active")?.textContent || "Products"} comparison`;
  elements.productTableNote.textContent = tab === "top_rated" || tab === "lowest_rated"
    ? "Company-wide lifetime reviews"
    : "Selected sales month and store scope";

  if (!items.length) {
    renderEmpty(elements.productChart, "No products to compare");
    renderEmpty(elements.productTable, "No product details available");
    return;
  }

  const max = tab === "top_rated" || tab === "lowest_rated"
    ? 5 : Math.max(1, ...items.map((item) => productChartMetric(tab, item).value));
  elements.productChart.className = "comparison-chart";
  elements.productChart.innerHTML = items.map((item) => {
    const metric = productChartMetric(tab, item);
    const width = Math.max(0, Math.min(100, metric.value / max * 100));
    return `<div class="comparison-row">
      <span class="comparison-name" title="${escapeHtml(item.product_name)}">${escapeHtml(item.product_name)}</span>
      <span class="comparison-track"><span class="comparison-fill" style="width:${width}%"></span></span>
      <strong>${escapeHtml(metric.label)}</strong>
    </div>`;
  }).join("");

  const columnLabels = tab === "best_sellers"
    ? ["Net units", "Revenue", "Est. gross profit"]
    : tab === "high_return_rate"
      ? ["Return rate", "Returned / sold", "Revenue"]
      : ["Rating", "Reviews", "Scope"];
  const cells = (item) => tab === "best_sellers"
    ? [numberFormatter.format(finiteNumber(item.net_units)), formatMoney(item.refund_adjusted_revenue), formatMoney(item.estimated_gross_profit)]
    : tab === "high_return_rate"
      ? [`${fixedNumber(item.return_rate_percent, 1)}%`, `${numberFormatter.format(finiteNumber(item.returned_units))} / ${numberFormatter.format(finiteNumber(item.sold_units))}`, formatMoney(item.refund_adjusted_revenue)]
      : [`${fixedNumber(item.average_rating, 2)} / 5`, numberFormatter.format(finiteNumber(item.review_count)), "Company-wide"];
  elements.productTable.className = "table-scroll";
  elements.productTable.innerHTML = `<table class="insight-table">
    <thead><tr><th scope="col">Product</th><th scope="col">Category</th>${columnLabels.map((label) => `<th scope="col">${label}</th>`).join("")}</tr></thead>
    <tbody>${items.map((item) => `<tr><th scope="row"><button class="review-product-link" type="button" data-review-product-id="${escapeHtml(item.product_id)}">${escapeHtml(item.product_name)}</button></th><td>${escapeHtml(item.product_category)}</td>${cells(item).map((value) => `<td>${escapeHtml(value)}</td>`).join("")}</tr>`).join("")}</tbody>
  </table>`;
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

  renderProductInsights(items);

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
              <button class="review-product-link row-title" type="button" data-review-product-id="${escapeHtml(item.product_id)}">${escapeHtml(item.product_name)}</button>
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

function renderReviewOverview(data) {
  state.reviewProducts = data.products;
  const products = data.products.filter((product) => product.review_count > 0);
  const totalReviews = products.reduce((sum, product) => sum + Number(product.review_count || 0), 0);
  const lowReviews = products.reduce((sum, product) => sum + Number(product.low_rating_count || 0), 0);
  const weightedRating = products.reduce((sum, product) => sum + Number(product.average_rating || 0) * Number(product.review_count || 0), 0);
  const highReviews = products.reduce((sum, product) => sum + Number(product.high_rating_count || 0), 0);
  elements.reviewSummaryMetrics.innerHTML = `
    <div><strong>${numberFormatter.format(totalReviews)}</strong><span>Total reviews</span></div>
    <div><strong>${totalReviews ? (weightedRating / totalReviews).toFixed(2) : "—"}</strong><span>Average rating</span></div>
    <div><strong>${totalReviews ? `${((lowReviews / totalReviews) * 100).toFixed(1)}%` : "—"}</strong><span>Low rating share</span></div>
    <div><strong>${totalReviews ? `${((highReviews / totalReviews) * 100).toFixed(1)}%` : "—"}</strong><span>High rating share</span></div>`;
  const high = [...products].sort((a, b) => Number(b.average_rating || 0) - Number(a.average_rating || 0) || Number(b.review_count) - Number(a.review_count)).slice(0, 5);
  const low = [...products].sort((a, b) => Number(a.average_rating || 0) - Number(b.average_rating || 0) || Number(b.review_count) - Number(a.review_count)).slice(0, 5);
  const ratingRows = (items) => items.length ? items.map((product) => `<div class="review-rating-row"><span><strong>${escapeHtml(product.product_name)}</strong><small>${escapeHtml(product.product_category)} · ${product.review_count} reviews</small></span><b>★ ${Number(product.average_rating || 0).toFixed(2)}</b></div>`).join("") : `<p class="review-empty">No reviews in this range.</p>`;
  elements.reviewHighList.innerHTML = ratingRows(high);
  elements.reviewLowList.innerHTML = ratingRows(low);
  const hotspots = products.filter((product) => product.low_rating_count > 0).slice(0, 5);
  const rangeLabel = data.start_date && data.end_date
    ? `${formatShortDate(data.start_date)} – ${formatShortDate(data.end_date)}`
    : formatMonth(data.month);
  elements.reviewScopeNote.textContent = `${rangeLabel} · company-wide (reviews have no store field)`;
  if (elements.reviewHotspotList) {
    if (!hotspots.length) {
      renderEmpty(elements.reviewHotspotList, "No 1–2 star product reviews in the selected range.");
    } else {
      elements.reviewHotspotList.className = "review-hotspot-list";
      elements.reviewHotspotList.innerHTML = hotspots.map((product) => `
        <button class="review-hotspot" type="button" data-review-product-id="${escapeHtml(product.product_id)}">
          <span><strong>${escapeHtml(product.product_name)}</strong><small>${escapeHtml(product.product_category)}</small></span>
          <span>${numberFormatter.format(product.low_rating_count)} low of ${numberFormatter.format(product.review_count)} reviews <span aria-hidden="true">→</span></span>
        </button>
      `).join("");
    }
  }

  const selected = data.products.some((product) => product.product_id === state.reviewSelectedProductId)
    ? state.reviewSelectedProductId
    : (data.products.find((product) => product.low_rating_count > 0)
      || data.products.find((product) => product.review_count > 0))?.product_id || "";
  state.reviewSelectedProductId = selected;
  elements.reviewProductSelect.replaceChildren();
  if (!data.products.length) {
    elements.reviewProductSelect.add(new Option("No products available", ""));
    elements.reviewProductSelect.disabled = true;
  } else {
    elements.reviewProductSelect.add(new Option("Choose a product", ""));
    data.products.forEach((product) => {
      elements.reviewProductSelect.add(new Option(
        `${product.product_name} · ${product.product_category}`,
        product.product_id,
      ));
    });
    elements.reviewProductSelect.disabled = false;
  }
  elements.reviewProductSelect.value = selected;
  loadProductReviews();
}

async function loadReviewOverview(month, range = null) {
  if (state.reviewOverviewController) state.reviewOverviewController.abort();
  const controller = new AbortController();
  state.reviewOverviewController = controller;
  if (elements.reviewHotspotList) {
    elements.reviewHotspotList.className = "review-hotspot-list loading-copy";
    elements.reviewHotspotList.textContent = "Loading product reviews…";
  }
  try {
    const query = range
      ? `start_date=${encodeURIComponent(range.start)}&end_date=${encodeURIComponent(range.end)}`
      : `month=${encodeURIComponent(month)}`;
    const data = await fetchJson(`/api/dashboard/product-reviews?${query}`, {
      signal: controller.signal,
    });
    if (controller.signal.aborted) return;
    renderReviewOverview(data);
  } catch (error) {
    if (controller.signal.aborted) return;
    if (elements.reviewHotspotList) renderEmpty(elements.reviewHotspotList, "Product reviews are temporarily unavailable.");
    renderEmpty(elements.reviewComments, "Could not load customer reviews.");
  }
}

async function loadProductReviews() {
  if (state.reviewDetailController) state.reviewDetailController.abort();
  const productId = state.reviewSelectedProductId;
  const product = state.reviewProducts.find((item) => item.product_id === productId);
  if (!product || (!state.month && !state.productDateRange.start)) {
    elements.reviewProductSummary.textContent = "Choose a product to see its reviews.";
    elements.reviewComments.replaceChildren();
    return;
  }

  elements.reviewProductSummary.textContent =
    `${numberFormatter.format(product.low_rating_count)} of ${numberFormatter.format(product.review_count)} reviews rated 1–2 stars in the selected range.`;
  elements.reviewComments.className = "review-comments loading-copy";
  elements.reviewComments.textContent = "Loading customer comments…";
  const controller = new AbortController();
  state.reviewDetailController = controller;
  const lowOnly = elements.reviewRatingFilter.value === "low";
  const month = state.month;
  const range = state.productDateRange.start
    ? `start_date=${encodeURIComponent(state.productDateRange.start)}&end_date=${encodeURIComponent(state.productDateRange.end)}`
    : `month=${encodeURIComponent(month)}`;
  try {
    const data = await fetchJson(
      `/api/dashboard/products/${encodeURIComponent(productId)}/reviews?${range}&low_only=${lowOnly}`,
      { signal: controller.signal },
    );
    if (controller.signal.aborted || state.reviewSelectedProductId !== productId || state.month !== month) return;
    if (!data.reviews.length) {
      renderEmpty(elements.reviewComments, lowOnly
        ? "No 1–2 star comments for this product this month. Try All ratings."
        : "No reviews for this product this month.");
      return;
    }
    elements.reviewComments.className = "review-comments";
    elements.reviewComments.innerHTML = data.reviews.map((review) => `
      <article class="review-comment">
        <div class="review-comment-meta"><strong aria-label="${review.rating} out of 5 stars">${"★".repeat(review.rating)}${"☆".repeat(5 - review.rating)}</strong><span>${escapeHtml(formatShortDate(review.review_date, true))}</span></div>
        <strong>${escapeHtml(review.review_title || "Customer review")}</strong>
        <p>${escapeHtml(review.review_text || "No written comment provided.")}</p>
      </article>
    `).join("");
  } catch (error) {
    if (controller.signal.aborted) return;
    renderEmpty(elements.reviewComments, "Could not load customer comments.");
  }
}

function openProductReviews(productId) {
  if (productId) state.reviewSelectedProductId = productId;
  elements.reviewRatingFilter.value = "low";
  elements.reviewProductSelect.value = state.reviewSelectedProductId;
  loadProductReviews();
  window.location.hash = "product-performance";
  window.setTimeout(() => {
    elements.productReviews.scrollIntoView({ behavior: "smooth", block: "start" });
  }, 80);
}

function renderCampaignInsights(campaigns) {
  if (!campaigns.length) {
    renderEmpty(elements.campaignChart, "No campaigns to compare");
    renderEmpty(elements.campaignTable, "No campaign details available");
    return;
  }

  const maxAbsRoi = Math.max(1, ...campaigns.map((campaign) => Math.abs(finiteNumber(campaign.roi))));
  elements.campaignChart.className = "comparison-chart";
  elements.campaignChart.innerHTML = campaigns.map((campaign) => {
    const roi = finiteNumber(campaign.roi);
    const width = Math.min(50, Math.abs(roi) / maxAbsRoi * 50);
    return `<div class="comparison-row">
      <span class="comparison-name" title="${escapeHtml(campaign.campaign_name)}">${escapeHtml(campaign.campaign_name)}</span>
      <span class="roi-track"><span class="roi-fill ${roi < 0 ? "negative" : "positive"}" style="width:${width}%;${roi < 0 ? `left:${50 - width}%` : "left:50%"}"></span></span>
      <strong class="${roi < 0 ? "roi-negative" : "roi-positive"}">${roi > 0 ? "+" : ""}${escapeHtml(roi.toFixed(0))}%</strong>
    </div>`;
  }).join("");

  elements.campaignTable.className = "table-scroll";
  elements.campaignTable.innerHTML = `<table class="insight-table"><thead><tr><th scope="col">Campaign</th><th scope="col">Type</th><th scope="col">Budget</th><th scope="col">Conversions</th><th scope="col">Conversion rate</th><th scope="col">Reported ROI</th><th scope="col">Dates</th></tr></thead>
    <tbody>${campaigns.map((campaign) => `<tr><th scope="row"><button class="campaign-select" type="button" data-campaign-id="${escapeHtml(campaign.campaign_id)}" aria-controls="campaign-detail" aria-expanded="false">${escapeHtml(campaign.campaign_name)}</button></th><td>${escapeHtml(campaign.campaign_type)}</td><td>${escapeHtml(formatMoney(campaign.budget))}</td><td>${escapeHtml(numberFormatter.format(finiteNumber(campaign.conversions)))}</td><td>${escapeHtml(fixedNumber(campaign.conversion_rate, 1))}%</td><td class="${finiteNumber(campaign.roi) < 0 ? "roi-negative" : "roi-positive"}">${finiteNumber(campaign.roi) > 0 ? "+" : ""}${escapeHtml(fixedNumber(campaign.roi, 0))}%</td><td>${escapeHtml(campaign.start_date)} – ${escapeHtml(campaign.end_date)}</td></tr>`).join("")}</tbody></table>`;
}

function renderMarketing(data) {
  if (!state.sharedDateRange.start && data?.period) {
    setSharedDateRange(data.period.start_date || "", data.period.end_date || "");
  }
  state.campaigns = data.campaigns;
  renderCampaignInsights(data.campaigns);

  if (!data.campaigns.length) {
    state.selectedCampaignId = "";
    elements.campaignDetail.hidden = true;
    renderEmpty(elements.campaignList, "No campaigns overlap the selected range");
    return;
  }

  elements.campaignList.className = "campaign-list";
  elements.campaignList.innerHTML = data.campaigns
    .map((campaign) => {
      const roi = Number(campaign.roi) || 0;
      return `
        <article class="campaign-row">
          <div>
            <button class="campaign-select row-title" type="button" data-campaign-id="${escapeHtml(campaign.campaign_id)}" aria-controls="campaign-detail" aria-expanded="false">${escapeHtml(campaign.campaign_name)}</button>
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
  showCampaignDetail(state.selectedCampaignId);
}

function applyCampaignDateRange() {
  return applySharedDateRange(
    elements.campaignStartDate.value,
    elements.campaignEndDate.value,
    "Campaign",
  );
}

function showCampaignDetail(campaignId, scrollIntoView = false) {
  const campaign = state.campaigns.find((item) => String(item.campaign_id) === campaignId);
  state.selectedCampaignId = campaign ? campaignId : "";
  elements.campaignPanel.querySelectorAll("[data-campaign-id]").forEach((button) => {
    const isSelected = Boolean(campaign) && button.dataset.campaignId === campaignId;
    button.setAttribute("aria-expanded", String(isSelected));
    button.classList.toggle("active", isSelected);
  });
  elements.campaignDetail.hidden = !campaign;
  if (!campaign) return;

  const start = formatShortDate(campaign.start_date, true);
  const end = formatShortDate(campaign.end_date, true);
  elements.campaignDetailTitle.textContent = campaign.campaign_name;
  elements.campaignDetailStart.textContent = start;
  elements.campaignDetailEnd.textContent = end;
  elements.campaignDetailCount.textContent = numberFormatter.format(
    finiteNumber(campaign.transactions_during_campaign),
  );
  elements.campaignDetailAxisStart.textContent = start;
  elements.campaignDetailAxisEnd.textContent = end;
  if (scrollIntoView) {
    window.requestAnimationFrame(() => {
      elements.campaignDetail.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
  }
}

function panelError(panel, message) {
  if (panel === "finance") {
    elements.financePeriod.textContent = "—";
    elements.financeMetrics.innerHTML = "";
    renderEmpty(elements.financeMetrics, message);
    renderEmpty(elements.financeChart, "The trend chart is temporarily unavailable");
    renderEmpty(elements.overviewCategoryChart, "Category share is temporarily unavailable");
  } else if (panel === "action") {
    elements.businessRiskCount.className = "soft-badge";
    elements.businessRiskCount.textContent = "Unavailable";
    renderEmpty(elements.businessRiskList, message);
    renderEmpty(elements.inventoryRiskSummary, "Inventory summary is temporarily unavailable");
    renderEmpty(elements.inventoryList, "Inventory data is temporarily unavailable");
  } else if (panel === "products") {
    state.productData = null;
    renderEmpty(elements.productList, message);
    renderEmpty(elements.productChart, message);
    renderEmpty(elements.productTable, message);
    renderEmpty(elements.productRevenueChart, message);
    renderEmpty(elements.productCategoryChart, message);
  } else if (panel === "marketing") {
    state.campaigns = [];
    state.selectedCampaignId = "";
    elements.campaignDetail.hidden = true;
    renderEmpty(elements.campaignList, message);
    renderEmpty(elements.campaignChart, message);
    renderEmpty(elements.campaignTable, message);
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
    renderBusinessActionCenter(
      data.result.action_center,
      Array.isArray(data.result.candidate_issues) ? data.result.candidate_issues : [],
    );
    renderProducts(data.result.products);
    renderMarketing(data.result.marketing);
    const initialReviewRange = state.sharedDateRange.start
      ? {
          start: state.sharedDateRange.start,
          end: exclusiveDateForRange(state.sharedDateRange.end),
        }
      : null;
    loadReviewOverview(state.month, initialReviewRange);

    setConnectionStatus("ok", "Database connected");
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
  }, appConfig.dashboardFilterDebounceMs);
}

elements.productTabs.addEventListener("click", (event) => {
  const button = event.target.closest("[data-tab]");
  if (!button) return;
  state.activeProductTab = button.dataset.tab;
  renderProductTab();
});

document.querySelector(".chart-view-toggle").addEventListener("click", (event) => {
  const button = event.target.closest("[data-finance-view]");
  if (!button || state.financeChartView === button.dataset.financeView) return;
  state.financeChartView = button.dataset.financeView;
  document.querySelectorAll("[data-finance-view]").forEach((option) => {
    option.setAttribute("aria-pressed", String(option === button));
  });
  renderFinanceChart(state.financeTrend);
});

elements.productDateApply.addEventListener("click", applyProductDateRange);
elements.campaignDateApply.addEventListener("click", applyCampaignDateRange);

document.querySelector("#product-performance").addEventListener("click", (event) => {
  const button = event.target.closest("[data-review-product-id]");
  if (button) openProductReviews(button.dataset.reviewProductId);
});

elements.reviewHotspotList?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-review-product-id]");
  if (button) openProductReviews(button.dataset.reviewProductId);
});

elements.businessRiskList.addEventListener("click", (event) => {
  const askButton = event.target.closest("[data-ask-agent]");
  if (askButton) {
    event.preventDefault();
    event.stopPropagation();
    const issue = candidateIssueFromElement(askButton);
    if (issue && !state.chatController) askAgentAboutIssue(issue);
    return;
  }
  if (event.target.closest("[data-support-risk-collapse]")) {
    renderDetectedRisks(state.candidateIssues);
    return;
  }
  const supportCard = event.target.closest("[data-support-risk-card]");
  if (supportCard) {
    const issue = candidateIssueFromElement(supportCard);
    const issueIndex = Number(supportCard.dataset.issueIndex);
    if (issue) expandSupportTicketCard(supportCard, issue, issueIndex);
    return;
  }
  if (event.target.closest("[data-review-investigate]")) {
    event.preventDefault();
    openProductReviews();
  }
});

elements.businessRiskList.addEventListener("keydown", (event) => {
  if (event.key !== "Enter" && event.key !== " ") return;
  if (event.target.closest("button, a")) return;
  const supportCard = event.target.closest("[data-support-risk-card]");
  if (!supportCard) return;
  event.preventDefault();
  const issue = candidateIssueFromElement(supportCard);
  const issueIndex = Number(supportCard.dataset.issueIndex);
  if (issue) expandSupportTicketCard(supportCard, issue, issueIndex);
});

elements.inventoryRiskSummary.addEventListener("click", (event) => {
  const askButton = event.target.closest("[data-ask-agent]");
  if (!askButton) return;
  event.preventDefault();
  const issue = candidateIssueFromElement(askButton);
  if (issue && !state.chatController) askAgentAboutIssue(issue);
});

elements.reviewProductSelect.addEventListener("change", () => {
  state.reviewSelectedProductId = elements.reviewProductSelect.value;
  loadProductReviews();
});

elements.reviewRatingFilter.addEventListener("change", loadProductReviews);

elements.campaignPanel.addEventListener("click", (event) => {
  const button = event.target.closest("[data-campaign-id]");
  if (!button || !elements.campaignPanel.contains(button)) return;
  showCampaignDetail(button.dataset.campaignId, true);
});

elements.storeFilter.addEventListener("change", () => {
  state.storeId = elements.storeFilter.value;
  updateFinanceStoreLabel();
  scheduleDashboardLoad();
});

elements.yearFilter.addEventListener("change", updateOperatingMonthFromFilters);
elements.monthFilter.addEventListener("change", updateOperatingMonthFromFilters);

elements.refreshButton.addEventListener("click", loadDashboard);

elements.financePeriodToggle.addEventListener("click", () => {
  const willOpen = elements.financeFilters.hidden;
  elements.financeFilters.hidden = !willOpen;
  elements.financePeriodToggle.setAttribute("aria-expanded", String(willOpen));
  if (willOpen && !elements.yearFilter.disabled) elements.yearFilter.focus();
});

elements.financeFilters.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  elements.financeFilters.hidden = true;
  elements.financePeriodToggle.setAttribute("aria-expanded", "false");
  elements.financePeriodToggle.focus();
});

elements.knowledgeOpen.addEventListener("click", () => {
  elements.knowledgeDialog.showModal();
  loadKnowledgeFiles();
});

elements.knowledgeClose.addEventListener("click", () => elements.knowledgeDialog.close());
elements.knowledgeDialog.addEventListener("close", () => elements.knowledgeOpen.focus());
elements.knowledgeDialog.addEventListener("click", (event) => {
  if (event.target !== elements.knowledgeDialog) return;
  const bounds = elements.knowledgeDialog.getBoundingClientRect();
  if (
    event.clientX < bounds.left || event.clientX > bounds.right ||
    event.clientY < bounds.top || event.clientY > bounds.bottom
  ) elements.knowledgeDialog.close();
});

function setAssistantOpen(isOpen) {
  if (!isOpen) setAssistantDocked(false);
  elements.assistantPanel.hidden = !isOpen;
  elements.assistantOpen.setAttribute("aria-expanded", String(isOpen));
  elements.assistantOpen.setAttribute(
    "aria-label",
    isOpen ? "Close business assistant" : "Open business assistant",
  );
  if (isOpen) {
    elements.chatInput.focus();
    window.requestAnimationFrame(() => {
      elements.chatConversation.scrollTop = elements.chatConversation.scrollHeight;
    });
  } else {
    elements.assistantOpen.focus();
  }
}

let assistantDockWidth = 520;

function assistantDockWidthBounds() {
  const viewportWidth = document.documentElement.clientWidth;
  const availableWidth = viewportWidth > 1100
    ? viewportWidth - (document.body.classList.contains("sidebar-collapsed") ? 0 : 244) - 320
    : viewportWidth - 16;
  const max = Math.max(280, Math.min(900, availableWidth));
  return { min: Math.min(320, max), max };
}

function setAssistantDockWidth(width) {
  const { min, max } = assistantDockWidthBounds();
  assistantDockWidth = Math.max(min, Math.min(max, Math.round(width)));
  document.body.style.setProperty("--assistant-dock-width", `${assistantDockWidth}px`);
  elements.assistantResizeHandle.setAttribute("aria-valuemin", String(min));
  elements.assistantResizeHandle.setAttribute("aria-valuemax", String(max));
  elements.assistantResizeHandle.setAttribute("aria-valuenow", String(assistantDockWidth));
}

function setAssistantDocked(isDocked) {
  document.body.classList.toggle("assistant-docked", isDocked);
  elements.assistantDockToggle.setAttribute("aria-pressed", String(isDocked));
  const label = isDocked ? "Shrink chat to floating window" : "Expand chat to side panel";
  elements.assistantDockToggle.setAttribute("aria-label", label);
  elements.assistantDockToggle.title = label;
  elements.assistantResizeHandle.tabIndex = isDocked ? 0 : -1;
  if (isDocked) setAssistantDockWidth(assistantDockWidth);
}

elements.assistantDockToggle.addEventListener("click", () => {
  setAssistantDocked(!document.body.classList.contains("assistant-docked"));
});

elements.assistantResizeHandle.addEventListener("pointerdown", (event) => {
  if (!document.body.classList.contains("assistant-docked")) return;
  event.preventDefault();
  elements.assistantResizeHandle.setPointerCapture(event.pointerId);
});

elements.assistantResizeHandle.addEventListener("pointermove", (event) => {
  if (elements.assistantResizeHandle.hasPointerCapture(event.pointerId)) {
    setAssistantDockWidth(document.documentElement.clientWidth - event.clientX);
  }
});

elements.assistantResizeHandle.addEventListener("pointerup", (event) => {
  if (elements.assistantResizeHandle.hasPointerCapture(event.pointerId)) {
    elements.assistantResizeHandle.releasePointerCapture(event.pointerId);
  }
});

elements.assistantResizeHandle.addEventListener("keydown", (event) => {
  if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
  event.preventDefault();
  setAssistantDockWidth(assistantDockWidth + (event.key === "ArrowLeft" ? 24 : -24));
});

window.addEventListener("resize", () => {
  if (document.body.classList.contains("assistant-docked")) setAssistantDockWidth(assistantDockWidth);
});

setAssistantDocked(false);

elements.assistantOpen.addEventListener("click", () => {
  setAssistantOpen(elements.assistantPanel.hidden);
});
elements.assistantClose.addEventListener("click", () => setAssistantOpen(false));
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !elements.assistantPanel.hidden && !elements.knowledgeDialog.open) {
    setAssistantOpen(false);
  }
});

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
  if (event.defaultPrevented || !elements.knowledgeDialog.open) return;
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
elements.chatHistoryToggle.addEventListener("click", async () => {
  const opening = elements.chatSessionHistory.hidden;
  elements.chatSessionHistory.hidden = !opening;
  elements.chatHistoryToggle.setAttribute("aria-expanded", String(opening));
  if (opening) {
    try { await loadChatSessions(); } catch (error) { showGlobalError(`Could not load chat history: ${error.message}`); }
  }
});
elements.chatSessionHistory.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-session-id]");
  if (!button) return;
  try { await openChatSession(button.dataset.sessionId); } catch (error) { showGlobalError(`Could not open chat: ${error.message}`); }
});
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
    }, appConfig.copyFeedbackMs);
  } catch (_error) {
    elements.chatCopyButton.textContent = "Copy failed";
  }
});

async function initialise() {
  initializeActivitySizing();
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
