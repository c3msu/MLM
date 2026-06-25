// render-liquidity.js — Macro-liquidity / liquidity-equity-lead renderers + SPY-warning
// class helper, split out of app.js (2026-06-20 Phase 3 全面重构, behavior-unchanged).
// Plain <script> loaded BEFORE app.js; global function declarations resolving app.js
// top-level state/utils at call time.

function spyWarningClass(score) {
  const numeric = Number(score);
  if (!Number.isFinite(numeric)) return "neutral";
  if (numeric >= 60) return "restrictive";
  if (numeric >= 40) return "neutral";
  return "supportive";
}

function renderLiquidityCurrentSignal(signal) {
  const cards = Array.isArray(signal.cards) ? signal.cards : [];
  if (!signal.available || !cards.length) {
    return `<div class="empty-state compact">${escapeHtml(signal.verdict || "暂无当前信号")}</div>`;
  }
  return `
    <div class="liquidity-signal-read ${escapeHtml(signal.confidence || "low")}">
      <strong>${escapeHtml(signal.changeBucket || "--")}</strong>
      <span>${escapeHtml(signal.verdict || "")}</span>
    </div>
    <div class="liquidity-signal-cards">
      ${cards.map((card) => `
        <div class="liquidity-signal-card ${escapeHtml(card.tone || "neutral")}">
          <span>${escapeHtml(card.label || "")}</span>
          <strong>${escapeHtml(card.value || "--")}</strong>
          <small>${escapeHtml(card.detail || "")}</small>
        </div>
      `).join("")}
    </div>
  `;
}

function renderLiquidityStateGrid(cells) {
  if (!Array.isArray(cells) || !cells.length) {
    return `<div class="empty-state compact">暂无状态分布统计</div>`;
  }
  const levelLabels = ["低评分", "中位评分", "高评分"];
  const changeLabels = ["评分下行", "变化不大", "评分上行"];
  const lookup = new Map(cells.map((cell) => [`${cell.levelBucket}::${cell.changeBucket}`, cell]));
  return `
    <div class="liquidity-state-head">
      <strong>历史状态分布</strong>
      <span>当前状态与相似样本3M表现</span>
    </div>
    <div class="liquidity-state-axis">
      ${changeLabels.map((label) => `<span>${escapeHtml(label)}</span>`).join("")}
    </div>
    <div class="liquidity-state-matrix">
      ${levelLabels.map((level) => `
        <div class="liquidity-state-row">
          <b>${escapeHtml(level)}</b>
          ${changeLabels.map((change) => {
            const cell = lookup.get(`${level}::${change}`) || {};
            const avg = Number(cell.avgForward3m);
            const dd = Number(cell.avgMaxDrawdown3m);
            const hit = Number(cell.hitRate);
            return `
              <div class="liquidity-state-cell ${escapeHtml(cell.tone || "neutral")} ${cell.isCurrent ? "current" : ""}">
                <span>${Number(cell.count) || 0} obs</span>
                <strong>${Number.isFinite(avg) ? `${avg >= 0 ? "+" : ""}${avg.toFixed(2)}%` : "--"}</strong>
                <small>${Number.isFinite(hit) ? `${hit.toFixed(0)}% hit` : "hit --"} · DD ${Number.isFinite(dd) ? `${dd.toFixed(2)}%` : "--"}</small>
              </div>
            `;
          }).join("")}
        </div>
      `).join("")}
    </div>
  `;
}

