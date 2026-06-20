// render-equity.js — Equity short-term risk panel + history chart/modal renderers,
// split out of app.js (2026-06-20 Phase 3 全面重构, behavior-unchanged). Plain <script>
// loaded BEFORE app.js; global function declarations resolving app.js top-level state/
// utils (state, $, escapeHtml, t, …) at call time.

function renderEquityShortTermRisk(risk) {
  const item = risk && typeof risk === "object" ? risk : DEFAULT_DATA.equityShortTermRisk;
  if (!item.available) {
    return `<div class="empty-state compact">${escapeHtml(item.summary || "暂无短期股市风险指标")}</div>`;
  }
  const score = Number(item.score);
  const baseScore = Number(item.baseScore);
  const riskClass = spyWarningClass(score);
  const allocation = item.allocation && typeof item.allocation === "object" ? item.allocation : {};
  const components = Array.isArray(item.components) ? item.components : [];
  const drivers = Array.isArray(item.drivers) ? item.drivers : [];
  const guard = item.lookAheadGuard && typeof item.lookAheadGuard === "object" ? item.lookAheadGuard : {};
  const backtest = item.backtest && typeof item.backtest === "object" ? item.backtest : {};
  const thresholdTests = Array.isArray(backtest.thresholdTests) ? backtest.thresholdTests : [];
  const threshold75 = thresholdTests.find((test) => Number(test.threshold) === 75) || {};
  const preferredThreshold = backtest.preferredThresholdTest && typeof backtest.preferredThresholdTest === "object" ? backtest.preferredThresholdTest : threshold75;
  const preferredHorizon = Number(preferredThreshold.horizon || backtest.preferredHorizon || 10);
  const tieredThresholdTests = Array.isArray(backtest.tieredThresholdTests) ? backtest.tieredThresholdTests : [];
  const cautionTier = tieredThresholdTests.find((test) => Number(test.threshold) === 60)
    || (Array.isArray(backtest.horizonTests) ? backtest.horizonTests.find((test) => Number(test.threshold) === 60 && Number(test.horizon) === preferredHorizon) : null)
    || {};
  const recommendedCautionThreshold = backtest.recommendedCautionThreshold && typeof backtest.recommendedCautionThreshold === "object"
    ? backtest.recommendedCautionThreshold
    : {};
  const highPrecisionThreshold = backtest.highPrecisionThresholdTest && typeof backtest.highPrecisionThresholdTest === "object"
    ? backtest.highPrecisionThresholdTest
    : {};
  const cautionDisplay = Number.isFinite(Number(recommendedCautionThreshold.threshold)) ? recommendedCautionThreshold : cautionTier;
  const strongTier = tieredThresholdTests.find((test) => Number(test.threshold) === 75) || preferredThreshold || {};
  const clusterTest = backtest.alertClusterTest && typeof backtest.alertClusterTest === "object" ? backtest.alertClusterTest : {};
  const regressionTests = Array.isArray(backtest.regressionTests) ? backtest.regressionTests : [];
  const componentDiagnostics = Array.isArray(backtest.componentDiagnostics) ? backtest.componentDiagnostics : [];
  const factorAuditRows = componentDiagnostics.length ? componentDiagnostics.slice(0, 5) : [];
  const firstTrimDiagnostic = componentDiagnostics.find((row) => row && row.decision === "trim");
  if (firstTrimDiagnostic && !factorAuditRows.some((row) => row && row.component === firstTrimDiagnostic.component)) {
    factorAuditRows.splice(Math.max(0, factorAuditRows.length - 1), 1, firstTrimDiagnostic);
  }
  const drawdownRegression = regressionTests.find((test) => test.target === `maxDrawdown${preferredHorizon}d`) || regressionTests.find((test) => test.target === "maxDrawdown10d") || {};
  const eventRegression = regressionTests.find((test) => test.target === `drawdownEvent${preferredHorizon}d`) || regressionTests.find((test) => test.target === "drawdownEvent10d") || {};
  const scoreBuckets = Array.isArray(backtest.scoreBuckets) ? backtest.scoreBuckets : [];
  const strongBucket = scoreBuckets.find((bucket) => bucket.label === "Strong Alert") || {};
  const worstWindows = Array.isArray(backtest.worstWindows) ? backtest.worstWindows : [];
  const dateRange = backtest.dateRange && typeof backtest.dateRange === "object" ? backtest.dateRange : {};
  const shock = item.nextSessionShock && typeof item.nextSessionShock === "object" ? item.nextSessionShock : {};
  const snapshot = item.marketSnapshot && typeof item.marketSnapshot === "object" ? item.marketSnapshot : {};
  const sourceQuality = item.sourceQuality && typeof item.sourceQuality === "object" ? item.sourceQuality : {};
  const weightCalibration = item.weightCalibration && typeof item.weightCalibration === "object" ? item.weightCalibration : {};
  const forwardCatalystRisk = item.forwardCatalystRisk && typeof item.forwardCatalystRisk === "object" ? item.forwardCatalystRisk : {};
  const factorEvidence = Array.isArray(item.factorEvidence) ? item.factorEvidence : [];
  const scoreUseLabel = (value) => ({
    scored: "计分",
    auditOnly: "审计",
    missing: "缺失"
  })[value] || "未分类";
  const shockText = shock.available ? `${escapeHtml(shock.date || "--")} ${formatSignedPercentMetric(shock.returnPct)}` : "next session --";
  const trendHistory = renderEquityRiskHistoryChart(item);
  const qualitySummary = `
    <div class="equity-risk-quality">
      <span><b>数据可信度</b><strong>${escapeHtml(sourceQuality.verdict || "--")}</strong><small>${escapeHtml(sourceQuality.detail || "等待证据评估")}</small></span>
      <span><b>计分权重</b><strong>${formatPercentMetric(sourceQuality.scoreEligibleWeightPct)}</strong><small>${Number(sourceQuality.scoredComponentCount) || 0} factors scored</small></span>
      <span><b>历史可回放</b><strong>${formatPercentMetric(sourceQuality.historicalReplayableWeightPct)}</strong><small>high-quality ${formatPercentMetric(sourceQuality.highQualityWeightPct)}</small></span>
      <span><b>权重校准</b><strong>${formatPercentMetric(weightCalibration.validatedWeightPct)}</strong><small>降权 ${formatPercentMetric(weightCalibration.downweightedWeightPct)} · 背景 ${formatPercentMetric(weightCalibration.contextWeightPct)}</small></span>
      <span><b>前瞻窗口</b><strong>${Number(forwardCatalystRisk.windowDays) || 5}D</strong><small>${Number(forwardCatalystRisk.eventCount) || 0} events · ${escapeHtml(forwardCatalystRisk.scoreUse ? scoreUseLabel(forwardCatalystRisk.scoreUse) : "--")}</small></span>
    </div>
    ${weightCalibration.available ? `
      <div class="equity-risk-weight-calibration">
        <span>权重校准</span>
        <b>${escapeHtml(weightCalibration.summary || "")}<small>${escapeHtml(weightCalibration.basis || "")}</small></b>
      </div>
    ` : ""}
    ${factorEvidence.length ? `
      <div class="equity-risk-evidence">
        <span>因子证据</span>
        ${factorEvidence.slice(0, 5).map((row) => `
          <b>${escapeHtml(row.label || row.component || "")}<small>${escapeHtml(scoreUseLabel(row.scoreUse))} · ${escapeHtml(row.sourceQuality || "--")} · ${escapeHtml(row.source || "--")}</small></b>
        `).join("")}
      </div>
    ` : ""}
  `;
  const regressionSummary = backtest.available ? `
    <div class="equity-risk-regression">
      <span>回归检验</span>
      <b>${preferredHorizon}D回撤<small>score+10: ${formatSignedPercentMetric(drawdownRegression.slopePer10Score)} · R² ${formatNumberMetric(drawdownRegression.rSquared, 2)}</small></b>
      <b>回撤概率<small>score+10: ${formatSignedPercentMetric(eventRegression.slopePer10Score)} · R² ${formatNumberMetric(eventRegression.rSquared, 2)}</small></b>
    </div>
  ` : "";
  const factorAudit = factorAuditRows.length ? `
    <div class="equity-risk-factor-audit">
      <span>全局因子审计</span>
      ${factorAuditRows.map((row) => `
        <b class="${escapeHtml(row.decision || "context")}">
          ${escapeHtml(row.label || row.component || "")}
          <small>${escapeHtml(row.decisionCn || "--")} · score≥${Number(row.threshold) || 75} ${formatPercentMetric(row.precision)} · recall ${formatPercentMetric(row.recall)} · false ${Number(row.falsePositives) || 0}</small>
        </b>
      `).join("")}
    </div>
  ` : "";
  const historicalAnalysis = backtest.available ? `
    <div class="equity-risk-backtest">
      <div class="equity-risk-backtest-head">
        <span>历史回放</span>
        <b>${Number(backtest.sampleSize) || 0} obs</b>
        <small>${escapeHtml(dateRange.start || "--")} → ${escapeHtml(dateRange.end || "--")}</small>
      </div>
      <div class="equity-risk-backtest-grid">
        <span><b>score≥75 ${preferredHorizon}D精确率</b><strong>${formatPercentMetric(preferredThreshold.precision)}</strong><small>${Number(preferredThreshold.alertDays) || 0} alerts · recall ${formatPercentMetric(preferredThreshold.recall)} · lead ${formatNumberMetric(preferredThreshold.avgDrawdownLeadDaysWhenHit, 1)}D</small></span>
        <span><b>告警簇命中率</b><strong>${formatPercentMetric(clusterTest.precision)}</strong><small>${Number(clusterTest.clusterCount) || 0} clusters · hit ${Number(clusterTest.hitClusters) || 0} · lead ${formatNumberMetric(clusterTest.avgLeadDays, 1)}D</small></span>
        <span><b>强告警${preferredHorizon}D回撤</b><strong>${formatSignedPercentMetric(strongBucket[`avgMaxDrawdown${preferredHorizon}d`] ?? strongBucket.avgMaxDrawdown10d)}</strong><small>${Number(strongBucket.count) || 0} obs · hit ${formatPercentMetric(strongBucket[`drawdownHitRate${preferredHorizon}d`] ?? strongBucket.drawdownHitRate10d)}</small></span>
      </div>
      <div class="equity-risk-tiered">
        <span><b>强告警</b><strong>${formatPercentMetric(strongTier.precision)}</strong><small>高精度 · recall ${formatPercentMetric(strongTier.recall)} · false ${Number(strongTier.falsePositives) || 0}</small></span>
        <span><b>中等预警 · 警戒以上</b><strong>${formatPercentMetric(cautionDisplay.precision)}</strong><small>推荐观察 score≥${Number(cautionDisplay.threshold) || 60} · 覆盖 ${formatPercentMetric(cautionDisplay.recall)} · false ${Number(cautionDisplay.falsePositives) || 0}</small></span>
        <span><b>高精度执行阈值</b><strong>${formatPercentMetric(highPrecisionThreshold.precision)}</strong><small>score≥${Number(highPrecisionThreshold.threshold) || 75} · recall ${formatPercentMetric(highPrecisionThreshold.recall)} · false ${Number(highPrecisionThreshold.falsePositives) || 0}</small></span>
      </div>
      ${factorAudit}
      ${trendHistory}
      <div class="equity-risk-worst">
        <span>最差窗口</span>
        ${worstWindows.slice(0, 3).map((row) => `<b>${escapeHtml(row.date || "--")}<small>score ${Number.isFinite(Number(row.score)) ? Number(row.score).toFixed(1) : "--"} · DD ${formatSignedPercentMetric(row[`maxDrawdown${preferredHorizon}d`] ?? row.maxDrawdown10d)}</small></b>`).join("")}
      </div>
      ${regressionSummary}
    </div>
  ` : `
    <div class="equity-risk-backtest muted"><span>历史回放</span><b>${escapeHtml(backtest.summary || "样本不足")}</b></div>
    ${trendHistory}
  `;
  return `
    <div class="equity-risk-head ${riskClass}">
      <div>
        <span>Equity Short-Term Risk · 短期股市风险</span>
        <strong>${Number.isFinite(score) ? score.toFixed(1) : "--"}</strong>
      </div>
      <div>
        <b>${escapeHtml(item.regimeCn || item.regime || "--")} · ${escapeHtml(item.asOf || "--")}</b>
        <small>${escapeHtml(allocation.stance || "--")} · ${escapeHtml(allocation.equityExposure || "--")}</small>
      </div>
    </div>
    <p class="equity-risk-summary">${escapeHtml(item.summary || "")}</p>
    <div class="equity-risk-metrics">
      <span><b>基础分</b><strong>${Number.isFinite(baseScore) ? baseScore.toFixed(1) : "--"}</strong></span>
      <span><b>SPY 63D</b><strong>${formatSignedPercentMetric(snapshot.spy63dReturn)}</strong></span>
      <span><b>SMH 当日</b><strong>${formatSignedPercentMetric(snapshot.smhDayReturn)}</strong></span>
      <span><b>次日审计</b><strong>${shockText}</strong></span>
    </div>
    ${qualitySummary}
    ${historicalAnalysis}
    <div class="equity-risk-components">
      ${components.map((component) => {
        const componentScore = Number(component.score);
        const componentClass = component.available ? spyWarningClass(componentScore) : "neutral";
        return `
          <div class="equity-risk-component ${componentClass}">
            <span>${escapeHtml(component.label || component.key || "")}</span>
            <strong>${component.available && Number.isFinite(componentScore) ? componentScore.toFixed(0) : "--"}</strong>
            <small>${escapeHtml(component.detail || "")}</small>
            <em>${escapeHtml(scoreUseLabel(component.scoreUse))} · ${escapeHtml(component.sourceQuality || "--")}</em>
          </div>
        `;
      }).join("")}
    </div>
    <div class="equity-risk-drivers">
      <span>短期驱动</span>
      ${drivers.length ? drivers.slice(0, 5).map((driver) => `
        <b>${escapeHtml(driver.name || "")}<small>${escapeHtml(driver.component || "")} · ${Number.isFinite(Number(driver.riskScore)) ? Number(driver.riskScore).toFixed(0) : "--"}</small></b>
      `).join("") : `<em>暂无高风险驱动</em>`}
    </div>
    <div class="equity-risk-foot">
      <span>${escapeHtml(allocation.hedgeAction || "")}</span>
      <em>dataThrough ${escapeHtml(guard.dataThrough || item.asOf || "--")}</em>
    </div>
  `;
}

