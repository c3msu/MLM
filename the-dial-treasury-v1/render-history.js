// render-history.js — Interactive history + cross-market history charts and the
// percentile-dashboard renderers/modal, split out of app.js (2026-06-20 Phase 3 全面重构,
// behavior-unchanged). Plain <script> loaded BEFORE app.js; global function declarations
// resolving app.js top-level state/utils at call time.

async function loadHistoryData() {
  const statsNode = $("#historyStats");
  const chartNode = $("#historyInteractiveChart");
  const crossChartNode = $("#crossHistoryChart");
  if ((!statsNode || !chartNode) && !crossChartNode) return;
  if (window.location.protocol === "file:") {
    renderCrossHistoryUnavailable("HTTP 服务模式下显示跨市场历史数据");
    return;
  }
  try {
    const [summaryResponse, statsResponse] = await Promise.all([
      fetch(`/api/history?ts=${Date.now()}`, { cache: "no-store" }),
      fetch(`/api/history/stats?limit=180&ts=${Date.now()}`, { cache: "no-store" }),
    ]);
    if (!summaryResponse.ok) throw new Error(`history summary HTTP ${summaryResponse.status}`);
    if (!statsResponse.ok) throw new Error(`history stats HTTP ${statsResponse.status}`);
    historySummaryCache = await summaryResponse.json();
    historyStatsCache = orderHistoryStats(await statsResponse.json());
    renderHistorySelectors();
    renderHistoryStats();
    renderCrossMarketHistoryControls();
    const tasks = [];
    if (chartNode) {
      tasks.push(loadSelectedHistorySeries().catch((error) => {
        console.warn("Failed to load selected history series", error);
        renderHistoryUnavailable("历史序列加载失败");
      }));
    }
    if (crossChartNode) {
      tasks.push(loadSelectedCrossMarketHistory().catch((error) => {
        console.warn("Failed to load cross-market history series", error);
        renderCrossHistoryUnavailable("跨市场历史序列加载失败");
      }));
    }
    await Promise.all(tasks);
  } catch (error) {
    console.warn("Failed to load historical series", error);
    renderHistoryUnavailable("历史库暂不可用");
    renderCrossHistoryUnavailable("跨市场历史库暂不可用");
  }
}

function orderHistoryStats(stats) {
  const rows = Array.isArray(stats) ? stats : [];
  return rows.sort((left, right) => {
    const leftPreferred = PREFERRED_HISTORY_SERIES.indexOf(left.name);
    const rightPreferred = PREFERRED_HISTORY_SERIES.indexOf(right.name);
    const leftRank = leftPreferred === -1 ? 999 : leftPreferred;
    const rightRank = rightPreferred === -1 ? 999 : rightPreferred;
    if (leftRank !== rightRank) return leftRank - rightRank;
    return (right.count || 0) - (left.count || 0);
  });
}

function renderHistorySelectors() {
  const select = $("#historySeriesSelect");
  const coverage = $("#historyCoverage");
  if (!select) return;
  const options = historyStatsCache.slice(0, 140);
  if (!options.length) {
    select.innerHTML = `<option>暂无历史序列</option>`;
    select.disabled = true;
    if (coverage) coverage.textContent = "no historical rows";
    return;
  }
  select.disabled = false;
  if (!selectedHistorySeriesKey || !options.some((item) => historySeriesKey(item) === selectedHistorySeriesKey)) {
    selectedHistorySeriesKey = historySeriesKey(options[0]);
  }
  select.innerHTML = options.map((item) => `
    <option value="${escapeHtml(historySeriesKey(item))}" ${historySeriesKey(item) === selectedHistorySeriesKey ? "selected" : ""}>
      ${escapeHtml(historySeriesLabel(item))}
    </option>
  `).join("");
  if (coverage && historySummaryCache) {
    const start = historySummaryCache.historicalStartDate || "--";
    const end = historySummaryCache.historicalEndDate || "--";
    coverage.textContent = `${start} → ${end} · ${historySummaryCache.historicalObservationCount || 0} rows · ${historySummaryCache.historicalSeriesCount || 0} series`;
  }
}

