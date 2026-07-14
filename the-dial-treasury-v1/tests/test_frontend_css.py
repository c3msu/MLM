import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _frontend_js():
    """Concatenate every local <script> the page loads, in index.html order, so feature-
    presence assertions are robust to the Phase 3 split of app.js into per-domain files
    (a function is "present" if it ships in the loaded bundle, regardless of which file)."""
    html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
    parts = []
    for src in re.findall(r'<script src="([^"?]+)(?:\?[^"]*)?">', html):
        if src.startswith("http"):
            continue
        path = PROJECT_ROOT / src
        if path.exists():
            parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


FRONTEND_JS = _frontend_js()


class FrontendCssTests(unittest.TestCase):
    def test_market_badge_text_span_is_not_sized_like_dot(self):
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")

        self.assertNotRegex(css, re.compile(r"\.market-badge\s+span\s*\{[^}]*width:\s*6px", re.DOTALL))
        self.assertRegex(css, re.compile(r"\.market-badge\s*>\s*span:first-child\s*\{[^}]*width:\s*6px", re.DOTALL))

    def test_bhadial_style_scorecard_panels_are_mounted(self):
        html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")

        for element_id in (
            "percentileTrendChart",
            "percentileMovers",
            "percentileAlerts",
            "factorDrivers",
            "modulePulse",
        ):
            self.assertIn(f'id="{element_id}"', html)

    def test_static_fallback_contains_percentile_history(self):
        app_js = FRONTEND_JS

        self.assertIn("percentiles:", app_js)
        self.assertIn("trends:", app_js)
        self.assertIn("银行准备金", app_js)

    def test_frontend_assets_are_cache_busted(self):
        html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")

        self.assertRegex(html, r'href="styles\.css\?v=[^"]+"')
        self.assertRegex(html, r'src="app\.js\?v=[^"]+"')

    def test_primary_navigation_keeps_five_core_links_and_folds_secondary_sections(self):
        html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
        app_js = FRONTEND_JS
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")

        nav = re.search(r'<nav class="top-nav"[^>]*>(.*?)</nav>', html, re.DOTALL)
        self.assertIsNotNone(nav)
        nav_html = nav.group(1)
        more_start = nav_html.index('id="primaryNavMore"')
        core_html = nav_html[:more_start]
        more_html = nav_html[more_start:]
        self.assertEqual(core_html.count('<a href='), 5)
        self.assertEqual(more_html.count('<a href='), 6)
        for target in ("#summary", "#curve", "#scorecard", "#regions", "#views"):
            self.assertIn(f'href="{target}"', core_html)
        for target in ("#decomposition", "#policy", "#supply", "#positioning", "#crossmarket", "#events"):
            self.assertIn(f'href="{target}"', more_html)
        self.assertIn('aria-label="更多页面"', more_html)
        self.assertIn("function initTopNavMore()", app_js)
        self.assertIn("function syncTopNavMoreActiveState()", app_js)
        self.assertIn('event.key !== "Escape"', app_js)
        self.assertIn('link.setAttribute("aria-current", "page")', app_js)
        self.assertIn(".top-nav-more-menu", css)
        self.assertIn(".top-nav a:focus-visible", css)
        self.assertRegex(css, re.compile(r"@media \(max-width: 640px\).*?\.data-status-row\s*\{[^}]*grid-template-columns:", re.DOTALL))

    def test_collapsible_sections_are_keyboard_operable_and_have_visible_focus(self):
        app_js = FRONTEND_JS
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")

        self.assertIn('heading.setAttribute("role", "button")', app_js)
        self.assertIn('heading.setAttribute("tabindex", "0")', app_js)
        self.assertIn('heading.setAttribute("aria-expanded"', app_js)
        self.assertIn('event.key === "Enter"', app_js)
        self.assertIn('event.key === " "', app_js)
        self.assertIn(".section-collapsible > .section-heading:focus-visible", css)
        self.assertIn(".diagnostic-details > summary:focus-visible", css)
        self.assertIn(".region-advanced-summary:focus-visible", css)
        self.assertIn(".idea-decision-summary:focus-visible", css)
        for selector in (
            "button:focus-visible",
            "input:focus-visible",
            "select:focus-visible",
            "summary:focus-visible",
            '[contenteditable="true"]:focus-visible',
        ):
            self.assertIn(selector, css)

    def test_removed_legacy_investment_card_css_does_not_linger(self):
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")

        self.assertNotIn(".idea-grid", css)
        self.assertNotIn(".idea-card", css)
        self.assertNotIn(".idea-card-meta", css)

    def test_header_export_downloads_current_html_document(self):
        html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
        app_js = FRONTEND_JS

        self.assertIn('id="exportState"', html)
        self.assertIn('title="导出当前页面HTML"', html)
        self.assertIn("function buildCurrentHtmlExport()", app_js)
        self.assertIn("function inlineExportStylesheets(clone)", app_js)
        self.assertIn("document.documentElement.cloneNode(true)", app_js)
        self.assertIn("Array.from(document.styleSheets)", app_js)
        self.assertIn("styleSheet.cssRules", app_js)
        self.assertIn("style.textContent = Array.from(cssRules).map((rule) => rule.cssText).join", app_js)
        self.assertIn('style.setAttribute("data-export-inline-stylesheet", sourceHref)', app_js)
        self.assertIn("link.replaceWith(style)", app_js)
        self.assertIn('new Blob([payload], { type: "text/html;charset=utf-8" })', app_js)
        self.assertRegex(app_js, r"link\.download\s*=\s*`macro-liquidity-monitor-\$\{[^}]+\}\.html`;")
        self.assertNotIn("treasury-factor-desk-${state.asOf}.json", app_js)
        self.assertNotIn("JSON.stringify({ exportedAt: new Date().toISOString(), state }", app_js)

    def test_symbol_buttons_have_localized_accessible_names_and_touch_targets(self):
        html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
        app_js = FRONTEND_JS
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")

        for element_id, label in (("resetState", "恢复默认计分"), ("exportState", "导出当前页面HTML")):
            button = re.search(rf'<button id="{element_id}"[^>]*>', html)
            self.assertIsNotNone(button)
            self.assertIn(f'aria-label="{label}"', button.group(0))
            self.assertIn('data-i18n-aria-label=', button.group(0))
        self.assertIn('[data-i18n-aria-label]', app_js)
        self.assertRegex(css, re.compile(r"\.icon-btn\s*\{[^}]*width:\s*44px;[^}]*height:\s*44px", re.DOTALL))
        self.assertRegex(css, re.compile(r"\.chart-expand-btn,\s*\.chart-close-btn\s*\{[^}]*width:\s*44px;[^}]*height:\s*44px", re.DOTALL))

    def test_runtime_snapshot_requests_use_stable_conditional_cache_urls(self):
        app_js = FRONTEND_JS

        self.assertIn('fetch("data/dashboard.json", { cache: "no-cache"', app_js)
        self.assertIn('fetch("/api/health", { cache: "no-cache"', app_js)
        self.assertNotIn('data/dashboard.json?ts=${Date.now()}', app_js)
        self.assertNotIn('/api/health?ts=${Date.now()}', app_js)

    def test_percentile_chart_has_expand_modal_controls(self):
        html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
        app_js = FRONTEND_JS

        for element_id in (
            "expandPercentileChart",
            "percentileModal",
            "percentileModalChart",
            "percentileModalLegend",
            "closePercentileModal",
        ):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn("CORE_PERCENTILE_TRENDS", app_js)
        self.assertIn("openPercentileModal", app_js)
        self.assertIn("closePercentileModal", app_js)

    def test_wide_layout_and_large_percentile_modal_are_sized(self):
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")

        self.assertIn("--site-max: 1860px;", css)
        self.assertRegex(css, re.compile(r"\.site-header\s*\{[^}]*calc\(\(100vw - var\(--site-max\)\) / 2\)", re.DOTALL))
        self.assertRegex(css, re.compile(r"main\s*\{[^}]*width:\s*min\(var\(--site-max\),\s*calc\(100% - 28px\)\)", re.DOTALL))
        self.assertRegex(css, re.compile(r"\.site-footer\s*\{[^}]*width:\s*min\(var\(--site-max\),\s*calc\(100% - 28px\)\)", re.DOTALL))
        self.assertRegex(css, re.compile(r"\.chart-modal-panel\s*\{[^}]*width:\s*80vw", re.DOTALL))
        self.assertRegex(css, re.compile(r"\.chart-modal-panel\s*\{[^}]*height:\s*80vh", re.DOTALL))
        self.assertRegex(css, re.compile(r"\.modal-chart\s*\{[^}]*flex:\s*1 1 auto", re.DOTALL))

    def test_percentile_modal_has_readability_modes(self):
        html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
        app_js = FRONTEND_JS
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")

        self.assertIn('id="percentileModalControls"', html)
        self.assertIn("data-percentile-mode", app_js)
        self.assertIn("percentileModalMode", app_js)
        self.assertIn("renderPercentileModalChart", app_js)
        self.assertIn("selectPercentileModalTrends", app_js)
        self.assertIn(".chart-mode-controls", css)

    def test_percentile_history_chart_has_focus_and_hover_interactions(self):
        html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
        app_js = FRONTEND_JS
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")

        self.assertIn('id="percentileTrendTooltip"', html)
        self.assertIn('id="percentileModalTooltip"', html)
        self.assertIn("percentileFocusedTrend", app_js)
        self.assertIn("data-percentile-focus", app_js)
        self.assertIn("bindPercentileTrendInteractions", app_js)
        self.assertIn("renderPercentileTooltip", app_js)
        self.assertIn("percentile-focus-dim", app_js)
        self.assertIn(".percentile-tooltip", css)
        self.assertIn(".percentile-legend button", css)
        self.assertIn(".percentile-focus-dim", css)

    def test_macro_liquidity_composite_panel_is_mounted(self):
        html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
        app_js = FRONTEND_JS
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")

        for element_id in (
            "macroLiquidityScore",
            "macroLiquidityRegime",
            "macroLiquidityRead",
            "macroLiquidityTrend",
            "macroLiquidityTrendChart",
            "macroLiquidityBalance",
            "macroLiquidityQuality",
            "macroLiquidityImplications",
            "macroLiquidityGauge",
        ):
            self.assertIn(f'id="{element_id}"', html)
        summary_start = html.index('<section id="summary"')
        summary_end = html.index('<section id="curve"')
        summary_html = html[summary_start:summary_end]
        self.assertNotIn('id="macroLiquidityComponents"', summary_html)
        self.assertNotIn('id="macroLiquidityDrivers"', summary_html)
        self.assertIn("macroLiquidity:", app_js)
        self.assertIn("renderMacroLiquidityScore", app_js)
        self.assertIn("renderMacroLiquidityTrend", app_js)
        self.assertIn("renderMacroLiquidityTrendChart", app_js)
        self.assertIn("renderMacroLiquidityQuality", app_js)
        self.assertIn("macroLiquidityClass", app_js)
        self.assertIn(".macro-liquidity-panel", css)
        self.assertIn(".macro-liquidity-gauge", css)
        self.assertIn(".macro-liquidity-quality", css)
        self.assertIn(".macro-liquidity-read", css)
        self.assertIn(".macro-liquidity-trend", css)
        self.assertIn(".macro-liquidity-trend-chart", css)
        self.assertIn("macro-liquidity-trend-area", app_js)
        self.assertIn("macro-liquidity-trend-line", app_js)
        self.assertIn(".macro-liquidity-trend-area", css)
        self.assertIn(".macro-liquidity-trend-line", css)
        self.assertIn(".macro-liquidity-balance", css)
        self.assertIn(".macro-liquidity-implications", css)
        self.assertIn("renderMacroLiquidityBalance", app_js)
        self.assertIn("renderMacroLiquidityImplications", app_js)

    def test_macro_liquidity_trend_chart_compares_sp500_and_expands(self):
        html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
        app_js = FRONTEND_JS
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")

        for element_id in (
            "expandMacroLiquidityTrend",
            "macroLiquidityTrendTooltip",
            "macroLiquidityTrendModal",
            "macroLiquidityTrendModalChart",
            "macroLiquidityTrendModalTooltip",
            "closeMacroLiquidityTrendModal",
        ):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn("prepareMacroLiquidityComparisonSeries", app_js)
        self.assertIn("bindMacroLiquidityTrendInteractions", app_js)
        self.assertIn("openMacroLiquidityTrendModal", app_js)
        self.assertIn("renderMacroLiquidityTrendModalChart", app_js)
        self.assertIn("macro-liquidity-spx-line", app_js)
        self.assertIn("S&P 500 indexed", app_js)
        self.assertIn(".macro-liquidity-spx-line", css)
        self.assertIn(".macro-liquidity-hover-guide", css)
        self.assertIn(".macro-trend-modal-chart", css)

    def test_macro_liquidity_trend_chart_includes_spy_early_warning_overlay(self):
        app_js = FRONTEND_JS
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")

        self.assertIn("spyWarningTrendPanel", app_js)
        self.assertIn("prepareMacroLiquidityComparisonSeries(trend, options.equity || macroLiquidityEquityPanel(), options.warning || spyWarningTrendPanel())", app_js)
        self.assertIn("macro-liquidity-spy-warning-line", app_js)
        self.assertIn("SPY Early Warning", app_js)
        self.assertIn("spyWarning", app_js)
        self.assertIn(".macro-liquidity-spy-warning-line", css)
        self.assertIn(".macro-liquidity-spy-warning-dot", css)

    def test_macro_liquidity_equity_lead_panel_is_mounted(self):
        html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
        app_js = FRONTEND_JS
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")

        for element_id in (
            "macroLiquidityEquityLead",
            "liquidityEquityStats",
            "liquidityEquitySignal",
            "liquidityEquityStateGrid",
            "liquidityEquityChart",
            "liquidityEquityBuckets",
            "liquidityEquityRead",
            "liquidityEquityDiagnostics",
            "liquidityEquityLeadLag",
            "liquidityEquityChangeBuckets",
            "liquidityEquityRolling",
        ):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn("renderMacroLiquidityEquityLead", app_js)
        self.assertIn("renderLiquidityCurrentSignal", app_js)
        self.assertIn("renderLiquidityStateGrid", app_js)
        self.assertIn("renderLiquidityEquityChart", app_js)
        self.assertIn("renderLiquidityLeadLag", app_js)
        self.assertIn("renderLiquidityChangeBuckets", app_js)
        self.assertIn("macroLiquidityEquity", app_js)
        self.assertIn("baseScore", app_js)
        self.assertIn("风险放大", app_js)
        self.assertIn("dampeners", app_js)
        self.assertIn("风险降噪", app_js)
        self.assertIn(".liquidity-equity-panel", css)
        self.assertIn(".liquidity-equity-signal", css)
        self.assertIn(".liquidity-state-grid", css)
        self.assertIn(".liquidity-equity-chart", css)
        self.assertIn(".liquidity-equity-buckets", css)
        self.assertIn(".liquidity-equity-diagnostics", css)

    def test_equity_short_term_risk_panel_is_mounted(self):
        html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
        app_js = FRONTEND_JS
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")

        self.assertIn('id="equityShortTermRisk"', html)
        self.assertIn("equityShortTermRisk", app_js)
        self.assertIn("renderEquityShortTermRisk", app_js)
        self.assertIn("renderEquityRiskHistoryChart", app_js)
        self.assertIn("Equity Short-Term Risk", app_js)
        self.assertIn("历史回放", app_js)
        self.assertIn("历史曲线", app_js)
        self.assertIn("回归检验", app_js)
        self.assertIn("formatPercentMetric", app_js)
        self.assertIn("dataThrough", app_js)
        self.assertIn("sourceQuality", app_js)
        self.assertIn("weightCalibration", app_js)
        self.assertIn("factorEvidence", app_js)
        self.assertIn("forwardCatalystRisk", app_js)
        self.assertIn("tieredThresholdTests", app_js)
        self.assertIn("recommendedCautionThreshold", app_js)
        self.assertIn("highPrecisionThresholdTest", app_js)
        self.assertIn("componentDiagnostics", app_js)
        self.assertIn("全局因子审计", app_js)
        self.assertIn("权重校准", app_js)
        self.assertIn("高精度执行阈值", app_js)
        self.assertIn("警戒以上", app_js)
        self.assertIn("中等预警", app_js)
        self.assertIn("推荐观察", app_js)
        self.assertIn(".equity-risk-panel", css)
        self.assertIn(".equity-risk-quality", css)
        self.assertIn(".equity-risk-weight-calibration", css)
        self.assertIn(".equity-risk-evidence", css)
        self.assertIn(".equity-risk-backtest", css)
        self.assertIn(".equity-risk-tiered", css)
        self.assertIn(".equity-risk-factor-audit", css)
        self.assertIn(".equity-risk-regression", css)
        self.assertIn(".equity-risk-history-chart", css)
        self.assertIn(".equity-risk-components", css)
        self.assertIn(".equity-risk-drivers", css)

    def test_equity_short_term_risk_history_chart_is_available_in_explanation_layer(self):
        app_js = FRONTEND_JS

        renderer_start = app_js.index("function renderEquityShortTermRisk")
        renderer_end = app_js.index("function renderEquityRiskHistoryChart")
        renderer = app_js[renderer_start:renderer_end]
        self.assertIn("const trendHistory = renderEquityRiskHistoryChart(item);", renderer)
        # Chart remains independent of backtest availability, but is intentionally folded
        # with the full component breakdown so the default view can lead with action.
        self.assertLess(renderer.index("${trendHistory}"), renderer.index('<div class="equity-risk-components">'))
        self.assertIn('<details class="diagnostic-details equity-risk-explain">', renderer)
        self.assertLess(renderer.index('<details class="diagnostic-details equity-risk-explain">'), renderer.index("${trendHistory}"))
        self.assertLess(renderer.index("${trendHistory}"), renderer.index('<details class="diagnostic-details equity-risk-deep">'))
        # The backtest tables / factor audit are folded into the collapsed deep-dive.
        self.assertIn('<details class="diagnostic-details equity-risk-deep">', renderer)

    def test_equity_short_term_risk_history_chart_expands_to_interactive_modal(self):
        html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
        app_js = FRONTEND_JS
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")

        for element_id in (
            "equityRiskHistoryModal",
            "equityRiskHistoryModalChart",
            "equityRiskHistoryModalTooltip",
            "equityRiskHistoryModalStats",
            "equityRiskHistoryModalAlerts",
            "closeEquityRiskHistoryModal",
        ):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn("expandEquityRiskHistory", app_js)
        self.assertIn("openEquityRiskHistoryModal", app_js)
        self.assertIn("closeEquityRiskHistoryModal", app_js)
        self.assertIn("renderEquityRiskHistoryModalChart", app_js)
        self.assertIn("renderEquityRiskHistoryModalAlerts", app_js)
        self.assertIn("alertWindows", app_js)
        self.assertIn("equity-risk-alert-marker", app_js)
        self.assertIn("score≥75历史告警", app_js)
        self.assertIn("bindEquityRiskHistoryInteractions", app_js)
        self.assertIn("renderEquityRiskHistoryTooltip", app_js)
        self.assertIn("nearestEquityRiskHistoryPoint", app_js)
        self.assertIn("equity-risk-hover-guide", app_js)
        self.assertIn("equity-risk-hover-dot", app_js)
        self.assertIn("SPY close", app_js)
        self.assertIn(".equity-risk-history-modal-chart", css)
        self.assertIn(".equity-risk-history-actions", css)
        self.assertIn(".equity-risk-modal-stats", css)
        self.assertIn(".equity-risk-modal-alerts", css)
        self.assertIn(".equity-risk-alert-marker", css)
        self.assertIn(".equity-risk-hover-guide", css)
        self.assertIn(".equity-risk-hover-dot", css)

    def test_global_lppl_risk_panel_is_mounted_as_independent_indicator(self):
        html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
        app_js = FRONTEND_JS
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")

        for element_id in (
            "globalLpplRisk",
            "globalLpplRiskHistoryModal",
            "globalLpplRiskHistoryModalChart",
            "globalLpplRiskHistoryModalStats",
            "globalLpplRiskHistoryModalTooltip",
            "closeGlobalLpplRiskHistoryModal",
        ):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn("globalLpplRisk", app_js)
        self.assertIn("renderGlobalLpplRisk", app_js)
        self.assertIn("renderGlobalLpplRiskHistoryChart", app_js)
        self.assertIn("renderGlobalLpplIndexHistoryCharts", app_js)
        self.assertIn("sampleGlobalLpplHistorySeries", app_js)
        self.assertIn("GLOBAL_LPPL_INLINE_HISTORY_MAX_POINTS", app_js)
        self.assertIn("fullWidth: true", app_js)
        self.assertIn("perIndexHistory", app_js)
        self.assertIn("data-global-lppl-symbol", app_js)
        self.assertIn("selectedGlobalLpplSymbol", app_js)
        self.assertIn("openGlobalLpplRiskHistoryModal", app_js)
        self.assertIn("Global LPPL Risk", app_js)
        self.assertIn("全球指数泡沫临界风险", app_js)
        self.assertIn("scoreUse", app_js)
        self.assertIn("criticalDate", app_js)
        self.assertIn("daysToCritical", app_js)
        self.assertIn("forwardSignal", app_js)
        self.assertIn("前瞻压力", app_js)
        self.assertIn("scoreMomentum20d", app_js)
        self.assertIn("globalLpplClipState", app_js)
        self.assertIn("globalLpplClipSummary", app_js)
        self.assertIn("clipState", app_js)
        self.assertIn("clipLock", app_js)
        self.assertIn("CLIP", app_js)
        self.assertIn("tcMedian", app_js)
        self.assertIn("criticalDate", app_js)
        self.assertIn("fitR2", app_js)
        self.assertIn(".global-lppl-risk-panel", css)
        self.assertIn("grid-column: 1 / -1", css)
        self.assertIn(".global-lppl-index-grid", css)
        self.assertIn(".global-lppl-history-chart", css)
        self.assertIn(".global-lppl-clip-note", css)
        self.assertIn(".global-lppl-chart-grid", css)
        self.assertIn("grid-template-columns: minmax(0, 1fr)", css)
        self.assertIn(".global-lppl-history-chart.full-width svg", css)
        self.assertIn(".global-lppl-modal-panel", css)

    def test_investment_views_render_historical_spy_proxy_impact(self):
        app_js = FRONTEND_JS
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")

        self.assertIn("renderIdeaEquityImpact", app_js)
        self.assertIn("equityImpact", app_js)
        self.assertIn("历史SPY影响", app_js)
        self.assertIn("S&P 500 price-index proxy for SPY", app_js)
        self.assertIn(".idea-equity-impact", css)
        self.assertIn(".idea-equity-impact.positive", css)
        self.assertIn(".idea-equity-impact.negative", css)

    def test_summary_leads_with_narrative_then_action_and_folds_market_metrics(self):
        html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")

        summary_start = html.index('<section id="summary"')
        summary_end = html.index('<section id="curve"')
        summary_html = html[summary_start:summary_end]
        macro_index = summary_html.index('class="panel macro-liquidity-panel macro-liquidity-topline summary-macro-liquidity"')
        hero_copy_index = summary_html.index('class="hero-copy"')
        action_index = summary_html.index('id="portfolioOverviewPanel"')
        stance_index = summary_html.index('class="stance-panel summary-decision-strip"')
        market_details_index = summary_html.index('class="summary-market-details diagnostic-details"')
        tiles_index = summary_html.index('id="heroTiles"')
        scorecard_start = html.index('<section id="scorecard"')
        scorecard_end = html.index('<section id="policy"')
        scorecard_html = html[scorecard_start:scorecard_end]
        # The summary now moves from context to action, then compact decision readouts. Raw
        # yield tiles are progressive disclosure instead of competing with the main action.
        self.assertLess(hero_copy_index, action_index)
        self.assertLess(action_index, stance_index)
        self.assertLess(stance_index, macro_index)
        self.assertLess(macro_index, market_details_index)
        self.assertLess(market_details_index, tiles_index)
        self.assertNotIn('macro-liquidity-topline summary-macro-liquidity', scorecard_html)
        self.assertIn(".macro-liquidity-topline", css)
        self.assertIn(".summary-macro-liquidity", css)
        self.assertIn(".summary-action-panel", css)
        self.assertIn(".summary-decision-strip", css)
        self.assertIn("<h2>当前行动 · Portfolio Action</h2>", summary_html)
        self.assertIn("<h2>宏观环境综合评分 · Conditions Score</h2>", summary_html)
        # The headline stance strip surfaces the equity position alongside duration/curve.
        self.assertIn('id="equityBandStance"', html)

    def test_macro_liquidity_mobile_layout_stays_compact(self):
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")

        self.assertRegex(css, re.compile(r"\.summary-macro-liquidity\s+\.macro-liquidity-trend-chart\s*\{[\s\S]*min-height:\s*170px", re.DOTALL))
        self.assertRegex(css, re.compile(r"@media\s*\(max-width:\s*640px\)[\s\S]*\.summary-macro-liquidity\s*\{[\s\S]*grid-template-columns:\s*1fr", re.DOTALL))
        self.assertRegex(css, re.compile(r"@media\s*\(max-width:\s*640px\)[\s\S]*\.macro-liquidity-trend-chart\s*\{[\s\S]*min-height:\s*150px", re.DOTALL))

    def test_decomposition_uses_backend_analysis_briefs(self):
        app_js = FRONTEND_JS

        self.assertIn("frameworkNote", app_js)
        self.assertIn("regimeRead", app_js)
        self.assertIn("policyRead", app_js)

    def test_scorecard_renders_factor_source_mode_badges(self):
        app_js = FRONTEND_JS
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")

        self.assertIn("sourceModeLabel", app_js)
        self.assertIn('"derived-public": "derived"', app_js)
        self.assertIn("factor-source-mode", app_js)
        self.assertIn(".factor-source-mode", css)
        self.assertIn(".factor-source-mode.derived-public", css)
        self.assertIn(".factor-source-mode.manual-placeholder", css)

    def test_scorecard_source_mode_legend_and_mobile_rows_are_compact(self):
        html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
        app_js = FRONTEND_JS
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")

        self.assertIn('id="scorecardSourceLegend"', html)
        self.assertIn('id="bhadialCoveragePanel"', html)
        self.assertIn("renderScorecardSourceLegend", app_js)
        self.assertIn("renderBhadialCoverage", app_js)
        self.assertIn("sourceModeLegendItems", app_js)
        self.assertIn('"derived-public"', app_js)
        self.assertIn(".score-source-legend", css)
        self.assertIn(".bhadial-coverage-grid", css)
        self.assertIn(".bhadial-gap-list", css)
        self.assertRegex(css, re.compile(r"@media\s*\(max-width:\s*640px\)[\s\S]*\.factor-row\s*\{[\s\S]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s+112px", re.DOTALL))
        self.assertRegex(css, re.compile(r"@media\s*\(max-width:\s*640px\)[\s\S]*\.factor-note\s*\{[\s\S]*-webkit-line-clamp:\s*2", re.DOTALL))

    def test_scorecard_leads_with_drivers_and_folds_research_editor(self):
        html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")

        scorecard_start = html.index('<section id="scorecard"')
        scorecard_end = html.index('<section id="policy"')
        scorecard = html[scorecard_start:scorecard_end]
        driver_index = scorecard.index('id="factorDrivers"')
        research_index = scorecard.index('class="diagnostic-details scorecard-research-details"')
        groups_index = scorecard.index('id="scorecardGroups"')
        percentile_index = scorecard.index('id="percentileTrendChart"')
        forward_index = scorecard.index('id="macroLiquidityEquityLead"')
        self.assertLess(driver_index, research_index)
        self.assertLess(research_index, groups_index)
        self.assertLess(groups_index, percentile_index)
        self.assertLess(percentile_index, forward_index)
        self.assertNotIn('scorecard-research-details" open', scorecard)
        self.assertIn(".scorecard-driver-layout", css)
        self.assertIn(".scorecard-research-body", css)
        self.assertRegex(css, re.compile(r"@media \(max-width: 640px\).*?\.section-band\s*\{[^}]*scroll-margin-top:\s*142px", re.DOTALL))

    def test_scorecard_removes_duplicate_stance_cards_and_names_score_controls(self):
        html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
        app_js = FRONTEND_JS
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")
        scorecard = html[html.index('<section id="scorecard"'):html.index('<section id="policy"')]

        self.assertNotIn('class="score-summary"', scorecard)
        self.assertIn('class="scorecard-current-read"', scorecard)
        research_index = scorecard.index('class="diagnostic-details scorecard-research-details"')
        scale_index = scorecard.index('class="score-scale"')
        self.assertLess(research_index, scale_index)
        self.assertIn('role="group" aria-label=', app_js)
        self.assertIn('aria-pressed="${selected ? "true" : "false"}"', app_js)
        self.assertIn('t("score.setAria"', app_js)
        self.assertRegex(css, re.compile(r"\.score-buttons button\s*\{[^}]*min-width:\s*44px;[^}]*height:\s*44px", re.DOTALL))
        self.assertIn(".module-pulse-grid", css)
        self.assertIn(".driver-rank", css)

    def test_forward_signals_lead_with_three_action_cards_and_fold_details(self):
        html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
        app_js = FRONTEND_JS
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")

        panel_start = html.index('id="macroLiquidityEquityLead"')
        panel_end = html.index('id="signalValidationPanel"')
        panel = html[panel_start:panel_end]
        cards_index = panel.index('id="forwardSignalCards"')
        short_index = panel.index('id="equityShortTermRisk"')
        spy_index = panel.index('id="spyEarlyWarning"')
        lppl_index = panel.index('id="globalLpplRisk"')
        self.assertLess(cards_index, short_index)
        self.assertLess(short_index, spy_index)
        self.assertLess(spy_index, lppl_index)
        self.assertEqual(panel.count('class="diagnostic-details forward-signal-detail"'), 3)
        self.assertIn("function renderForwardSignalCards()", app_js)
        self.assertIn('state.portfolioOverview || DEFAULT_DATA.portfolioOverview', app_js)
        self.assertIn("forwardSignalEvidenceText", app_js)
        self.assertIn(".forward-signal-cards", css)
        self.assertIn(".forward-signal-detail-list", css)

    def test_curve_and_policy_lead_with_decision_snapshots_and_fold_research_details(self):
        html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
        app_js = FRONTEND_JS
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")

        curve_start = html.index('<section id="curve"')
        curve_end = html.index('<section id="decomposition"')
        curve = html[curve_start:curve_end]
        self.assertLess(curve.index('id="curveDecisionCards"'), curve.index('id="curveChart"'))
        self.assertLess(curve.index('id="curveDecisionRead"'), curve.index('id="curveTable"'))
        self.assertEqual(curve.count('class="diagnostic-details decision-detail"'), 1)
        self.assertNotIn('decision-detail" open', curve)

        policy_start = html.index('<section id="policy"')
        policy_end = html.index('<section id="supply"')
        policy = html[policy_start:policy_end]
        self.assertLess(policy.index('id="policyDecisionCards"'), policy.index('id="policyCards"'))
        self.assertLess(policy.index('id="policyDecisionRead"'), policy.index('id="fedPathChart"'))
        self.assertEqual(policy.count('class="diagnostic-details decision-detail"'), 2)
        self.assertNotIn('decision-detail" open', policy)

        self.assertIn("function renderCurveDecisionSnapshot()", app_js)
        self.assertIn("function renderPolicyDecisionSnapshot()", app_js)
        self.assertIn("function decisionSnapshotCard", app_js)
        self.assertIn(".decision-snapshot-cards", css)
        self.assertIn(".decision-snapshot-read", css)
        self.assertIn(".decision-detail-list", css)

    def test_remaining_research_sections_use_action_snapshots_and_fold_details(self):
        html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
        app_js = FRONTEND_JS

        sections = (
            ("supply", "positioning", "supplyDecisionCards", "auctionTable", 1),
            ("positioning", "crossmarket", "positioningDecisionCards", "cftcList", 1),
            ("crossmarket", "regions", "crossDecisionCards", "globalYields", 2),
            ("events", "views", "eventsDecisionCards", "eventTimeline", 2),
        )
        for section_id, next_id, cards_id, detail_id, detail_count in sections:
            with self.subTest(section=section_id):
                start = html.index(f'<section id="{section_id}"')
                end = html.index(f'<section id="{next_id}"')
                section = html[start:end]
                self.assertLess(section.index(f'id="{cards_id}"'), section.index(f'id="{detail_id}"'))
                self.assertEqual(section.count('class="diagnostic-details decision-detail"'), detail_count)
                self.assertNotIn('decision-detail" open', section)

        for function_name in (
            "renderSupplyDecisionSnapshot",
            "renderPositioningDecisionSnapshot",
            "renderCrossMarketDecisionSnapshot",
            "renderEventsDecisionSnapshot",
        ):
            self.assertIn(f"function {function_name}()", app_js)
        self.assertIn("Stooq XAUUSD 暂缺有效报价", app_js)

    def test_investment_views_render_ranked_decision_rows_with_editable_details(self):
        html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
        app_js = FRONTEND_JS
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")

        views_start = html.index('<section id="views"')
        views_end = html.index('</main>')
        views = html[views_start:views_end]
        self.assertIn('id="ideaCards" class="idea-decision-list"', views)
        self.assertIn('class="diagnostic-details decision-detail investment-risk-detail"', views)
        self.assertNotIn('investment-risk-detail" open', views)
        self.assertIn("function ideaDecisionFields", app_js)
        self.assertIn("function ideaDecisionFallback", app_js)
        self.assertIn('class="idea-decision-row${', app_js)
        self.assertIn('class="idea-decision-gate trigger"', app_js)
        self.assertIn('class="idea-decision-gate invalidation"', app_js)
        self.assertIn('contenteditable="true" role="textbox" aria-multiline="true"', app_js)
        self.assertIn('data-idea="${index}"', app_js)
        self.assertIn(".idea-decision-summary", css)
        self.assertIn(".idea-decision-body", css)
        self.assertIn(".idea-decision-gate.invalidation", css)

    def test_investment_views_progressively_disclose_and_split_evidence_layers(self):
        app_js = FRONTEND_JS
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")

        self.assertIn("const featured = entries.slice(0, 3);", app_js)
        self.assertIn("const additional = entries.slice(3);", app_js)
        self.assertIn('class="idea-more-details diagnostic-details"', app_js)
        self.assertIn("function ideaEvidenceLayers(idea)", app_js)
        self.assertIn("function renderIdeaEvidenceStrip(evidence)", app_js)
        self.assertIn('t("evidence.model")', app_js)
        self.assertIn('t("evidence.history")', app_js)
        self.assertIn('t("evidence.execution")', app_js)
        self.assertIn(".idea-evidence-strip", css)
        self.assertIn(".idea-evidence-compact", css)
        self.assertIn(".idea-decision-row.primary-view", css)

    def test_small_text_tokens_meet_aa_contrast_baseline(self):
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")

        # These tokens are used by 9.5-12px metadata across the dashboard. The selected
        # values all exceed 4.5:1 against white, --panel-2 and --bg.
        for declaration in (
            "--faint: #6f6b61;",
            "--accent: #805400;",
            "--bull: #167048;",
            "--neutral: #62655c;",
        ):
            self.assertIn(declaration, css)
        self.assertNotIn(".portfolio-overview-layer.tier-unverified { opacity: 0.72; }", css)
        self.assertNotIn(".global-lppl-index-card.missing {\n  opacity: 0.72;", css)

    def test_source_status_modal_exposes_data_coverage(self):
        html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
        app_js = FRONTEND_JS
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")

        for element_id in (
            "openSourceStatus",
            "sourceStatusModal",
            "sourceStatusSummary",
            "sourceStatusTable",
            "closeSourceStatusModal",
        ):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn("sourceStatusCounts", app_js)
        self.assertIn("renderSourceStatusModal", app_js)
        self.assertIn("openSourceStatusModal", app_js)
        self.assertIn("closeSourceStatusModal", app_js)
        self.assertIn(".source-status-grid", css)

    def test_source_status_modal_has_filter_search_and_export(self):
        html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
        app_js = FRONTEND_JS
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")

        for element_id in (
            "sourceStatusControls",
            "sourceStatusSearch",
            "sourceStatusVisibleCount",
            "exportSourceStatusCsv",
        ):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn("data-source-filter", app_js)
        self.assertIn("sourceStatusFilter", app_js)
        self.assertIn("sourceStatusQuery", app_js)
        self.assertIn("filterSourceStatusRows", app_js)
        self.assertIn("exportSourceStatusCsv", app_js)
        self.assertIn(".source-status-controls", css)

    def test_source_status_modal_shows_data_age_and_expected_cadence(self):
        app_js = FRONTEND_JS

        self.assertIn("sourceStatusAgeText", app_js)
        self.assertIn("sourceStatusCadenceText", app_js)
        self.assertIn("<th>数据年龄</th>", app_js)
        self.assertIn("<th>预期节奏</th>", app_js)
        self.assertIn("ageDays", app_js)
        self.assertIn("expectedMaxAgeDays", app_js)

    def test_conclusion_source_quality_is_consumed_from_dashboard_payload(self):
        app_js = FRONTEND_JS

        self.assertIn("conclusionSourceQuality", app_js)
        self.assertIn("state.conclusionSourceQuality", app_js)
        self.assertNotIn("const CONCLUSION_SOURCE_QUALITY =", app_js)

    def test_frontend_can_trigger_manual_background_refresh(self):
        html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
        app_js = FRONTEND_JS
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")

        self.assertIn('id="refreshRuntimeData"', html)
        self.assertIn('id="refreshEquityRisk"', html)
        self.assertIn("/api/update", app_js)
        self.assertIn("/api/update-equity", app_js)
        self.assertIn("runtimeRefreshInFlight", app_js)
        self.assertIn("equityRefreshInFlight", app_js)
        self.assertIn("refreshRuntimeData", app_js)
        self.assertIn("refreshEquityRisk", app_js)
        self.assertIn("#refreshRuntimeData", app_js)
        self.assertIn("#refreshEquityRisk", app_js)
        self.assertRegex(css, re.compile(r"\.data-status-btn:disabled\s*\{[^}]*cursor:\s*progress", re.DOTALL))

    def test_frontend_auto_syncs_runtime_snapshot_without_history_reload(self):
        app_js = FRONTEND_JS

        self.assertRegex(app_js, re.compile(r"const RUNTIME_AUTO_REFRESH_MS\s*=\s*5\s*\*\s*60\s*\*\s*1000"))
        self.assertIn("runtimeAutoRefreshTimer", app_js)
        self.assertIn("startRuntimeAutoRefresh", app_js)
        self.assertIn("refreshRuntimeSnapshotSilently", app_js)
        self.assertIn("document.visibilityState", app_js)
        self.assertIn("window.setInterval", app_js)
        self.assertIn("loadRuntimeData({ refreshHistory: false", app_js)
        self.assertIn('document.addEventListener("visibilitychange"', app_js)

    def test_frontend_surfaces_equity_risk_freshness(self):
        html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
        app_js = FRONTEND_JS
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")

        self.assertIn('id="equityFreshnessStatus"', html)
        self.assertIn("/api/health", app_js)
        self.assertIn("equityRiskFreshness", app_js)
        self.assertIn("loadEquityFreshnessStatus", app_js)
        self.assertIn("renderEquityFreshnessStatus", app_js)
        self.assertIn("EQUITY_FRESHNESS_FAST_REFRESH_MS", app_js)
        self.assertIn("scheduleEquityFreshnessRefresh", app_js)
        self.assertIn("refreshEquityFreshnessSilently", app_js)
        self.assertIn("equityFreshnessRefreshDelay", app_js)
        self.assertIn("clearTimeout(equityFreshnessRefreshTimer)", app_js)
        self.assertIn("#equityFreshnessStatus", app_js)
        self.assertIn("post_close_wait", app_js)
        self.assertIn("equity-freshness-status", css)
        self.assertIn("equity-freshness-waiting", css)
        self.assertIn("equity-freshness-stale", css)

    def test_equity_freshness_polling_uses_failure_backoff(self):
        app_js = FRONTEND_JS

        self.assertIn("EQUITY_FRESHNESS_BACKOFF_MAX_MS", app_js)
        self.assertIn("equityFreshnessFailureCount", app_js)
        self.assertIn("equityFreshnessBackoffDelay", app_js)
        self.assertIn("Math.min(EQUITY_FRESHNESS_BACKOFF_MAX_MS", app_js)

    def test_history_panel_mounts_interactive_chart_controls(self):
        html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
        app_js = FRONTEND_JS
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")

        for element_id in (
            "historyStats",
            "historySeriesSelect",
            "historyRangeControls",
            "historyInteractiveChart",
            "historyChartTooltip",
        ):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn("/api/history/stats", app_js)
        self.assertIn("/api/history/series", app_js)
        self.assertIn("loadHistoryData", app_js)
        self.assertIn("renderInteractiveHistoryChart", app_js)
        self.assertIn("bindHistoryChartHover", app_js)
        self.assertIn("data-history-range", app_js)
        self.assertIn(".history-chart", css)
        self.assertIn(".history-tooltip", css)

    def test_signal_validation_panel_mounts_walk_forward_diagnostics(self):
        html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
        app_js = FRONTEND_JS
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")

        for element_id in (
            "signalValidationPanel",
            "signalValidationMethod",
            "signalValidationCoverage",
            "signalValidationComposites",
            "signalValidationFactors",
            "signalValidationClusters",
        ):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn("renderSignalValidation", app_js)
        self.assertIn("signalValidation:", app_js)
        self.assertIn("signalValidationBadge", app_js)
        self.assertIn("oosIc3m", app_js)
        self.assertIn(".signal-validation-panel", css)
        self.assertIn(".sv-table", css)
        self.assertIn(".sv-badge.leading", css)
        self.assertIn(".sv-lens", css)
        self.assertIn("predictiveLens", app_js)
        # Assets are cache-busted with a versioned query string (exact suffix may change
        # as the bundle evolves; just require app.js carries a non-empty ?v= token).
        self.assertRegex(html, r'src="app\.js\?v=[\w.-]+"')

    def test_portfolio_overview_panel_mounts_three_horizon_card(self):
        html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
        app_js = FRONTEND_JS
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")

        for element_id in (
            "portfolioOverviewPanel",
            "portfolioOverviewBand",
            "portfolioOverviewSummary",
            "portfolioOverviewLayers",
            "portfolioOverviewConflicts",
        ):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn("renderPortfolioOverview", app_js)
        self.assertIn("portfolioOverview:", app_js)
        self.assertIn("portfolioOverviewEvidenceText", app_js)
        self.assertIn(".portfolio-overview-panel", css)
        self.assertIn(".portfolio-overview-conflict", css)
        self.assertIn(".pol-evidence", css)
        # Global regional-tilt dimension surfaced in the headline overview.
        self.assertIn('id="portfolioOverviewRegionalTilt"', html)
        self.assertIn("regionalTilt", app_js)
        self.assertIn("全球地区倾斜", app_js)
        self.assertIn(".portfolio-overview-tilt-card", css)

    def test_regional_monitor_section_mounts_first_level_region_tabs(self):
        html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
        app_js = FRONTEND_JS
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")
        i18n = (PROJECT_ROOT / "i18n.js").read_text(encoding="utf-8")

        # First-level nav entry + dedicated section.
        self.assertIn('href="#regions"', html)
        self.assertIn('data-i18n="nav.regions"', html)
        self.assertIn('id="regions"', html)
        for element_id in (
            "regionalMonitorPanel",
            "regionalMonitorTabs",
            "regionalMonitorAggregate",
            "regionalMonitorGrid",
            "regionalMonitorSummary",
        ):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn("renderRegionalMonitor", app_js)
        self.assertIn("regionalMonitor:", app_js)
        self.assertIn("selectedRegionKey", app_js)
        self.assertIn("data-region-key", app_js)
        self.assertIn(".region-tab", css)
        self.assertIn(".region-agg", css)
        # Per-region price-factor strip (momentum / vol / drawdown / relative strength).
        self.assertIn("globalLpplPriceFactorSummary", app_js)
        self.assertIn("region-factor-strip", app_js)
        self.assertIn("相对美国", app_js)
        self.assertIn(".region-factor-strip", css)
        # Per-region factor forward-validation table.
        self.assertIn('id="regionalMonitorValidation"', html)
        self.assertIn("renderRegionalFactorValidation", app_js)
        self.assertIn("factorValidation", app_js)
        self.assertIn("本地区因子前瞻验证", app_js)
        # Evidence-weighted multi-factor regional composite.
        self.assertIn("证据加权综合信号", app_js)
        self.assertIn("composite", app_js)
        self.assertIn(".region-composite", css)
        # Cross-region diversification (correlation) block.
        self.assertIn('id="regionalMonitorDiversification"', html)
        self.assertIn("renderRegionalDiversification", app_js)
        self.assertIn("跨地区相关性", app_js)
        self.assertIn(".region-corr-pair", css)
        # Round-2 directions: breach track record + composite/rotation bilingual labels.
        self.assertIn("trackRecord", app_js)
        self.assertIn("证据加权综合信号 · Composite", app_js)
        # Rotation is now a prominent action bar: a small "地区轮动 · Rotation" tag over the
        # bold action text (the reduce/favor advice).
        self.assertIn("地区轮动 · Rotation", app_js)
        self.assertIn("region-rotation-action", app_js)
        # Round-4 directions: cluster shared-band chips + US internal rotation.
        self.assertIn("region-reduce-cluster", app_js)
        self.assertIn("减持风险预算", app_js)
        self.assertIn("美股内部轮动", app_js)
        self.assertIn("internalRotation", app_js)
        self.assertIn(".region-internal-rotation", css)
        self.assertIn(".region-reduce-cluster", css)
        # Round-5 directions: US-internal tilt in overview + per-region breach timeline.
        self.assertIn("usInternalTilt", app_js)
        self.assertIn("pot-us-internal", app_js)
        self.assertIn("region-breach-timeline", app_js)
        self.assertIn("历史突破回放", app_js)
        self.assertIn("breachEvents", app_js)
        self.assertIn(".region-breach-dot", css)
        # Breach timeline is clickable → opens that region's LPPL history modal.
        self.assertIn("点击看历史图", app_js)
        self.assertIn(".region-breach-timeline.clickable", css)
        # Dedup: scorecard LPPL panel points to the regional monitor instead of re-rendering cards.
        self.assertIn("global-lppl-regional-pointer", app_js)
        self.assertIn("逐市场卡片", app_js)
        # ①: the pointer is a clickable anchor that jumps to the regions section.
        self.assertRegex(app_js, r'class="global-lppl-regional-pointer" href="#regions"')
        # ③: breach-date markers overlaid on the LPPL history modal chart.
        self.assertIn("globalLpplBreachMarkersSvg", app_js)
        self.assertIn("globalLpplBreachEventsForSymbol", app_js)
        self.assertIn(".global-lppl-breach-marker", css)
        self.assertIn("global-lppl-breach-legend", app_js)
        # Per-region allocation stance + cross-region rotation.
        self.assertIn('id="regionalMonitorRotation"', html)
        self.assertIn("regionStanceClass", app_js)
        self.assertIn("region-alloc-rationale", app_js)
        self.assertIn("region-rotation-tag", app_js)
        self.assertIn(".region-alloc", css)
        self.assertIn(".region-rotation-card", css)
        # Live per-region validated-factor breach alert.
        self.assertIn("factorAlert", app_js)
        self.assertIn("region-factor-alert", app_js)
        self.assertIn("验证阈值", app_js)
        self.assertIn(".region-factor-alert.breached", css)
        # Both languages carry the region nav + section keys.
        self.assertIn('"nav.regions": "地区监控"', i18n)
        self.assertIn('"nav.regions": "Regions"', i18n)


if __name__ == "__main__":
    unittest.main()