function prepareEquityRiskHistorySeries(item) {
  const trendPoints = Array.isArray(item?.trend?.points) ? item.trend.points : [];
  const dataThroughTime = Date.parse(item?.lookAheadGuard?.dataThrough || item?.asOf || "");
  const series = trendPoints
    .map((point, index, rows) => {
      const spyClose = Number(point.spyClose);
      const previousSpyClose = index > 0 ? Number(rows[index - 1]?.spyClose) : NaN;
      const spyDayReturn = Number(point.spyDayReturn);
      return {
        time: Date.parse(point.date),
        date: point.date,
        score: Number(point.score),
        spyClose,
        spyDayReturn: Number.isFinite(spyDayReturn)
          ? spyDayReturn
          : Number.isFinite(spyClose) && Number.isFinite(previousSpyClose) && previousSpyClose > 0
            ? ((spyClose / previousSpyClose - 1) * 100)
            : null,
        regime: point.regime || "",
        regimeCn: point.regimeCn || "",
      };
    })
    .filter((point) => Number.isFinite(point.time) && Number.isFinite(point.score))
    .filter((point) => !Number.isFinite(dataThroughTime) || point.time <= dataThroughTime);
  const priceSeries = series.filter((point) => Number.isFinite(point.spyClose) && point.spyClose > 0);
  const baseClose = priceSeries[0]?.spyClose || null;
  priceSeries.forEach((point) => {
    point.spyIndexed = baseClose ? (point.spyClose / baseClose) * 100 : null;
  });
  return { series, priceSeries, baseClose };
}

