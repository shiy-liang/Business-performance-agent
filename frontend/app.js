"use strict";

const state = {
  month: "",
  storeId: "",
  activeProductTab: "best_sellers",
  productData: null,
  runId: null,
  requestController: null,
  filterTimer: null,
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
  chatInput: document.querySelector("#chat-input"),
  chatResponse: document.querySelector("#chat-response"),
};

const moneyFormatter = new Intl.NumberFormat("zh-CN", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

const numberFormatter = new Intl.NumberFormat("zh-CN", {
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
  return `${year} 年 ${Number(monthNumber)} 月`;
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
    let detail = `请求失败（${response.status}）`;
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
      context: "已扣除本月完成退款",
    },
    {
      ...metrics.estimated_gross_profit,
      context: "基于已匹配商品成本",
    },
    {
      ...metrics.estimated_profit,
      context:
        data.scope.type === "company"
          ? "扣除经营费用与分摊推广预算"
          : "扣除该店经营费用",
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
    data.period.is_complete ? " · 完整月" : " · 数据未完整"
  }`;
  elements.salesDataThrough.textContent = data.period.sales_data_through;
  elements.scopeCaption.textContent = `${data.scope.label} · ${
    data.period.is_complete ? "完整自然月" : "部分月份"
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
    renderEmpty(elements.financeChart, "该范围暂无趋势数据");
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
      return `<text x="${x(index)}" y="${height - 9}" text-anchor="middle" fill="#66706a" font-size="9">${escapeHtml(item.month.slice(5))}月</text>`;
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
        `${item.month} 营收 ${formatMoney(item.refund_adjusted_revenue)}，毛利润 ${formatMoney(item.estimated_gross_profit)}`,
    )
    .join("；");

  elements.financeChart.className = "line-chart";
  elements.financeChart.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-labelledby="finance-chart-title finance-chart-desc">
      <title id="finance-chart-title">最近十二个月财务趋势</title>
      <desc id="finance-chart-desc">${escapeHtml(description)}</desc>
      ${grid}
      <line x1="${margin.left}" y1="${y(0)}" x2="${width - margin.right}" y2="${y(0)}" stroke="#aeb7b0" stroke-width="1" />
      <path d="${pathFor("refund_adjusted_revenue")}" fill="none" stroke="#167d5a" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />
      <path d="${pathFor("estimated_gross_profit")}" fill="none" stroke="#c7812c" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />
      ${circles("refund_adjusted_revenue", "#167d5a", "退款后营收")}
      ${circles("estimated_gross_profit", "#c7812c", "估算毛利润")}
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
    <span>项严重告急</span>
    <strong>${numberFormatter.format(inventory.additional_reorder_count)}</strong>
    <span>项需要补货</span>
  `;

  if (inventory.top_items.length === 0) {
    renderEmpty(elements.inventoryList, "当前范围没有库存告急项");
  } else {
    elements.inventoryList.className = "compact-list";
    elements.inventoryList.innerHTML = inventory.top_items
      .map(
        (item) => `
          <article class="inventory-row">
            <i class="severity-dot ${escapeHtml(item.severity)}" aria-hidden="true"></i>
            <div>
              <span class="row-title">${escapeHtml(item.product_name)}</span>
              <span class="row-subtitle">${escapeHtml(item.store_location)} · ${escapeHtml({ critical: "严重", high: "高风险", warning: "预警" }[item.severity] || item.severity)}</span>
            </div>
            <span class="stock-value">
              <strong>${numberFormatter.format(item.stock_quantity)}</strong>
              补货线 ${numberFormatter.format(item.reorder_level)}
            </span>
          </article>
        `,
      )
      .join("");
  }

  elements.ticketCount.textContent = `${numberFormatter.format(
    tickets.unresolved_high_priority_count,
  )} 条未解决`;

  if (tickets.oldest.length === 0) {
    renderEmpty(elements.ticketList, "当前没有未解决的高优先级工单");
  } else {
    elements.ticketList.className = "ticket-list";
    elements.ticketList.innerHTML = tickets.oldest
      .map(
        (ticket) => `
          <article class="ticket-row">
            <span class="age-box">
              <strong>${numberFormatter.format(ticket.open_days)}</strong>
              <small>天未解决</small>
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
  best_sellers: "按净销量排名 · 所选月份",
  top_rated: "按平均评分排名 · 全公司全周期评价",
  high_return_rate: "按所选月销售订单的完成退货率排名",
  lowest_rated: "按平均评分排名 · 全公司全周期评价",
};

function productMetrics(tab, item) {
  if (tab === "best_sellers") {
    return [
      [`${numberFormatter.format(item.net_units)} 件`, "净销量"],
      [formatMoney(item.refund_adjusted_revenue), "退款后营收"],
    ];
  }
  if (tab === "high_return_rate") {
    return [
      [`${Number(item.return_rate_percent).toFixed(1)}%`, "完成退货率"],
      [`${item.returned_units} / ${item.sold_units} 件`, "退货 / 销售"],
    ];
  }
  return [
    [`★ ${Number(item.average_rating).toFixed(2)}`, "平均评分"],
    [`${numberFormatter.format(item.review_count)} 条`, "有效评价"],
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
    renderEmpty(elements.productList, "该榜单暂无足够数据");
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
  )} 个活动`;

  if (!data.campaigns.length) {
    renderEmpty(elements.campaignList, "所选月份没有进行中的推广活动");
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
            <span class="row-subtitle">${escapeHtml(campaign.campaign_type)} · 预算 ${escapeHtml(formatMoney(campaign.budget))}</span>
          </div>
          <span aria-label="转化率 ${escapeHtml(campaign.conversion_rate)}%">
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
    renderEmpty(elements.financeChart, "趋势图暂时无法读取");
  } else if (panel === "action") {
    elements.ticketCount.textContent = "—";
    renderEmpty(elements.inventorySummary, message);
    renderEmpty(elements.inventoryList, "库存数据暂时无法读取");
    renderEmpty(elements.ticketList, "工单数据暂时无法读取");
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
  setConnectionStatus("loading", "正在生成经营分析");
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
    setConnectionStatus("ok", "Supabase 已连接");
  } catch (error) {
    if (!responseAccepted && isStale()) return;
    if (signal.aborted || state.requestController.signal !== signal) return;

    const message = error instanceof Error ? error.message : String(error);
    setConnectionStatus("error", "经营分析生成失败");
    showGlobalError(`经营分析生成失败：${message}`);
    panelError("finance", "财务数据暂时无法读取");
    panelError("action", "行动数据暂时无法读取");
    panelError("products", "商品榜单暂时无法读取");
    panelError("marketing", "营销数据暂时无法读取");
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

async function submitChat(message) {
  const cleanMessage = message.trim();
  if (!cleanMessage) return;

  elements.chatResponse.hidden = false;
  elements.chatResponse.textContent = "正在准备回答…";
  const submitButton = elements.chatForm.querySelector("button");
  submitButton.disabled = true;

  try {
    const data = await fetchJson("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: cleanMessage }),
    });
    elements.chatResponse.innerHTML = `
      <strong>${escapeHtml(cleanMessage)}</strong><br />
      ${escapeHtml(data.answer)}
    `;
  } catch (error) {
    elements.chatResponse.textContent = `聊天接口暂时不可用：${error.message}`;
  } finally {
    submitButton.disabled = false;
  }
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

document.querySelectorAll(".prompt-chip").forEach((button) => {
  button.addEventListener("click", () => {
    elements.chatInput.value = button.textContent.trim();
    submitChat(elements.chatInput.value);
  });
});

elements.chatForm.addEventListener("submit", (event) => {
  event.preventDefault();
  submitChat(elements.chatInput.value);
});

async function initialise() {
  try {
    await loadStores();
    await loadDashboard();
  } catch (error) {
    setConnectionStatus("error", "数据库连接失败");
    showGlobalError(`Dashboard 初始化失败：${error.message}`);
    elements.refreshButton.classList.remove("is-loading");
    elements.refreshButton.disabled = false;
  }
}

initialise();
