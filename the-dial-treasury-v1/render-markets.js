// render-markets.js — Global LPPL bubble monitor + regional monitor renderers (interleaved,
// share globalLpplBreach* helpers), split out of app.js (2026-06-20 Phase 3 全面重构,
// behavior-unchanged). Plain <script> loaded BEFORE app.js; global function declarations
// resolving app.js top-level state/utils at call time.

function renderGlobalLpplRisk(payload) {
  const item = payload && typeof payload === "object" ? payload : DEFAULT_DATA.globalLpplRisk;
  const indices = globalLpplIndexRows(item);
  const available = indices.filter((row) => row.available && Number.isFinite(Number(row.score)));
  const leader = available.slice().sort((a, b) => Number(b.score) - Number(a.score))[0] || null;
  const forwardLeader = available.slice().sort((a, b) => Number(globalLpplForwardSignal(b)?.score) - Number(globalLpplForwardSignal(a)?.score))[0] || null;
  if (!selectedGlobalLpplSymbol || !available.some((row) => row.symbol === selectedGlobalLpplSymbol)) {
    selectedGlobalLpplSymbol = leader?.symbol || available[0]?.symbol || "";
  }
  if (!item.available) {
    return `
      <div class="global-lppl-empty">
        <div>
          <span>Global LPPL Risk · 全球指数泡沫临界风险</span>
          <strong>--</strong>
        </div>
        <p>${escapeHtml(item.summary || "暂无全球LPPL风险评估")}</p>
        ${indices.length ? renderGlobalLpplIndexGrid(indices) : ""}
      </div>
    `;
  }
  const indexValidation = item.indexValidation && typeof item.indexValidation === "object" ? item.indexValidation : {};
  const forwardLeaderSignal = globalLpplForwardSignal(forwardLeader);
  const riskClass = forwardLeaderSignal ? spyWarningClass(Number(forwardLeaderSignal.score)) : leader ? spyWarningClass(Number(leader.score)) : "neutral";
  const highRiskCount = available.filter((row) => Number(row.score) >= 65).length;
  const forwardRiskCount = available.filter((row) => Number(globalLpplForwardSignal(row)?.score) >= 65).length;
  return `
    <div class="global-lppl-head ${riskClass}">
      <div>
        <span>Global LPPL Risk · 全球指数泡沫临界风险</span>
        <strong>${forwardLeader ? escapeHtml(forwardLeader.symbol) : leader ? escapeHtml(leader.symbol) : "--"}</strong>
      </div>
      <div>
        <b>${forwardLeaderSignal ? `前瞻压力 ${escapeHtml(forwardLeader.name || forwardLeader.symbol)} ${Number(forwardLeaderSignal.score).toFixed(1)}` : leader ? `${escapeHtml(leader.name || leader.symbol)} ${Number(leader.score).toFixed(1)}` : escapeHtml(item.regimeCn || item.regime || "--")} · ${escapeHtml(item.asOf || "--")}</b>
        <small>per-index only · ${available.length}/${indices.length} available · raw risk ${highRiskCount} · forward risk ${forwardRiskCount}</small>
      </div>
    </div>
    <p class="global-lppl-summary">${escapeHtml(item.summary || "")}</p>
    ${renderGlobalLpplBreadthConfirmation(item.breadthConfirmation)}
    ${indexValidation.summary ? `<p class="global-lppl-validation-summary">${escapeHtml(indexValidation.summary)}</p>` : ""}
    ${renderGlobalLpplPerIndexBacktestStrip(item)}
    <a class="global-lppl-regional-pointer" href="#regions">逐市场卡片、价格因子、配置建议与历史曲线见「地区监控」板块 →</a>
  `;
}

function globalLpplIndexRows(item) {
  return Array.isArray(item?.indices) ? item.indices : [];
}

function globalLpplIndexRow(item, symbol) {
  const normalized = String(symbol || "").toUpperCase();
  return globalLpplIndexRows(item).find((row) => String(row.symbol || "").toUpperCase() === normalized) || null;
}

function firstGlobalLpplSymbol(item) {
  const rows = globalLpplIndexRows(item).filter((row) => row.available && Number.isFinite(Number(row.score)));
  return (rows.slice().sort((a, b) => Number(b.score) - Number(a.score))[0] || rows[0] || {}).symbol || "";
}

function globalLpplIndexHistory(item, symbol) {
  const normalized = String(symbol || "").toUpperCase();
  const row = globalLpplIndexRow(item, normalized);
  if (row?.history && typeof row.history === "object") return row.history;
  const map = item?.perIndexHistory && typeof item.perIndexHistory === "object" ? item.perIndexHistory : {};
  return map[normalized] && typeof map[normalized] === "object" ? map[normalized] : { available: false, points: [] };
}

function globalLpplIndexBacktest(item, symbol) {
  const normalized = String(symbol || "").toUpperCase();
  const row = globalLpplIndexRow(item, normalized);
  if (row?.backtest && typeof row.backtest === "object") return row.backtest;
  const map = item?.perIndexBacktests && typeof item.perIndexBacktests === "object" ? item.perIndexBacktests : {};
  return map[normalized] && typeof map[normalized] === "object" ? map[normalized] : { available: false, horizonTests: [] };
}

function globalLpplForwardSignal(row) {
  return row?.forwardSignal && typeof row.forwardSignal === "object" && row.forwardSignal.available ? row.forwardSignal : null;
}

function renderGlobalLpplBreadthConfirmation(breadth) {
  if (!breadth || typeof breadth !== "object" || !breadth.available) return "";
  return `
    <div class="global-lppl-backtest breadth">
      <span>
        <b>市场宽度</b>
        <strong>${Number(breadth.riskCount) || 0}/${Number(breadth.sampleSize) || 0}</strong>
        <small>${escapeHtml(breadth.regimeCn || breadth.regime || "--")} · weighted ${formatPercentMetric(breadth.weightedRiskSharePct)}</small>
      </span>
      <span>
        <b>前瞻/CLIP</b>
        <strong>${Number(breadth.forwardRiskCount) || 0}/${Number(breadth.clipLockCount) || 0}</strong>
        <small>${escapeHtml(breadth.summary || "")}</small>
      </span>
    </div>
  `;
}