function renderHistoryStats() {
  const node = $("#historyStats");
  if (!node) return;
  const selected = selectedHistorySeries();
  if (!selected) {
    node.innerHTML = `<div class="empty-state compact">暂无历史统计</div>`;
    return;
  }
  const unit = selected.unit ? ` ${selected.unit}` : "";
  const stats = [
    ["最新", formatHistoryValue(selected.latest, unit)],
    ["样本数", selected.count ?? "--"],
    ["区间", `${selected.startDate || "--"} / ${selected.endDate || "--"}`],
    ["P10 / P50 / P90", `${formatHistoryValue(selected.p10, unit)} / ${formatHistoryValue(selected.p50, unit)} / ${formatHistoryValue(selected.p90, unit)}`],
    ["Min / Max", `${formatHistoryValue(selected.min, unit)} / ${formatHistoryValue(selected.max, unit)}`],
  ];
  node.innerHTML = stats.map(([label, value]) => `
    <div class="history-stat">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </div>
  `).join("");
}

function crossHistoryGroups() {
  const groups = state.cross?.historySeries;
  return Array.isArray(groups) ? groups : [];
}

function crossHistoryGroupLabel(group) {
  return currentLanguage === "en" ? (group.en || group.label || group.id) : (group.label || group.en || group.id);
}

function matchingHistoryStat(target) {
  return historyStatsCache.find((item) => (
    item.category === target.category
    && item.name === target.name
    && String(item.label || "") === String(target.label || "")
  ));
}

function crossHistoryOptions(groupId = crossHistoryGroup) {
  const group = crossHistoryGroups().find((item) => item.id === groupId) || crossHistoryGroups()[0];
  if (!group) return [];
  return (group.series || []).map((target) => ({
    group,
    target,
    stat: matchingHistoryStat(target)
  })).filter((item) => item.stat);
}

function allCrossHistoryOptionsByGroup() {
  return crossHistoryGroups().map((group) => ({
    group,
    options: crossHistoryOptions(group.id)
  })).filter((item) => item.options.length);
}

function renderCrossMarketHistoryControls() {
  const groupNode = $("#crossHistoryGroupControls");
  const select = $("#crossHistorySeriesSelect");
  const coverage = $("#crossHistoryCoverage");
  if (!groupNode || !select) return;
  const groups = allCrossHistoryOptionsByGroup();
  if (!groups.length) {
    select.innerHTML = `<option>暂无跨市场历史序列</option>`;
    select.disabled = true;
    groupNode.innerHTML = "";
    renderCrossHistoryStats(null);
    if (coverage) coverage.textContent = historyStatsCache.length ? "no cross-market history series" : "loading public history";
    return;
  }
  if (!groups.some((item) => item.group.id === crossHistoryGroup)) {
    crossHistoryGroup = groups[0].group.id;
  }
  groupNode.innerHTML = groups.map(({ group, options }) => `
    <button type="button" class="${group.id === crossHistoryGroup ? "active" : ""}" data-cross-history-group="${escapeHtml(group.id)}">
      ${escapeHtml(crossHistoryGroupLabel(group))}<span>${options.length}</span>
    </button>
  `).join("");
  const options = crossHistoryOptions(crossHistoryGroup);
  if (!selectedCrossHistorySeriesKey || !options.some((item) => historySeriesKey(item.target) === selectedCrossHistorySeriesKey)) {
    selectedCrossHistorySeriesKey = historySeriesKey(options[0].target);
  }
  select.disabled = false;
  select.innerHTML = options.map(({ target }) => `
    <option value="${escapeHtml(historySeriesKey(target))}" ${historySeriesKey(target) === selectedCrossHistorySeriesKey ? "selected" : ""}>
      ${escapeHtml(target.displayName || historySeriesLabel(target))}
    </option>
  `).join("");
  const selected = selectedCrossHistoryOption();
  renderCrossHistoryStats(selected);
  if (coverage && selected) {
    const stat = selected.stat;
    coverage.textContent = `${crossHistoryGroupLabel(selected.group)} · ${stat.startDate || "--"} → ${stat.endDate || "--"} · ${crossHistoryRangeYears}Y dynamic`;
  }
}

function selectedCrossHistoryOption() {
  return crossHistoryOptions(crossHistoryGroup).find((item) => historySeriesKey(item.target) === selectedCrossHistorySeriesKey) || crossHistoryOptions(crossHistoryGroup)[0];
}

function renderCrossHistoryStats(selected) {
  const node = $("#crossHistoryStats");
  if (!node) return;
  if (!selected) {
    node.innerHTML = `<div class="empty-state compact">暂无跨市场历史统计</div>`;
    return;
  }
  const stat = selected.stat;
  const unit = stat.unit ? ` ${stat.unit}` : "";
  const rows = [
    ["最新", formatHistoryValue(stat.latest, unit)],
    ["样本数", stat.count ?? "--"],
    ["区间", `${stat.startDate || "--"} / ${stat.endDate || "--"}`],
    ["P10 / P50 / P90", `${formatHistoryValue(stat.p10, unit)} / ${formatHistoryValue(stat.p50, unit)} / ${formatHistoryValue(stat.p90, unit)}`],
    ["来源", selected.target.source || stat.source || "--"],
  ];
  node.innerHTML = rows.map(([label, value]) => `
    <div class="history-stat">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </div>
  `).join("");
}