function renderLiquidityEquityChart(panel) {
  const series = Array.isArray(panel.series) ? panel.series
    .map((point) => ({
      time: Date.parse(point.date),
      date: point.date,
      score: Number(point.liquidityScore),
      spx: Number(point.sp500Indexed),
    }))
    .filter((point) => Number.isFinite(point.time) && Number.isFinite(point.score) && Number.isFinite(point.spx)) : [];
  if (series.length < 2) {
    return `<div class="empty-state">暂无足够历史点生成对比图</div>`;
  }
  const W = 840;
  const H = 230;
  const pad = { l: 34, r: 44, t: 16, b: 28 };
  const minTime = Math.min(...series.map((point) => point.time));
  const maxTime = Math.max(...series.map((point) => point.time));
  const spxMin = Math.min(...series.map((point) => point.spx));
  const spxMax = Math.max(...series.map((point) => point.spx));
  const spxPad = Math.max(6, (spxMax - spxMin) * 0.12);
  const spxLow = Math.max(0, spxMin - spxPad);
  const spxHigh = spxMax + spxPad;
  const x = (time) => pad.l + ((time - minTime) / Math.max(1, maxTime - minTime)) * (W - pad.l - pad.r);
  const yScore = (value) => pad.t + ((100 - Math.max(0, Math.min(100, value))) / 100) * (H - pad.t - pad.b);
  const ySpx = (value) => pad.t + ((spxHigh - value) / Math.max(1, spxHigh - spxLow)) * (H - pad.t - pad.b);
  const path = (key, yFn) => series.map((point, index) => `${index ? "L" : "M"}${x(point.time).toFixed(1)},${yFn(point[key]).toFixed(1)}`).join(" ");
  const dateTicks = buildDateTicks(series, 4);
  return `
    <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Conditions score versus indexed S&P 500">
      <rect x="0" y="0" width="${W}" height="${H}" fill="transparent"></rect>
      ${[25, 50, 75].map((tick) => `
        <line x1="${pad.l}" x2="${W - pad.r}" y1="${yScore(tick)}" y2="${yScore(tick)}" stroke="var(--line-soft)"></line>
        <text x="8" y="${yScore(tick) + 4}" fill="var(--muted)" font-size="10" font-family="var(--mono)">${tick}</text>
      `).join("")}
      ${dateTicks.map((point) => `
        <text x="${x(point.time).toFixed(1)}" y="${H - 9}" text-anchor="middle" fill="var(--faint)" font-size="10.5" font-family="var(--mono)">${formatMonthLabel(point.time)}</text>
      `).join("")}
      <path d="${path("spx", ySpx)}" class="liquidity-equity-line spx"></path>
      <path d="${path("score", yScore)}" class="liquidity-equity-line score"></path>
      <circle cx="${x(series[series.length - 1].time).toFixed(1)}" cy="${yScore(series[series.length - 1].score).toFixed(1)}" r="3.5" class="liquidity-equity-dot score"></circle>
      <circle cx="${x(series[series.length - 1].time).toFixed(1)}" cy="${ySpx(series[series.length - 1].spx).toFixed(1)}" r="3.5" class="liquidity-equity-dot spx"></circle>
      <text x="${W - pad.r}" y="15" text-anchor="end" fill="var(--accent)" font-size="11" font-family="var(--mono)">Macro score</text>
      <text x="${W - pad.r}" y="30" text-anchor="end" fill="var(--bear)" font-size="11" font-family="var(--mono)">S&P 500 indexed</text>
      <text x="${W - 8}" y="${ySpx(spxHigh).toFixed(1) + 4}" text-anchor="end" fill="var(--muted)" font-size="10" font-family="var(--mono)">${spxHigh.toFixed(0)}</text>
      <text x="${W - 8}" y="${ySpx(spxLow).toFixed(1) + 4}" text-anchor="end" fill="var(--muted)" font-size="10" font-family="var(--mono)">${spxLow.toFixed(0)}</text>
    </svg>
  `;
}

function renderLiquidityLeadLag(rows) {
  if (!Array.isArray(rows) || !rows.length) return `<div class="empty-state compact">暂无领先矩阵</div>`;
  return `
    <table class="liquidity-equity-mini-table">
      <thead><tr><th>Signal</th><th>1M</th><th>3M</th><th>6M</th></tr></thead>
      <tbody>
        ${rows.map((row) => `
          <tr>
            <td>${escapeHtml(row.signal || "")}</td>
            ${["forward1m", "forward3m", "forward6m"].map((key) => `<td class="${correlationToneClass(row[key])}">${formatSignedMetric(row[key], 2)}</td>`).join("")}
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
}