function prepareEquityRiskAlertWindows(item) {
  const backtest = item?.backtest && typeof item.backtest === "object" ? item.backtest : {};
  const dataThroughTime = Date.parse(item?.lookAheadGuard?.dataThrough || item?.asOf || "");
  return (Array.isArray(backtest.alertWindows) ? backtest.alertWindows : [])
    .map((row) => ({
      ...row,
      time: Date.parse(row?.date || ""),
      score: Number(row?.score),
      horizon: Number(row?.horizon || backtest.preferredHorizon || 15),
    }))
    .filter((row) => Number.isFinite(row.time) && Number.isFinite(row.score))
    .filter((row) => !Number.isFinite(dataThroughTime) || row.time <= dataThroughTime);
}

function equityRiskHistoryScale(series, priceSeries, options = {}) {
  const W = options.large ? 1180 : 840;
  const H = options.large ? 420 : 180;
  const pad = options.large ? { l: 48, r: 72, t: 34, b: 40 } : { l: 34, r: 48, t: 24, b: 28 };
  const minTime = Math.min(...series.map((point) => point.time));
  const maxTime = Math.max(...series.map((point) => point.time));
  const spxValues = priceSeries.map((point) => point.spyIndexed).filter(Number.isFinite);
  const spxMin = spxValues.length ? Math.min(...spxValues) : 100;
  const spxMax = spxValues.length ? Math.max(...spxValues) : 100;
  const spxPad = Math.max(4, (spxMax - spxMin) * 0.12);
  const spxLow = Math.max(0, spxMin - spxPad);
  const spxHigh = spxMax + spxPad;
  const x = (time) => pad.l + ((time - minTime) / Math.max(1, maxTime - minTime)) * (W - pad.l - pad.r);
  const yRisk = (value) => pad.t + ((100 - Math.max(0, Math.min(100, value))) / 100) * (H - pad.t - pad.b);
  const ySpy = (value) => pad.t + ((spxHigh - value) / Math.max(1, spxHigh - spxLow)) * (H - pad.t - pad.b);
  return { W, H, pad, minTime, maxTime, spxLow, spxHigh, x, yRisk, ySpy };
}