async function loadSelectedCrossMarketHistory() {
  renderCrossMarketHistoryControls();
  const selected = selectedCrossHistoryOption();
  if (!selected) {
    renderCrossHistoryUnavailable("暂无可绘制跨市场历史序列");
    return;
  }
  const target = selected.target;
  const params = new URLSearchParams({
    category: target.category,
    name: target.name,
    years: String(crossHistoryRangeYears),
    limit: "1100",
  });
  if (target.label) params.set("label", target.label);
  const response = await fetch(`/api/history/series?${params.toString()}&ts=${Date.now()}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`cross history series HTTP ${response.status}`);
  renderCrossMarketHistoryChart(await response.json());
}

async function loadSelectedHistorySeries() {
  const selected = selectedHistorySeries();
  if (!selected) {
    renderHistoryUnavailable("暂无可绘制历史序列");
    return;
  }
  const params = new URLSearchParams({
    category: selected.category,
    name: selected.name,
    years: String(historyRangeYears),
    limit: "1100",
  });
  if (selected.label) params.set("label", selected.label);
  const response = await fetch(`/api/history/series?${params.toString()}&ts=${Date.now()}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`history series HTTP ${response.status}`);
  renderInteractiveHistoryChart(await response.json());
}

function renderInteractiveHistoryChart(payload) {
  renderHistoricalLineChart(payload, {
    chartSelector: "#historyInteractiveChart",
    tooltipSelector: "#historyChartTooltip",
    emptyMessage: "历史点数不足,等待回填或下一次后台更新",
  });
}

function renderCrossMarketHistoryChart(payload) {
  renderHistoricalLineChart(payload, {
    chartSelector: "#crossHistoryChart",
    tooltipSelector: "#crossHistoryTooltip",
    emptyMessage: "跨市场历史点数不足,等待回填或下一次后台更新",
  });
}

function renderHistoricalLineChart(payload, options = {}) {
  const node = $(options.chartSelector || "#historyInteractiveChart");
  if (!node) return;
  const points = (payload?.points || [])
    .map((point) => ({ ...point, time: Date.parse(point.date), value: Number(point.value) }))
    .filter((point) => Number.isFinite(point.time) && Number.isFinite(point.value));
  const series = payload?.series || selectedHistorySeries() || {};
  if (points.length < 2) {
    node.innerHTML = `<div class="empty-state">${escapeHtml(options.emptyMessage || "历史点数不足")}</div>`;
    $(options.tooltipSelector || "#historyChartTooltip")?.setAttribute("hidden", "");
    return;
  }
  const W = 1040;
  const H = 300;
  const pad = { l: 52, r: 22, t: 18, b: 36 };
  const minTime = Math.min(...points.map((point) => point.time));
  const maxTime = Math.max(...points.map((point) => point.time));
  const rawMin = Math.min(...points.map((point) => point.value));
  const rawMax = Math.max(...points.map((point) => point.value));
  const spread = rawMax - rawMin || Math.max(1, Math.abs(rawMax) * 0.04);
  const minValue = rawMin - spread * 0.08;
  const maxValue = rawMax + spread * 0.08;
  const x = (time) => pad.l + ((time - minTime) / Math.max(1, maxTime - minTime)) * (W - pad.l - pad.r);
  const y = (value) => pad.t + ((maxValue - value) / Math.max(1e-9, maxValue - minValue)) * (H - pad.t - pad.b);
  const path = points.map((point, index) => `${index ? "L" : "M"}${x(point.time).toFixed(1)},${y(point.value).toFixed(1)}`).join(" ");
  const yTicks = buildTicks(minValue, maxValue, 5);
  const xTicks = buildDateTicks(points, 5);
  const unit = series.unit || points[0]?.unit || "";
  node.innerHTML = `
    <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${escapeHtml(series.name || "Historical series")}" data-history-chart>
      <rect x="0" y="0" width="${W}" height="${H}" fill="transparent"></rect>
      ${yTicks.map((tick) => `
        <line x1="${pad.l}" x2="${W - pad.r}" y1="${y(tick).toFixed(1)}" y2="${y(tick).toFixed(1)}" stroke="var(--line-soft)"></line>
        <text x="10" y="${y(tick).toFixed(1)}" dy="4" fill="var(--faint)" font-size="11" font-family="var(--mono)">${formatAxisTick(tick)}</text>
      `).join("")}
      ${xTicks.map((point) => `
        <text x="${x(point.time).toFixed(1)}" y="${H - 10}" text-anchor="middle" fill="var(--faint)" font-size="11" font-family="var(--mono)">${formatMonthLabel(point.time)}</text>
      `).join("")}
      <path d="${path}" fill="none" stroke="var(--accent)" stroke-width="2.1" stroke-linejoin="round" stroke-linecap="round"></path>
      <circle cx="${x(points[points.length - 1].time).toFixed(1)}" cy="${y(points[points.length - 1].value).toFixed(1)}" r="4" fill="var(--accent)"></circle>
      <line class="history-hover-guide" x1="${pad.l}" x2="${pad.l}" y1="${pad.t}" y2="${H - pad.b}" stroke="var(--ink)" stroke-opacity="0" stroke-dasharray="3 4"></line>
      <circle class="history-hover-dot" cx="${pad.l}" cy="${pad.t}" r="4" fill="var(--bear)" opacity="0"></circle>
      <text x="${pad.l}" y="13" fill="var(--muted)" font-size="11" font-family="var(--mono)">${escapeHtml(series.source || "")}</text>
      <text x="${W - pad.r}" y="13" text-anchor="end" fill="var(--muted)" font-size="11" font-family="var(--mono)">${escapeHtml(unit)}</text>
    </svg>
  `;
  bindHistoryChartHover(node, points, { minTime, maxTime, minValue, maxValue, W, H, pad }, series, options.tooltipSelector || "#historyChartTooltip");
}