function globalLpplClipState(row, history = null) {
  if (row?.clipState && typeof row.clipState === "object" && row.clipState.available) return row.clipState;
  if (history?.clipState && typeof history.clipState === "object" && history.clipState.available) return history.clipState;
  return null;
}

function globalLpplClipSummary(clipState) {
  if (!clipState) return "";
  const locked = Boolean(clipState.clipLock);
  const status = locked ? (clipState.statusCn || "CLIP锁定") : clipState.statusCn || clipState.status || "CLIP";
  const statusText = String(status).toUpperCase().startsWith("CLIP") ? String(status) : `CLIP ${status}`;
  const tc = clipState.tcMedian ? `tc ${clipState.tcMedian}` : "";
  const windowDays = Number(clipState.tcWindowDays);
  const windowText = Number.isFinite(windowDays) ? `20-80 ${windowDays.toFixed(0)}D` : "";
  const leadDays = Number(clipState.medianLeadDays);
  const leadText = Number.isFinite(leadDays) ? `lead ${leadDays.toFixed(0)}D` : "";
  return [statusText, tc, windowText, leadText].filter(Boolean).join(" · ");
}

function globalLpplPointCriticalSummary(point) {
  if (!point?.criticalDate) return "";
  const days = Number(point.daysToCritical);
  return `critical ${point.criticalDate}${Number.isFinite(days) ? ` · ${days.toFixed(0)}D` : ""}`;
}

function globalLpplTcAggregationSummary(row) {
  const tc = row?.tcAggregation && typeof row.tcAggregation === "object" && row.tcAggregation.available ? row.tcAggregation : null;
  if (!tc) return "";
  const valid = Number(tc.validFitCount);
  const total = Number(tc.totalFitCount);
  const residual = Number(tc.residualPassRatioPct);
  return [
    `tc ${tc.tcMedian || "--"}`,
    Number.isFinite(valid) && Number.isFinite(total) ? `${valid}/${total} windows` : "",
    Number.isFinite(residual) ? `resid ${residual.toFixed(0)}%` : "",
    tc.windowAgreement ? `agree ${tc.windowAgreement}` : "",
  ].filter(Boolean).join(" · ");
}

function renderGlobalLpplPerIndexBacktestStrip(item) {
  const rows = globalLpplIndexRows(item).filter((row) => row.available && Number.isFinite(Number(row.score)));
  if (!rows.length) return `<div class="global-lppl-backtest"><span><b>逐市场验证</b><strong>--</strong><small>等待可回放指数样本</small></span></div>`;
  return `
    <div class="global-lppl-backtest">
      ${rows.slice(0, 4).map((row) => {
        const backtest = globalLpplIndexBacktest(item, row.symbol);
        const horizonTests = Array.isArray(backtest.horizonTests) ? backtest.horizonTests : [];
        const preferred = horizonTests.find((entry) => Number(entry.horizon) === 15) || horizonTests[0] || {};
        return `
          <span>
            <b>${escapeHtml(row.symbol || "")} 15D验证</b>
            <strong>${formatPercentMetric(preferred.precision)}</strong>
            <small>${Number(backtest.sampleSize) || 0} obs · ${Number(preferred.alertDays) || 0} alerts · false ${Number(preferred.falsePositives) || 0}</small>
          </span>
        `;
      }).join("")}
    </div>
  `;
}

function regionalMonitorPanel() {
  return state.regionalMonitor || DEFAULT_DATA.regionalMonitor || {};
}

function regionStatusClass(status) {
  if (status === "risk") return "risk";
  if (status === "watch") return "watch";
  if (status === "quiet") return "quiet";
  return "neutral";
}

function marketStateClass(state) {
  if (state === "stressed") return "risk";
  if (state === "constructive") return "quiet";
  return "neutral";
}

function regionStanceClass(stance) {
  if (stance === "underweight") return "risk";
  if (stance === "overweight") return "quiet";
  return "neutral";
}

function marketStateLabel(factors) {
  const cn = factors && (factors.marketStateCn || factors.marketState);
  return cn ? String(cn) : "--";
}

function regionalRepresentativeIndex(region) {
  const indices = Array.isArray(region.indices) ? region.indices : [];
  const withValidation = indices.filter((row) => row.factorValidation && row.factorValidation.available);
  if (!withValidation.length) return null;
  // Prefer the US benchmark (SPY) for the US region; otherwise the first validated index.
  return withValidation.find((row) => String(row.symbol).toUpperCase() === "SPY") || withValidation[0];
}

function globalLpplBreachEventsForSymbol(symbol) {
  const target = String(symbol || "").toUpperCase();
  const monitor = state.regionalMonitor || DEFAULT_DATA.regionalMonitor || {};
  const regions = Array.isArray(monitor.regions) ? monitor.regions : [];
  for (const region of regions) {
    const rep = regionalRepresentativeIndex(region);
    if (!rep || String(rep.symbol || "").toUpperCase() !== target) continue;
    const fa = region.factorAlert && typeof region.factorAlert === "object" ? region.factorAlert : {};
    if (fa.available && Array.isArray(fa.breachEvents)) return fa.breachEvents;
  }
  return [];
}