function renderEquityRiskHistoryChart(item, options = {}) {
  const { series, priceSeries } = prepareEquityRiskHistorySeries(item);
  if (series.length < 2) return `<div class="empty-state compact">历史曲线样本不足</div>`;
  const scale = equityRiskHistoryScale(series, priceSeries, options);
  const { W, H, pad, spxLow, spxHigh, x, yRisk, ySpy } = scale;
  const riskPath = macroLiquidityPath(series, x, yRisk, "score");
  const spyPath = priceSeries.length >= 2 ? macroLiquidityPath(priceSeries, x, ySpy, "spyIndexed") : "";
  const latestRisk = series[series.length - 1];
  const latestSpy = priceSeries[priceSeries.length - 1];
  const ticks = buildDateTicks(series, options.large ? 8 : 5);
  const alertMarkers = options.large || options.showAlerts ? prepareEquityRiskAlertWindows(item) : [];
  const markerLayer = alertMarkers.length ? `
        <g class="equity-risk-alert-markers" aria-label="score>=75 alert markers">
          ${alertMarkers.map((alert) => {
            const drawdown = alert[`maxDrawdown${alert.horizon}d`] ?? alert.maxDrawdown15d ?? alert.maxDrawdown10d;
            const lead = alert[`drawdownLeadDays${alert.horizon}d`] ?? alert.leadDays;
            const title = `${alert.date || "--"} · score ${alert.score.toFixed(1)} · DD ${formatSignedPercentMetric(drawdown)} · lead ${Number.isFinite(Number(lead)) ? `${Number(lead).toFixed(0)}D` : "--"}`;
            return `
              <circle class="equity-risk-alert-marker ${alert.hit === true ? "hit" : "miss"}" data-alert-date="${escapeHtml(alert.date || "")}" cx="${x(alert.time).toFixed(1)}" cy="${yRisk(alert.score).toFixed(1)}" r="${alert.hit === true ? "4.5" : "3.8"}">
                <title>${escapeHtml(title)}</title>
              </circle>
            `;
          }).join("")}
        </g>
  ` : "";
  const interactiveLayer = options.interactive ? `
        <line class="equity-risk-hover-guide" x1="${pad.l}" x2="${pad.l}" y1="${pad.t}" y2="${H - pad.b}" stroke-opacity="0"></line>
        <circle class="equity-risk-hover-dot risk" cx="${x(latestRisk.time).toFixed(1)}" cy="${yRisk(latestRisk.score).toFixed(1)}" r="5" opacity="0"></circle>
        <circle class="equity-risk-hover-dot spy" cx="${latestSpy ? x(latestSpy.time).toFixed(1) : pad.l}" cy="${latestSpy ? ySpy(latestSpy.spyIndexed).toFixed(1) : pad.t}" r="4.5" opacity="0"></circle>
        <rect x="${pad.l}" y="${pad.t}" width="${W - pad.l - pad.r}" height="${H - pad.t - pad.b}" fill="transparent"></rect>
  ` : "";
  return `
    <div class="equity-risk-history-chart ${options.large ? "large" : ""}">
      <div class="equity-risk-history-head">
        <span>历史曲线</span>
        <div class="equity-risk-history-actions">
          <b>Risk score vs SPY indexed</b>
          ${options.large ? "" : `<button id="expandEquityRiskHistory" class="icon-btn chart-expand-btn" type="button" title="放大查看短期股市风险历史曲线" aria-label="放大查看短期股市风险历史曲线">⛶</button>`}
        </div>
      </div>
      <svg data-equity-risk-history-chart viewBox="0 0 ${W} ${H}" role="img" aria-label="equityShortTermRisk historical curve versus SPY indexed price">
        <rect x="0" y="0" width="${W}" height="${H}" fill="transparent"></rect>
        ${[40, 60, 75].map((tick) => `
          <line x1="${pad.l}" x2="${W - pad.r}" y1="${yRisk(tick).toFixed(1)}" y2="${yRisk(tick).toFixed(1)}" class="${tick === 75 ? "equity-risk-threshold-line strong" : "equity-risk-threshold-line"}"></line>
          <text x="8" y="${yRisk(tick).toFixed(1)}" dy="4">${tick}</text>
        `).join("")}
        ${ticks.map((point) => `
          <text x="${x(point.time).toFixed(1)}" y="${H - 8}" text-anchor="middle">${formatMonthLabel(point.time)}</text>
        `).join("")}
        ${spyPath ? `<path d="${spyPath}" class="equity-risk-spy-line"></path>` : ""}
        <path d="${riskPath}" class="equity-risk-score-line"></path>
        ${markerLayer}
        <circle class="equity-risk-score-dot" cx="${x(latestRisk.time).toFixed(1)}" cy="${yRisk(latestRisk.score).toFixed(1)}" r="4.2"></circle>
        ${latestSpy ? `<circle class="equity-risk-spy-dot" cx="${x(latestSpy.time).toFixed(1)}" cy="${ySpy(latestSpy.spyIndexed).toFixed(1)}" r="3.8"></circle>` : ""}
        <text x="${W - pad.r}" y="15" text-anchor="end">equityShortTermRisk ${latestRisk.score.toFixed(1)}</text>
        ${latestSpy ? `<text x="${W - pad.r}" y="30" text-anchor="end" class="equity-risk-spy-label">SPY indexed ${latestSpy.spyIndexed.toFixed(0)}</text>` : ""}
        <text x="${W - 8}" y="${ySpy(spxHigh).toFixed(1) + 4}" text-anchor="end" class="equity-risk-spy-axis">${spxHigh.toFixed(0)}</text>
        <text x="${W - 8}" y="${ySpy(spxLow).toFixed(1) + 4}" text-anchor="end" class="equity-risk-spy-axis">${spxLow.toFixed(0)}</text>
        ${interactiveLayer}
      </svg>
    </div>
  `;
}