function renderLiquidityChangeBuckets(buckets) {
  if (!Array.isArray(buckets) || !buckets.length) return `<div class="empty-state compact">暂无变化分组</div>`;
  return buckets.map((bucket) => {
    const avg = Number(bucket.avgForward3m);
    const dd = Number(bucket.avgMaxDrawdown3m);
    return `
      <div class="liquidity-change-row">
        <span>${escapeHtml(bucket.label || "")}<small>${escapeHtml(bucket.changeRange || "--")} · n=${Number(bucket.count) || 0}</small></span>
        <strong>${Number.isFinite(avg) ? `${avg >= 0 ? "+" : ""}${avg.toFixed(2)}%` : "--"}</strong>
        <em>DD ${Number.isFinite(dd) ? `${dd.toFixed(2)}%` : "--"}</em>
      </div>
    `;
  }).join("");
}

function renderLiquidityRolling(rolling, drawdown) {
  const latest = Number(rolling.latest);
  const min = Number(rolling.range?.min);
  const max = Number(rolling.range?.max);
  const worst = Number(drawdown.maxDrawdown);
  const worstDate = drawdown.worstDate || "--";
  return `
    <div class="liquidity-rolling-grid">
      <div>
        <span>${Number(rolling.windowMonths) || 24}M rolling corr</span>
        <strong class="${correlationToneClass(latest)}">${formatSignedMetric(latest, 2)}</strong>
        <small>${Number.isFinite(min) && Number.isFinite(max) ? `range ${formatSignedMetric(min, 2)} / ${formatSignedMetric(max, 2)}` : "range --"}</small>
      </div>
      <div>
        <span>Worst 3M drawdown</span>
        <strong class="restrictive">${Number.isFinite(worst) ? `${worst.toFixed(2)}%` : "--"}</strong>
        <small>${escapeHtml(worstDate)}</small>
      </div>
    </div>
  `;
}

function formatSignedMetric(value, digits = 2) {
  // Number(null)/Number("") coerce to 0; guard blanks so missing data reads "--" not "+0.00".
  if (value === null || value === undefined || value === "") return "--";
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "--";
  return `${numeric >= 0 ? "+" : ""}${numeric.toFixed(digits)}`;
}

function correlationToneClass(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || Math.abs(numeric) < 0.15) return "neutral";
  return numeric > 0 ? "supportive" : "restrictive";
}

function renderMacroLiquidityTrend(trend) {
  if (!trend.available) {
    return `<div class="empty-state compact">${escapeHtml(trend.summary || "综合评分历史分位样本不足")}</div>`;
  }
  const percentile = Number(trend.historicalPercentile);
  const score1m = Number(trend.score1mChange);
  const score3m = Number(trend.score3mChange);
  const percentile3m = Number(trend.percentile3mChange);
  return `
    <div class="macro-trend-card ${macroLiquidityTrendClass(trend.direction)}">
      <span>历史分位</span>
      <strong>${Number.isFinite(percentile) ? `p${percentile.toFixed(0)}` : "p--"}</strong>
      <small>${escapeHtml(trend.direction || "--")}</small>
    </div>
    <div class="macro-trend-card ${macroLiquidityTrendClass(score1m)}">
      <span>1M评分</span>
      <strong>${formatSignedMetric(score1m, 1)}</strong>
      <small>score change</small>
    </div>
    <div class="macro-trend-card ${macroLiquidityTrendClass(score3m)}">
      <span>3M评分</span>
      <strong>${formatSignedMetric(score3m, 1)}</strong>
      <small>${Number.isFinite(percentile3m) ? `p ${formatSignedMetric(percentile3m, 0)}` : "p --"}</small>
    </div>
  `;
}