function bindHistoryChartHover(chartNode, points, scale, series, tooltipSelector = "#historyChartTooltip") {
  const svg = chartNode.querySelector("[data-history-chart]");
  const tooltip = $(tooltipSelector);
  if (!svg || !tooltip) return;
  const guide = svg.querySelector(".history-hover-guide");
  const dot = svg.querySelector(".history-hover-dot");
  const x = (time) => scale.pad.l + ((time - scale.minTime) / Math.max(1, scale.maxTime - scale.minTime)) * (scale.W - scale.pad.l - scale.pad.r);
  const y = (value) => scale.pad.t + ((scale.maxValue - value) / Math.max(1e-9, scale.maxValue - scale.minValue)) * (scale.H - scale.pad.t - scale.pad.b);
  svg.addEventListener("mousemove", (event) => {
    const rect = svg.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
    const targetTime = scale.minTime + ratio * (scale.maxTime - scale.minTime);
    const point = nearestPoint(points, targetTime);
    if (!point) return;
    const pointX = x(point.time);
    const pointY = y(point.value);
    guide?.setAttribute("x1", pointX.toFixed(1));
    guide?.setAttribute("x2", pointX.toFixed(1));
    guide?.setAttribute("stroke-opacity", "0.35");
    dot?.setAttribute("cx", pointX.toFixed(1));
    dot?.setAttribute("cy", pointY.toFixed(1));
    dot?.setAttribute("opacity", "1");
    const unit = series.unit || point.unit || "";
    tooltip.innerHTML = `<b>${escapeHtml(point.date)}</b>${escapeHtml(series.name || point.name)} · ${escapeHtml(formatHistoryValue(point.value, unit ? ` ${unit}` : ""))}`;
    tooltip.hidden = false;
    const chartRect = chartNode.getBoundingClientRect();
    tooltip.style.left = `${Math.min(chartNode.clientWidth - 250, Math.max(8, event.clientX - chartRect.left + 12))}px`;
    tooltip.style.top = `${Math.max(8, event.clientY - chartRect.top - 42)}px`;
  });
  svg.addEventListener("mouseleave", () => {
    guide?.setAttribute("stroke-opacity", "0");
    dot?.setAttribute("opacity", "0");
    tooltip.hidden = true;
  });
}

function renderHistoryUnavailable(message) {
  const statsNode = $("#historyStats");
  const chartNode = $("#historyInteractiveChart");
  const coverage = $("#historyCoverage");
  if (coverage) coverage.textContent = message;
  if (statsNode) statsNode.innerHTML = `<div class="empty-state compact">${escapeHtml(message)}</div>`;
  if (chartNode) chartNode.innerHTML = `<div class="empty-state">${escapeHtml(message)}</div>`;
}