function renderEquityRiskHistoryModalStats(item) {
  const { series, priceSeries } = prepareEquityRiskHistorySeries(item);
  if (series.length < 2) return `<div class="empty-state compact">历史样本不足</div>`;
  const latest = series[series.length - 1];
  const minScore = Math.min(...series.map((point) => point.score));
  const maxScore = Math.max(...series.map((point) => point.score));
  const alertCount = series.filter((point) => point.score >= 75).length;
  const latestSpy = priceSeries[priceSeries.length - 1];
  return [
    ["样本", `${series.length} obs`],
    ["区间", `${series[0].date} / ${latest.date}`],
    ["最新风险", latest.score.toFixed(1)],
    ["强告警日", alertCount],
    ["分数区间", `${minScore.toFixed(1)} / ${maxScore.toFixed(1)}`],
    ["SPY close", latestSpy ? latestSpy.spyClose.toFixed(2) : "--"],
  ].map(([label, value]) => `
    <div class="history-stat">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(String(value))}</strong>
    </div>
  `).join("");
}

function renderEquityRiskHistoryModalAlerts(item) {
  const backtest = item?.backtest && typeof item.backtest === "object" ? item.backtest : {};
  const alertWindows = prepareEquityRiskAlertWindows(item);
  if (!alertWindows.length) return `<div class="empty-state compact">暂无score≥75历史告警明细</div>`;
  const preferredHorizon = Number(backtest.preferredHorizon || alertWindows[0]?.horizon || 15);
  const hitCount = alertWindows.filter((row) => row.hit === true).length;
  const rows = alertWindows.slice(0, 10);
  return `
    <div class="equity-risk-modal-alert-head">
      <span>score≥75历史告警</span>
      <b>${alertWindows.length} days · hit ${formatPercentMetric(100 * hitCount / alertWindows.length)}</b>
      <small>${preferredHorizon}D max drawdown audit, sorted by strongest score</small>
    </div>
    <div class="equity-risk-modal-alert-grid">
      ${rows.map((row) => {
        const horizon = Number(row.horizon || preferredHorizon);
        const drawdown = row[`maxDrawdown${horizon}d`] ?? row.maxDrawdown15d ?? row.maxDrawdown10d;
        const forward = row[`forward${horizon}d`] ?? row.forward15d ?? row.forward10d;
        const lead = row[`drawdownLeadDays${horizon}d`] ?? row.leadDays;
        const leadText = row.hit === true
          ? (Number.isFinite(Number(lead)) ? `${Number(lead).toFixed(0)}D` : "--")
          : "未命中";
        return `
          <div class="equity-risk-alert-row ${row.hit === true ? "hit" : "miss"}">
            <b>${escapeHtml(row.date || "--")}<small>score ${Number.isFinite(row.score) ? row.score.toFixed(1) : "--"} · ${escapeHtml(row.regimeCn || row.regime || "--")}</small></b>
            <span><em>${horizon}D DD</em><strong>${formatSignedPercentMetric(drawdown)}</strong></span>
            <span><em>Lead</em><strong>${escapeHtml(leadText)}</strong></span>
            <span><em>${horizon}D Ret</em><strong>${formatSignedPercentMetric(forward)}</strong></span>
            <span><em>SPY</em><strong>${formatNumberMetric(row.spyClose, 2)}</strong></span>
          </div>
        `;
      }).join("")}
    </div>
  `;
}