function renderMacroLiquidityTrendChart(trend, options = {}) {
  const prepared = prepareMacroLiquidityComparisonSeries(trend, options.equity || macroLiquidityEquityPanel(), options.warning || spyWarningTrendPanel());
  const series = prepared.series;
  if (series.length < 2) return `<div class="empty-state compact">综合评分历史趋势样本不足</div>`;
  const scale = macroLiquidityComparisonScale(series, options);
  const { W, H, pad, x, yPercentile, ySpx } = scale;
  const liquidityPath = macroLiquidityPath(series, x, yPercentile, "percentile");
  const areaPath = `${liquidityPath} L${x(series[series.length - 1].time).toFixed(1)},${yPercentile(0).toFixed(1)} L${x(series[0].time).toFixed(1)},${yPercentile(0).toFixed(1)} Z`;
  const spxSeries = series.filter((point) => Number.isFinite(point.spxIndexed));
  const spxPath = spxSeries.length >= 2 ? macroLiquidityPath(spxSeries, x, ySpx, "spxIndexed") : "";
  const warningSeries = series.filter((point) => Number.isFinite(point.spyWarning));
  const warningPath = warningSeries.length >= 2 ? macroLiquidityPath(warningSeries, x, yPercentile, "spyWarning") : "";
  const latest = series[series.length - 1];
  const latestSpx = [...spxSeries].reverse().find((point) => point.time <= latest.time) || spxSeries[spxSeries.length - 1];
  const latestWarning = [...warningSeries].reverse().find((point) => point.time <= latest.time) || warningSeries[warningSeries.length - 1];
  const dateTicks = buildDateTicks(series, options.large ? 7 : 5);
  const spxLabel = spxSeries.length >= 2 ? `S&P 500 indexed ${latestSpx?.spxIndexed?.toFixed(0) || "--"}` : "S&P 500 indexed --";
  const warningLabel = warningSeries.length >= 2 ? `SPY Early Warning ${latestWarning?.spyWarning?.toFixed(0) || "--"}` : "SPY Early Warning --";
  return `
    <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Conditions score historical percentile trend versus S&P 500 and SPY Early Warning" data-macro-liquidity-chart>
      <rect x="0" y="0" width="${W}" height="${H}" fill="transparent"></rect>
      ${[20, 50, 80].map((tick) => `
        <line x1="${pad.l}" x2="${W - pad.r}" y1="${yPercentile(tick).toFixed(1)}" y2="${yPercentile(tick).toFixed(1)}"></line>
        <text x="8" y="${yPercentile(tick).toFixed(1)}" dy="4">p${tick}</text>
      `).join("")}
      ${dateTicks.map((point) => `
        <text x="${x(point.time).toFixed(1)}" y="${H - 8}" text-anchor="middle">${formatMonthLabel(point.time)}</text>
      `).join("")}
      <path d="${areaPath}" class="macro-liquidity-trend-area"></path>
      ${spxPath ? `<path d="${spxPath}" class="macro-liquidity-spx-line"></path>` : ""}
      ${warningPath ? `<path d="${warningPath}" class="macro-liquidity-spy-warning-line"></path>` : ""}
      <path d="${liquidityPath}" class="macro-liquidity-trend-line"></path>
      <line class="macro-liquidity-hover-guide" x1="${pad.l}" x2="${pad.l}" y1="${pad.t}" y2="${H - pad.b}"></line>
      <circle class="macro-liquidity-hover-dot liquidity" cx="${pad.l}" cy="${pad.t}" r="${options.large ? "5.2" : "4.2"}"></circle>
      <circle class="macro-liquidity-hover-dot spx" cx="${pad.l}" cy="${pad.t}" r="${options.large ? "5.0" : "4.0"}"></circle>
      <circle class="macro-liquidity-hover-dot spy-warning" cx="${pad.l}" cy="${pad.t}" r="${options.large ? "5.0" : "4.0"}"></circle>
      <circle class="macro-liquidity-trend-dot" cx="${x(latest.time).toFixed(1)}" cy="${yPercentile(latest.percentile).toFixed(1)}" r="${options.large ? "5.0" : "4.2"}"></circle>
      ${latestSpx ? `<circle class="macro-liquidity-spx-dot" cx="${x(latestSpx.time).toFixed(1)}" cy="${ySpx(latestSpx.spxIndexed).toFixed(1)}" r="${options.large ? "4.8" : "3.8"}"></circle>` : ""}
      ${latestWarning ? `<circle class="macro-liquidity-spy-warning-dot" cx="${x(latestWarning.time).toFixed(1)}" cy="${yPercentile(latestWarning.spyWarning).toFixed(1)}" r="${options.large ? "4.8" : "3.8"}"></circle>` : ""}
      <text x="${W - pad.r}" y="16" text-anchor="end">综合评分历史分位 · ${series.length} obs</text>
      <text x="${W - pad.r}" y="31" text-anchor="end" class="macro-liquidity-spx-label">${spxLabel}</text>
      <text x="${W - pad.r}" y="46" text-anchor="end" class="macro-liquidity-spy-warning-label">${warningLabel}</text>
      <text x="${W - 8}" y="${ySpx(scale.spxHigh).toFixed(1) + 4}" text-anchor="end" class="macro-liquidity-spx-axis">${scale.spxHigh.toFixed(0)}</text>
      <text x="${W - 8}" y="${ySpx(scale.spxLow).toFixed(1) + 4}" text-anchor="end" class="macro-liquidity-spx-axis">${scale.spxLow.toFixed(0)}</text>
      <text x="${x(latest.time).toFixed(1) - 8}" y="${Math.max(16, yPercentile(latest.percentile) - 8).toFixed(1)}" text-anchor="end">p${latest.percentile.toFixed(0)}</text>
    </svg>
  `;
}