function renderCrossHistoryUnavailable(message) {
  const statsNode = $("#crossHistoryStats");
  const chartNode = $("#crossHistoryChart");
  const coverage = $("#crossHistoryCoverage");
  if (coverage) coverage.textContent = message;
  if (statsNode) statsNode.innerHTML = `<div class="empty-state compact">${escapeHtml(message)}</div>`;
  if (chartNode) chartNode.innerHTML = `<div class="empty-state">${escapeHtml(message)}</div>`;
  $("#crossHistoryTooltip")?.setAttribute("hidden", "");
}

function selectedHistorySeries() {
  return historyStatsCache.find((item) => historySeriesKey(item) === selectedHistorySeriesKey) || historyStatsCache[0];
}

function historySeriesKey(item) {
  return `${item.category || ""}||${item.name || ""}||${item.label || ""}`;
}

function historySeriesLabel(item) {
  const label = item.label ? ` · ${item.label}` : "";
  const unit = item.unit ? ` (${item.unit})` : "";
  return `${item.name}${label}${unit}`;
}

function formatHistoryValue(value, unit = "") {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "--";
  const digits = Math.abs(numeric) >= 100 ? 1 : Math.abs(numeric) >= 10 ? 2 : 3;
  return `${numeric.toLocaleString(currentLanguage === "en" ? "en-US" : "zh-CN", { maximumFractionDigits: digits })}${unit}`;
}

function buildTicks(minValue, maxValue, count) {
  if (!Number.isFinite(minValue) || !Number.isFinite(maxValue) || count <= 1) return [];
  const step = (maxValue - minValue) / (count - 1);
  return Array.from({ length: count }, (_, index) => minValue + step * index);
}

function buildDateTicks(points, count) {
  if (!points.length) return [];
  if (points.length <= count) return points;
  const last = points.length - 1;
  return Array.from({ length: count }, (_, index) => points[Math.round(index * last / (count - 1))]);
}

function formatAxisTick(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "--";
  if (Math.abs(numeric) >= 1000) return `${(numeric / 1000).toFixed(1)}k`;
  if (Math.abs(numeric) >= 100) return numeric.toFixed(0);
  return numeric.toFixed(2);
}

function formatMonthLabel(time) {
  return new Date(time).toLocaleDateString(currentLanguage === "en" ? "en-US" : "zh-CN", { year: "2-digit", month: "2-digit" });
}

function nearestPoint(points, targetTime) {
  if (!points.length) return null;
  let best = points[0];
  let bestDistance = Math.abs(points[0].time - targetTime);
  for (const point of points) {
    const distance = Math.abs(point.time - targetTime);
    if (distance < bestDistance) {
      best = point;
      bestDistance = distance;
    }
  }
  return best;
}

function renderPercentileDashboard() {
  const percentiles = state.percentiles || {};
  const trends = (percentiles.trends || []).filter((trend) => Array.isArray(trend.points) && trend.points.length);
  percentileTrendCache = trends;
  const compactTrends = visiblePercentileTrends(trends);
  const method = $("#percentileMethod");
  if (method) {
    method.textContent = trends.length ? `核心${compactTrends.length}项 · 放大查看全部${trends.length}项` : "等待历史百分位数据";
  }
  drawPercentileTrendChart(compactTrends, {
    chartSelector: "#percentileTrendChart",
    legendSelector: "#percentileTrendLegend",
    large: false,
    hiddenCount: Math.max(0, trends.length - compactTrends.length),
  });
  renderPercentileMovers(percentiles.movers || []);
  renderPercentileAlerts(percentiles.alerts || []);
}

function visiblePercentileTrends(trends) {
  const byName = new Map(trends.map((trend) => [trend.name, trend]));
  const ordered = CORE_PERCENTILE_TRENDS.map((name) => byName.get(name)).filter(Boolean);
  const fill = trends.filter((trend) => !CORE_PERCENTILE_TRENDS.includes(trend.name));
  return [...ordered, ...fill].slice(0, DEFAULT_PERCENTILE_TREND_LIMIT);
}

function percentileStressRank(trend) {
  const latest = Number(trend.latestPercentile);
  const change = Math.abs(Number(trend.change) || 0);
  const edgeDistance = Number.isFinite(latest) ? Math.abs(latest - 50) : 0;
  return edgeDistance + change * 0.35;
}