function openEquityRiskHistoryModal() {
  const modal = $("#equityRiskHistoryModal");
  if (!modal) return;
  modal.hidden = false;
  document.body.classList.add("modal-open");
  renderEquityRiskHistoryModalChart();
  $("#closeEquityRiskHistoryModal")?.focus();
}

function closeEquityRiskHistoryModal() {
  const modal = $("#equityRiskHistoryModal");
  if (!modal) return;
  modal.hidden = true;
  document.body.classList.remove("modal-open");
}

function renderEquityRiskHistoryModalChart() {
  const item = state.equityShortTermRisk || DEFAULT_DATA.equityShortTermRisk;
  const chartNode = $("#equityRiskHistoryModalChart");
  const statsNode = $("#equityRiskHistoryModalStats");
  const alertsNode = $("#equityRiskHistoryModalAlerts");
  if (statsNode) statsNode.innerHTML = renderEquityRiskHistoryModalStats(item);
  if (alertsNode) alertsNode.innerHTML = renderEquityRiskHistoryModalAlerts(item);
  if (!chartNode) return;
  chartNode.innerHTML = renderEquityRiskHistoryChart(item, { large: true, interactive: true, showAlerts: true });
  bindEquityRiskHistoryInteractions(chartNode, item, { large: true, tooltipSelector: "#equityRiskHistoryModalTooltip" });
}