function macroLiquidityEquityPanel() {
  return state.macroLiquidityEquity || DEFAULT_DATA.macroLiquidityEquity || {};
}

function spyWarningTrendPanel() {
  return state.spyEarlyWarning || DEFAULT_DATA.spyEarlyWarning || {};
}

function prepareMacroLiquidityComparisonSeries(trend, equityPanel = {}, warningPanel = {}) {
  const equityRows = Array.isArray(equityPanel.series) ? equityPanel.series : [];
  const spxByMonth = new Map();
  equityRows.forEach((point) => {
    const time = Date.parse(point.date);
    const spxIndexed = Number(point.sp500Indexed);
    if (!Number.isFinite(time) || !Number.isFinite(spxIndexed)) return;
    spxByMonth.set(monthKeyFromTime(time), {
      spxIndexed,
      sp500: Number(point.sp500),
      trailing3m: Number(point.sp500Trailing3m),
    });
  });
  const warningRows = Array.isArray(warningPanel?.trend?.points) ? warningPanel.trend.points : [];
  const warningByMonth = new Map();
  warningRows.forEach((point) => {
    const time = Date.parse(point.date);
    const score = Number(point.score);
    if (!Number.isFinite(time) || !Number.isFinite(score)) return;
    warningByMonth.set(monthKeyFromTime(time), {
      score: Math.max(0, Math.min(100, score)),
      regime: point.regime || "",
      regimeCn: point.regimeCn || "",
    });
  });
  const points = Array.isArray(trend?.points) ? trend.points : [];
  const series = points
    .map((point) => {
      const time = Date.parse(point.date);
      const spx = Number.isFinite(time) ? spxByMonth.get(monthKeyFromTime(time)) : null;
      const warning = Number.isFinite(time) ? warningByMonth.get(monthKeyFromTime(time)) : null;
      return {
        time,
        date: point.date,
        percentile: Number(point.percentile),
        score: Number(point.score),
        spxIndexed: spx?.spxIndexed,
        sp500: spx?.sp500,
        sp500Trailing3m: spx?.trailing3m,
        spyWarning: warning?.score,
        spyWarningRegime: warning?.regime,
        spyWarningRegimeCn: warning?.regimeCn,
      };
    })
    .filter((point) => Number.isFinite(point.time) && Number.isFinite(point.percentile));
  return {
    series,
    hasSpx: series.some((point) => Number.isFinite(point.spxIndexed)),
    hasSpyWarning: series.some((point) => Number.isFinite(point.spyWarning)),
  };
}