function selectPercentileModalTrends(mode, trends = percentileTrendCache) {
  if (mode === "core") return visiblePercentileTrends(trends);
  if (mode === "stress") {
    const stress = trends
      .filter((trend) => {
        const latest = Number(trend.latestPercentile);
        const change = Math.abs(Number(trend.change) || 0);
        return (Number.isFinite(latest) && (latest <= 15 || latest >= 85)) || change >= 50;
      })
      .sort((a, b) => percentileStressRank(b) - percentileStressRank(a));
    return stress.length ? stress : [...trends].sort((a, b) => percentileStressRank(b) - percentileStressRank(a)).slice(0, DEFAULT_PERCENTILE_TREND_LIMIT);
  }
  return trends;
}

function renderPercentileModalControls() {
  const controls = $("#percentileModalControls");
  if (!controls) return;
  controls.innerHTML = PERCENTILE_MODAL_MODES.map((mode) => {
    const count = selectPercentileModalTrends(mode.id).length;
    return `<button type="button" class="${percentileModalMode === mode.id ? "active" : ""}" data-percentile-mode="${mode.id}">${mode.label}<span>${count}</span></button>`;
  }).join("");
}

function renderPercentileModalChart() {
  const selectedMode = PERCENTILE_MODAL_MODES.find((mode) => mode.id === percentileModalMode) || PERCENTILE_MODAL_MODES[0];
  const selectedTrends = selectPercentileModalTrends(selectedMode.id);
  const title = $("#percentileModalTitle");
  if (title) title.textContent = `历史百分位趋势 · ${selectedMode.title}`;
  renderPercentileModalControls();
  drawPercentileTrendChart(selectedTrends, {
    chartSelector: "#percentileModalChart",
    legendSelector: "#percentileModalLegend",
    large: true,
  });
}