function globalLpplBreachMarkersSvg(symbol, scale) {
  const events = globalLpplBreachEventsForSymbol(symbol);
  if (!events.length) return "";
  const { x, pad, H, minTime, maxTime } = scale;
  const markers = events.map((event) => {
    const time = Date.parse(event && event.date || "");
    if (!Number.isFinite(time) || time < minTime || time > maxTime) return "";
    const px = x(time).toFixed(1);
    const cls = event && event.hit ? "hit" : "miss";
    return `<line class="global-lppl-breach-marker ${cls}" x1="${px}" x2="${px}" y1="${pad.t}" y2="${H - pad.b}"></line>`
      + `<polygon class="global-lppl-breach-flag ${cls}" points="${px},${pad.t} ${(Number(px) - 4).toFixed(1)},${pad.t - 6} ${(Number(px) + 4).toFixed(1)},${pad.t - 6}"></polygon>`;
  }).join("");
  return markers ? `<g class="global-lppl-breach-markers">${markers}</g>` : "";
}

function renderRegionalFactorValidation(region) {
  const representative = regionalRepresentativeIndex(region);
  if (!representative) return "";
  const validation = representative.factorValidation || {};
  const factors = Array.isArray(validation.factors) ? validation.factors : [];
  if (!factors.length) return "";
  const sorted = factors.slice().sort((a, b) => Math.abs(Number(b.oosIc3m) || 0) - Math.abs(Number(a.oosIc3m) || 0));
  const proxy = escapeHtml(representative.proxyNoteCn || representative.proxyNote || representative.symbol || "");
  const rows = sorted.map((row) => `
    <tr>
      <td class="sv-name">${escapeHtml(row.labelCn || row.label || row.id || "--")}</td>
      <td>${formatSignalIc(row.ic3m)}</td>
      <td>${formatSignalIc(row.oosIc3m)}</td>
      <td>${formatSignalRate(row.hitRateOos)} / ${formatSignalRate(row.baseRate)}</td>
      <td>${formatSignalLift(row.lift)}</td>
      <td>${formatSignalDays(row.leadTimeDays)}</td>
      <td>${signalValidationBadge(row.classification)}</td>
    </tr>
  `).join("");
  const composite = validation.composite && typeof validation.composite === "object" ? validation.composite : {};
  let compositeHtml = "";
  if (composite.available) {
    const weights = Array.isArray(composite.weights) ? composite.weights.filter((w) => Number(w.weight) > 0) : [];
    const weightText = weights.map((w) => `${escapeHtml(w.labelCn || w.id)} ${(Number(w.weight) * 100).toFixed(0)}%`).join(" · ");
    const beats = composite.beatsBestSingleFactor;
    const verdict = beats === true ? `<span class="sv-badge leading">优于最强单因子</span>` : beats === false ? `<span class="sv-badge none">未超过最强单因子</span>` : "";
    compositeHtml = `
      <div class="region-composite ${beats === true ? "beats" : ""}">
        <div class="region-composite-head">
          <strong>证据加权综合信号 · Composite</strong>
          <span>OOS IC 3M ${formatSignalIc(composite.oosIc3m)} · 命中 ${formatSignalRate(composite.hitRateOos)}/基准 ${formatSignalRate(composite.baseRate)} · Lift ${formatSignalLift(composite.lift)} · ${signalValidationBadge(composite.classification)}</span>
          ${verdict}
        </div>
        ${weightText ? `<span class="region-composite-weights">校准段权重: ${weightText}</span>` : ""}
      </div>
    `;
  }
  return `
    <h4 class="sv-heading">本地区因子前瞻验证 · ${escapeHtml(region.nameCn || region.name || "")} <small>(对该地区自身远期收益, 走出样本; 代理 ${proxy})</small></h4>
    ${compositeHtml}
    <div class="sv-table-wrap">
      <table class="sv-table">
        <thead><tr><th>因子</th><th>IC 3M</th><th>OOS IC 3M</th><th>命中/基准</th><th>Lift</th><th>提前量</th><th>分类</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

function globalLpplPriceFactorSummary(factors) {
  if (!factors || typeof factors !== "object" || !factors.available) return "";
  const parts = [`市场状态 ${escapeHtml(marketStateLabel(factors))}`];
  if (Number.isFinite(Number(factors.return3m))) parts.push(`3M ${formatSignedMetric(factors.return3m, 1)}%`);
  if (Number.isFinite(Number(factors.realizedVol))) parts.push(`波动 ${Number(factors.realizedVol).toFixed(0)}%`);
  if (Number.isFinite(Number(factors.drawdownFromHigh))) parts.push(`回撤 ${formatSignedMetric(factors.drawdownFromHigh, 0)}%`);
  if (!factors.isBenchmark && Number.isFinite(Number(factors.relativeStrength3m))) parts.push(`相对美国 ${formatSignedMetric(factors.relativeStrength3m, 1)}%`);
  return parts.join(" · ");
}

function renderRegionalMonitor() {
  const panel = regionalMonitorPanel();
  const tabsNode = $("#regionalMonitorTabs");
  if (!tabsNode) return;
  const aggNode = $("#regionalMonitorAggregate");
  const gridNode = $("#regionalMonitorGrid");
  const validationNode = $("#regionalMonitorValidation");
  const chartsNode = $("#regionalMonitorCharts");
  const rotationNode = $("#regionalMonitorRotation");
  const summaryNode = $("#regionalMonitorSummary");
  const methodNode = $("#regionalMonitorMethod");
  const regions = (Array.isArray(panel.regions) ? panel.regions : []).filter(
    (region) => region && Number(region.aggregate && region.aggregate.availableCount) > 0
  );
  if (methodNode) methodNode.textContent = panel.available ? `${regions.length} regions · per-region LPPL factors` : "per-region bubble factors";
  if (summaryNode) summaryNode.textContent = panel.summary || (panel.available ? "" : "等待数据");
  if (!panel.available || !regions.length) {
    tabsNode.innerHTML = "";
    if (rotationNode) rotationNode.innerHTML = "";
    if (aggNode) aggNode.innerHTML = "";
    if (gridNode) gridNode.innerHTML = `<div class="empty-state compact">${escapeHtml(panel.reason || panel.summary || "暂无地区LPPL数据")}</div>`;
    if (validationNode) validationNode.innerHTML = "";
    if (chartsNode) chartsNode.innerHTML = "";
    return;
  }
  if (rotationNode) {
    const rotation = panel.rotation && typeof panel.rotation === "object" ? panel.rotation : {};
    const clusters = Array.isArray(rotation.reduceClusters) ? rotation.reduceClusters : [];
    const clusterChips = clusters.map((cluster) => {
      const band = Array.isArray(cluster.exposureBandPct) ? cluster.exposureBandPct : null;
      const bandText = band ? ` ${Number(band[0]).toFixed(0)}-${Number(band[1]).toFixed(0)}%` : "";
      const names = (cluster.names || []).join("+");
      return `<span class="region-reduce-cluster ${cluster.merged ? "merged" : ""}">${escapeHtml(names)}${escapeHtml(bandText)}${cluster.merged ? " · 共享额度" : ""}</span>`;
    }).join("");
    const clusterRow = clusterChips
      ? `<div class="region-reduce-clusters">减持风险预算: ${clusterChips}</div>`
      : "";
    rotationNode.innerHTML = rotation.available
      ? `<div class="region-rotation-card"><strong>地区轮动建议 · Regional Rotation</strong><span>${escapeHtml(rotation.summary || "")}</span>${clusterRow}</div>`
      : "";
  }
  if (!regions.some((region) => region.key === selectedRegionKey)) {
    const alerting = regions.find((region) => (panel.alertingRegions || []).includes(region.key));
    selectedRegionKey = (alerting || regions[0]).key;
  }
  tabsNode.innerHTML = regions.map((region) => {
    const agg = region.aggregate || {};
    const score = Number(agg.maxScore);
    const alloc = region.allocation && typeof region.allocation === "object" ? region.allocation : {};
    const stancePill = alloc.stanceCn
      ? `<span class="region-tab-stance ${regionStanceClass(alloc.stance)}">${escapeHtml(alloc.stanceCn)}</span>`
      : "";
    const breached = region.factorAlert && region.factorAlert.available && region.factorAlert.state === "breached";
    const breachMark = breached ? `<span class="region-tab-breach" title="已验证领先因子突破阈值">⚠</span>` : "";
    return `
      <button type="button" role="tab" class="region-tab ${regionStatusClass(agg.status)} ${region.key === selectedRegionKey ? "active" : ""}" data-region-key="${escapeHtml(region.key)}" aria-selected="${region.key === selectedRegionKey ? "true" : "false"}">
        <span class="region-tab-name">${breachMark}${escapeHtml(region.nameCn || region.name || region.key)}${stancePill}</span>
        <span class="region-tab-score">${Number.isFinite(score) ? score.toFixed(0) : "--"}</span>
        <span class="region-tab-status">${escapeHtml(agg.statusCn || "--")}</span>
      </button>
    `;
  }).join("");
  const active = regions.find((region) => region.key === selectedRegionKey) || regions[0];
  const agg = active.aggregate || {};
  if (aggNode) {
    const days = Number(agg.minDaysToCritical);
    const daysText = Number.isFinite(days) ? `最近临界窗口约 ${days} 个交易日` : "无临界窗口告警";
    const score = Number(agg.maxScore);
    const pf = agg.priceFactors && typeof agg.priceFactors === "object" ? agg.priceFactors : {};
    const factorStrip = pf.available ? `
      <div class="region-factor-strip">
        <span class="region-factor-state ${marketStateClass(pf.marketState)}">市场状态 ${escapeHtml(marketStateLabel(pf))}</span>
        <span>3M 动量 <strong>${formatSignedMetric(pf.return3m, 1)}%</strong></span>
        <span>年化波动 <strong>${Number.isFinite(Number(pf.realizedVol)) ? Number(pf.realizedVol).toFixed(0) + "%" : "--"}</strong></span>
        <span>距高点 <strong>${formatSignedMetric(pf.worstDrawdownFromHigh, 0)}%</strong></span>
        <span>相对美国 <strong>${Number.isFinite(Number(pf.relativeStrength3m)) ? formatSignedMetric(pf.relativeStrength3m, 1) + "%" : "—"}</strong></span>
      </div>
    ` : "";
    const fa = active.factorAlert && typeof active.factorAlert === "object" ? active.factorAlert : {};
    const sourceTag = fa.source === "composite" ? `<span class="region-alert-source">综合</span>` : "";
    const alertBanner = fa.available && fa.state !== "normal" ? `
      <div class="region-factor-alert ${fa.state === "breached" ? "breached" : "approaching"}">
        <span class="region-factor-alert-tag">${fa.state === "breached" ? "⚠ 信号突破" : "信号逼近"}</span>
        <span>${sourceTag}${escapeHtml(fa.factorLabelCn || "")} 当前 <strong>${escapeHtml(String(fa.current))}</strong> / 验证阈值 ${escapeHtml(String(fa.threshold))}${fa.evidence ? ` · ${escapeHtml(fa.evidence)}` : ""}${fa.trackRecord ? ` · ${escapeHtml(fa.trackRecord)}` : ""}</span>
      </div>
    ` : "";
    const breachEvents = fa.available && Array.isArray(fa.breachEvents) ? fa.breachEvents : [];
    const timelineRep = regionalRepresentativeIndex(active);
    const timelineSymbol = timelineRep ? String(timelineRep.symbol || "").toUpperCase() : "";
    const breachTimeline = breachEvents.length ? `
      <button type="button" class="region-breach-timeline${timelineSymbol ? " clickable" : ""}"${timelineSymbol ? ` data-global-lppl-symbol="${escapeHtml(timelineSymbol)}" title="点击查看 ${escapeHtml(timelineSymbol)} 历史曲线"` : ""}>
        <span class="region-breach-timeline-label">历史突破回放(近${breachEvents.length}次, ●=随后回撤命中)${timelineSymbol ? " · 点击看历史图" : ""}:</span>
        <span class="region-breach-dots">${breachEvents.map((event) => {
          const hit = event && event.hit;
          const dd = Number(event && event.drawdownPct);
          const title = `${escapeHtml(String(event && event.date || ""))}${Number.isFinite(dd) ? ` 后续回撤 ${dd.toFixed(1)}%` : ""}`;
          return `<span class="region-breach-dot ${hit ? "hit" : "miss"}" title="${title}">${hit ? "●" : "○"}</span>`;
        }).join("")}</span>
      </button>
    ` : "";
    const alloc = active.allocation && typeof active.allocation === "object" ? active.allocation : {};
    const band = Array.isArray(alloc.exposureBandPct) ? alloc.exposureBandPct : null;
    const allocBlock = alloc.stanceCn ? `
      <div class="region-alloc ${regionStanceClass(alloc.stance)}">
        <div class="region-alloc-head">
          <span class="region-alloc-stance">${escapeHtml(alloc.stanceCn)}</span>
          ${band ? `<span class="region-alloc-band">仓位 ${Number(band[0]).toFixed(0)}-${Number(band[1]).toFixed(0)}%</span>` : ""}
          <span class="region-alloc-conf">置信 ${escapeHtml(alloc.confidenceCn || "--")}</span>
        </div>
        <span class="region-alloc-rationale">${escapeHtml(alloc.rationale || "")}</span>
      </div>
    ` : "";
    const internal = active.internalRotation && typeof active.internalRotation === "object" ? active.internalRotation : {};
    const internalBlock = internal.available ? `
      <div class="region-internal-rotation ${internal.tilt === "balanced" ? "balanced" : "tilted"}">
        <strong>美股内部轮动 · ${escapeHtml(internal.tiltCn || "")}</strong>
        <span>${escapeHtml(internal.rationale || "")}</span>
      </div>
    ` : "";
    aggNode.innerHTML = `
      <div class="region-agg ${regionStatusClass(agg.status)}">
        <strong>${escapeHtml(active.nameCn || active.name)}</strong>
        <span>泡沫: ${escapeHtml(agg.statusCn || "--")} · 峰值评分 ${Number.isFinite(score) ? score.toFixed(0) : "--"} · ${daysText} · ${Number(agg.availableCount) || 0}/${Number(agg.indexCount) || 0} 指数可用</span>
      </div>
      ${factorStrip}
      ${alertBanner}
      ${breachTimeline}
      ${internalBlock}
      ${allocBlock}
    `;
  }
  if (gridNode) gridNode.innerHTML = renderGlobalLpplIndexGrid(active.indices || []);
  if (validationNode) validationNode.innerHTML = renderRegionalFactorValidation(active);
  const diversificationNode = $("#regionalMonitorDiversification");
  if (diversificationNode) diversificationNode.innerHTML = renderRegionalDiversification(panel.diversification);
  if (chartsNode) {
    const item = state.globalLpplRisk || DEFAULT_DATA.globalLpplRisk;
    const chartable = (active.indices || []).filter((row) => row.available && globalLpplIndexHistory(item, row.symbol).available);
    chartsNode.innerHTML = chartable.length
      ? `<div class="global-lppl-chart-grid">${chartable.map((row) => renderGlobalLpplRiskHistoryChart(item, { symbol: row.symbol, fullWidth: true })).join("")}</div>`
      : "";
  }
}

function regionCorrelationClass(corr) {
  const value = Number(corr);
  if (!Number.isFinite(value)) return "neutral";
  if (value >= 0.7) return "risk";
  if (value <= 0.3) return "quiet";
  return "neutral";
}

function renderRegionalDiversification(diversification) {
  const div = diversification && typeof diversification === "object" ? diversification : {};
  if (!div.available) return "";
  const matrix = Array.isArray(div.matrix) ? div.matrix : [];
  const stats = Array.isArray(div.regionStats) ? div.regionStats : [];
  const pairs = matrix.slice().sort((a, b) => Number(b.corr) - Number(a.corr)).map((pair) => `
    <span class="region-corr-pair ${regionCorrelationClass(pair.corr)}">${escapeHtml(pair.aCn)}·${escapeHtml(pair.bCn)} ${Number(pair.corr) >= 0 ? "+" : ""}${Number(pair.corr).toFixed(2)}</span>
  `).join("");
  const statText = stats.map((s) => `${escapeHtml(s.nameCn)} ${Number(s.avgCorr) >= 0 ? "+" : ""}${Number(s.avgCorr).toFixed(2)}`).join(" · ");
  return `
    <h4 class="sv-heading">跨地区相关性与分散度 · Diversification <small>(周度收益两两相关; 高=同向风险冗余, 低=分散价值)</small></h4>
    <div class="region-diversification">
      <p class="region-diversification-summary">${escapeHtml(div.summary || "")}</p>
      <div class="region-corr-pairs">${pairs}</div>
      ${statText ? `<div class="region-corr-stats">平均相关性: ${statText}</div>` : ""}
    </div>
  `;
}

function renderGlobalLpplIndexGrid(indices) {
  return `
    <div class="global-lppl-index-grid">
      ${indices.map((row) => {
        const symbol = String(row.symbol || "").toUpperCase();
        const score = Number(row.score);
        const confidence = Number(row.confidence);
        const validation = row.validation && typeof row.validation === "object" ? row.validation : {};
        const forwardSignal = globalLpplForwardSignal(row);
        const clipText = globalLpplClipSummary(globalLpplClipState(row));
        const tcText = globalLpplTcAggregationSummary(row);
        const riskClass = row.available ? spyWarningClass(score) : "neutral";
        const validationText = row.available && validation.symbol
          ? `15D验证 ${formatPercentMetric(validation.precision15d)} · ${escapeHtml(validation.validationRoleCn || validation.validationRole || "")}`
          : "";
        const forwardText = forwardSignal
          ? `前瞻压力 ${Number(forwardSignal.score).toFixed(0)} · ${escapeHtml(forwardSignal.regimeCn || forwardSignal.regime || "")} · 20D ${formatSignedMetric(forwardSignal.scoreMomentum20d, 1)}`
          : "";
        const factorText = globalLpplPriceFactorSummary(row.priceFactors);
        return `
          <div class="global-lppl-index-card ${riskClass} ${row.available ? "" : "missing"}">
            <span>${escapeHtml(row.name || row.symbol || "")}<small>${escapeHtml(row.proxyNoteCn || row.proxyNote || row.region || row.symbol || "")}</small></span>
            <strong>${row.available && Number.isFinite(score) ? score.toFixed(0) : "--"}</strong>
            <b>${escapeHtml(row.statusCn || row.status || "--")}</b>
            <small>${row.available ? `criticalDate ${escapeHtml(row.criticalDate || "--")} · ${Number(row.daysToCritical) || "--"}D · fitR2 ${formatNumberMetric(row.fitR2, 2)} · conf ${formatPercentMetric(confidence * 100)}` : escapeHtml(row.reason || "source unavailable")}</small>
            ${tcText ? `<small>${escapeHtml(tcText)}</small>` : ""}
            ${forwardText ? `<small>${forwardText}</small>` : ""}
            ${factorText ? `<small class="global-lppl-factor-note">${factorText}</small>` : ""}
            ${clipText ? `<small class="global-lppl-clip-note">${escapeHtml(clipText)}</small>` : ""}
            ${validationText ? `<small>${validationText}</small>` : ""}
            ${row.available ? `<button class="icon-btn chart-expand-btn expandGlobalLpplRiskHistory" type="button" data-global-lppl-symbol="${escapeHtml(symbol)}" title="放大查看${escapeHtml(symbol)} LPPL历史曲线" aria-label="放大查看${escapeHtml(symbol)} LPPL历史曲线">⛶</button>` : ""}
          </div>
        `;
      }).join("")}
    </div>
  `;
}

function renderGlobalLpplIndexHistoryCharts(item) {
  const rows = globalLpplIndexRows(item).filter((row) => row.available && globalLpplIndexHistory(item, row.symbol).available);
  if (!rows.length) return `<div class="empty-state compact">LPPL逐市场历史曲线样本不足</div>`;
  return `
    <div class="global-lppl-chart-grid">
      ${rows.map((row) => renderGlobalLpplRiskHistoryChart(item, { symbol: row.symbol, fullWidth: true })).join("")}
    </div>
  `;
}

function prepareGlobalLpplHistorySeries(item, symbol) {
  const activeSymbol = String(symbol || selectedGlobalLpplSymbol || firstGlobalLpplSymbol(item) || "").toUpperCase();
  const row = globalLpplIndexRow(item, activeSymbol) || {};
  const history = globalLpplIndexHistory(item, activeSymbol);
  const raw = Array.isArray(history?.points) ? history.points : [];
  const series = raw.map((point) => ({
    date: point.date,
    time: Date.parse(point.date || ""),
    score: Number(point.score),
    indexedClose: Number(point.indexedClose),
    close: Number(point.close),
    criticalDate: point.criticalDate,
    daysToCritical: Number(point.daysToCritical),
    passesLpplCoreDiagnostics: Boolean(point.passesLpplCoreDiagnostics),
  })).filter((point) => Number.isFinite(point.time) && Number.isFinite(point.score));
  return {
    symbol: activeSymbol,
    row,
    history,
    series,
    priceSeries: series.filter((point) => Number.isFinite(point.indexedClose)),
  };
}

function sampleGlobalLpplHistorySeries(series, maxPoints = GLOBAL_LPPL_INLINE_HISTORY_MAX_POINTS) {
  if (!Array.isArray(series) || series.length <= maxPoints) return series;
  if (maxPoints < 2) return series.slice(-Math.max(0, maxPoints));
  const last = series.length - 1;
  return Array.from({ length: maxPoints }, (_, index) => series[Math.round(index * last / (maxPoints - 1))]);
}

function globalLpplHistoryScale(series, priceSeries, options = {}) {
  const W = options.large || options.fullWidth ? 1180 : 840;
  const H = options.large ? 420 : options.fullWidth ? 300 : 190;
  const pad = options.large || options.fullWidth ? { l: 48, r: 72, t: 34, b: 40 } : { l: 34, r: 48, t: 24, b: 28 };
  const minTime = Math.min(...series.map((point) => point.time));
  const maxTime = Math.max(...series.map((point) => point.time));
  const priceValues = priceSeries.map((point) => point.indexedClose).filter(Number.isFinite);
  const priceMin = priceValues.length ? Math.min(...priceValues) : 100;
  const priceMax = priceValues.length ? Math.max(...priceValues) : 100;
  const pricePad = Math.max(4, (priceMax - priceMin) * 0.12);
  const priceLow = Math.max(0, priceMin - pricePad);
  const priceHigh = priceMax + pricePad;
  const x = (time) => pad.l + ((time - minTime) / Math.max(1, maxTime - minTime)) * (W - pad.l - pad.r);
  const yRisk = (value) => pad.t + ((100 - Math.max(0, Math.min(100, value))) / 100) * (H - pad.t - pad.b);
  const yPrice = (value) => pad.t + ((priceHigh - value) / Math.max(1, priceHigh - priceLow)) * (H - pad.t - pad.b);
  return { W, H, pad, minTime, maxTime, priceLow, priceHigh, x, yRisk, yPrice };
}

function renderGlobalLpplRiskHistoryChart(item, options = {}) {
  const { symbol, row, history, series } = prepareGlobalLpplHistorySeries(item, options.symbol);
  const chartSeries = options.large ? series : sampleGlobalLpplHistorySeries(series);
  const chartPriceSeries = chartSeries.filter((point) => Number.isFinite(point.indexedClose));
  if (chartSeries.length < 2) return `<div class="empty-state compact">LPPL历史曲线样本不足</div>`;
  const scale = globalLpplHistoryScale(chartSeries, chartPriceSeries, options);
  const { W, H, pad, priceLow, priceHigh, x, yRisk, yPrice } = scale;
  const riskPath = macroLiquidityPath(chartSeries, x, yRisk, "score");
  const pricePath = chartPriceSeries.length >= 2 ? macroLiquidityPath(chartPriceSeries, x, yPrice, "indexedClose") : "";
  const latest = chartSeries[chartSeries.length - 1];
  const clipText = globalLpplClipSummary(globalLpplClipState(row, history));
  const ticks = buildDateTicks(chartSeries, options.large ? 8 : 5);
  const interactiveLayer = options.interactive ? `
        <line class="global-lppl-hover-guide" x1="${pad.l}" x2="${pad.l}" y1="${pad.t}" y2="${H - pad.b}" stroke-opacity="0"></line>
        <circle class="global-lppl-hover-dot risk" cx="${x(latest.time).toFixed(1)}" cy="${yRisk(latest.score).toFixed(1)}" r="5" opacity="0"></circle>
        <rect x="${pad.l}" y="${pad.t}" width="${W - pad.l - pad.r}" height="${H - pad.t - pad.b}" fill="transparent"></rect>
  ` : "";
  return `
    <div class="global-lppl-history-chart ${options.large ? "large" : ""} ${options.fullWidth ? "full-width" : ""}">
      <div class="equity-risk-history-head">
        <span>${escapeHtml(symbol || "LPPL")} 历史曲线</span>
        <div class="equity-risk-history-actions">
          <b>${escapeHtml(row.name || symbol || "LPPL")} risk vs own indexed price</b>
          ${options.large ? "" : `<button class="icon-btn chart-expand-btn expandGlobalLpplRiskHistory" type="button" data-global-lppl-symbol="${escapeHtml(symbol)}" title="放大查看${escapeHtml(symbol)} LPPL历史曲线" aria-label="放大查看${escapeHtml(symbol)} LPPL历史曲线">⛶</button>`}
        </div>
      </div>
      ${clipText ? `<small class="global-lppl-clip-note">${escapeHtml(clipText)}</small>` : ""}
      ${options.large && globalLpplBreachEventsForSymbol(symbol).length ? `<small class="global-lppl-breach-legend">▲ 历史突破标记: <i class="bm hit"></i>红=突破后回撤命中 · <i class="bm miss"></i>灰=未命中</small>` : ""}
      <svg data-global-lppl-history-chart data-global-lppl-symbol="${escapeHtml(symbol)}" viewBox="0 0 ${W} ${H}" role="img" aria-label="${escapeHtml(symbol)} LPPL risk historical curve versus indexed price">
        <rect x="0" y="0" width="${W}" height="${H}" fill="transparent"></rect>
        ${[45, 65, 75].map((tick) => `
          <line x1="${pad.l}" x2="${W - pad.r}" y1="${yRisk(tick).toFixed(1)}" y2="${yRisk(tick).toFixed(1)}" class="${tick === 65 ? "global-lppl-threshold-line strong" : "global-lppl-threshold-line"}"></line>
          <text x="8" y="${yRisk(tick).toFixed(1)}" dy="4">${tick}</text>
        `).join("")}
        ${ticks.map((point) => `<text x="${x(point.time).toFixed(1)}" y="${H - 8}" text-anchor="middle">${formatMonthLabel(point.time)}</text>`).join("")}
        ${options.large ? globalLpplBreachMarkersSvg(symbol, scale) : ""}
        ${pricePath ? `<path d="${pricePath}" class="global-lppl-price-line"></path>` : ""}
        <path d="${riskPath}" class="global-lppl-score-line"></path>
        <circle class="global-lppl-score-dot" cx="${x(latest.time).toFixed(1)}" cy="${yRisk(latest.score).toFixed(1)}" r="4.2"></circle>
        <text x="${W - pad.r}" y="15" text-anchor="end">${escapeHtml(symbol)} LPPL ${latest.score.toFixed(1)}</text>
        ${Number.isFinite(latest.indexedClose) ? `<text x="${W - pad.r}" y="30" text-anchor="end" class="global-lppl-price-label">${escapeHtml(symbol)} indexed ${latest.indexedClose.toFixed(0)}</text>` : ""}
        <text x="${W - 8}" y="${yPrice(priceHigh).toFixed(1) + 4}" text-anchor="end" class="global-lppl-price-axis">${priceHigh.toFixed(0)}</text>
        <text x="${W - 8}" y="${yPrice(priceLow).toFixed(1) + 4}" text-anchor="end" class="global-lppl-price-axis">${priceLow.toFixed(0)}</text>
        ${interactiveLayer}
      </svg>
    </div>
  `;
}

function renderGlobalLpplRiskHistoryModalStats(item) {
  const { symbol, row, history, series } = prepareGlobalLpplHistorySeries(item, selectedGlobalLpplSymbol);
  const backtest = globalLpplIndexBacktest(item, symbol);
  const horizonTests = Array.isArray(backtest.horizonTests) ? backtest.horizonTests : [];
  const preferred = horizonTests.find((row) => Number(row.horizon) === 15) || horizonTests[0] || {};
  const cluster = backtest.alertClusterTest && typeof backtest.alertClusterTest === "object" ? backtest.alertClusterTest : {};
  const clipState = globalLpplClipState(row, history);
  if (series.length < 2) return `<div class="empty-state compact">LPPL历史样本不足</div>`;
  const latest = series[series.length - 1];
  return [
    ["指数", `${symbol || "--"} ${row.name ? `· ${row.name}` : ""}`],
    ["样本", `${series.length} pts`],
    ["区间", `${series[0].date} / ${latest.date}`],
    ["最新LPPL", latest.score.toFixed(1)],
    ["价格指数", Number.isFinite(latest.indexedClose) ? latest.indexedClose.toFixed(1) : "--"],
    ["CLIP", clipState ? (clipState.statusCn || clipState.status || "--") : "--"],
    ["tc中位", clipState?.tcMedian || "--"],
    ["tc窗口", Number.isFinite(Number(clipState?.tcWindowDays)) ? `${Number(clipState.tcWindowDays).toFixed(0)}D` : "--"],
    ["阈值", `score≥${Number(backtest.threshold) || 65}`],
    ["15D精确率", formatPercentMetric(preferred.precision)],
    ["误报", `${Number(preferred.falsePositives) || 0}`],
    ["簇命中率", formatPercentMetric(cluster.precision)],
    ["最大误报簇", `${Number(cluster.maxFalseClusterDays) || 0} pts`],
  ].map(([label, value]) => `
    <div class="history-stat">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(String(value))}</strong>
    </div>
  `).join("");
}

function openGlobalLpplRiskHistoryModal(symbol = "") {
  const modal = $("#globalLpplRiskHistoryModal");
  if (!modal) return;
  const item = state.globalLpplRisk || DEFAULT_DATA.globalLpplRisk;
  selectedGlobalLpplSymbol = String(symbol || selectedGlobalLpplSymbol || firstGlobalLpplSymbol(item) || "").toUpperCase();
  modal.hidden = false;
  document.body.classList.add("modal-open");
  renderGlobalLpplRiskHistoryModalChart();
  $("#closeGlobalLpplRiskHistoryModal")?.focus();
}

function closeGlobalLpplRiskHistoryModal() {
  const modal = $("#globalLpplRiskHistoryModal");
  if (!modal) return;
  modal.hidden = true;
  document.body.classList.remove("modal-open");
}

function renderGlobalLpplRiskHistoryModalChart() {
  const item = state.globalLpplRisk || DEFAULT_DATA.globalLpplRisk;
  const chartNode = $("#globalLpplRiskHistoryModalChart");
  const statsNode = $("#globalLpplRiskHistoryModalStats");
  const titleNode = $("#globalLpplRiskHistoryModalTitle");
  const symbol = selectedGlobalLpplSymbol || firstGlobalLpplSymbol(item);
  if (titleNode) titleNode.textContent = `Global LPPL Risk · ${symbol || "--"} 历史验证`;
  if (statsNode) statsNode.innerHTML = renderGlobalLpplRiskHistoryModalStats(item);
  if (!chartNode) return;
  chartNode.innerHTML = renderGlobalLpplRiskHistoryChart(item, { symbol, large: true, interactive: true });
  bindGlobalLpplRiskHistoryInteractions(chartNode, item, { symbol, large: true, tooltipSelector: "#globalLpplRiskHistoryModalTooltip" });
}

function bindGlobalLpplRiskHistoryInteractions(chartNode, item, options = {}) {
  const svg = chartNode?.querySelector("[data-global-lppl-history-chart]");
  const tooltip = $(options.tooltipSelector || "#globalLpplRiskHistoryModalTooltip");
  if (!svg || !tooltip) return;
  const { symbol, series, priceSeries } = prepareGlobalLpplHistorySeries(item, options.symbol);
  if (series.length < 2) return;
  const scale = globalLpplHistoryScale(series, priceSeries, options);
  const guide = svg.querySelector(".global-lppl-hover-guide");
  const riskDot = svg.querySelector(".global-lppl-hover-dot.risk");
  svg.addEventListener("mousemove", (event) => {
    const rect = svg.getBoundingClientRect();
    const svgX = ((event.clientX - rect.left) / Math.max(1, rect.width)) * scale.W;
    const point = nearestEquityRiskHistoryPoint(series, svgX, scale);
    if (!point) return;
    const pointX = scale.x(point.time);
    guide?.setAttribute("x1", pointX.toFixed(1));
    guide?.setAttribute("x2", pointX.toFixed(1));
    guide?.setAttribute("stroke-opacity", "0.42");
    riskDot?.setAttribute("cx", pointX.toFixed(1));
    riskDot?.setAttribute("cy", scale.yRisk(point.score).toFixed(1));
    riskDot?.setAttribute("opacity", "1");
    tooltip.innerHTML = `
      <b>${escapeHtml(point.date)} · ${escapeHtml(symbol)} LPPL ${point.score.toFixed(1)}</b>
      <span>${escapeHtml(symbol)} indexed ${Number.isFinite(point.indexedClose) ? point.indexedClose.toFixed(1) : "--"} · close ${Number.isFinite(point.close) ? point.close.toFixed(2) : "--"}</span>
      <small>${escapeHtml(globalLpplPointCriticalSummary(point) || "per-index LPPL replay")} · no blended global score</small>
    `;
    const parentRect = (tooltip.offsetParent || chartNode).getBoundingClientRect();
    tooltip.hidden = false;
    tooltip.style.left = `${Math.min(Math.max(8, event.clientX - parentRect.left + 12), Math.max(8, parentRect.width - tooltip.offsetWidth - 8))}px`;
    tooltip.style.top = `${Math.min(Math.max(8, event.clientY - parentRect.top - 58), Math.max(8, parentRect.height - tooltip.offsetHeight - 8))}px`;
  });
  svg.addEventListener("mouseleave", () => {
    guide?.setAttribute("stroke-opacity", "0");
    riskDot?.setAttribute("opacity", "0");
    tooltip.hidden = true;
  });
}