function monthKeyFromTime(time) {
  const date = new Date(time);
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}`;
}

function macroLiquidityComparisonScale(series, options = {}) {
  const W = options.large ? 980 : 620;
  const H = options.large ? 380 : 190;
  const pad = options.large ? { l: 46, r: 58, t: 30, b: 42 } : { l: 34, r: 44, t: 24, b: 28 };
  const minTime = Math.min(...series.map((point) => point.time));
  const maxTime = Math.max(...series.map((point) => point.time));
  const spxValues = series.map((point) => point.spxIndexed).filter(Number.isFinite);
  const spxMin = spxValues.length ? Math.min(...spxValues) : 100;
  const spxMax = spxValues.length ? Math.max(...spxValues) : 100;
  const spxPad = Math.max(6, (spxMax - spxMin) * 0.12);
  const spxLow = Math.max(0, spxMin - spxPad);
  const spxHigh = spxMax + spxPad;
  const x = (time) => pad.l + ((time - minTime) / Math.max(1, maxTime - minTime)) * (W - pad.l - pad.r);
  const yPercentile = (value) => pad.t + ((100 - Math.max(0, Math.min(100, value))) / 100) * (H - pad.t - pad.b);
  const ySpx = (value) => pad.t + ((spxHigh - value) / Math.max(1, spxHigh - spxLow)) * (H - pad.t - pad.b);
  return { W, H, pad, x, yPercentile, ySpx, spxLow, spxHigh };
}

function macroLiquidityPath(points, x, y, key) {
  return points
    .filter((point) => Number.isFinite(point[key]))
    .map((point, index) => `${index ? "L" : "M"}${x(point.time).toFixed(1)},${y(point[key]).toFixed(1)}`)
    .join(" ");
}

function bindMacroLiquidityTrendInteractions(chartNode, trend, options = {}) {
  const svg = chartNode?.querySelector("[data-macro-liquidity-chart]");
  const tooltip = $(options.tooltipSelector || "#macroLiquidityTrendTooltip");
  if (!svg || !tooltip) return;
  const prepared = prepareMacroLiquidityComparisonSeries(trend, options.equity || macroLiquidityEquityPanel(), options.warning || spyWarningTrendPanel());
  if (prepared.series.length < 2) return;
  const scale = macroLiquidityComparisonScale(prepared.series, options);
  const guide = svg.querySelector(".macro-liquidity-hover-guide");
  const liquidityDot = svg.querySelector(".macro-liquidity-hover-dot.liquidity");
  const spxDot = svg.querySelector(".macro-liquidity-hover-dot.spx");
  const spyWarningDot = svg.querySelector(".macro-liquidity-hover-dot.spy-warning");
  svg.addEventListener("mousemove", (event) => {
    const rect = svg.getBoundingClientRect();
    const svgX = ((event.clientX - rect.left) / Math.max(1, rect.width)) * scale.W;
    const point = nearestMacroLiquidityPoint(prepared.series, svgX, scale);
    if (!point) return;
    const pointX = scale.x(point.time);
    guide?.setAttribute("x1", pointX.toFixed(1));
    guide?.setAttribute("x2", pointX.toFixed(1));
    guide?.setAttribute("stroke-opacity", "0.42");
    liquidityDot?.setAttribute("cx", pointX.toFixed(1));
    liquidityDot?.setAttribute("cy", scale.yPercentile(point.percentile).toFixed(1));
    liquidityDot?.setAttribute("opacity", "1");
    if (Number.isFinite(point.spxIndexed)) {
      spxDot?.setAttribute("cx", pointX.toFixed(1));
      spxDot?.setAttribute("cy", scale.ySpx(point.spxIndexed).toFixed(1));
      spxDot?.setAttribute("opacity", "1");
    } else {
      spxDot?.setAttribute("opacity", "0");
    }
    if (Number.isFinite(point.spyWarning)) {
      spyWarningDot?.setAttribute("cx", pointX.toFixed(1));
      spyWarningDot?.setAttribute("cy", scale.yPercentile(point.spyWarning).toFixed(1));
      spyWarningDot?.setAttribute("opacity", "1");
    } else {
      spyWarningDot?.setAttribute("opacity", "0");
    }
    renderMacroLiquidityComparisonTooltip(tooltip, chartNode, event, point);
  });
  svg.addEventListener("mouseleave", () => {
    guide?.setAttribute("stroke-opacity", "0");
    liquidityDot?.setAttribute("opacity", "0");
    spxDot?.setAttribute("opacity", "0");
    spyWarningDot?.setAttribute("opacity", "0");
    tooltip.hidden = true;
  });
}

function nearestMacroLiquidityPoint(points, svgX, scale) {
  let best = null;
  let bestDistance = Number.POSITIVE_INFINITY;
  points.forEach((point) => {
    const distance = Math.abs(scale.x(point.time) - svgX);
    if (distance < bestDistance) {
      best = point;
      bestDistance = distance;
    }
  });
  return best;
}

function renderMacroLiquidityComparisonTooltip(tooltip, chartNode, event, point) {
  const spxText = Number.isFinite(point.spxIndexed) ? `S&P 500 indexed ${point.spxIndexed.toFixed(1)}` : "S&P 500 indexed --";
  const warningText = Number.isFinite(point.spyWarning)
    ? `SPY Early Warning ${point.spyWarning.toFixed(1)}${point.spyWarningRegimeCn ? ` · ${point.spyWarningRegimeCn}` : ""}`
    : "SPY Early Warning --";
  const trailing = Number.isFinite(point.sp500Trailing3m) ? ` · 3M ${formatSignedMetric(point.sp500Trailing3m, 2)}%` : "";
  tooltip.innerHTML = `
    <b>${escapeHtml(point.date)} · p${point.percentile.toFixed(0)}</b>
    <span>综合评分 ${Number.isFinite(point.score) ? point.score.toFixed(1) : "--"} · ${escapeHtml(spxText)}</span>
    <small>${escapeHtml(warningText)} · ${Number.isFinite(point.sp500) ? `SPX ${point.sp500.toFixed(2)}` : "SPX --"}${trailing}</small>
  `;
  const parentRect = (tooltip.offsetParent || chartNode).getBoundingClientRect();
  tooltip.hidden = false;
  const left = Math.min(Math.max(8, event.clientX - parentRect.left + 12), Math.max(8, parentRect.width - tooltip.offsetWidth - 8));
  const top = Math.min(Math.max(8, event.clientY - parentRect.top - 54), Math.max(8, parentRect.height - tooltip.offsetHeight - 8));
  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${top}px`;
}