function drawPercentileTrendChart(trends, options = {}) {
  const node = $(options.chartSelector || "#percentileTrendChart");
  const legend = $(options.legendSelector || "#percentileTrendLegend");
  if (!node || !legend) return;
  if (!trends.length) {
    node.innerHTML = `<div class="empty-state">暂无可绘制的历史百分位趋势</div>`;
    legend.innerHTML = "";
    return;
  }
  const colors = ["var(--accent)", "var(--bear)", "#3267a8", "var(--neutral)", "var(--accent-2)", "#7a5a9e", "#5d7f38", "#a05c42"];
  const W = options.large ? 1040 : 760;
  const H = options.large ? 460 : 252;
  const pad = options.large ? { l: 50, r: 30, t: 24, b: 42 } : { l: 42, r: 20, t: 18, b: 34 };
  const prepared = trends.map((trend, index) => ({
    trend,
    index,
    color: colors[index % colors.length],
    points: trend.points
      .map((point) => ({ ...point, time: Date.parse(point.date), percentile: Number(point.percentile) }))
      .filter((point) => Number.isFinite(point.time) && Number.isFinite(point.percentile)),
  }));
  const allPoints = prepared.flatMap((item) => item.points);
  if (!allPoints.length) {
    node.innerHTML = `<div class="empty-state">暂无可绘制的历史百分位趋势</div>`;
    legend.innerHTML = "";
    return;
  }
  const minTime = Math.min(...allPoints.map((point) => point.time));
  const maxTime = Math.max(...allPoints.map((point) => point.time));
  const x = (time) => {
    if (maxTime === minTime) return pad.l + (W - pad.l - pad.r) / 2;
    return pad.l + ((time - minTime) / (maxTime - minTime)) * (W - pad.l - pad.r);
  };
  const y = (percentile) => pad.t + ((100 - percentile) / 100) * (H - pad.t - pad.b);
  const linePath = (points) => points
    .map((point, index) => `${index ? "L" : "M"}${x(point.time).toFixed(1)},${y(point.percentile).toFixed(1)}`)
    .join(" ");
  const dateLabel = (time) => new Date(time).toLocaleDateString(currentLanguage === "en" ? "en-US" : "zh-CN", { year: "2-digit", month: "2-digit" });
  node.innerHTML = `
    <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Historical percentile trends" data-percentile-chart>
      <rect x="0" y="0" width="${W}" height="${H}" fill="transparent"></rect>
      <rect x="${pad.l}" y="${y(100)}" width="${W - pad.l - pad.r}" height="${Math.max(1, y(90) - y(100))}" class="percentile-zone high"></rect>
      <rect x="${pad.l}" y="${y(10)}" width="${W - pad.l - pad.r}" height="${Math.max(1, y(0) - y(10))}" class="percentile-zone low"></rect>
      ${[0, 25, 50, 75, 100].map((tick) => `
        <line x1="${pad.l}" x2="${W - pad.r}" y1="${y(tick)}" y2="${y(tick)}" stroke="var(--line-soft)"></line>
        <text x="9" y="${y(tick) + 4}" fill="var(--muted)" font-size="11" font-family="var(--mono)">p${tick}</text>
      `).join("")}
      <line x1="${pad.l}" x2="${W - pad.r}" y1="${y(90)}" y2="${y(90)}" stroke="var(--bear)" stroke-opacity=".25" stroke-dasharray="4 5"></line>
      <line x1="${pad.l}" x2="${W - pad.r}" y1="${y(10)}" y2="${y(10)}" stroke="var(--accent)" stroke-opacity=".25" stroke-dasharray="4 5"></line>
      <text x="${pad.l}" y="${H - 9}" fill="var(--faint)" font-size="11" font-family="var(--mono)">${dateLabel(minTime)}</text>
      <text x="${W - pad.r}" y="${H - 9}" text-anchor="end" fill="var(--faint)" font-size="11" font-family="var(--mono)">${dateLabel(maxTime)}</text>
      ${prepared.map(({ trend, color, points }) => {
        const latest = points[points.length - 1];
        const isFocused = percentileFocusedTrend === trend.name;
        const isDimmed = Boolean(percentileFocusedTrend && !isFocused);
        const lineClass = isDimmed ? "percentile-focus-dim" : isFocused ? "percentile-focus-active" : "";
        const strokeWidth = isFocused ? (options.large ? 3.1 : 3.4) : (options.large ? 1.9 : 2.5);
        return `
          <g class="${lineClass}" data-percentile-series="${escapeHtml(trend.name)}">
            <path d="${linePath(points)}" fill="none" stroke="${color}" stroke-width="${strokeWidth}" stroke-opacity="${options.large ? "0.72" : "0.92"}" stroke-linejoin="round" stroke-linecap="round" data-percentile-line="${escapeHtml(trend.name)}"></path>
            ${latest ? `<circle cx="${x(latest.time).toFixed(1)}" cy="${y(latest.percentile).toFixed(1)}" r="${isFocused ? 4.5 : 3.2}" fill="${color}"></circle>` : ""}
            ${latest && (!options.large || isFocused) ? `<text x="${Math.min(W - pad.r - 4, x(latest.time) + 8).toFixed(1)}" y="${y(latest.percentile).toFixed(1)}" dy="4" fill="${color}" font-size="10.5" font-family="var(--mono)">${escapeHtml(trend.name)}</text>` : ""}
          </g>
        `;
      }).join("")}
      <line class="percentile-hover-guide" x1="${pad.l}" x2="${pad.l}" y1="${pad.t}" y2="${H - pad.b}" stroke="var(--ink)" stroke-opacity="0" stroke-dasharray="3 4"></line>
      <circle class="percentile-hover-dot" cx="${pad.l}" cy="${pad.t}" r="4" fill="var(--accent)" opacity="0"></circle>
    </svg>
  `;
  const hiddenNote = options.hiddenCount ? `<span class="muted-chip">+${options.hiddenCount} 项在放大图</span>` : "";
  legend.innerHTML = prepared.map(({ trend, color }) => `
    <button type="button" class="${percentileFocusedTrend === trend.name ? "active" : ""}" data-percentile-focus="${escapeHtml(trend.name)}" aria-pressed="${percentileFocusedTrend === trend.name ? "true" : "false"}">
      <i style="background:${color}"></i><span>${escapeHtml(trend.name)}</span> <b>p${trend.latestPercentile ?? "--"}</b>
    </button>
  `).join("") + hiddenNote;
  bindPercentileTrendInteractions(node, legend, prepared, { minTime, maxTime, W, H, pad, x, y }, options);
}