function bindEquityRiskHistoryInteractions(chartNode, item, options = {}) {
  const svg = chartNode?.querySelector("[data-equity-risk-history-chart]");
  const tooltip = $(options.tooltipSelector || "#equityRiskHistoryModalTooltip");
  if (!svg || !tooltip) return;
  const { series, priceSeries } = prepareEquityRiskHistorySeries(item);
  if (series.length < 2) return;
  const scale = equityRiskHistoryScale(series, priceSeries, options);
  const guide = svg.querySelector(".equity-risk-hover-guide");
  const riskDot = svg.querySelector(".equity-risk-hover-dot.risk");
  const spyDot = svg.querySelector(".equity-risk-hover-dot.spy");
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
    if (Number.isFinite(point.spyIndexed)) {
      spyDot?.setAttribute("cx", pointX.toFixed(1));
      spyDot?.setAttribute("cy", scale.ySpy(point.spyIndexed).toFixed(1));
      spyDot?.setAttribute("opacity", "1");
    } else {
      spyDot?.setAttribute("opacity", "0");
    }
    renderEquityRiskHistoryTooltip(tooltip, chartNode, event, point);
  });
  svg.addEventListener("mouseleave", () => {
    guide?.setAttribute("stroke-opacity", "0");
    riskDot?.setAttribute("opacity", "0");
    spyDot?.setAttribute("opacity", "0");
    tooltip.hidden = true;
  });
}