function openMacroLiquidityTrendModal() {
  const modal = $("#macroLiquidityTrendModal");
  if (!modal) return;
  modal.hidden = false;
  document.body.classList.add("modal-open");
  renderMacroLiquidityTrendModalChart();
  $("#closeMacroLiquidityTrendModal")?.focus();
}

function closeMacroLiquidityTrendModal() {
  const modal = $("#macroLiquidityTrendModal");
  if (!modal) return;
  modal.hidden = true;
  document.body.classList.remove("modal-open");
}

function renderMacroLiquidityTrendModalChart() {
  const node = $("#macroLiquidityTrendModalChart");
  if (!node) return;
  const panel = state.macroLiquidity || DEFAULT_DATA.macroLiquidity || {};
  const equityPanel = macroLiquidityEquityPanel();
  const warningPanel = spyWarningTrendPanel();
  node.innerHTML = renderMacroLiquidityTrendChart(panel.trend || {}, { equity: equityPanel, warning: warningPanel, large: true });
  bindMacroLiquidityTrendInteractions(node, panel.trend || {}, {
    equity: equityPanel,
    warning: warningPanel,
    large: true,
    tooltipSelector: "#macroLiquidityTrendModalTooltip",
  });
}

function macroLiquidityTrendClass(value) {
  if (value === "上行") return "supportive";
  if (value === "下行") return "restrictive";
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || Math.abs(numeric) < 1) return "neutral";
  return numeric > 0 ? "supportive" : "restrictive";
}

function renderMacroLiquidityBalance(balance) {
  if (!Array.isArray(balance) || !balance.length) return "";
  return balance.map((item) => {
    const contribution = Number(item.contribution) || 0;
    const direction = item.direction || (contribution > 0 ? "supportive" : contribution < 0 ? "restrictive" : "neutral");
    return `
      <span class="${escapeHtml(direction)}">
        <b>${escapeHtml(item.label || "")}</b>
        <em>${Number(item.count) || 0}项</em>
        <strong>${contribution >= 0 ? "+" : ""}${contribution.toFixed(1)}</strong>
      </span>
    `;
  }).join("");
}

function renderMacroLiquidityImplications(implications) {
  if (!Array.isArray(implications) || !implications.length) return "";
  return implications.map((item) => `
    <span class="${escapeHtml(item.tone || "neutral")}">
      <b>${escapeHtml(item.label || "")}</b>
      <em>${escapeHtml(item.text || "")}</em>
    </span>
  `).join("");
}

function macroLiquidityLabel(score) {
  if (score >= 70) return "流动性宽松";
  if (score >= 55) return "边际宽松";
  if (score > 45) return "中性";
  if (score > 30) return "偏紧";
  return "紧缩压力";
}

function macroLiquidityClass(score) {
  if (score >= 55) return "supportive";
  if (score <= 45) return "restrictive";
  return "neutral";
}