function bindPercentileTrendInteractions(chartNode, legendNode, prepared, scale, options = {}) {
  const svg = chartNode.querySelector("[data-percentile-chart]");
  const tooltip = $(options.tooltipSelector || (options.large ? "#percentileModalTooltip" : "#percentileTrendTooltip"));
  if (!svg || !tooltip) return;
  legendNode.querySelectorAll("[data-percentile-focus]").forEach((button) => {
    button.addEventListener("click", () => {
      const name = button.dataset.percentileFocus || "";
      percentileFocusedTrend = percentileFocusedTrend === name ? "" : name;
      renderPercentileDashboard();
      if (!$("#percentileModal")?.hidden) renderPercentileModalChart();
    });
  });
  const guide = svg.querySelector(".percentile-hover-guide");
  const dot = svg.querySelector(".percentile-hover-dot");
  const points = prepared.flatMap(({ trend, color, points: trendPoints }) => trendPoints.map((point) => ({ ...point, trend, color })));
  svg.addEventListener("mousemove", (event) => {
    const rect = svg.getBoundingClientRect();
    const svgX = ((event.clientX - rect.left) / rect.width) * scale.W;
    const svgY = ((event.clientY - rect.top) / rect.height) * scale.H;
    const point = nearestPercentilePoint(points, svgX, svgY, scale);
    if (!point) return;
    const pointX = scale.x(point.time);
    const pointY = scale.y(point.percentile);
    guide?.setAttribute("x1", pointX.toFixed(1));
    guide?.setAttribute("x2", pointX.toFixed(1));
    guide?.setAttribute("stroke-opacity", "0.35");
    dot?.setAttribute("cx", pointX.toFixed(1));
    dot?.setAttribute("cy", pointY.toFixed(1));
    dot?.setAttribute("fill", point.color);
    dot?.setAttribute("opacity", "1");
    renderPercentileTooltip(tooltip, chartNode, event, point);
  });
  svg.addEventListener("mouseleave", () => {
    guide?.setAttribute("stroke-opacity", "0");
    dot?.setAttribute("opacity", "0");
    tooltip.hidden = true;
  });
}

function nearestPercentilePoint(points, svgX, svgY, scale) {
  let best = null;
  let bestDistance = Number.POSITIVE_INFINITY;
  for (const point of points) {
    const distance = Math.hypot((scale.x(point.time) - svgX) * 0.75, scale.y(point.percentile) - svgY);
    if (distance < bestDistance) {
      best = point;
      bestDistance = distance;
    }
  }
  return best;
}

function renderPercentileTooltip(tooltip, chartNode, event, point) {
  const valueText = point.value == null ? "" : ` · ${escapeHtml(point.value)}${escapeHtml(point.trend.unit || "")}`;
  tooltip.innerHTML = `
    <b>${escapeHtml(point.trend.name)} · p${escapeHtml(point.percentile)}</b>
    <span>${escapeHtml(point.date)}${valueText}</span>
    <small>${escapeHtml(point.trend.source || point.trend.window || "")}</small>
  `;
  const parentRect = (tooltip.offsetParent || chartNode).getBoundingClientRect();
  tooltip.hidden = false;
  const left = Math.min(Math.max(8, event.clientX - parentRect.left + 12), Math.max(8, parentRect.width - tooltip.offsetWidth - 8));
  const top = Math.min(Math.max(8, event.clientY - parentRect.top - 46), Math.max(8, parentRect.height - tooltip.offsetHeight - 8));
  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${top}px`;
}

function openPercentileModal() {
  const modal = $("#percentileModal");
  if (!modal) return;
  modal.hidden = false;
  document.body.classList.add("modal-open");
  percentileModalMode = "all";
  renderPercentileModalChart();
  $("#closePercentileModal")?.focus();
}

function closePercentileModal() {
  const modal = $("#percentileModal");
  if (!modal) return;
  modal.hidden = true;
  document.body.classList.remove("modal-open");
}

function renderPercentileMovers(movers) {
  const node = $("#percentileMovers");
  if (!node) return;
  if (!movers.length) {
    node.innerHTML = `<div class="empty-state compact">暂无显著变化</div>`;
    return;
  }
  node.innerHTML = movers.slice(0, 5).map((item) => `
    <div class="mini-row">
      <span>${escapeHtml(item.name)}<small>${escapeHtml(item.window || "")}</small></span>
      <strong class="${item.change > 0 ? "bear" : "bull"}">${item.change > 0 ? "+" : ""}${item.change}p</strong>
    </div>
  `).join("");
}

function renderPercentileAlerts(alerts) {
  const node = $("#percentileAlerts");
  if (!node) return;
  if (!alerts.length) {
    node.innerHTML = `<div class="empty-state compact">无极端分位</div>`;
    return;
  }
  node.innerHTML = alerts.slice(0, 5).map((item) => `
    <div class="mini-row alert ${item.side === "high" ? "high" : "low"}">
      <span>${escapeHtml(item.name)}<small>${escapeHtml(item.value)} · ${escapeHtml(item.message)}</small></span>
      <strong>p${item.percentile}</strong>
    </div>
  `).join("");
}
