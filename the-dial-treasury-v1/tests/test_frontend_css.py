import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


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
        app_js = (PROJECT_ROOT / "app.js").read_text(encoding="utf-8")

        self.assertIn("percentiles:", app_js)
        self.assertIn("trends:", app_js)
        self.assertIn("银行准备金", app_js)

    def test_frontend_assets_are_cache_busted(self):
        html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")

        self.assertRegex(html, r'href="styles\.css\?v=[^"]+"')
        self.assertRegex(html, r'src="app\.js\?v=[^"]+"')

    def test_header_export_downloads_current_html_document(self):
        html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
        app_js = (PROJECT_ROOT / "app.js").read_text(encoding="utf-8")

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

    def test_percentile_chart_has_expand_modal_controls(self):
        html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
        app_js = (PROJECT_ROOT / "app.js").read_text(encoding="utf-8")

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
        app_js = (PROJECT_ROOT / "app.js").read_text(encoding="utf-8")
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")

        self.assertIn('id="percentileModalControls"', html)
        self.assertIn("data-percentile-mode", app_js)
        self.assertIn("percentileModalMode", app_js)
        self.assertIn("renderPercentileModalChart", app_js)
        self.assertIn("selectPercentileModalTrends", app_js)
        self.assertIn(".chart-mode-controls", css)

    def test_percentile_history_chart_has_focus_and_hover_interactions(self):
        html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
        app_js = (PROJECT_ROOT / "app.js").read_text(encoding="utf-8")
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
        app_js = (PROJECT_ROOT / "app.js").read_text(encoding="utf-8")
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
        app_js = (PROJECT_ROOT / "app.js").read_text(encoding="utf-8")
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
        app_js = (PROJECT_ROOT / "app.js").read_text(encoding="utf-8")
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
        app_js = (PROJECT_ROOT / "app.js").read_text(encoding="utf-8")
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

    def test_investment_views_render_historical_spy_proxy_impact(self):
        app_js = (PROJECT_ROOT / "app.js").read_text(encoding="utf-8")
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")

        self.assertIn("renderIdeaEquityImpact", app_js)
        self.assertIn("equityImpact", app_js)
        self.assertIn("历史SPY影响", app_js)
        self.assertIn("S&P 500 price-index proxy for SPY", app_js)
        self.assertIn(".idea-equity-impact", css)
        self.assertIn(".idea-equity-impact.positive", css)
        self.assertIn(".idea-equity-impact.negative", css)

    def test_macro_liquidity_panel_is_top_of_summary(self):
        html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")

        summary_start = html.index('<section id="summary"')
        summary_end = html.index('<section id="curve"')
        summary_html = html[summary_start:summary_end]
        macro_index = summary_html.index('class="panel macro-liquidity-panel macro-liquidity-topline summary-macro-liquidity"')
        hero_copy_index = summary_html.index('class="hero-copy"')
        stance_index = summary_html.index('class="stance-panel"')
        tiles_index = summary_html.index('id="heroTiles"')
        scorecard_start = html.index('<section id="scorecard"')
        scorecard_end = html.index('<section id="policy"')
        scorecard_html = html[scorecard_start:scorecard_end]
        self.assertLess(macro_index, hero_copy_index)
        self.assertLess(macro_index, stance_index)
        self.assertLess(macro_index, tiles_index)
        self.assertNotIn('macro-liquidity-topline summary-macro-liquidity', scorecard_html)
        self.assertIn(".macro-liquidity-topline", css)
        self.assertIn(".summary-macro-liquidity", css)

    def test_macro_liquidity_mobile_layout_stays_compact(self):
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")

        self.assertRegex(css, re.compile(r"\.summary-macro-liquidity\s+\.macro-liquidity-trend-chart\s*\{[\s\S]*min-height:\s*170px", re.DOTALL))
        self.assertRegex(css, re.compile(r"@media\s*\(max-width:\s*640px\)[\s\S]*\.summary-macro-liquidity\s*\{[\s\S]*grid-template-columns:\s*1fr", re.DOTALL))
        self.assertRegex(css, re.compile(r"@media\s*\(max-width:\s*640px\)[\s\S]*\.macro-liquidity-trend-chart\s*\{[\s\S]*min-height:\s*150px", re.DOTALL))

    def test_decomposition_uses_backend_analysis_briefs(self):
        app_js = (PROJECT_ROOT / "app.js").read_text(encoding="utf-8")

        self.assertIn("frameworkNote", app_js)
        self.assertIn("regimeRead", app_js)
        self.assertIn("policyRead", app_js)

    def test_scorecard_renders_factor_source_mode_badges(self):
        app_js = (PROJECT_ROOT / "app.js").read_text(encoding="utf-8")
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")

        self.assertIn("sourceModeLabel", app_js)
        self.assertIn('"derived-public": "derived"', app_js)
        self.assertIn("factor-source-mode", app_js)
        self.assertIn(".factor-source-mode", css)
        self.assertIn(".factor-source-mode.derived-public", css)
        self.assertIn(".factor-source-mode.manual-placeholder", css)

    def test_scorecard_source_mode_legend_and_mobile_rows_are_compact(self):
        html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
        app_js = (PROJECT_ROOT / "app.js").read_text(encoding="utf-8")
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

    def test_source_status_modal_exposes_data_coverage(self):
        html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
        app_js = (PROJECT_ROOT / "app.js").read_text(encoding="utf-8")
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
        app_js = (PROJECT_ROOT / "app.js").read_text(encoding="utf-8")
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

    def test_frontend_can_trigger_manual_background_refresh(self):
        html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
        app_js = (PROJECT_ROOT / "app.js").read_text(encoding="utf-8")
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")

        self.assertIn('id="refreshRuntimeData"', html)
        self.assertIn("/api/update", app_js)
        self.assertIn("runtimeRefreshInFlight", app_js)
        self.assertIn("refreshRuntimeData", app_js)
        self.assertIn("#refreshRuntimeData", app_js)
        self.assertRegex(css, re.compile(r"\.data-status-btn:disabled\s*\{[^}]*cursor:\s*progress", re.DOTALL))

    def test_history_panel_mounts_interactive_chart_controls(self):
        html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
        app_js = (PROJECT_ROOT / "app.js").read_text(encoding="utf-8")
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


if __name__ == "__main__":
    unittest.main()