function nearestEquityRiskHistoryPoint(points, svgX, scale) {
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

function renderEquityRiskHistoryTooltip(tooltip, chartNode, event, point) {
  const spyCloseText = Number.isFinite(point.spyClose) ? `SPY close ${point.spyClose.toFixed(2)}` : "SPY close --";
  const spyIndexedText = Number.isFinite(point.spyIndexed) ? `SPY indexed ${point.spyIndexed.toFixed(1)}` : "SPY indexed --";
  const spyReturnText = Number.isFinite(point.spyDayReturn) ? `SPY day ${formatSignedPercentMetric(point.spyDayReturn)}` : "SPY day --";
  tooltip.innerHTML = `
    <b>${escapeHtml(point.date)} · score ${point.score.toFixed(1)}</b>
    <span>${escapeHtml(point.regimeCn || point.regime || "--")} · ${escapeHtml(spyCloseText)}</span>
    <small>${escapeHtml(spyIndexedText)} · ${escapeHtml(spyReturnText)}</small>
  `;
  const parentRect = (tooltip.offsetParent || chartNode).getBoundingClientRect();
  tooltip.hidden = false;
  const left = Math.min(Math.max(8, event.clientX - parentRect.left + 12), Math.max(8, parentRect.width - tooltip.offsetWidth - 8));
  const top = Math.min(Math.max(8, event.clientY - parentRect.top - 58), Math.max(8, parentRect.height - tooltip.offsetHeight - 8));
  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${top}px`;
}
