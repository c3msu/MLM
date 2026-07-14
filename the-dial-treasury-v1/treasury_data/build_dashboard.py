from __future__ import annotations

import copy
import json
import math
import re
import sqlite3
from statistics import median
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from .sources import (
    AcmRecord,
    CalendarEvent,
    CftcTreasuryPosition,
    DebtLimitStatus,
    FomcProjection,
    MarketDailyBar,
    MarketQuote,
    NewsItem,
    OptionOpenInterestSnapshot,
    PrimaryDealerStats,
    QuarterlyRefunding,
    TENORS,
    SeriesPoint,
    TicHolding,
    TicHoldings,
    TimeSeries,
    YieldCurveRecord,
    fetch_acm_term_premium,
    fetch_announced_auctions,
    fetch_bea_release_events,
    fetch_cftc_treasury_positions,
    fetch_debt_limit_status,
    fetch_fed_funds_futures_quote,
    fetch_federal_reserve_press_releases,
    fetch_fomc_calendar_events,
    fetch_fomc_projection,
    fetch_fred_series_bulk,
    fetch_fred_macro_release_events,
    fetch_gold_spot_quote,
    fetch_cboe_option_open_interest,
    fetch_nasdaq_daily_bars,
    fetch_primary_dealer_stats,
    fetch_quarterly_refunding,
    fetch_stooq_daily_bars,
    fetch_tic_major_holders,
    fetch_treasury_press_releases,
    fetch_treasury_auctions,
    fetch_treasury_yield_curves,
    fetch_text_curl_first,
    nearest_record,
)
from .signal_validation import (
    MIN_SIGNAL_VALIDATION_POINTS,
    SortedSeries,
    signal_validation_metric_row,
    trailing_return_values,
    classify_lead_lag,
    effective_weights,
    evaluate_signal,
    pearson_correlation,
    redundancy_clusters,
    spearman_ic,
    weekly_dates,
)
from .series_math import *  # noqa: F401,F403  (facade re-export, Phase 1 refactor)
from .dashboard_core import *  # noqa: F401,F403  (facade re-export, Phase 1 refactor)
from .dashboard_core import _float_or_zero  # noqa: F401  (underscore name not covered by import *)
from .dashboard_format import *  # noqa: F401,F403  (facade re-export, shared parsing/formatting)
from .fetch import *  # noqa: F401,F403  (facade re-export, Phase 1 refactor)
from .indicators import *  # noqa: F401,F403  (facade re-export, Phase 1 refactor)
from .scoring_bhadial import *  # noqa: F401,F403  (facade re-export, Phase 1 refactor)
from .factor_groups import *  # noqa: F401,F403  (facade re-export, factor-group extraction)
from .scoring_spy_warning import *  # noqa: F401,F403  (facade re-export, Phase 1 refactor)
from .scoring_equity import *  # noqa: F401,F403  (facade re-export, Phase 1 refactor)
from .scoring_lppl import *  # noqa: F401,F403  (facade re-export, Phase 1 refactor)
from .scoring_lppl_validation import *  # noqa: F401,F403  (facade re-export, LPPL validation extraction)
from . import scoring_lppl_history as _lppl_history
from .scoring_lppl_history import *  # noqa: F401,F403  (facade re-export, LPPL history extraction)
from .scoring_regional import *  # noqa: F401,F403  (facade re-export, Phase 1 refactor)
from .investment_views import *  # noqa: F401,F403  (facade re-export, investment-view extraction)
from .validation_build import *  # noqa: F401,F403  (facade re-export, Phase 1 refactor)
from .advice import *  # noqa: F401,F403  (facade re-export, Phase 1 refactor)
from .live_sources import LiveSourceTask, run_live_source_tasks

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OVERRIDES_PATH = PROJECT_ROOT / "content" / "overrides.json"
CONCLUSION_SOURCE_QUALITY = {
    "real-public": 1.0,
    "derived-public": 0.9,
    "official-news": 0.8,
    "proxy-public": 0.65,
    "modeled": 0.55,
    "manual-placeholder": 0.25,
}
LOWER_CONFIDENCE_SOURCE_MODES = {"proxy-public", "modeled", "manual-placeholder"}
REMOTE_COMPATIBILITY_FACTOR_NAMES = [
    "隐含政策路径",
    "新任主席倾向",
    "增长动能",
    "30年期拍卖",
    "一级交易商持仓",
    "互换利差",
    "市场流动性",
    "新老券利差",
]

# 实际计入综合分的因子本地名(唯一真相): 去冗余后=21。覆盖率面板的 inScorecard 据此判定,
# 被剔除的因子仍作为原始指标展示(display)但 inScorecard=False。

FRED_SERIES = [
    "DFII5",
    "DFII10",
    "T10YIE",
    "DFF",
    "SOFR",
    "OBFR",
    "IORB",
    "RRPONTSYAWARD",
    "RPONTSYD",
    "WTREGEN",
    "WALCL",
    "TREAST",
    "WRESBAL",
    "RRPONTSYD",
    "CPIAUCSL",
    "PCEPI",
    "PCEPILFE",
    "PCETRIM12M159SFRBDAL",
    "PPIACO",
    "UNRATE",
    "PAYEMS",
    "GDPC1",
    "SP500",
    "VIXCLS",
    "VXVCLS",
    "DTWEXBGS",
    "DCPF3M",
    "DTB3",
    "NFCI",
    "BAMLH0A0HYM2",
    "BAMLC0A0CM",
    "IRLTLT01JPM156N",
    "IRLTLT01DEM156N",
    "IRLTLT01GBM156N",
    "DCOILWTICO",
    "DHHNGSP",
    "OVXCLS",
    "GVZCLS",
    "DGS10",
    "NASDAQXNDX",
    "NASDAQNQUS500LCT",
    "NASDAQBANK",
    "BAMLHYH0A0HYM2TRIV",
    "BAMLCC0A0CMTRIV",
]

# Each index carries structured region metadata so the dashboard can group factors by
# first-class region (US groups SPY+QQQ) rather than burying HK/TW/JP as "ETF proxy"
# sub-rows. regionKey is the stable grouping key; proxyNote keeps the data source transparent.
GLOBAL_LPPL_INDEX_SPECS: list[dict[str, Any]] = [
    {
        "symbol": "SPY",
        "name": "S&P 500",
        "region": "United States",
        "regionKey": "us",
        "regionName": "United States",
        "regionNameCn": "美国",
        "proxyNote": "S&P 500 ETF · SPY",
        "proxyNoteCn": "标普500 · SPY",
        "source": "nasdaq",
        "sourceSymbol": "SPY",
        "fallbackSymbol": "spy.us",
        "assetClass": "etf",
        "sourceQuality": "high",
        "weight": 0.23,
    },
    {
        "symbol": "QQQ",
        "name": "Nasdaq 100",
        "region": "United States",
        "regionKey": "us",
        "regionName": "United States",
        "regionNameCn": "美国",
        "proxyNote": "Nasdaq 100 ETF · QQQ",
        "proxyNoteCn": "纳斯达克100 · QQQ",
        "source": "nasdaq",
        "sourceSymbol": "QQQ",
        "fallbackSymbol": "qqq.us",
        "assetClass": "etf",
        "sourceQuality": "high",
        "weight": 0.23,
    },
    {
        "symbol": "KOSPI",
        "name": "KOSPI",
        "region": "South Korea",
        "regionKey": "korea",
        "regionName": "South Korea",
        "regionNameCn": "韩国",
        "proxyNote": "US-listed ETF proxy · EWY",
        "proxyNoteCn": "美上市ETF代理 · EWY",
        "source": "nasdaq",
        "sourceSymbol": "EWY",
        "fallbackSymbol": "ewy.us",
        "assetClass": "etf",
        "sourceQuality": "medium",
        "weight": 0.13,
    },
    {
        "symbol": "HSI",
        "name": "Hang Seng",
        "region": "Hong Kong",
        "regionKey": "hongkong",
        "regionName": "Hong Kong",
        "regionNameCn": "香港",
        "proxyNote": "US-listed ETF proxy · EWH",
        "proxyNoteCn": "美上市ETF代理 · EWH",
        "source": "nasdaq",
        "sourceSymbol": "EWH",
        "fallbackSymbol": "ewh.us",
        "assetClass": "etf",
        "sourceQuality": "medium",
        "weight": 0.13,
    },
    {
        "symbol": "TWII",
        "name": "Taiwan Weighted",
        "region": "Taiwan",
        "regionKey": "taiwan",
        "regionName": "Taiwan",
        "regionNameCn": "台湾",
        "proxyNote": "US-listed ETF proxy · EWT",
        "proxyNoteCn": "美上市ETF代理 · EWT",
        "source": "nasdaq",
        "sourceSymbol": "EWT",
        "fallbackSymbol": "ewt.us",
        "assetClass": "etf",
        "sourceQuality": "medium",
        "weight": 0.13,
    },
    {
        "symbol": "NIKKEI",
        "name": "Nikkei 225",
        "region": "Japan",
        "regionKey": "japan",
        "regionName": "Japan",
        "regionNameCn": "日本",
        "proxyNote": "US-listed ETF proxy · EWJ",
        "proxyNoteCn": "美上市ETF代理 · EWJ",
        "source": "nasdaq",
        "sourceSymbol": "EWJ",
        "fallbackSymbol": "ewj.us",
        "assetClass": "etf",
        "sourceQuality": "medium",
        "weight": 0.15,
    },
]
def fetch_daily_bars_with_stooq_fallback(
    symbol: str,
    *,
    start: date,
    end: date,
    asset_class: str = "stocks",
    timeout: int = 14,
    limit: int = 900,
    fallback_symbol: str | None = None,
    output_symbol: str | None = None,
    fetcher: DailyBarFetcher | None = None,
    fallback_fetcher: DailyBarFetcher | None = None,
) -> tuple[list[MarketDailyBar], dict[str, Any]]:
    primary_fetcher = fetcher or fetch_nasdaq_daily_bars
    stooq_fetcher = fallback_fetcher or fetch_stooq_daily_bars
    try:
        bars = primary_fetcher(symbol, start=start, end=end, asset_class=asset_class, timeout=timeout, limit=limit)
        latest = bars[-1].date.isoformat() if bars else "none"
        return remap_market_bars_symbol(bars, output_symbol or symbol), {"status": "ok", "latest": latest, "source": "nasdaq"}
    except Exception as nasdaq_exc:  # noqa: BLE001
        fallback = stooq_fallback_symbol(symbol, fallback_symbol)
        try:
            bars = stooq_fetcher(fallback, start=start, end=end, timeout=timeout)
        except Exception as fallback_exc:  # noqa: BLE001
            raise RuntimeError(f"Nasdaq failed ({nasdaq_exc}); Stooq fallback {fallback} failed ({fallback_exc})") from fallback_exc
        latest = bars[-1].date.isoformat() if bars else "none"
        note = f"Nasdaq failed; using Stooq {fallback}: {nasdaq_exc}"
        return remap_market_bars_symbol(bars, output_symbol or symbol), {
            "status": "ok",
            "latest": latest,
            "source": "stooq-fallback",
            "note": note,
        }


def build_live_dashboard() -> dict[str, Any]:
    equity_end = datetime.now(timezone.utc).date()
    equity_start = equity_end - timedelta(days=365 * 3 + 10)
    tasks = [
        LiveSourceTask("curve", "treasury", lambda: fetch_treasury_yield_curves()),
        LiveSourceTask("fred", "fred", lambda: fetch_fred_series_bulk(FRED_SERIES)),
        LiveSourceTask("auctions", "treasury", lambda: fetch_treasury_auctions()),
        LiveSourceTask("announced-auctions", "treasury", lambda: fetch_announced_auctions()),
        LiveSourceTask("fomc-calendar", "federal-reserve", lambda: fetch_fomc_calendar_events()),
        LiveSourceTask("fred-calendar", "fred", lambda: fetch_fred_macro_release_events()),
        LiveSourceTask("bea-calendar", "bea", lambda: fetch_bea_release_events()),
        LiveSourceTask("fomc-projection", "federal-reserve", lambda: fetch_fomc_projection()),
        LiveSourceTask("acm", "new-york-fed", lambda: fetch_acm_term_premium()),
        LiveSourceTask("cftc", "cftc", lambda: fetch_cftc_treasury_positions()),
        LiveSourceTask("tic", "treasury", lambda: fetch_tic_major_holders()),
        LiveSourceTask("primary-dealer", "new-york-fed", lambda: fetch_primary_dealer_stats()),
        LiveSourceTask("quarterly-refunding", "treasury", lambda: fetch_quarterly_refunding()),
        LiveSourceTask("debt-limit", "treasury", lambda: fetch_debt_limit_status()),
        LiveSourceTask("fed-funds-futures", "stooq", lambda: fetch_fed_funds_futures_quote()),
        LiveSourceTask("gold", "stooq", lambda: fetch_gold_spot_quote()),
    ]
    for index, (symbol, asset_class) in enumerate(EQUITY_RISK_SYMBOLS.items()):
        tasks.append(
            LiveSourceTask(
                f"equity:{symbol}",
                f"market-{index % 3}",
                lambda symbol=symbol, asset_class=asset_class: fetch_daily_bars_with_stooq_fallback(
                    symbol,
                    start=equity_start,
                    end=equity_end,
                    asset_class=asset_class,
                    timeout=14,
                    limit=900,
                ),
            )
        )
    global_fetch_specs = [
        spec for spec in GLOBAL_LPPL_INDEX_SPECS if str(spec["symbol"]).upper() not in EQUITY_RISK_SYMBOLS
    ]
    for index, spec in enumerate(global_fetch_specs):
        symbol = str(spec["symbol"]).upper()
        if spec.get("source") == "nasdaq":
            fetch = lambda spec=spec, symbol=symbol: fetch_daily_bars_with_stooq_fallback(
                str(spec["sourceSymbol"]),
                start=equity_start,
                end=equity_end,
                asset_class=str(spec.get("assetClass") or "etf"),
                timeout=14,
                limit=900,
                fallback_symbol=str(spec.get("fallbackSymbol") or ""),
                output_symbol=symbol,
            )
        elif spec.get("source") == "stooq":
            fetch = lambda spec=spec: fetch_stooq_daily_bars(
                str(spec["sourceSymbol"]), start=equity_start, end=equity_end, timeout=14
            )
        else:
            continue
        tasks.append(LiveSourceTask(f"global:{symbol}", f"market-{index % 3}", fetch))
    tasks.extend(
        [
            LiveSourceTask("option-open-interest", "cboe", lambda: fetch_cboe_option_open_interest("SPY")),
            LiveSourceTask("fed-news", "federal-reserve", lambda: fetch_federal_reserve_press_releases()),
            LiveSourceTask("treasury-news", "treasury", lambda: fetch_treasury_press_releases()),
            LiveSourceTask("benchmark", "bhadial", lambda: fetch_bhadial_public_score()),
        ]
    )

    # Six workers bound total network concurrency.  Provider lanes serialize
    # same-domain requests; the three market lanes deliberately cap the large
    # equity/global symbol batch at three concurrent requests.
    results = {result.key: result for result in run_live_source_tasks(tasks, max_workers=6)}

    source_status: list[dict[str, Any]] = []
    curve_records: list[YieldCurveRecord] = []
    auctions: list[dict[str, object]] = []
    announced_auctions: list[dict[str, object]] = []
    calendar_events: list[CalendarEvent] = []
    fomc_projection: FomcProjection | None = None
    fred: dict[str, TimeSeries] = {}
    acm: AcmRecord | None = None
    cftc_positions: list[CftcTreasuryPosition] = []
    tic_holdings: TicHoldings | None = None
    primary_dealer_stats: PrimaryDealerStats | None = None
    quarterly_refunding: QuarterlyRefunding | None = None
    debt_limit_status: DebtLimitStatus | None = None
    fed_funds_futures: MarketQuote | None = None
    gold_quote: MarketQuote | None = None
    equity_market_bars: dict[str, list[MarketDailyBar]] = {}
    global_lppl_market_bars: dict[str, list[MarketDailyBar]] = {}
    option_open_interest: OptionOpenInterestSnapshot | None = None
    official_news: list[NewsItem] = []

    try:
        curve_records = results["curve"].get()
        latest = curve_records[-1].date.isoformat() if curve_records else "none"
        source_status.append({"name": "U.S. Treasury yield curve XML", "status": "ok", "latest": latest})
    except Exception as exc:  # noqa: BLE001
        try:
            dgs_fred = fetch_fred_series_bulk(FRED_TREASURY_CURVE_SERIES.values(), chunk_size=len(FRED_TREASURY_CURVE_SERIES))
            curve_records = build_fred_dgs_curve_records(dgs_fred)
            if not curve_records:
                raise ValueError("FRED DGS fallback did not return a complete curve")
            latest = curve_records[-1].date.isoformat()
            source_status.append(
                {
                    "name": "U.S. Treasury yield curve XML",
                    "status": "warning",
                    "latest": f"FRED DGS fallback through {latest}; Treasury XML failed: {exc}",
                    "source": "fred-fallback",
                    "note": "Curve built from FRED DGS1MO...DGS30 because Treasury XML was unavailable.",
                }
            )
        except Exception as fallback_exc:  # noqa: BLE001
            source_status.append({"name": "U.S. Treasury yield curve XML", "status": "error", "latest": f"{exc}; FRED DGS fallback failed: {fallback_exc}"})

    try:
        fred = results["fred"].get()
        for series_id in FRED_SERIES:
            series = fred.get(series_id)
            if series:
                source_status.append({"name": f"FRED {series_id}", "status": "ok", "latest": series.latest.date.isoformat()})
            else:
                source_status.append({"name": f"FRED {series_id}", "status": "error", "latest": "missing from bulk daily.csv"})
    except Exception as exc:  # noqa: BLE001
        for series_id in FRED_SERIES:
            source_status.append({"name": f"FRED {series_id}", "status": "error", "latest": str(exc)})

    try:
        auctions = results["auctions"].get()
        source_status.append({"name": "TreasuryDirect auctioned securities", "status": "ok", "latest": str(len(auctions))})
    except Exception as exc:  # noqa: BLE001
        auctions = load_historical_auction_fallback()
        if auctions:
            latest = max(str(item.get("auctionDate") or "") for item in auctions)
            source_status.append(
                {
                    "name": "TreasuryDirect auctioned securities",
                    "status": "warning",
                    "latest": f"live fetch failed; using {len(auctions)} cached observations through {latest}: {exc}",
                }
            )
        else:
            source_status.append({"name": "TreasuryDirect auctioned securities", "status": "error", "latest": str(exc)})

    try:
        announced_auctions = results["announced-auctions"].get()
        source_status.append({"name": "TreasuryDirect announced securities", "status": "ok", "latest": str(len(announced_auctions))})
    except Exception as exc:  # noqa: BLE001
        source_status.append({"name": "TreasuryDirect announced securities", "status": "warning", "latest": str(exc)})

    try:
        calendar_events = results["fomc-calendar"].get()
        latest = max((event.date for event in calendar_events), default=None)
        source_status.append({"name": "Federal Reserve FOMC calendar", "status": "ok", "latest": latest.isoformat() if latest else "none"})
    except Exception as exc:  # noqa: BLE001
        source_status.append({"name": "Federal Reserve FOMC calendar", "status": "error", "latest": str(exc)})

    try:
        macro_events = results["fred-calendar"].get()
        calendar_events.extend(macro_events)
        latest = max((event.date for event in macro_events), default=None)
        source_status.append({"name": "FRED economic release calendar", "status": "ok", "latest": latest.isoformat() if latest else "none"})
    except Exception as exc:  # noqa: BLE001
        source_status.append({"name": "FRED economic release calendar", "status": "error", "latest": str(exc)})

    try:
        bea_events = results["bea-calendar"].get()
        calendar_events.extend(bea_events)
        latest = max((event.date for event in bea_events), default=None)
        source_status.append({"name": "BEA release schedule", "status": "ok", "latest": latest.isoformat() if latest else "none"})
    except Exception as exc:  # noqa: BLE001
        source_status.append({"name": "BEA release schedule", "status": "error", "latest": str(exc)})

    try:
        fomc_projection = results["fomc-projection"].get()
        source_status.append({"name": "Federal Reserve SEP projections", "status": "ok", "latest": fomc_projection.release_date.isoformat()})
    except Exception as exc:  # noqa: BLE001
        source_status.append({"name": "Federal Reserve SEP projections", "status": "warning", "latest": str(exc)})

    try:
        acm = results["acm"].get()
        source_status.append({"name": "NY Fed ACM term premium", "status": "ok", "latest": acm.date.isoformat()})
    except Exception as exc:  # noqa: BLE001
        source_status.append({"name": "NY Fed ACM term premium", "status": "error", "latest": str(exc)})

    try:
        cftc_positions = results["cftc"].get()
        latest = cftc_positions[0].report_date.isoformat() if cftc_positions else "none"
        source_status.append({"name": "CFTC financial futures COT", "status": "ok", "latest": latest})
    except Exception as exc:  # noqa: BLE001
        source_status.append({"name": "CFTC financial futures COT", "status": "error", "latest": str(exc)})

    try:
        tic_holdings = results["tic"].get()
        source_status.append({"name": "Treasury TIC major foreign holders", "status": "ok", "latest": tic_holdings.period})
    except Exception as exc:  # noqa: BLE001
        source_status.append({"name": "Treasury TIC major foreign holders", "status": "error", "latest": str(exc)})

    try:
        primary_dealer_stats = results["primary-dealer"].get()
        source_status.append({"name": "NY Fed primary dealer statistics", "status": "ok", "latest": primary_dealer_stats.as_of.isoformat()})
    except Exception as exc:  # noqa: BLE001
        source_status.append({"name": "NY Fed primary dealer statistics", "status": "error", "latest": str(exc)})

    try:
        quarterly_refunding = results["quarterly-refunding"].get()
        source_status.append({"name": "U.S. Treasury quarterly refunding documents", "status": "ok", "latest": quarterly_refunding.release_date.isoformat()})
    except Exception as exc:  # noqa: BLE001
        source_status.append({"name": "U.S. Treasury quarterly refunding documents", "status": "error", "latest": str(exc)})

    try:
        debt_limit_status = results["debt-limit"].get()
        source_status.append({"name": "Treasury Fiscal Data debt subject to limit", "status": "ok", "latest": debt_limit_status.record_date.isoformat()})
    except Exception as exc:  # noqa: BLE001
        source_status.append({"name": "Treasury Fiscal Data debt subject to limit", "status": "error", "latest": str(exc)})

    try:
        fed_funds_futures = results["fed-funds-futures"].get()
        source_status.append({"name": "Stooq 30-Day Fed Funds futures ZQ.F", "status": "ok", "latest": fed_funds_futures.date.isoformat()})
    except Exception as exc:  # noqa: BLE001
        source_status.append({"name": "Stooq 30-Day Fed Funds futures ZQ.F", "status": "warning", "latest": str(exc)})

    try:
        gold_quote = results["gold"].get()
        source_status.append({"name": "Stooq gold spot XAUUSD", "status": "ok", "latest": gold_quote.date.isoformat()})
    except Exception as exc:  # noqa: BLE001
        source_status.append({"name": "Stooq gold spot XAUUSD", "status": "warning", "latest": str(exc)})

    for symbol in EQUITY_RISK_SYMBOLS:
        try:
            bars, status = results[f"equity:{symbol}"].get()
            equity_market_bars[symbol] = bars
            source_status.append({"name": f"Nasdaq {symbol} OHLCV", **status})
        except Exception as exc:  # noqa: BLE001
            source_status.append({"name": f"Nasdaq {symbol} OHLCV", "status": "warning", "latest": str(exc)})

    global_lppl_market_bars.update({symbol: bars for symbol, bars in equity_market_bars.items() if symbol in {"SPY", "QQQ"}})
    for spec in GLOBAL_LPPL_INDEX_SPECS:
        symbol = str(spec["symbol"]).upper()
        if symbol in global_lppl_market_bars:
            bars = global_lppl_market_bars[symbol]
            latest = bars[-1].date.isoformat() if bars else "none"
            source_status.append({"name": f"Global LPPL {symbol} OHLCV", "status": "ok", "latest": latest})
            continue
        if spec.get("source") == "nasdaq":
            try:
                bars, status = results[f"global:{symbol}"].get()
                global_lppl_market_bars[symbol] = bars
                source_status.append({"name": f"Global LPPL {symbol} OHLCV", **status})
            except Exception as exc:  # noqa: BLE001
                source_status.append({"name": f"Global LPPL {symbol} OHLCV", "status": "warning", "latest": str(exc)})
            continue
        if spec.get("source") != "stooq":
            continue
        try:
            bars = results[f"global:{symbol}"].get()
            global_lppl_market_bars[symbol] = [MarketDailyBar(symbol=symbol, date=bar.date, open=bar.open, high=bar.high, low=bar.low, close=bar.close, volume=bar.volume, source=bar.source) for bar in bars]
            latest = bars[-1].date.isoformat() if bars else "none"
            source_status.append({"name": f"Global LPPL {symbol} OHLCV", "status": "ok", "latest": latest})
        except Exception as exc:  # noqa: BLE001
            source_status.append({"name": f"Global LPPL {symbol} OHLCV", "status": "warning", "latest": str(exc)})

    try:
        option_open_interest = results["option-open-interest"].get()
        source_status.append({"name": "Cboe SPY option open interest", "status": "ok", "latest": option_open_interest.as_of.isoformat()})
    except Exception as exc:  # noqa: BLE001
        source_status.append({"name": "Cboe SPY option open interest", "status": "warning", "latest": str(exc)})

    try:
        fed_news = results["fed-news"].get()
        official_news.extend(fed_news)
        latest = max((item.date for item in fed_news), default=None)
        source_status.append({"name": "Federal Reserve press release RSS", "status": "ok", "latest": latest.isoformat() if latest else "none"})
    except Exception as exc:  # noqa: BLE001
        source_status.append({"name": "Federal Reserve press release RSS", "status": "warning", "latest": str(exc)})

    try:
        treasury_news = results["treasury-news"].get()
        official_news.extend(treasury_news)
        latest = max((item.date for item in treasury_news), default=None)
        source_status.append({"name": "U.S. Treasury press releases", "status": "ok", "latest": latest.isoformat() if latest else "none"})
    except Exception as exc:  # noqa: BLE001
        source_status.append({"name": "U.S. Treasury press releases", "status": "warning", "latest": str(exc)})

    dashboard = build_dashboard_from_inputs(
        curve_records=curve_records,
        fred=fred,
        auctions=auctions,
        generated_at=datetime.now(timezone.utc),
        acm=acm,
        cftc_positions=cftc_positions,
        tic_holdings=tic_holdings,
        fomc_projection=fomc_projection,
        primary_dealer_stats=primary_dealer_stats,
        quarterly_refunding=quarterly_refunding,
        debt_limit_status=debt_limit_status,
        fed_funds_futures=fed_funds_futures,
        gold_quote=gold_quote,
        official_news=official_news,
        calendar_events=calendar_events,
        announced_auctions=announced_auctions,
        equity_market_bars=equity_market_bars,
        global_lppl_market_bars=global_lppl_market_bars,
        option_open_interest=option_open_interest,
        overrides=load_content_overrides(),
    )
    try:
        benchmark_score = results["benchmark"].get()
        macro_liquidity = dashboard.get("macroLiquidity")
        if isinstance(macro_liquidity, dict):
            local_score = optional_float(macro_liquidity.get("score"))
            macro_liquidity["benchmark"] = {
                "score": round(benchmark_score, 1),
                "delta": round(local_score - benchmark_score, 1) if local_score is not None else None,
                "sourceUrl": BHADIAL_SCORE_SOURCE_URL,
                "status": "ok",
            }
        source_status.append({"name": "Bhadial public score benchmark", "status": "ok", "latest": f"{benchmark_score:.1f}"})
    except Exception as exc:  # noqa: BLE001
        macro_liquidity = dashboard.get("macroLiquidity")
        if isinstance(macro_liquidity, dict):
            macro_liquidity["benchmark"] = {"sourceUrl": BHADIAL_SCORE_SOURCE_URL, "status": "warning", "latest": str(exc)}
        source_status.append({"name": "Bhadial public score benchmark", "status": "warning", "latest": str(exc)})
    # Pass as_of from this module's (patchable) clock so freshness uses the same wall-clock
    # the orchestration does — the freshness helper now lives in fetch.py with its own datetime.
    dashboard["sourceStatus"] = annotate_source_status_freshness(
        source_status + dashboard.get("sourceStatus", []),
        as_of=datetime.now(timezone.utc).date(),
    )
    dashboard["conclusionAudit"] = build_conclusion_audit(dashboard.get("groups", []), source_status=dashboard["sourceStatus"])
    return dashboard


def load_historical_auction_fallback(db_path: Path | None = None) -> list[dict[str, object]]:
    path = db_path or PROJECT_ROOT / "data" / "history.sqlite3"
    if not path.exists():
        return []
    query = """
        select date, label, value
        from historical_observations
        where category = 'auction'
          and name = '拍卖投标倍数'
        order by date
    """
    try:
        with sqlite3.connect(path) as connection:
            rows = connection.execute(query).fetchall()
    except sqlite3.Error:
        return []
    auctions: list[dict[str, object]] = []
    for auction_date, label, bid_to_cover in rows:
        term, security_type = split_auction_label(str(label or ""))
        auctions.append(
            {
                "auctionDate": str(auction_date),
                "securityTerm": term,
                "securityType": security_type,
                "bidToCoverRatio": str(bid_to_cover),
            }
        )
    return auctions


def split_auction_label(label: str) -> tuple[str, str]:
    normalized = label.strip()
    for security_type in ("TIPS", "FRN", "Bill", "Note", "Bond"):
        suffix = f" {security_type}"
        if normalized.endswith(suffix):
            return normalized[: -len(suffix)].strip(), security_type
    return normalized, ""


def parse_bhadial_public_score(html_content: str) -> float:
    patterns = (
        r'class="hero-gauge-score"[^>]*>\s*([0-9]+(?:\.[0-9]+)?)\s*<',
        r'"marketingTeaser"\s*:\s*\{[^}]*"score"\s*:\s*([0-9]+(?:\.[0-9]+)?)',
    )
    for pattern in patterns:
        match = re.search(pattern, html_content)
        if match:
            return float(match.group(1))
    raise ValueError("Bhadial public score was not found in the dashboard HTML")


def fetch_bhadial_public_score(timeout: int = 12) -> float:
    return parse_bhadial_public_score(fetch_text_curl_first(BHADIAL_SCORE_SOURCE_URL, timeout=timeout, retries=0))


def build_dashboard_from_inputs(
    *,
    curve_records: list[YieldCurveRecord],
    fred: dict[str, TimeSeries],
    auctions: list[dict[str, object]],
    generated_at: datetime,
    acm: AcmRecord | None = None,
    cftc_positions: list[CftcTreasuryPosition] | None = None,
    tic_holdings: TicHoldings | None = None,
    fomc_projection: FomcProjection | None = None,
    primary_dealer_stats: PrimaryDealerStats | None = None,
    quarterly_refunding: QuarterlyRefunding | None = None,
    debt_limit_status: DebtLimitStatus | None = None,
    fed_funds_futures: MarketQuote | None = None,
    gold_quote: MarketQuote | None = None,
    official_news: list[NewsItem] | None = None,
    calendar_events: list[CalendarEvent] | None = None,
    announced_auctions: list[dict[str, object]] | None = None,
    equity_market_bars: dict[str, list[MarketDailyBar]] | None = None,
    global_lppl_market_bars: dict[str, list[MarketDailyBar]] | None = None,
    option_open_interest: OptionOpenInterestSnapshot | None = None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not curve_records:
        raise ValueError("A real Treasury yield curve is required to build dashboard data")

    today = curve_records[-1]
    one_day = nearest_record(curve_records[:-1] or curve_records, today.date - timedelta(days=1))
    one_week = nearest_record(curve_records, today.date - timedelta(days=7))
    one_month = nearest_record(curve_records, today.date - timedelta(days=30))

    d1 = [round(today.values[tenor] - one_day.values[tenor], 4) for tenor in TENORS]
    curve = {
        "tenors": TENORS,
        "today": [today.values[tenor] for tenor in TENORS],
        "w1": [one_week.values[tenor] for tenor in TENORS],
        "m1": [one_month.values[tenor] for tenor in TENORS],
        "d1": d1,
    }

    indicators = compute_indicators(
        today=today,
        one_week=one_week,
        one_month=one_month,
        curve_records=curve_records,
        fred=fred,
        fed_funds_futures=fed_funds_futures,
        gold_quote=gold_quote,
    )
    cftc_positions = cftc_positions or []
    groups = build_groups(
        indicators,
        auctions=auctions,
        cftc_positions=cftc_positions,
        tic_holdings=tic_holdings,
        acm=acm,
        primary_dealer_stats=primary_dealer_stats,
        quarterly_refunding=quarterly_refunding,
        debt_limit_status=debt_limit_status,
        official_news=official_news or [],
        as_of=today.date,
    )
    policy = build_policy(indicators)
    macro_liquidity = build_macro_liquidity_score(indicators, as_of=today.date)
    macro_liquidity_equity = build_macro_liquidity_equity_lead(indicators)
    spy_early_warning = build_spy_early_warning(macro_liquidity, macro_liquidity_equity, indicators.get("percentile_series", {}))
    equity_short_term_risk = build_equity_short_term_risk_index(
        market_bars=equity_market_bars or {},
        macro_liquidity_equity=macro_liquidity_equity,
        spy_early_warning=spy_early_warning,
        calendar_events=calendar_events or [],
        option_open_interest=option_open_interest,
    )
    lppl_bars = dict(equity_market_bars or {})
    lppl_bars.update(global_lppl_market_bars or {})
    global_lppl_risk = build_global_lppl_risk_index(market_bars=lppl_bars)
    regional_monitor = build_regional_monitor(global_lppl_risk)
    signal_validation = build_signal_validation(indicators, equity_short_term_risk=equity_short_term_risk)
    amplifier_audit = signal_validation.pop("amplifierAudit", None)
    if isinstance(spy_early_warning, dict) and isinstance(amplifier_audit, dict):
        spy_early_warning["amplifierAudit"] = amplifier_audit
    annotate_spy_warning_robustness(spy_early_warning, signal_validation)
    portfolio_overview = build_portfolio_overview(
        spy_early_warning=spy_early_warning,
        equity_short_term_risk=equity_short_term_risk,
        global_lppl_risk=global_lppl_risk,
        macro_liquidity=macro_liquidity,
        signal_validation=signal_validation,
        regional_monitor=regional_monitor,
    )
    fed_path = build_fed_path(
        indicators,
        as_of=today.date,
        calendar_events=calendar_events or [],
    )
    fed_path_audit = build_fed_path_audit(
        indicators,
        as_of=today.date,
        calendar_events=calendar_events or [],
    )
    bhadial_coverage = build_bhadial_coverage(groups)
    source_status = [
        {
            "name": "Fed path",
            "status": "modeled",
            "latest": (
                f"{len(fed_path_audit['futureMeetings'])} future official meetings; "
                "qualitative modeled scenario only; probabilities unavailable"
            ),
            "note": fed_path_audit["reason"],
        },
    ]
    if acm is None:
        source_status.append({"name": "NY Fed ACM term premium", "status": "modeled", "latest": "10Y minus effective policy proxy"})
    if not cftc_positions:
        source_status.append({"name": "CFTC financial futures COT", "status": "manual-placeholder", "latest": "weekly parser unavailable"})
    if tic_holdings is None:
        source_status.append({"name": "Treasury TIC major foreign holders", "status": "manual-placeholder", "latest": "monthly parser unavailable"})
    if primary_dealer_stats is None:
        source_status.append({"name": "NY Fed primary dealer statistics", "status": "manual-placeholder", "latest": "weekly parser unavailable"})
    if quarterly_refunding is None:
        source_status.append({"name": "U.S. Treasury quarterly refunding documents", "status": "manual-placeholder", "latest": "QRA parser unavailable"})
    if debt_limit_status is None:
        source_status.append({"name": "Treasury Fiscal Data debt subject to limit", "status": "manual-placeholder", "latest": "debt-limit parser unavailable"})
    if fomc_projection is None:
        source_status.append({"name": "Federal Reserve SEP projections", "status": "manual-placeholder", "latest": "projection parser unavailable"})
    if not calendar_events and not announced_auctions:
        source_status.append({"name": "Official event calendar", "status": "manual-placeholder", "latest": "official event feeds unavailable"})
    if not official_news:
        source_status.append({"name": "Official news flow", "status": "manual-placeholder", "latest": "official news feeds unavailable"})
    if not equity_market_bars:
        source_status.append({"name": "Nasdaq equity OHLCV", "status": "manual-placeholder", "latest": "daily equity market-structure feeds unavailable"})
    if not lppl_bars:
        source_status.append({"name": "Global LPPL index OHLCV", "status": "manual-placeholder", "latest": "global index replay feeds unavailable"})
    if option_open_interest is None:
        source_status.append({"name": "Cboe SPY option open interest", "status": "manual-placeholder", "latest": "option OI snapshot unavailable"})
    conclusion_audit = build_conclusion_audit(groups, source_status=source_status)

    dashboard = {
        "asOf": today.date.isoformat(),
        "generatedAt": generated_at.isoformat(),
        "meta": {
            "dataMode": "real-public-sources",
            "remoteCompatibility": {
                "sourceUrl": "https://us-treasury-bonds-monitor-luffa.vercel.app/",
                "factorNames": REMOTE_COMPATIBILITY_FACTOR_NAMES,
                "scoringRule": "-2..+2 duration score, optional curve score; sourceMode marks real, proxy, modeled, official-news, or manual-placeholder data boundaries.",
            },
            "bhadialCompatibility": {
                "sourceUrl": "https://bhadial.com/",
                "moduleCount": len(BHADIAL_MODULE_NAMES),
                "modules": BHADIAL_MODULE_NAMES,
                "coverage": bhadial_coverage,
                "scoringRule": "5Y historical percentile layer plus level, deviation, target-distance, shock-only, and risk-signal interpretations where public inputs exist.",
                "gapBoundary": "ETF-exact relative-performance factors are represented by real public FRED/Nasdaq proxies where free local market-history feeds are unstable or unavailable.",
            },
            "notes": [
                "Treasury curve, QRA documents, Fiscal Data debt-limit tables, FRED macro/liquidity/cross-market series, TreasuryDirect auctions, Federal Reserve FOMC calendar, NY Fed ACM, NY Fed primary dealer statistics, CFTC COT, and TIC are fetched from public sources when available.",
                "Fed path probabilities fail closed because the current public continuous ZQ quote cannot identify meeting-level hike/hold/cut odds. The curve, inflation, and futures gap are exposed only as a qualitative modeled scenario.",
                "Fed and Treasury official public news headlines are fetched when available; broader full-text market news remains curated because reliable redistribution usually requires licensed feeds.",
                "Remote-site narrative compatibility factors are preserved as explicit real/proxy/modeled/manual sourceMode rows rather than disguised as fully live market feeds.",
                "Bhadial-style module factors are filled with real public or derived-public series where possible; unsupported ETF-relative factors are not synthesized from unrelated data.",
            ],
        },
        "sourceStatus": source_status,
        "conclusionSourceQuality": dict(CONCLUSION_SOURCE_QUALITY),
        "curve": curve,
        "decomposition": build_decomposition(indicators, acm=acm, fomc_projection=fomc_projection),
        "fedPath": fed_path,
        "fedPathAudit": fed_path_audit,
        "groups": groups,
        "conclusionAudit": conclusion_audit,
        "macroLiquidity": macro_liquidity,
        "macroLiquidityEquity": macro_liquidity_equity,
        "spyEarlyWarning": spy_early_warning,
        "equityShortTermRisk": equity_short_term_risk,
        "globalLpplRisk": global_lppl_risk,
        "regionalMonitor": regional_monitor,
        "signalValidation": signal_validation,
        "portfolioOverview": portfolio_overview,
        "policy": policy,
        "auctions": build_auctions(auctions),
        "fiscal": build_fiscal(indicators, quarterly_refunding=quarterly_refunding, debt_limit_status=debt_limit_status),
        "positioning": build_positioning(cftc_positions=cftc_positions, tic_holdings=tic_holdings, primary_dealer_stats=primary_dealer_stats),
        "cross": build_cross_market(indicators),
        "percentiles": build_percentiles(indicators, auctions),
        "events": build_events(today.date, calendar_events=calendar_events or [], announced_auctions=announced_auctions or [], quarterly_refunding=quarterly_refunding),
        "news": build_news(today.date, indicators, quarterly_refunding=quarterly_refunding, official_news=official_news),
        "ideas": build_ideas(
            indicators,
            macro_liquidity=macro_liquidity,
            macro_liquidity_equity=macro_liquidity_equity,
            quarterly_refunding=quarterly_refunding,
            conclusion_audit=conclusion_audit,
        ),
    }
    return compact_dashboard_payload(apply_content_overrides(dashboard, overrides or {}))


def compact_dashboard_payload(dashboard: dict[str, Any]) -> dict[str, Any]:
    """Strip build-only diagnostics after every dependent calculation has run.

    ``equityShortTermRisk.trend.points[].componentScores`` is required while the
    backtest builds component diagnostics, but it is not consumed by the runtime
    UI.  The backtest is already attached before this final serialization step,
    so removing the repeated per-day component maps is lossless for users.
    """
    compact = dict(dashboard)
    equity = compact.get("equityShortTermRisk")
    if not isinstance(equity, dict):
        return compact
    trend = equity.get("trend")
    if not isinstance(trend, dict) or not isinstance(trend.get("points"), list):
        return compact
    compact_points = []
    for point in trend["points"]:
        if not isinstance(point, dict):
            compact_points.append(point)
            continue
        compact_point = dict(point)
        compact_point.pop("componentScores", None)
        compact_points.append(compact_point)
    compact_trend = dict(trend)
    compact_trend["points"] = compact_points
    compact_equity = dict(equity)
    compact_equity["trend"] = compact_trend
    compact["equityShortTermRisk"] = compact_equity
    return compact


def available_indicator_value(ind: dict[str, Any], key: str) -> float | None:
    availability = ind.get("availability")
    if isinstance(availability, dict) and key in availability and availability[key] is not True:
        return None
    return optional_float(ind.get(key))


def build_decomposition(ind: dict[str, Any], acm: AcmRecord | None = None, fomc_projection: FomcProjection | None = None) -> dict[str, Any]:
    dff = available_indicator_value(ind, "dff")
    breakeven = available_indicator_value(ind, "breakeven_10y")
    real_10y = available_indicator_value(ind, "real_10y")
    real_short = dff - max(breakeven, 0) if dff is not None and breakeven is not None else None
    if acm is not None:
        term_premium_value = f"{acm.term_premium_10y:+.2f}%"
        term_premium_note = f"NY Fed ACM 10Y期限溢价,最新日期 {acm.date.isoformat()}。"
        term_premium_driver = "NY Fed ACM"
    elif dff is not None:
        term_premium_value = f"{max(ind['ten_year'] - dff, -2):+.2f}%"
        term_premium_note = "ACM拉取失败时用10Y相对短端补偿近似; 仅作未校准代理。"
        term_premium_driver = "未校准模型代理"
    else:
        term_premium_value = "--"
        term_premium_note = "ACM与DFF均不可用,不生成期限溢价替代值。"
        term_premium_driver = "数据不足"
    attribution = [
        decomposition_attribution_row(
            ind,
            label=label,
            total_bp=total,
            real_key=real_key,
            breakeven_key=breakeven_key,
        )
        for label, total, real_key, breakeven_key in (
            ("1 周", ind["ten_year_w1_change_bp"], "real_10y_w1_change_bp", "breakeven_10y_w1_change_bp"),
            ("1 月", ind["ten_year_m1_change_bp"], "real_10y_m1_change_bp", "breakeven_10y_m1_change_bp"),
        )
    ]
    measured_windows = sum(1 for row in attribution if row["measured"])
    return {
        "components": [
            {"index": "01", "name": "短端实际利率", "en": "E[real short rate]", "value": f"~{real_short:.1f}%" if real_short is not None else "--", "note": "由有效联邦基金利率减去10Y盈亏平衡通胀近似; 任一输入缺失即停算。", "driver": "FRED DFF + T10YIE" if real_short is not None else "数据不足"},
            {"index": "02", "name": "短端通胀预期", "en": "E[π short]", "value": f"~{breakeven:.2f}%" if breakeven is not None else "--", "note": "用10Y盈亏平衡通胀作为公开代理。", "driver": "FRED T10YIE" if breakeven is not None else "数据不足"},
            {"index": "03", "name": "实际期限溢价", "en": "Real term premium", "value": term_premium_value, "note": term_premium_note, "driver": term_premium_driver},
            {"index": "04", "name": "通胀风险溢价", "en": "Inflation risk prem.", "value": f"{max(breakeven - 2.3, 0):+.2f}%" if breakeven is not None else "--", "note": "以盈亏平衡通胀相对2.3%锚的偏离近似; T10YIE缺失即停算。", "driver": "未校准模型代理" if breakeven is not None else "数据不足"},
        ],
        "attribution": attribution,
        "attributionAudit": {
            "measured": measured_windows == len(attribution),
            "measuredWindowCount": measured_windows,
            "productionUse": measured_windows == len(attribution),
            "method": "DFII10 real-yield change + T10YIE breakeven change + nominal 10Y residual",
            "limitation": "Breakeven includes expected inflation plus inflation-risk compensation; the residual also includes basis noise. Missing aligned changes fall back to an explicitly non-measured 65/35 narrative split.",
        },
        "frameworkNote": (
            "Clarida框架:长期名义利率 = 预期短端真实利率 + 预期短端通胀 + "
            "实际期限溢价 + 通胀风险溢价。核心用途不是机械相加,而是把收益率变化翻译成叙事变化。"
        ),
        "regimeRead": decomposition_regime_read(ind, term_premium_value),
        "policyRead": policy_path_read(ind, fomc_projection=fomc_projection),
        "marketMeasures": {
            "dff": f"{dff:.2f}%" if dff is not None else "--",
            "real10y": f"{real_10y:.2f}%" if real_10y is not None else "--",
            "breakeven10y": f"{breakeven:.2f}%" if breakeven is not None else "--",
            "termPremium10y": term_premium_value,
        },
        "sources": build_expectation_sources(ind, fomc_projection=fomc_projection),
    }


def decomposition_attribution_row(
    ind: dict[str, Any],
    *,
    label: str,
    total_bp: float,
    real_key: str,
    breakeven_key: str,
) -> dict[str, Any]:
    real_change = available_indicator_value(ind, real_key)
    breakeven_change = available_indicator_value(ind, breakeven_key)
    if real_change is not None and breakeven_change is not None:
        return {
            "window": label,
            "total": round(total_bp),
            "real": round(real_change),
            "inflation": round(breakeven_change),
            "term": round(total_bp - real_change - breakeven_change),
            "risk": None,
            "driver": "DFII10 + T10YIE同期变化; 期限/基差取残差",
            "measured": True,
            "productionUse": True,
        }
    return {
        "window": label,
        "total": round(total_bp),
        "real": round(total_bp * 0.65),
        "inflation": round(total_bp * 0.35),
        "term": 0,
        "risk": 0,
        "driver": "固定65/35叙事拆分(非实测)",
        "measured": False,
        "productionUse": False,
    }


def decomposition_regime_read(ind: dict[str, Any], term_premium_value: str) -> str:
    monthly_move = ind["ten_year_m1_change_bp"]
    direction = "上行" if monthly_move >= 0 else "下行"
    real_10y = available_indicator_value(ind, "real_10y")
    breakeven = available_indicator_value(ind, "breakeven_10y")
    hard_combo = real_10y is not None and breakeven is not None and real_10y >= 2.0 and breakeven >= 2.35
    combo_text = (
        "真实利率和通胀补偿同时偏高,这是名义久期最难缠的组合"
        if hard_combo
        else "真实利率或通胀补偿数据不足,暂不能判断二者是否共振"
        if real_10y is None or breakeven is None
        else "当前更多是单一驱动,需要观察真实利率与通胀补偿是否共振"
    )
    real_text = f"{real_10y:.2f}%" if real_10y is not None else "--"
    breakeven_text = f"{breakeven:.2f}%" if breakeven is not None else "--"
    return (
        f"10Y过去一个月{direction}{monthly_move:+.0f}bp,真实利率{real_text}、"
        f"通胀补偿{breakeven_text}、期限溢价{term_premium_value}。"
        f"{combo_text}; 若油价或CPI/PCE/核心PCE继续超预期,收益率上行会更像通胀冲击下的政策对峙。"
    )


def policy_path_read(ind: dict[str, Any], fomc_projection: FomcProjection | None) -> str:
    sep_text = "SEP待解析"
    if fomc_projection:
        years = sorted((key for key in fomc_projection.median_fed_funds if key.isdigit()), key=int)
        if years:
            year = years[0]
            sep_text = f"SEP {year}中位数{fomc_projection.median_fed_funds[year]:.2f}%"
    futures_rate = ind.get("fed_funds_futures_implied_rate")
    futures_text = f"Fed Funds期货代理{futures_rate:.2f}%" if futures_rate is not None else "2Y/通胀模型代理"
    return (
        f"市场先跑、官方后确认: {futures_text}和2Y月变动{ind['two_year_m1_change_bp']:+.0f}bp先反映路径再定价, "
        f"{sep_text}属于低频官方锚。下一次FOMC和点阵图的关键不是单次决定,而是是否正式确认降息退潮或加息尾部风险。"
    )


def build_expectation_sources(ind: dict[str, Any], fomc_projection: FomcProjection | None) -> list[dict[str, str]]:
    if fomc_projection:
        first_year = sorted((key for key in fomc_projection.median_fed_funds if key.isdigit()), key=int)[0]
        sep_value = f"{first_year} median {fomc_projection.median_fed_funds[first_year]:.2f}%"
        sep_note = f"Federal Reserve SEP, released {fomc_projection.release_date.isoformat()}, official quarterly participant projections."
    else:
        sep_value = "等待Federal Reserve SEP"
        sep_note = "官方季度点阵图解析失败时不填入估计值。"
    inflation_values = [
        value
        for key in ("cpi_yoy", "pce_yoy", "core_pce_yoy", "trimmed_mean_pce_yoy")
        if (value := available_indicator_value(ind, key)) is not None
    ]
    inflation_pressure = max(inflation_values) if inflation_values else None
    if ind["two_year_m1_change_bp"] > 10 or (inflation_pressure is not None and inflation_pressure > 3):
        path_bias = "加息尾部升温"
    elif not inflation_values:
        path_bias = "通胀数据不足"
    else:
        path_bias = "持平为主"
    futures_rate = ind.get("fed_funds_futures_implied_rate")
    if futures_rate is not None:
        futures_value = f"{ind['fed_funds_futures_symbol']} implied {futures_rate:.2f}%"
        futures_note = (
            f"Stooq public quote dated {ind['fed_funds_futures_date']}; futures price "
            f"{ind['fed_funds_futures_close']:.2f} implies average fed-funds rate near {futures_rate:.2f}%. "
            "This continuous-contract monthly average is used only as a directional scenario input; "
            "meeting-level probabilities are not computed."
        )
        futures_name = "30-Day Fed Funds futures · public proxy"
    else:
        futures_value = path_bias
        futures_note = (
            "通胀数据缺失时不把兼容字段0当作降温证据;当前仅保留2Y方向观察。"
            if not inflation_values
            else "由2Y再定价与CPI/PCE通胀跟踪生成定性情景;缺少逐会议合约时不计算概率。"
        )
        futures_name = "公开曲线代理 · Fed path model"
    survey_anchor = "公开调查待接入"
    return [
        {"name": "美联储 SEP · 点阵图", "value": sep_value, "note": sep_note},
        {"name": futures_name, "value": futures_value, "note": futures_note},
        {"name": "调查 SPF / Blue Chip", "value": survey_anchor, "note": "调查预期通常低频且滞后;当前本地版保留为授权/后续公共源接入边界。"},
    ]




def build_conclusion_audit(groups: list[dict[str, Any]], source_status: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    def eligible_factors(group: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            factor
            for factor in group.get("factors", [])
            if isinstance(factor, dict)
            and factor.get("auditEligible") is not False
            and str(factor.get("sourceMode") or "") != "manual-placeholder"
        ]

    factors_by_group = {id(group): eligible_factors(group) for group in groups}
    total_weight = sum(
        max(0.0, _float_or_zero(group.get("weight")))
        for group in groups
        if factors_by_group[id(group)]
    )
    duration_score = 0.0
    curve_score = 0.0
    drivers: list[dict[str, Any]] = []
    group_diagnostics: list[dict[str, Any]] = []

    for group in groups:
        factors = factors_by_group[id(group)]
        if not factors:
            continue
        group_weight = max(0.0, _float_or_zero(group.get("weight")))
        normalized_weight = group_weight / total_weight if total_weight else 0.0
        factor_count = len(factors)
        group_duration = sum(_float_or_zero(factor.get("score")) for factor in factors) / factor_count
        group_curve = sum(_float_or_zero(factor.get("curve")) for factor in factors) / factor_count
        duration_score += group_duration * normalized_weight
        curve_score += group_curve * normalized_weight

        quality_numerator = 0.0
        quality_weight = 0.0
        for factor in factors:
            score = _float_or_zero(factor.get("score"))
            curve = _float_or_zero(factor.get("curve"))
            contribution = score * normalized_weight / factor_count
            curve_contribution = curve * normalized_weight / factor_count
            source_mode = str(factor.get("sourceMode") or "real-public")
            quality = conclusion_source_quality(source_mode)
            contribution_abs = abs(contribution)
            quality_numerator += quality * max(contribution_abs, abs(curve_contribution), 0.01)
            quality_weight += max(contribution_abs, abs(curve_contribution), 0.01)
            if contribution == 0 and curve_contribution == 0:
                continue
            drivers.append(
                {
                    "module": str(group.get("name") or group.get("id") or ""),
                    "moduleEn": str(group.get("en") or group.get("name") or group.get("id") or ""),
                    "name": str(factor.get("n") or factor.get("name") or ""),
                    "value": str(factor.get("v") or factor.get("tag") or ""),
                    "score": score,
                    "curve": curve,
                    "sourceMode": source_mode,
                    "quality": quality,
                    "contribution": contribution,
                    "curveContribution": curve_contribution,
                    "direction": "buffer" if contribution > 0 else "drag" if contribution < 0 else "curve",
                }
            )

        group_diagnostics.append(
            {
                "id": str(group.get("id") or ""),
                "name": str(group.get("name") or group.get("id") or ""),
                "en": str(group.get("en") or group.get("name") or group.get("id") or ""),
                "weight": round(group_weight, 2),
                "factorCount": factor_count,
                "durationAverage": round(group_duration, 2),
                "curveAverage": round(group_curve, 2),
                "durationContribution": round(group_duration * normalized_weight, 2),
                "curveContribution": round(group_curve * normalized_weight, 2),
                "evidenceQuality": round(quality_numerator / quality_weight, 2) if quality_weight else 1.0,
            }
        )

    source_status = source_status or []
    warning_count = sum(1 for source in source_status if _source_status(source) in {"warning", "warn"})
    error_count = sum(1 for source in source_status if _source_status(source) == "error")
    absolute_total = sum(abs(item["contribution"]) for item in drivers)
    evidence_quality = (
        sum(abs(item["contribution"]) * float(item["quality"]) for item in drivers) / absolute_total
        if absolute_total
        else 1.0
    )
    proxy_contribution = sum(
        abs(item["contribution"])
        for item in drivers
        if str(item["sourceMode"]) in LOWER_CONFIDENCE_SOURCE_MODES
    )
    concentration = max((abs(item["contribution"]) for item in drivers), default=0.0) / absolute_total if absolute_total else 0.0
    proxy_share = proxy_contribution / absolute_total if absolute_total else 0.0
    confidence_level = conclusion_confidence_level(
        evidence_quality=evidence_quality,
        concentration=concentration,
        warning_count=warning_count,
        error_count=error_count,
    )
    sorted_drivers = sorted(drivers, key=lambda item: abs(float(item["contribution"])), reverse=True)
    return {
        "duration": {"score": round(duration_score, 2), "label": conclusion_duration_label(duration_score)},
        "curve": {"score": round(curve_score, 2), "label": conclusion_curve_label(curve_score)},
        "confidence": {
            "level": confidence_level,
            "label": {"high": "高", "medium": "中等", "low": "低"}[confidence_level],
            "evidenceQuality": round(evidence_quality, 2),
            "concentration": round(concentration, 2),
            "proxyContributionShare": round(proxy_share, 2),
        },
        "sourceWarningCount": warning_count,
        "sourceErrorCount": error_count,
        "weightRecommendation": conclusion_weight_recommendation(
            evidence_quality=evidence_quality,
            concentration=concentration,
            proxy_share=proxy_share,
            warning_count=warning_count,
            error_count=error_count,
        ),
        "drivers": [round_conclusion_driver(driver) for driver in sorted_drivers[:8]],
        "groupDiagnostics": group_diagnostics,
    }


def round_conclusion_driver(driver: dict[str, Any]) -> dict[str, Any]:
    item = dict(driver)
    item["score"] = round(_float_or_zero(item.get("score")), 2)
    item["curve"] = round(_float_or_zero(item.get("curve")), 2)
    item["quality"] = round(_float_or_zero(item.get("quality")), 2)
    item["contribution"] = round(_float_or_zero(item.get("contribution")), 2)
    item["curveContribution"] = round(_float_or_zero(item.get("curveContribution")), 2)
    return item


def conclusion_source_quality(source_mode: str) -> float:
    return CONCLUSION_SOURCE_QUALITY.get(str(source_mode or "real-public"), 1.0)


def conclusion_confidence_level(*, evidence_quality: float, concentration: float, warning_count: int, error_count: int) -> str:
    if error_count > 0:
        return "low"
    if evidence_quality >= 0.82 and concentration <= 0.45 and warning_count == 0:
        return "high"
    if evidence_quality >= 0.62 and concentration <= 0.65:
        return "medium"
    return "low"


def conclusion_duration_label(score: float) -> str:
    if score <= -0.5:
        return "偏空久期"
    if score < -0.18:
        return "轻度偏空"
    if score < 0.18:
        return "中性"
    if score < 0.5:
        return "轻度偏多"
    return "偏多久期"


def conclusion_curve_label(score: float) -> str:
    if score <= -0.15:
        return "偏平坦"
    if score <= 0.15:
        return "中性"
    return "偏陡峭"


def conclusion_weight_recommendation(
    *,
    evidence_quality: float,
    concentration: float,
    proxy_share: float,
    warning_count: int,
    error_count: int,
) -> str:
    notes: list[str] = []
    if error_count:
        notes.append("存在关键数据源错误,结论应降级,暂不提高受影响因子的权重。")
    elif warning_count:
        notes.append("存在数据源警告,结论可信度不应上调到高。")
    if proxy_share >= 0.25 or evidence_quality < 0.82:
        notes.append("代理/模型因子占比偏高,权重不宜继续提高代理因子;优先接入真实市场源或降低其结论措辞强度。")
    if concentration > 0.45:
        notes.append("单一因子贡献集中,应避免让一个模块主导总判断。")
    if not notes:
        notes.append("当前权重暂不需要机械调整;更适合保留模块权重,只在新增真实数据源后再重估。")
    return "".join(notes)


def _source_status(source: dict[str, Any]) -> str:
    return str(source.get("status") or "").lower()




def build_policy(ind: dict[str, Any]) -> dict[str, list[list[str]]]:
    dff = available_indicator_value(ind, "dff")
    sofr = available_indicator_value(ind, "sofr")
    sofr_effr_spread = available_indicator_value(ind, "sofr_effr_spread_bp")
    walcl = available_indicator_value(ind, "walcl_trillions")
    soma = available_indicator_value(ind, "soma_treasury_trillions")
    bank_reserves = available_indicator_value(ind, "bank_reserves_trillions")
    net_liquidity = available_indicator_value(ind, "net_liquidity_trillions")
    rrp = available_indicator_value(ind, "rrp_trillions")
    tga = available_indicator_value(ind, "tga_trillions")
    return {
        "rates": [
            ["联邦基金目标区间", ind["target_range"], "由DFF近似推断"],
            ["有效联邦基金利率", f"{dff:.2f}%" if dff is not None else "--", "FRED DFF"],
            ["SOFR", f"{sofr:.2f}%" if sofr is not None else "--", "FRED SOFR"],
            ["SOFR-EFFR利差", f"{sofr_effr_spread:+.0f}bp" if sofr_effr_spread is not None else "--", percentile_label(ind["percentiles"].get("sofr_effr_spread"))],
            ["2Y收益率", f"{ind['two_year']:.2f}%", "政策路径市场代理"],
            ["10Y收益率", f"{ind['ten_year']:.2f}%", "长端定价锚"],
            ["1月2Y变化", f"{ind['two_year_m1_change_bp']:+.0f}bp", "政策再定价"],
        ],
        "plumbing": [
            ["美联储资产负债表", f"${walcl:.2f}T" if walcl is not None else "--", "FRED WALCL"],
            ["SOMA Treasury持仓", f"${soma:.2f}T" if soma is not None else "--", "FRED TREAST"],
            ["银行准备金", f"${bank_reserves:.2f}T" if bank_reserves is not None else "--", f"FRED WRESBAL · {percentile_label(ind['percentiles'].get('bank_reserves'))}"],
            ["净流动性", f"${net_liquidity:.2f}T" if net_liquidity is not None else "--", f"WALCL-TGA-RRP · {percentile_label(ind['percentiles'].get('net_liquidity'))}"],
            ["SOFR", f"{sofr:.2f}%" if sofr is not None else "--", "隔夜融资"],
            ["ON RRP", f"${rrp:.3f}T" if rrp is not None else "--", "FRED RRPONTSYD"],
            ["财政部一般账户", f"${tga:.2f}T" if tga is not None else "--", "FRED WTREGEN"],
            ["流动性结论", "数据不足" if rrp is None else "边际偏紧" if rrp < 0.05 else "中性", "公开数据代理"],
        ],
    }


def _percentile_observation_value(
    ind: dict[str, Any],
    series_key: str,
    value_key: str,
    *,
    prefix: str = "",
    suffix: str = "",
    digits: int = 2,
    signed: bool = False,
) -> str:
    """Format a percentile input only when the underlying series was observed."""
    series_map = ind.get("percentile_series")
    if isinstance(series_map, dict) and series_key in series_map:
        points = series_map.get(series_key)
        if not isinstance(points, (list, tuple)) or not points:
            return "--"
    value = optional_float(ind.get(value_key))
    if value is None:
        return "--"
    sign = "+" if signed else ""
    return f"{prefix}{value:{sign}.{digits}f}{suffix}"


def build_percentiles(ind: dict[str, Any], auctions: list[dict[str, object]]) -> dict[str, Any]:
    auction_signal = auction_demand_signal(auctions)
    items = [
        {"name": "银行准备金", "value": _percentile_observation_value(ind, "bank_reserves", "bank_reserves_trillions", prefix="$", suffix="T"), "percentile": ind["percentiles"].get("bank_reserves"), "source": "FRED WRESBAL", "window": "5Y"},
        {"name": "净流动性", "value": _percentile_observation_value(ind, "net_liquidity", "net_liquidity_trillions", prefix="$", suffix="T"), "percentile": ind["percentiles"].get("net_liquidity"), "source": "FRED WALCL - WTREGEN - RRPONTSYD", "window": "5Y"},
        {"name": "流动性动量", "value": _percentile_observation_value(ind, "net_liquidity_momentum", "net_liquidity_m1_change_trillions", suffix="T", signed=True), "percentile": ind["percentiles"].get("net_liquidity_momentum"), "source": "Net liquidity 1M change", "window": "5Y"},
        {"name": "13周净流动性动量", "value": _percentile_observation_value(ind, "net_liquidity_13w_momentum", "net_liquidity_13w_change_trillions", suffix="T", signed=True), "percentile": ind["percentiles"].get("net_liquidity_13w_momentum"), "source": "Net liquidity 13W change", "window": "5Y"},
        {"name": "TGA偏离度", "value": _percentile_observation_value(ind, "tga_deviation", "tga_deviation_trillions", suffix="T", signed=True), "percentile": ind["percentiles"].get("tga_deviation"), "source": "FRED WTREGEN - 52W median", "window": "5Y"},
        {"name": "ON RRP缓冲风险", "value": _percentile_observation_value(ind, "onrrp_buffer_risk", "onrrp_buffer_risk"), "percentile": ind["percentiles"].get("onrrp_buffer_risk"), "source": "FRED RRPONTSYD risk signal", "window": "5Y"},
        {"name": "SOFR-EFFR利差", "value": _percentile_observation_value(ind, "sofr_effr_spread", "sofr_effr_spread_bp", suffix="bp", digits=0, signed=True), "percentile": ind["percentiles"].get("sofr_effr_spread"), "source": "FRED SOFR - DFF", "window": "5Y"},
        {"name": "商票-TBill利差", "value": _percentile_observation_value(ind, "cp_tbill_spread", "cp_tbill_spread_bp", suffix="bp", digits=0, signed=True), "percentile": ind["percentiles"].get("cp_tbill_spread"), "source": "FRED DCPF3M - DTB3", "window": "5Y"},
        {"name": "资金分裂度(21D)", "value": _percentile_observation_value(ind, "funding_fragmentation", "funding_fragmentation_21d"), "percentile": ind["percentiles"].get("funding_fragmentation"), "source": "SOFR corridor spread dispersion", "window": "5Y"},
        {"name": "真实利率水平", "value": _percentile_observation_value(ind, "real_rate_level", "real_rate_level", suffix="%"), "percentile": ind["percentiles"].get("real_rate_level"), "source": "60% DFII5 + 40% DFII10", "window": "5Y"},
        {"name": "VIX", "value": _percentile_observation_value(ind, "vix", "vix"), "percentile": ind["percentiles"].get("vix"), "source": "FRED VIXCLS", "window": "5Y"},
        {"name": "VIX期限结构", "value": _percentile_observation_value(ind, "vix_term_structure", "vix_term_structure"), "percentile": ind["percentiles"].get("vix_term_structure"), "source": "FRED VIXCLS / VXVCLS", "window": "5Y"},
        {"name": "HY信用利差", "value": _percentile_observation_value(ind, "hy_oas", "hy_oas", suffix="%"), "percentile": ind["percentiles"].get("hy_oas"), "source": "FRED BAMLH0A0HYM2", "window": "5Y"},
        {"name": "HY-IG利差", "value": _percentile_observation_value(ind, "hy_ig_oas_spread", "hy_ig_oas_spread_bp", suffix="bp", digits=0, signed=True), "percentile": ind["percentiles"].get("hy_ig_oas_spread"), "source": "FRED HY OAS - IG OAS", "window": "5Y"},
        {"name": "HY信用偏好(HY/UST)", "value": _percentile_observation_value(ind, "hy_credit_preference", "hy_credit_preference"), "percentile": ind["percentiles"].get("hy_credit_preference"), "source": "FRED HY TR 63/126D relative return vs DGS10 duration proxy", "window": "available up to 5Y"},
        {"name": "IG信用偏好(IG/UST)", "value": _percentile_observation_value(ind, "ig_credit_preference", "ig_credit_preference"), "percentile": ind["percentiles"].get("ig_credit_preference"), "source": "FRED IG TR 63/126D relative return vs DGS10 duration proxy", "window": "available up to 5Y"},
        {"name": "金融条件指数(NFCI)", "value": _percentile_observation_value(ind, "nfci", "nfci", signed=True), "percentile": ind["percentiles"].get("nfci"), "source": "FRED NFCI", "window": "5Y"},
        {"name": "银行股相对S&P500", "value": _percentile_observation_value(ind, "regional_bank_vs_market", "regional_bank_vs_market"), "percentile": ind["percentiles"].get("regional_bank_vs_market"), "source": "FRED NASDAQBANK / SP500", "window": "5Y"},
        {"name": "风险资产/美债代理", "value": _percentile_observation_value(ind, "risk_vs_safe", "risk_vs_safe"), "percentile": ind["percentiles"].get("risk_vs_safe"), "source": "FRED SP500 63/126D relative return vs DGS10 duration proxy", "window": "5Y"},
        {"name": "高Beta偏好(NDX/US500)", "value": _percentile_observation_value(ind, "high_beta_preference", "high_beta_preference"), "percentile": ind["percentiles"].get("high_beta_preference"), "source": "FRED NASDAQXNDX / NASDAQNQUS500LCT", "window": "5Y"},
        {"name": "美元广义指数", "value": _percentile_observation_value(ind, "dxy", "dxy"), "percentile": ind["percentiles"].get("dxy"), "source": "FRED DTWEXBGS", "window": "5Y"},
        {"name": "美元实现波动率", "value": _percentile_observation_value(ind, "dxy_realized_vol", "dxy_realized_vol", suffix="%", digits=1), "percentile": ind["percentiles"].get("dxy_realized_vol"), "source": "FRED DTWEXBGS 63D realized vol", "window": "5Y"},
        {"name": "原油波动偏离", "value": _percentile_observation_value(ind, "oil_vol_deviation", "oil_vol_deviation", digits=1), "percentile": ind["percentiles"].get("oil_vol_deviation"), "source": "FRED OVXCLS - rolling median", "window": "5Y"},
        {"name": "天然气", "value": _percentile_observation_value(ind, "natgas", "natgas", prefix="$"), "percentile": ind["percentiles"].get("natgas"), "source": "FRED DHHNGSP", "window": "5Y"},
        {"name": "拍卖投标倍数", "value": auction_signal["value"], "percentile": auction_signal["percentile"], "source": "TreasuryDirect auctioned securities", "window": "available sample"},
    ]
    trends = build_percentile_trends(ind, auctions)
    return {
        "method": "Historical percentile rank; FRED-derived factors use a 5Y rolling window where available, auctions use the TreasuryDirect endpoint sample.",
        "items": items,
        "trends": trends,
        "movers": build_percentile_movers(trends),
        "alerts": build_percentile_alerts(items),
    }


def build_macro_liquidity_score(
    ind: dict[str, Any],
    *,
    as_of: date | None = None,
) -> dict[str, Any]:
    snapshot = bhadial_conditions_snapshot(ind, as_of=as_of)
    score = snapshot["score"]
    components = snapshot["components"]
    modules = snapshot["modules"]
    eligible_components = [item for item in components if item.get("scoreEligible")]
    drivers = sorted(eligible_components, key=lambda item: abs(item["contribution"]), reverse=True)[:4]
    constraint = min(eligible_components, key=lambda item: item["contribution"]) if eligible_components else {}
    offset = max(eligible_components, key=lambda item: item["contribution"]) if eligible_components else {}
    drag_components = [item for item in eligible_components if item["contribution"] < -0.01]
    buffer_components = [item for item in eligible_components if item["contribution"] > 0.01]
    neutral_components = [item for item in eligible_components if -0.01 <= item["contribution"] <= 0.01]
    focus_components = sorted(eligible_components, key=lambda item: abs(item["contribution"]), reverse=True)[:5]
    balance = [
        {
            "label": "拖累",
            "count": len(drag_components),
            "contribution": round(sum(item["contribution"] for item in drag_components), 2),
            "direction": "restrictive",
        },
        {
            "label": "中性",
            "count": len(neutral_components),
            "contribution": round(sum(item["contribution"] for item in neutral_components), 2),
            "direction": "neutral",
        },
        {
            "label": "缓冲",
            "count": len(buffer_components),
            "contribution": round(sum(item["contribution"] for item in buffer_components), 2),
            "direction": "supportive",
        },
    ]
    trend = build_macro_liquidity_trend(ind, score)
    return {
        "score": score,
        "regime": macro_liquidity_regime(score),
        "bias": "supportive" if score >= 55 else "restrictive" if score <= 45 else "neutral",
        "method": "Bhadial Conditions Score-compatible 21-factor (redundancy-deduplicated from 30; 2026-06), 7-module 5Y historical percentile composite; module weights follow the public factor-coverage/overlap method; Funding uses EMA(5).",
        "sourceUrl": BHADIAL_SCORE_SOURCE_URL,
        "moduleCount": len(BHADIAL_CONDITION_MODULES),
        "totalFactorCount": sum(int(module["scored"]) + int(module["display"]) for module in BHADIAL_FACTOR_COVERAGE),
        "activeFactorCount": snapshot["factorCount"],
        "scoredFactorCount": snapshot["scoredFactorCount"],
        "observedFactorCount": snapshot["observedFactorCount"],
        "coveragePct": snapshot["coveragePct"],
        "scoredCoveragePct": snapshot["scoredCoveragePct"],
        "effectiveWeightCoveragePct": snapshot["effectiveWeightCoveragePct"],
        "legacyFixedScore": snapshot["legacyFixedScore"],
        "observedOnlyScore": snapshot["observedOnlyScore"],
        "reliabilityScore": snapshot["reliabilityScore"],
        "scoreContract": "legacy-fixed-weight-compatible",
        "proxyFactorCount": 5,
        "modules": modules,
        "summary": macro_liquidity_summary(score, constraint, offset, trend),
        "trend": trend,
        "constraint": constraint,
        "offset": offset,
        "balance": balance,
        "focusComponents": focus_components,
        "hiddenComponentCount": max(0, len(eligible_components) - len(focus_components)),
        "implications": macro_liquidity_implications(score, constraint, offset),
        "components": components,
        "drivers": drivers,
    }


def build_macro_liquidity_trend(ind: dict[str, Any], current_score: float) -> dict[str, Any]:
    points = macro_liquidity_history_points(ind.get("percentile_series", {}))
    if not points:
        return {
            "available": False,
            "historicalPercentile": None,
            "score1mChange": None,
            "score3mChange": None,
            "percentile1mChange": None,
            "percentile3mChange": None,
            "direction": "不足",
            "summary": "综合评分历史样本不足",
            "regimeCalibration": unavailable_macro_regime_calibration(),
            "points": [],
        }
    latest = points[-1]
    prior_1m = points[-2] if len(points) >= 2 else None
    prior_3m = points[-4] if len(points) >= 4 else None
    score_1m_change = round(latest["score"] - prior_1m["score"], 1) if prior_1m else None
    score_3m_change = round(latest["score"] - prior_3m["score"], 1) if prior_3m else None
    percentile_1m_change = latest["percentile"] - prior_1m["percentile"] if prior_1m and latest.get("percentile") is not None and prior_1m.get("percentile") is not None else None
    percentile_3m_change = latest["percentile"] - prior_3m["percentile"] if prior_3m and latest.get("percentile") is not None and prior_3m.get("percentile") is not None else None
    direction = macro_liquidity_trend_direction(score_3m_change if score_3m_change is not None else score_1m_change)
    latest_percentile = latest.get("percentile")
    return {
        "available": True,
        "date": latest["date"],
        "score": round(current_score, 1),
        "historicalPercentile": latest_percentile,
        "score1mChange": score_1m_change,
        "score3mChange": score_3m_change,
        "percentile1mChange": percentile_1m_change,
        "percentile3mChange": percentile_3m_change,
        "direction": direction,
        "summary": macro_liquidity_trend_summary(latest_percentile, score_3m_change, percentile_3m_change, direction),
        "regimeCalibration": build_macro_regime_calibration(points, current_score),
        "points": points,
    }


def unavailable_macro_regime_calibration() -> dict[str, Any]:
    return {
        "available": False,
        "mode": "shadow-only",
        "sampleSize": 0,
        "fixedThresholds": [30, 45, 55, 70],
        "empiricalThresholds": [],
        "currentEmpiricalRegime": None,
        "fixedRegimeOccupancy": {},
        "dormantFixedRegimes": [],
        "summary": "历史样本不足,固定阈值暂不做分布校准诊断。",
    }


def nearest_rank_value(values: list[float], percentile: float) -> float | None:
    clean = sorted(float(value) for value in values if math.isfinite(float(value)))
    if not clean:
        return None
    index = max(0, min(len(clean) - 1, math.ceil(percentile * len(clean)) - 1))
    return round(clean[index], 1)


def build_macro_regime_calibration(points: list[dict[str, Any]], current_score: float) -> dict[str, Any]:
    scores = [
        float(point["score"])
        for point in points
        if isinstance(point, dict) and isinstance(point.get("score"), (int, float))
    ]
    if len(scores) < 12:
        return unavailable_macro_regime_calibration()
    empirical = [nearest_rank_value(scores, percentile) for percentile in (0.2, 0.4, 0.6, 0.8)]
    if any(value is None for value in empirical):
        return unavailable_macro_regime_calibration()
    thresholds = [float(value) for value in empirical if value is not None]
    empirical_labels = ["历史紧缩尾部", "历史偏紧", "历史中位", "历史偏松", "历史宽松尾部"]
    empirical_index = sum(1 for threshold in thresholds if current_score > threshold)
    fixed_regimes = ["紧缩压力", "偏紧", "中性", "边际宽松", "流动性宽松"]
    occupancy = {regime: 0 for regime in fixed_regimes}
    for score in scores:
        occupancy[macro_liquidity_regime(score)] += 1
    dormant = [regime for regime, count in occupancy.items() if count == 0]
    return {
        "available": True,
        "mode": "shadow-only",
        "sampleSize": len(scores),
        "fixedThresholds": [30, 45, 55, 70],
        "empiricalThresholds": thresholds,
        "currentEmpiricalRegime": empirical_labels[empirical_index],
        "fixedRegimeOccupancy": occupancy,
        "dormantFixedRegimes": dormant,
        "summary": (
            f"近{len(scores)}个月经验分位阈值为"
            f"{thresholds[0]:.1f}/{thresholds[1]:.1f}/{thresholds[2]:.1f}/{thresholds[3]:.1f}; "
            "仅作分布诊断,生产状态仍使用固定30/45/55/70阈值。"
        ),
    }


def macro_liquidity_history_points(series: dict[str, list[SeriesPoint]]) -> list[dict[str, Any]]:
    prepared = prepare_bhadial_series(series)
    dated_component_points: list[SeriesPoint] = []
    for key in BHADIAL_CONDITION_SERIES_KEYS:
        dated_component_points.extend(prepared.get(key, []))
    if not dated_component_points:
        return []
    latest_date = max(point.date for point in dated_component_points)
    start = window_start(latest_date, years=5)
    month_ends: dict[tuple[int, int], date] = {}
    for point in sorted(dated_component_points, key=lambda item: item.date):
        if point.date < start:
            continue
        month_ends[(point.date.year, point.date.month)] = point.date
    raw_points: list[dict[str, Any]] = []
    for target in sorted(set(month_ends.values())):
        score_row = macro_liquidity_score_at(prepared, target)
        if score_row is None:
            continue
        raw_points.append(
            {
                "date": target.isoformat(),
                "score": round(score_row["score"], 1),
                "componentCoverage": score_row["coverage"],
            }
        )
    for index, point in enumerate(raw_points):
        point_date = date.fromisoformat(point["date"])
        start_date = window_start(point_date, years=5)
        values = [
            item["score"]
            for item in raw_points[: index + 1]
            if start_date <= date.fromisoformat(item["date"]) <= point_date
        ]
        point["percentile"] = historical_percentile(float(point["score"]), [float(value) for value in values])
    return raw_points


def macro_liquidity_trend_direction(score_change: float | None) -> str:
    if score_change is None:
        return "不足"
    if score_change >= 3:
        return "上行"
    if score_change <= -3:
        return "下行"
    return "震荡"


def macro_liquidity_trend_summary(
    percentile: int | None,
    score_3m_change: float | None,
    percentile_3m_change: int | None,
    direction: str,
) -> str:
    # The percentile / 3M score / percentile-change numbers are already shown in the trend
    # metric grid directly below this read, so keep only the trend direction + the narrative
    # conclusion here to avoid restating the same figures (UI de-dup, 2026-06-24).
    if direction == "上行":
        return "3M趋势上行; 低位改善正在形成边际支撑。"
    if direction == "下行":
        return "3M趋势下行; 趋势转弱会放大低分位约束。"
    if direction == "震荡":
        return "3M趋势震荡; 当前位置优先按区间震荡处理。"
    return "历史趋势样本不足; 暂以当前分项拖累和缓冲为主。"


def build_macro_liquidity_equity_lead(ind: dict[str, Any]) -> dict[str, Any]:
    series = ind.get("percentile_series", {})
    sp500_points = clean_points(series.get("sp500", []))
    if len(sp500_points) < 24:
        return unavailable_macro_liquidity_equity("S&P 500 history is unavailable or too short.")
    latest_spx = sp500_points[-1]
    start = window_start(latest_spx.date, years=5)
    monthly_spx = monthly_last_points(sp500_points, start=start)
    rows: list[dict[str, Any]] = []
    base_spx: float | None = None
    for spx_point in monthly_spx:
        score_row = macro_liquidity_score_at(series, spx_point.date)
        if score_row is None:
            continue
        if base_spx is None:
            base_spx = spx_point.value
        forward_1m = forward_return_pct(sp500_points, spx_point.date, days=30)
        forward_3m = forward_return_pct(sp500_points, spx_point.date, days=91)
        forward_6m = forward_return_pct(sp500_points, spx_point.date, days=182)
        forward_3m_drawdown = forward_max_drawdown_pct(sp500_points, spx_point.date, days=91)
        rows.append(
            {
                "date": spx_point.date.isoformat(),
                "liquidityScore": round(score_row["score"], 1),
                "componentCoverage": score_row["coverage"],
                "sp500": round(spx_point.value, 2),
                "sp500Indexed": round((spx_point.value / base_spx) * 100, 1) if base_spx else 100.0,
                "forward1m": round(forward_1m, 2) if forward_1m is not None else None,
                "forward3m": round(forward_3m, 2) if forward_3m is not None else None,
                "forward6m": round(forward_6m, 2) if forward_6m is not None else None,
                "forward3mMaxDrawdown": round(forward_3m_drawdown, 2) if forward_3m_drawdown is not None else None,
            }
        )
    if len(rows) < 18:
        return unavailable_macro_liquidity_equity("Conditions score history has fewer than 18 monthly observations.")
    add_macro_liquidity_equity_deltas(rows)
    corr_1m = row_correlation(rows, "liquidityScore", "forward1m")
    corr_3m = row_correlation(rows, "liquidityScore", "forward3m")
    corr_6m = row_correlation(rows, "liquidityScore", "forward6m")
    buckets = liquidity_forward_return_buckets(rows)
    lead_lag = macro_liquidity_lead_lag(rows)
    change_buckets = score_change_forward_return_buckets(rows)
    rolling_correlation = rolling_forward_correlation(rows)
    drawdown_risk = liquidity_drawdown_risk(rows)
    current_signal = macro_liquidity_current_signal(rows, buckets, change_buckets, lead_lag)
    state_grid = macro_liquidity_state_grid(rows, current_signal)
    high_low = None
    if len(buckets) >= 3 and buckets[0].get("avgForward3m") is not None and buckets[-1].get("avgForward3m") is not None:
        high_low = round(float(buckets[-1]["avgForward3m"]) - float(buckets[0]["avgForward3m"]), 2)
    conclusion = macro_liquidity_equity_conclusion(corr_3m, high_low, buckets)
    stats = [
        {"label": "1M forward corr", "value": format_correlation(corr_1m), "tone": correlation_tone(corr_1m)},
        {"label": "3M forward corr", "value": format_correlation(corr_3m), "tone": correlation_tone(corr_3m)},
        {"label": "6M forward corr", "value": format_correlation(corr_6m), "tone": correlation_tone(corr_6m)},
        {"label": "High-Low 3M", "value": f"{high_low:+.2f}pp" if high_low is not None else "--", "tone": "supportive" if high_low and high_low > 0 else "restrictive" if high_low and high_low < 0 else "neutral"},
    ]
    return {
        "available": True,
        "title": "宏观环境评分 vs S&P 500 · 5Y Lead Study",
        "method": "Monthly 5Y sample; macro conditions replay the same Bhadial-compatible 21-factor, 7-module composite and compare it with FRED S&P 500 price-index forward returns.",
        "asOf": latest_spx.date.isoformat(),
        "observationCount": len(rows),
        "correlations": {
            "forward1m": round(corr_1m, 3) if corr_1m is not None else None,
            "forward3m": round(corr_3m, 3) if corr_3m is not None else None,
            "forward6m": round(corr_6m, 3) if corr_6m is not None else None,
        },
        "stats": stats,
        "buckets": buckets,
        "leadLag": lead_lag,
        "changeBuckets": change_buckets,
        "rollingCorrelation": rolling_correlation,
        "drawdownRisk": drawdown_risk,
        "currentSignal": current_signal,
        "stateGrid": state_grid,
        "conclusion": conclusion,
        "series": rows,
    }


def unavailable_macro_liquidity_equity(reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "title": "宏观环境评分 vs S&P 500 · 5Y Lead Study",
        "method": "Monthly 5Y sample; requires S&P 500 and Bhadial-compatible conditions-score component history.",
        "asOf": "",
        "observationCount": 0,
        "correlations": {"forward1m": None, "forward3m": None, "forward6m": None},
        "stats": [],
        "buckets": [],
        "leadLag": [],
        "changeBuckets": [],
        "rollingCorrelation": {"windowMonths": 24, "latest": None, "points": []},
        "drawdownRisk": {"maxDrawdown": None, "worstDate": "", "avgDrawdownByBucket": []},
        "currentSignal": {
            "available": False,
            "levelBucket": "",
            "changeBucket": "",
            "verdict": reason,
            "expectedForward3m": None,
            "expectedDrawdown3m": None,
            "confidence": "low",
            "cards": [],
        },
        "stateGrid": [],
        "conclusion": reason,
        "series": [],
    }


# 2026-06-19 ROBUST-driven restructure (supersedes the bounded 2026-06-13 reweight). The
# OOS-aligned bootstrap CIs (signalValidation `robust`/`oosCi3m`) now distinguish reliable
# signals from single-slice noise: fundingStress (OOS CI [0.24,0.56]) and ratesCurveStress
# (CI [0.13,0.55]) are ROBUSTLY leading; creditVolStress is ROBUSTLY ANTI-predictive
# (CI [-0.78,-0.20]) — i.e. VIX/OAS/NFCI are coincident-contrarian, structurally wrong as a
# FORWARD early-warning input. So creditVolStress is removed from the forward aggregate
# (weight 0; still computed + displayed as a coincident "current stress" context sleeve),
# the freed weight goes to the two robust leaders, and macroDeterioration (derived from the
# validated-LAGGING Conditions-Score 3M change, bhadialComposite robust=False) is demoted
# 0.20->0.10. Rationale is structural (direction + robustness verdict + established market
# behaviour), NOT a fit to maximise the aggregate's OOS metric.
# CAVEAT (unchanged discipline): these weights remain quasi-in-sample for the SPY warning
# composite — revalidate on fresh data; do NOT cite any post-restructure OOS improvement of
# the AGGREGATE as independent confirmation (that would be circular/by-construction).

# Dampener retained: 2026-06-12 weekly OOS audit (91 weeks, base drawdown rate 30.8%)
# showed lift 0.81 after firing with avg forward 3M +7.14% — it suppresses noise, not real risk.
# Zeroed 2026-06-12: 3 fires in 5Y, 0% OOS drawdown hit rate.
# Zeroed 2026-06-12: 1 fire in 5Y, no out-of-sample evidence.
# Zeroed 2026-06-12: OOS lift 0.59 (18.2% hit vs 30.8% base) and avg forward 3M +5.39%
# after firing — the rule fired into recoveries, raising false alarms.
# Halved 6.0→3.0 2026-06-12: 0% OOS drawdown hit, but avg forward 3M after firing was
# -0.96% vs +3.34% base — keeps the negative-forward-return half of the target at half weight.


def build_global_lppl_risk_index(
    *,
    market_bars: dict[str, list[MarketDailyBar]] | None = None,
    as_of: date | None = None,
) -> dict[str, Any]:
    bars_by_symbol = normalize_market_bars(market_bars or {})
    index_rows = build_global_lppl_index_rows(bars_by_symbol, as_of=as_of)
    per_index_history = build_global_lppl_per_index_histories(index_rows, bars_by_symbol)
    index_validation = build_global_lppl_index_validation(index_rows, bars_by_symbol, histories=per_index_history)
    index_rows = apply_global_lppl_index_validation(index_rows, index_validation)
    per_index_backtests = build_global_lppl_per_index_backtests(per_index_history, bars_by_symbol)
    index_rows = attach_global_lppl_per_index_payloads(index_rows, per_index_history, per_index_backtests)
    index_rows = attach_global_lppl_tc_aggregations(index_rows)
    index_rows = attach_global_lppl_forward_signals(index_rows)
    index_rows = attach_global_lppl_price_factors(index_rows, bars_by_symbol)
    index_rows = attach_global_lppl_factor_validation(index_rows, bars_by_symbol, per_index_history)
    available_rows = [row for row in index_rows if row.get("available") and optional_float(row.get("score")) is not None]
    if not available_rows:
        return unavailable_global_lppl_risk(
            index_rows,
            "全球LPPL逐市场评估需要至少一个可回放指数样本; 当前公开日线源不足。",
            per_index_history=per_index_history,
            per_index_backtests=per_index_backtests,
        )

    latest_date = latest_global_lppl_date(available_rows)
    breadth_confirmation = build_global_lppl_breadth_confirmation(index_rows)
    return global_lppl_payload(
        latest_date=latest_date,
        available_rows=available_rows,
        index_rows=index_rows,
        index_validation=index_validation,
        per_index_history=per_index_history,
        per_index_backtests=per_index_backtests,
        breadth_confirmation=breadth_confirmation,
    )


def build_global_lppl_index_rows(
    bars_by_symbol: dict[str, list[MarketDailyBar]],
    *,
    as_of: date | None = None,
) -> list[dict[str, Any]]:
    return [
        global_lppl_index_row(spec, bars_by_symbol.get(str(spec["symbol"]).upper(), []), as_of=as_of)
        for spec in GLOBAL_LPPL_INDEX_SPECS
    ]


def latest_global_lppl_date(available_rows: list[dict[str, Any]]) -> date:
    dated_rows = [
        date.fromisoformat(str(row["asOf"]))
        for row in available_rows
        if parse_payload_date(row.get("asOf"))
    ]
    return max(dated_rows) if dated_rows else date.today()


def global_lppl_summary(available_rows: list[dict[str, Any]], index_rows: list[dict[str, Any]]) -> str:
    high_risk_count = sum(
        1
        for row in available_rows
        if (optional_float(row.get("score")) or 0.0) >= GLOBAL_LPPL_ALERT_THRESHOLD
    )
    nearest = min(
        (
            int(days)
            for row in available_rows
            for days in [optional_float(row.get("daysToCritical"))]
            if days is not None
        ),
        default=None,
    )
    leaders = sorted(
        (
            (optional_float(row.get("score")) or 0.0, str(row.get("symbol") or ""))
            for row in available_rows
        ),
        reverse=True,
    )[:3]
    leader_text = ", ".join(f"{symbol} {score:.0f}" for score, symbol in leaders if symbol)
    forward_rows = [
        (
            optional_float((row.get("forwardSignal") or {}).get("score")) or 0.0,
            str(row.get("symbol") or ""),
        )
        for row in available_rows
        if isinstance(row.get("forwardSignal"), dict) and (row.get("forwardSignal") or {}).get("available")
    ]
    forward_count = sum(1 for score, _symbol in forward_rows if score >= GLOBAL_LPPL_ALERT_THRESHOLD)
    forward_leaders = sorted(forward_rows, reverse=True)[:3]
    forward_text = ", ".join(f"{symbol} {score:.0f}" for score, symbol in forward_leaders if symbol)
    breadth = build_global_lppl_breadth_confirmation(index_rows)
    breadth_text = (
        f" 市场宽度{breadth.get('riskCount')}/{breadth.get('sampleSize')}个风险, "
        f"加权{breadth.get('weightedRiskSharePct')}%。"
        if breadth.get("available")
        else ""
    )
    return (
        f"LPPL逐市场独立评估; "
        f"{high_risk_count}/{len(available_rows)}个可用指数处于风险阈值上方"
        + (f", 当前较高: {leader_text}" if leader_text else "")
        + (f", 最近临界窗口约{nearest}天。" if nearest is not None else "。")
        + (f" 前瞻压力{forward_count}/{len(available_rows)}个市场高于阈值" + (f", 领先: {forward_text}。" if forward_text else "。") if forward_rows else "")
        + breadth_text
        + f" 不计算混合综合分, 图表和回测按{len(index_rows)}个市场分别展示。"
    )


def global_lppl_payload(
    *,
    latest_date: date,
    available_rows: list[dict[str, Any]],
    index_rows: list[dict[str, Any]],
    index_validation: dict[str, Any],
    per_index_history: dict[str, Any],
    per_index_backtests: dict[str, Any],
    breadth_confirmation: dict[str, Any],
) -> dict[str, Any]:
    serialized_index_rows = compact_global_lppl_index_payloads(index_rows)
    return {
        "available": True,
        "title": "Global LPPL Risk · 全球指数泡沫临界风险",
        "score": None,
        "scoreUse": "independent",
        "regime": "Per-Index",
        "regimeCn": "逐市场",
        "horizon": "tc-window",
        "horizonCn": "临界窗口(各指数daysToCritical)",
        "asOf": latest_date.isoformat(),
        "summary": global_lppl_summary(available_rows, index_rows),
        "method": "LPPL grid search over constrained tc/m/omega with linear least-squares fit; each market is scored, charted, and backtested separately.",
        "indices": serialized_index_rows,
        "indexValidation": index_validation,
        "breadthConfirmation": breadth_confirmation,
        "history": {
            "available": False,
            "points": [],
            "summary": "Top-level aggregate LPPL history is disabled; use perIndexHistory (indices carry historyRef only).",
        },
        "backtest": {
            "available": False,
            "sampleSize": 0,
            "threshold": GLOBAL_LPPL_ALERT_THRESHOLD,
            "horizonTests": [],
            "summary": "Top-level aggregate LPPL backtest is disabled; use perIndexBacktests (indices carry backtestRef only).",
        },
        "perIndexHistory": per_index_history,
        "perIndexBacktests": per_index_backtests,
        "lookAheadGuard": {
            "dataThrough": latest_date.isoformat(),
            "scoreInputs": "Only same-day or earlier daily OHLCV bars are used. Forward drawdowns are audit-only per-market backtest outputs.",
            "scoreUse": "independent; not included in equityShortTermRisk.",
        },
    }


def build_global_lppl_breadth_confirmation(index_rows: list[dict[str, Any]]) -> dict[str, Any]:
    available = [
        row
        for row in index_rows
        if isinstance(row, dict) and row.get("available") and optional_float(row.get("score")) is not None
    ]
    if not available:
        return {
            "available": False,
            "sampleSize": 0,
            "riskCount": 0,
            "riskSharePct": 0.0,
            "weightedRiskSharePct": 0.0,
            "forwardRiskCount": 0,
            "clipLockCount": 0,
            "regime": "Unavailable",
            "regimeCn": "不可用",
            "summary": "LPPL breadth unavailable; no current market rows with scores.",
        }
    risk_rows = [
        row
        for row in available
        if (optional_float(row.get("score")) or 0.0) >= GLOBAL_LPPL_ALERT_THRESHOLD
    ]
    forward_risk_rows = [
        row
        for row in available
        if isinstance(row.get("forwardSignal"), dict)
        and (row.get("forwardSignal") or {}).get("available")
        and (optional_float((row.get("forwardSignal") or {}).get("score")) or 0.0) >= GLOBAL_LPPL_ALERT_THRESHOLD
    ]
    clip_lock_count = sum(
        1
        for row in available
        if isinstance(row.get("clipState"), dict) and bool((row.get("clipState") or {}).get("clipLock"))
    )
    validated_count = sum(
        1
        for row in available
        if optional_float(row.get("effectiveWeightMultiplier")) is not None
        and (optional_float(row.get("effectiveWeightMultiplier")) or 0.0) >= 0.75
    )
    total_weight = sum(max(0.0, optional_float(row.get("weight")) or 0.0) for row in available)
    risk_weight = sum(max(0.0, optional_float(row.get("weight")) or 0.0) for row in risk_rows)
    risk_share = 100 * len(risk_rows) / max(1, len(available))
    weighted_risk_share = 100 * risk_weight / total_weight if total_weight > 0 else risk_share
    if weighted_risk_share >= 50 or len(risk_rows) >= 4:
        regime, regime_cn = "Broad Risk", "宽度风险"
    elif len(risk_rows) >= 2 or clip_lock_count >= 2:
        regime, regime_cn = "Clustered Watch", "集群观察"
    elif len(risk_rows) >= 1 or len(forward_risk_rows) >= 1:
        regime, regime_cn = "Narrow Watch", "局部观察"
    else:
        regime, regime_cn = "Quiet", "宽度平静"
    leaders = ", ".join(str(row.get("symbol") or "") for row in risk_rows[:3] if row.get("symbol"))
    return {
        "available": True,
        "sampleSize": len(available),
        "riskCount": len(risk_rows),
        "riskSharePct": round(risk_share, 1),
        "weightedRiskSharePct": round(weighted_risk_share, 1),
        "forwardRiskCount": len(forward_risk_rows),
        "clipLockCount": clip_lock_count,
        "validatedCount": validated_count,
        "regime": regime,
        "regimeCn": regime_cn,
        "leaders": [str(row.get("symbol") or "") for row in risk_rows[:3] if row.get("symbol")],
        "summary": (
            f"LPPL breadth {len(risk_rows)}/{len(available)} markets above raw threshold"
            f"{f' ({leaders})' if leaders else ''}; weighted breadth {weighted_risk_share:.1f}%, "
            f"forward risk {len(forward_risk_rows)}, CLIP locks {clip_lock_count}."
        ),
    }


def unavailable_global_lppl_risk(
    index_rows: list[dict[str, Any]],
    reason: str,
    *,
    per_index_history: dict[str, Any] | None = None,
    per_index_backtests: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "available": False,
        "title": "Global LPPL Risk · 全球指数泡沫临界风险",
        "score": None,
        "scoreUse": "independent",
        "regime": "Unavailable",
        "regimeCn": "不可用",
        "asOf": "",
        "summary": reason,
        "method": "LPPL grid search over constrained tc/m/omega with linear least-squares fit.",
        "indices": compact_global_lppl_index_payloads(index_rows),
        "indexValidation": {"available": False, "rows": [], "summary": reason},
        "breadthConfirmation": {
            "available": False,
            "sampleSize": 0,
            "riskCount": 0,
            "riskSharePct": 0.0,
            "weightedRiskSharePct": 0.0,
            "forwardRiskCount": 0,
            "clipLockCount": 0,
            "regime": "Unavailable",
            "regimeCn": "不可用",
            "summary": reason,
        },
        "history": {"available": False, "points": [], "summary": "Top-level aggregate LPPL history is disabled; use per-index histories."},
        "backtest": {"available": False, "sampleSize": 0, "threshold": GLOBAL_LPPL_ALERT_THRESHOLD, "horizonTests": [], "summary": "Top-level aggregate LPPL backtest is disabled; use per-index backtests."},
        "perIndexHistory": per_index_history or {},
        "perIndexBacktests": per_index_backtests or {},
        "lookAheadGuard": {"scoreUse": "independent; not included in equityShortTermRisk."},
    }


def build_global_lppl_per_index_histories(
    index_rows: list[dict[str, Any]],
    bars_by_symbol: dict[str, list[MarketDailyBar]],
) -> dict[str, Any]:
    """Facade wrapper preserving the patch seam for global_lppl_index_row."""
    return _lppl_history.build_global_lppl_per_index_histories(
        index_rows,
        bars_by_symbol,
        row_builder=global_lppl_index_row,
        history_points_builder=build_single_index_lppl_history_points,
    )


def build_global_lppl_single_index_history(
    index_row: dict[str, Any],
    bars: list[MarketDailyBar],
) -> dict[str, Any]:
    """Facade wrapper preserving the patch seam for global_lppl_index_row."""
    return _lppl_history.build_global_lppl_single_index_history(
        index_row,
        bars,
        row_builder=global_lppl_index_row,
        history_points_builder=build_single_index_lppl_history_points,
    )


def attach_global_lppl_tc_aggregations(index_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched_rows: list[dict[str, Any]] = []
    for row in index_rows:
        enriched = dict(row)
        enriched["tcAggregation"] = build_global_lppl_tc_aggregation(enriched)
        enriched_rows.append(enriched)
    return enriched_rows


def build_global_lppl_tc_aggregation(row: dict[str, Any]) -> dict[str, Any]:
    symbol = str(row.get("symbol") or "").upper()
    ensemble = row.get("fitEnsemble") if isinstance(row.get("fitEnsemble"), dict) else {}
    as_of_raw = row.get("asOf")
    try:
        as_of_date = date.fromisoformat(str(as_of_raw))
    except (TypeError, ValueError):
        as_of_date = None
    if not ensemble.get("available") or as_of_date is None:
        return {
            "available": False,
            "symbol": symbol,
            "summary": "LPPL tc aggregation unavailable; fit ensemble or asOf date missing.",
        }

    def lead_date(key: str) -> str | None:
        lead = optional_float(ensemble.get(key))
        if lead is None:
            return None
        return (as_of_date + timedelta(days=int(round(lead)))).isoformat()

    q20 = lead_date("tcLeadDaysQ20")
    median = lead_date("tcLeadDaysMedian")
    q80 = lead_date("tcLeadDaysQ80")
    return {
        "available": True,
        "symbol": symbol,
        "tcQ20": q20,
        "tcMedian": median,
        "tcQ80": q80,
        "tcLeadDaysQ20": ensemble.get("tcLeadDaysQ20"),
        "tcLeadDaysMedian": ensemble.get("tcLeadDaysMedian"),
        "tcLeadDaysQ80": ensemble.get("tcLeadDaysQ80"),
        "tcWindowDays": ensemble.get("tcWindowDays"),
        "validFitCount": ensemble.get("validFitCount"),
        "totalFitCount": ensemble.get("totalFitCount"),
        "validFitRatioPct": ensemble.get("validFitRatioPct"),
        "residualPassRatioPct": ensemble.get("residualPassRatioPct"),
        "windowDays": ensemble.get("windowDays", []),
        "windowAgreement": ensemble.get("windowAgreement") or "",
        "optimizerAgreement": ensemble.get("optimizerAgreement") or "",
        "summary": (
            f"{symbol} tc aggregation {q20 or '--'} / {median or '--'} / {q80 or '--'}; "
            f"{ensemble.get('validFitCount')}/{ensemble.get('totalFitCount')} windows valid."
        ),
    }


def attach_global_lppl_forward_signals(index_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched_rows: list[dict[str, Any]] = []
    for row in index_rows:
        enriched = dict(row)
        enriched["forwardSignal"] = build_global_lppl_forward_signal(enriched)
        enriched_rows.append(enriched)
    return enriched_rows


GLOBAL_LPPL_US_BENCHMARK_SYMBOL = "SPY"


def attach_global_lppl_price_factors(
    index_rows: list[dict[str, Any]],
    bars_by_symbol: dict[str, list[MarketDailyBar]],
) -> list[dict[str, Any]]:
    """Attach per-region price/technical factors computed from each index's own ETF
    proxy bars (momentum, 200DMA trend, realized vol, drawdown, relative strength vs the
    US benchmark). These describe each region's equity market-state — a complement to the
    LPPL bubble-risk score, not a separately OOS-validated drawdown forecast."""
    benchmark_bars = bars_by_symbol.get(GLOBAL_LPPL_US_BENCHMARK_SYMBOL, [])
    enriched_rows: list[dict[str, Any]] = []
    for row in index_rows:
        enriched = dict(row)
        symbol = str(row.get("symbol") or "").upper()
        bars = bars_by_symbol.get(symbol, [])
        as_of = date.fromisoformat(str(row.get("asOf"))) if parse_payload_date(row.get("asOf")) else None
        enriched["priceFactors"] = global_lppl_price_factors(
            bars,
            benchmark_bars=benchmark_bars,
            as_of=as_of,
            is_benchmark=symbol == GLOBAL_LPPL_US_BENCHMARK_SYMBOL,
        )
        enriched_rows.append(enriched)
    return enriched_rows


def global_lppl_price_factors(
    bars: list[MarketDailyBar],
    *,
    benchmark_bars: list[MarketDailyBar],
    as_of: date | None,
    is_benchmark: bool = False,
) -> dict[str, Any]:
    target = as_of or (bars[-1].date if bars else None)
    if target is None or len(bars) < 30:
        return {"available": False, "reason": "价格样本不足,暂不能计算技术因子。"}
    return_1m = trailing_return(bars, target, 21)
    return_3m = trailing_return(bars, target, 63)
    return_6m = trailing_return(bars, target, 126)
    ma200_gap = moving_average_gap(bars, target, 200)
    realized_vol = annualized_parkinson_vol(bars, target, 21)
    drawdown_252 = drawdown_from_recent_high(bars, target, 252)
    benchmark_3m = trailing_return(benchmark_bars, target, 63) if benchmark_bars else None
    relative_strength_3m = (
        None if return_3m is None or benchmark_3m is None or is_benchmark else return_3m - benchmark_3m
    )
    state, state_cn = global_lppl_market_state(ma200_gap, return_3m, drawdown_252)
    return {
        "available": True,
        "asOf": target.isoformat(),
        "return1m": pct_metric(return_1m),
        "return3m": pct_metric(return_3m),
        "return6m": pct_metric(return_6m),
        "ma200Gap": pct_metric(ma200_gap),
        "realizedVol": pct_metric(realized_vol),
        "drawdownFromHigh": pct_metric(drawdown_252),
        "relativeStrength3m": pct_metric(relative_strength_3m),
        "isBenchmark": is_benchmark,
        "marketState": state,
        "marketStateCn": state_cn,
    }


def global_lppl_market_state(
    ma200_gap: float | None,
    return_3m: float | None,
    drawdown_252: float | None,
) -> tuple[str, str]:
    below_trend = ma200_gap is not None and ma200_gap < 0
    deep_drawdown = drawdown_252 is not None and drawdown_252 <= -0.10
    above_trend = ma200_gap is not None and ma200_gap > 0
    positive_momentum = return_3m is not None and return_3m > 0
    shallow_drawdown = drawdown_252 is None or drawdown_252 > -0.08
    if below_trend and deep_drawdown:
        return "stressed", "承压"
    if above_trend and positive_momentum and shallow_drawdown:
        return "constructive", "偏强"
    return "neutral", "中性"


REGIONAL_FACTOR_VALIDATION_MIN_WEEKS = 60


def attach_global_lppl_factor_validation(
    index_rows: list[dict[str, Any]],
    bars_by_symbol: dict[str, list[MarketDailyBar]],
    per_index_history: dict[str, Any],
) -> list[dict[str, Any]]:
    """Validate each region's own factors (LPPL score, 3M momentum, relative strength vs
    US, realized vol) against that region's OWN forward returns via the shared walk-forward
    harness. Upgrades the region price-factors from descriptive to OOS-evaluated, and tells
    you which factor actually has predictive power for each region's equity."""
    benchmark_bars = bars_by_symbol.get(GLOBAL_LPPL_US_BENCHMARK_SYMBOL, [])
    enriched_rows: list[dict[str, Any]] = []
    for row in index_rows:
        enriched = dict(row)
        symbol = str(row.get("symbol") or "").upper()
        bars = bars_by_symbol.get(symbol, [])
        history = per_index_history.get(symbol, {}) if isinstance(per_index_history, dict) else {}
        enriched["factorValidation"] = build_index_factor_validation(
            symbol,
            bars,
            benchmark_bars,
            history,
            is_benchmark=symbol == GLOBAL_LPPL_US_BENCHMARK_SYMBOL,
        )
        enriched_rows.append(enriched)
    return enriched_rows


def build_index_factor_validation(
    symbol: str,
    bars: list[MarketDailyBar],
    benchmark_bars: list[MarketDailyBar],
    lppl_history: dict[str, Any],
    *,
    is_benchmark: bool = False,
) -> dict[str, Any]:
    clean = normalize_market_bars({symbol: bars}).get(symbol, [])
    if len(clean) < GLOBAL_LPPL_MIN_OBSERVATIONS:
        return {"available": False, "reason": "该地区ETF样本不足,暂不能验证因子。", "factors": []}
    bench_clean = normalize_market_bars({GLOBAL_LPPL_US_BENCHMARK_SYMBOL: benchmark_bars}).get(GLOBAL_LPPL_US_BENCHMARK_SYMBOL, [])
    price_points = [SeriesPoint(date=bar.date, value=bar.close) for bar in clean]
    prices_sorted = SortedSeries(price_points)
    week_dates = weekly_dates(price_points, years=5)
    if len(week_dates) < REGIONAL_FACTOR_VALIDATION_MIN_WEEKS:
        return {"available": False, "reason": "该地区周度样本不足,暂不能验证因子。", "factors": []}

    lppl_points: list[SeriesPoint] = []
    for point in (lppl_history.get("points", []) if isinstance(lppl_history, dict) else []):
        if not isinstance(point, dict):
            continue
        try:
            point_date = date.fromisoformat(str(point.get("date")))
        except (TypeError, ValueError):
            continue
        score = optional_float(point.get("score"))
        if score is not None:
            lppl_points.append(SeriesPoint(date=point_date, value=score))
    lppl_sorted = SortedSeries(lppl_points)

    momentum_pts: list[SeriesPoint] = []
    vol_pts: list[SeriesPoint] = []
    relative_pts: list[SeriesPoint] = []
    lppl_series_pts: list[SeriesPoint] = []
    for target in week_dates:
        momentum = trailing_return(clean, target, 63)
        if momentum is not None:
            momentum_pts.append(SeriesPoint(date=target, value=momentum * 100))
        realized_vol = annualized_parkinson_vol(clean, target, 21)
        if realized_vol is not None:
            vol_pts.append(SeriesPoint(date=target, value=realized_vol * 100))
        lppl_value = lppl_sorted.value_at_or_before(target)
        if lppl_value is not None:
            lppl_series_pts.append(SeriesPoint(date=target, value=lppl_value))
        if not is_benchmark and bench_clean:
            benchmark_momentum = trailing_return(bench_clean, target, 63)
            if momentum is not None and benchmark_momentum is not None:
                relative_pts.append(SeriesPoint(date=target, value=(momentum - benchmark_momentum) * 100))

    factor_specs = [
        ("lpplScore", "LPPL Score", "LPPL泡沫评分", lppl_series_pts, "higher_risk"),
        ("momentum3m", "3M Momentum", "3M动量", momentum_pts, "higher_better"),
        ("realizedVol", "Realized Vol", "已实现波动", vol_pts, "higher_risk"),
    ]
    if not is_benchmark:
        factor_specs.append(("relativeStrength3m", "Relative Strength vs US", "相对美国强弱", relative_pts, "higher_better"))

    rows: list[dict[str, Any]] = []
    for factor_id, label, label_cn, points, direction in factor_specs:
        row = signal_validation_metric_row(
            row_id=factor_id,
            label=label,
            label_cn=label_cn,
            module=symbol,
            signal_points=points,
            price_points=price_points,
            prices_sorted=prices_sorted,
            direction=direction,
        )
        if row is not None:
            rows.append(row)
    if not rows:
        return {"available": False, "reason": "因子周度样本不足,暂不能验证。", "factors": []}
    best = max(rows, key=lambda item: abs(optional_float(item.get("oosIc3m")) or 0.0))
    composite = build_region_composite_signal(
        factor_specs,
        price_points=price_points,
        prices_sorted=prices_sorted,
        best_single_oos_ic3m=optional_float(best.get("oosIc3m")),
        module=symbol,
    )
    return {
        "available": True,
        "method": (
            "Per-region walk-forward validation: each factor's weekly series is scored against this "
            "region's OWN forward returns (65/35 calibration/OOS split, 91D drawdown definition). "
            "Higher OOS IC and lift>1 mean the factor genuinely leads this region's equity."
        ),
        "observationCount": len(week_dates),
        "bestFactor": str(best.get("id") or ""),
        "bestFactorOosIc3m": best.get("oosIc3m"),
        "composite": composite,
        "factors": rows,
    }


def build_region_composite_signal(
    factor_specs: list[tuple[str, str, str, list[SeriesPoint], str]],
    *,
    price_points: list[SeriesPoint],
    prices_sorted: SortedSeries,
    best_single_oos_ic3m: float | None,
    module: str,
) -> dict[str, Any]:
    """Evidence-weighted multi-factor composite per region: each factor is oriented to
    'higher = more drawdown risk', z-scored on the CALIBRATION slice, and weighted by its
    calibration-slice predictive strength (so the OOS evaluation of the composite stays
    honest). Validates whether combining beats the best single factor for that region."""
    series_by_id: dict[str, dict[date, float]] = {}
    direction_by_id: dict[str, str] = {}
    label_by_id: dict[str, str] = {}
    for factor_id, _label, label_cn, points, direction in factor_specs:
        series_by_id[factor_id] = {point.date: point.value for point in points}
        direction_by_id[factor_id] = direction
        label_by_id[factor_id] = label_cn
    # Composite is defined only where every factor has a reading (dense, comparable).
    common_dates = sorted(set.intersection(*[set(series.keys()) for series in series_by_id.values()])) if series_by_id else []
    if len(common_dates) < MIN_SIGNAL_VALIDATION_POINTS:
        return {"available": False, "reason": "因子重叠样本不足,暂不能合成综合信号。"}
    split_index = max(1, int(len(common_dates) * SIGNAL_VALIDATION_OOS_SPLIT))
    calibration_dates = common_dates[:split_index]

    forward_by_date = {target: prices_sorted.forward_return_pct(target, days=91) for target in common_dates}
    weights: dict[str, float] = {}
    stats: dict[str, tuple[float, float]] = {}
    factor_weight_rows: list[dict[str, Any]] = []
    for factor_id, series in series_by_id.items():
        calibration_values = [series[target] for target in calibration_dates]
        mean = sum(calibration_values) / len(calibration_values)
        variance = sum((value - mean) ** 2 for value in calibration_values) / len(calibration_values)
        std = math.sqrt(variance)
        if std <= 1e-9:
            continue
        stats[factor_id] = (mean, std)
        sign = 1.0 if direction_by_id[factor_id] == "higher_risk" else -1.0
        # Calibration oriented-to-risk IC: positive => higher reading led LOWER forward return.
        risk_z_cal = [sign * (series[target] - mean) / std for target in calibration_dates]
        forward_cal = [forward_by_date[target] for target in calibration_dates]
        raw_ic = spearman_ic(risk_z_cal, forward_cal)
        risk_ic = -raw_ic if raw_ic is not None else None
        weight = max(0.0, risk_ic) if risk_ic is not None else 0.0
        weights[factor_id] = weight
        factor_weight_rows.append(
            {"id": factor_id, "labelCn": label_by_id[factor_id], "calibrationRiskIc": round(risk_ic, 3) if risk_ic is not None else None, "weight": round(weight, 3)}
        )
    weight_total = sum(weights.values())
    if weight_total <= 1e-9:
        return {"available": False, "reason": "校准段无因子对该地区呈现风险预测力,暂不合成综合信号。"}
    for row in factor_weight_rows:
        row["weight"] = round((weights.get(row["id"], 0.0)) / weight_total, 3)

    composite_points: list[SeriesPoint] = []
    for target in common_dates:
        total = 0.0
        for factor_id, weight in weights.items():
            if weight <= 0:
                continue
            mean, std = stats[factor_id]
            sign = 1.0 if direction_by_id[factor_id] == "higher_risk" else -1.0
            total += weight * sign * (series_by_id[factor_id][target] - mean) / std
        composite_points.append(SeriesPoint(date=target, value=total / weight_total))

    metric = signal_validation_metric_row(
        row_id="regionComposite",
        label="Evidence-weighted composite",
        label_cn="证据加权综合信号",
        module=module,
        signal_points=composite_points,
        price_points=price_points,
        prices_sorted=prices_sorted,
        direction="higher_risk",
    )
    if metric is None:
        return {"available": False, "reason": "综合信号样本不足,暂不能验证。"}
    composite_oos = optional_float(metric.get("oosIc3m"))
    improvement = None
    beats_best = None
    if composite_oos is not None and best_single_oos_ic3m is not None:
        improvement = round(abs(composite_oos) - abs(best_single_oos_ic3m), 3)
        beats_best = abs(composite_oos) > abs(best_single_oos_ic3m)
    return {
        "available": True,
        "method": (
            "因子定向到'高=高回撤风险'后按校准段定向IC加权(z-score标准化), 仅用校准段定权以保持OOS诚实; "
            "综合信号再经同一走出样本框架验证, 并与最强单因子对比。"
        ),
        "oosIc3m": metric.get("oosIc3m"),
        "ic3m": metric.get("ic3m"),
        "hitRateOos": metric.get("hitRateOos"),
        "baseRate": metric.get("baseRate"),
        "lift": metric.get("lift"),
        "leadTimeDays": metric.get("leadTimeDays"),
        "classification": metric.get("classification"),
        "currentValue": round(composite_points[-1].value, 3),
        "alertThreshold": metric.get("alertThreshold"),
        "breachCountTotal": metric.get("alertCountTotal"),
        "breachHitRateTotal": metric.get("hitRateTotal"),
        "breachEvents": metric.get("breachEvents", []),
        "weights": sorted(factor_weight_rows, key=lambda item: item["weight"], reverse=True),
        "beatsBestSingleFactor": beats_best,
        "oosIc3mImprovement": improvement,
    }


def global_lppl_ensemble_multiplier(row: dict[str, Any]) -> float:
    ensemble = row.get("fitEnsemble") if isinstance(row.get("fitEnsemble"), dict) else {}
    if not ensemble or ensemble.get("available") is not True:
        return 1.0
    valid_ratio = optional_float(ensemble.get("validFitRatioPct"))
    residual_ratio = optional_float(ensemble.get("residualPassRatioPct"))
    valid_ratio = 1.0 if valid_ratio is None else max(0.0, min(1.0, valid_ratio / 100.0))
    residual_ratio = 1.0 if residual_ratio is None else max(0.0, min(1.0, residual_ratio / 100.0))
    agreement = str(ensemble.get("windowAgreement") or "").lower()
    agreement_multiplier = {
        "tight": 1.0,
        "moderate": 0.90,
        "scattered": 0.65,
        "unavailable": 0.80,
    }.get(agreement, 0.85)
    tc_window_days = optional_float(ensemble.get("tcWindowDays"))
    if tc_window_days is None:
        tc_multiplier = 1.0
    elif tc_window_days > 120:
        tc_multiplier = 0.75
    elif tc_window_days > 75:
        tc_multiplier = 0.85
    elif tc_window_days > 45:
        tc_multiplier = 0.93
    else:
        tc_multiplier = 1.0
    valid_multiplier = 0.70 + 0.30 * valid_ratio
    residual_multiplier = 0.60 + 0.40 * residual_ratio
    return round(max(0.45, min(1.0, agreement_multiplier, tc_multiplier, valid_multiplier, residual_multiplier)), 3)


def build_global_lppl_forward_signal(row: dict[str, Any]) -> dict[str, Any]:
    symbol = str(row.get("symbol") or "").upper()
    model_score = optional_float(row.get("score"))
    if not row.get("available") or model_score is None:
        return {"available": False, "symbol": symbol, "score": None, "regime": "Unavailable", "regimeCn": "不可用", "summary": "LPPL forward signal unavailable."}
    history = row.get("history") if isinstance(row.get("history"), dict) else {}
    history_points = history.get("points", []) if isinstance(history, dict) else []
    score_momentum_5d = lppl_history_score_delta(history_points, 5)
    score_momentum_20d = lppl_history_score_delta(history_points, 20)
    clip_state = row.get("clipState") if isinstance(row.get("clipState"), dict) else history.get("clipState") if isinstance(history, dict) else {}
    clip_lock = bool(clip_state.get("clipLock")) if isinstance(clip_state, dict) else False
    validation = row.get("validation") if isinstance(row.get("validation"), dict) else {}
    production_evidence_available = validation.get("productionEvidenceAvailable") is True
    threshold = (
        optional_float(validation.get("productionThreshold"))
        if production_evidence_available
        else None
    )
    if threshold is None and production_evidence_available:
        threshold = optional_float(validation.get("threshold"))
    if threshold is None:
        # Per-index backtests are intentionally descriptive full-sample audits.
        # They must never select the live forward-signal threshold.
        threshold = GLOBAL_LPPL_ALERT_THRESHOLD
    threshold_distance = model_score - threshold
    days_to_critical = optional_float(row.get("daysToCritical"))
    confidence = max(0.0, min(1.0, optional_float(row.get("confidence")) or 0.0))
    validation_multiplier = (
        optional_float(validation.get("productionEffectiveWeightMultiplier"))
        if production_evidence_available
        else None
    )
    if validation_multiplier is None and production_evidence_available:
        validation_multiplier = optional_float(validation.get("effectiveWeightMultiplier"))
    # No untouched OOS evidence means no validation credit in production.
    validation_multiplier = max(0.0, min(1.0, validation_multiplier if validation_multiplier is not None else 0.0))
    ensemble_multiplier = global_lppl_ensemble_multiplier(row)
    threshold_pressure = risk_linear(threshold_distance, -15.0, 10.0)
    momentum_pressure = risk_linear(score_momentum_20d if score_momentum_20d is not None else 0.0, -8.0, 12.0)
    critical_pressure = risk_linear(180.0 - days_to_critical, 0.0, 140.0) if days_to_critical is not None else 50.0
    raw_score = (
        0.42 * bounded_score(model_score)
        + 0.22 * threshold_pressure
        + 0.18 * momentum_pressure
        + 0.18 * critical_pressure
    )
    if clip_lock:
        raw_score = min(100.0, raw_score + 8.0)
    elif isinstance(clip_state, dict) and clip_state.get("status") == "converging":
        raw_score = min(100.0, raw_score + 3.0)
    forward_score = bounded_score(
        raw_score
        * (0.65 + 0.35 * validation_multiplier)
        * (0.75 + 0.25 * confidence)
        * ensemble_multiplier
    )
    drivers: list[str] = []
    if threshold_distance >= 0:
        drivers.append("above_threshold")
    elif threshold_distance >= -10:
        drivers.append("near_threshold")
    if score_momentum_20d is not None and score_momentum_20d >= 8:
        drivers.append("rising")
    elif score_momentum_20d is not None and score_momentum_20d <= -8:
        drivers.append("falling")
    if days_to_critical is not None and days_to_critical <= 90:
        drivers.append("critical_window")
    if clip_lock:
        drivers.append("clip_lock")
    if validation_multiplier < 0.75:
        drivers.append("weak_validation")
    if ensemble_multiplier < 0.85:
        drivers.append("weak_ensemble")
    regime, regime_cn = global_lppl_forward_regime(forward_score, score_momentum_20d)
    return {
        "available": True,
        "symbol": symbol,
        "score": round(forward_score, 1),
        "regime": regime,
        "regimeCn": regime_cn,
        "scoreMomentum5d": round(score_momentum_5d, 1) if score_momentum_5d is not None else None,
        "scoreMomentum20d": round(score_momentum_20d, 1) if score_momentum_20d is not None else None,
        "threshold": int(threshold),
        "thresholdSource": (
            str(validation.get("productionThresholdSource") or "purged_calibration_first_65pct")
            if production_evidence_available
            else "fixed_prior_no_oos"
        ),
        "thresholdDistance": round(threshold_distance, 1),
        "daysToCritical": int(days_to_critical) if days_to_critical is not None else None,
        "clipLock": clip_lock,
        "clipStatus": str(clip_state.get("status") or "") if isinstance(clip_state, dict) else "",
        "validationMultiplier": round(validation_multiplier, 2),
        "ensembleMultiplier": round(ensemble_multiplier, 2),
        "drivers": drivers,
        "summary": global_lppl_forward_summary(symbol, forward_score, regime_cn, score_momentum_20d, threshold_distance, validation_multiplier, ensemble_multiplier),
    }


def lppl_history_score_delta(points: list[dict[str, Any]], lookback: int) -> float | None:
    clean_scores = [
        optional_float(point.get("score"))
        for point in points
        if isinstance(point, dict) and optional_float(point.get("score")) is not None
    ]
    if len(clean_scores) < 2:
        return None
    latest = clean_scores[-1]
    anchor = clean_scores[max(0, len(clean_scores) - 1 - max(1, lookback))]
    return latest - anchor


def global_lppl_forward_regime(score: float, score_momentum_20d: float | None) -> tuple[str, str]:
    if score_momentum_20d is not None and score_momentum_20d <= -8 and score < 60:
        return "Fading", "前瞻降温"
    if score >= 70:
        return "Forward Risk", "前瞻风险"
    if score >= 55 and (score_momentum_20d or 0.0) > 0:
        return "Rising Watch", "前瞻升温"
    if score >= 55:
        return "Watch", "观察"
    return "Quiet", "低前瞻压力"


def global_lppl_forward_summary(
    symbol: str,
    score: float,
    regime_cn: str,
    score_momentum_20d: float | None,
    threshold_distance: float,
    validation_multiplier: float,
    ensemble_multiplier: float,
) -> str:
    momentum_text = "20D动量不足" if score_momentum_20d is None else f"20D动量{score_momentum_20d:+.1f}"
    threshold_text = f"距阈值{threshold_distance:+.1f}"
    validation_text = f"验证权重x{validation_multiplier:.2f}"
    ensemble_text = f"窗口一致性x{ensemble_multiplier:.2f}"
    return f"{symbol} LPPL前瞻压力{score:.1f} ({regime_cn}); {momentum_text}, {threshold_text}, {validation_text}, {ensemble_text}."


def apply_global_lppl_index_validation(
    index_rows: list[dict[str, Any]],
    validation: dict[str, Any],
) -> list[dict[str, Any]]:
    validation_by_symbol = {
        str(row.get("symbol") or "").upper(): row
        for row in validation.get("rows", [])
        if isinstance(row, dict)
    } if isinstance(validation, dict) else {}
    adjusted_rows: list[dict[str, Any]] = []
    for row in index_rows:
        adjusted = dict(row)
        symbol = str(adjusted.get("symbol") or "").upper()
        validation_row = validation_by_symbol.get(symbol)
        if validation_row:
            adjusted["validation"] = validation_row
            adjusted["effectiveWeightMultiplier"] = validation_row.get("effectiveWeightMultiplier")
        elif adjusted.get("available"):
            adjusted["effectiveWeightMultiplier"] = 0.0
        adjusted_rows.append(adjusted)
    return adjusted_rows


def build_global_lppl_index_validation(
    index_rows: list[dict[str, Any]],
    bars_by_symbol: dict[str, list[MarketDailyBar]],
    *,
    histories: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for index_row in index_rows:
        if not index_row.get("available"):
            continue
        symbol = str(index_row.get("symbol") or "").upper()
        bars = bars_by_symbol.get(symbol, [])
        history = histories.get(symbol) if isinstance(histories, dict) else None
        history_points = history.get("points") if isinstance(history, dict) and isinstance(history.get("points"), list) else None
        row = build_global_lppl_single_index_validation(index_row, bars, history_points=history_points)
        if row:
            rows.append(row)
    if not rows:
        return {"available": False, "rows": [], "summary": "No index-level LPPL validation samples were available."}
    validated = sum(1 for row in rows if row.get("validationRole") == "validated")
    weak = sum(1 for row in rows if row.get("validationRole") == "weak")
    unvalidated = sum(1 for row in rows if not row.get("productionEvidenceAvailable"))
    summary = (
        f"{len(rows)} indices replayed; {validated} validated, {weak} weak, {unvalidated} unavailable "
        "by purged-calibration / untouched-OOS own-market 15D drawdown audit."
    )
    return {"available": True, "rows": rows, "summary": summary}


def build_global_lppl_single_index_validation(
    index_row: dict[str, Any],
    bars: list[MarketDailyBar],
    *,
    drawdown_threshold_pct: float = -2.0,
    history_points: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    symbol = str(index_row.get("symbol") or "").upper()
    clean = normalize_market_bars({symbol: bars}).get(symbol, [])
    if len(clean) < GLOBAL_LPPL_MIN_OBSERVATIONS + 20:
        return None
    points = history_points if history_points is not None else build_single_index_lppl_history_points(symbol, clean)
    observations = build_global_lppl_validation_observations(points, clean, drawdown_threshold_pct)
    if not observations:
        return None
    descriptive_calibration_grid = [
        equity_backtest_threshold_test(candidate_threshold, observations, drawdown_threshold_pct, horizon=15)
        for candidate_threshold in (55, 60, 65, 70, 75, 80, 85, 90)
    ]
    descriptive_recommended = global_lppl_recommended_threshold(
        descriptive_calibration_grid,
        len(observations),
    )
    descriptive_threshold = int(
        descriptive_recommended.get("threshold") or GLOBAL_LPPL_ALERT_THRESHOLD
    )
    descriptive_test_15d = equity_backtest_threshold_test(
        descriptive_threshold,
        observations,
        drawdown_threshold_pct,
        horizon=15,
    )
    descriptive_multiplier, descriptive_role, descriptive_role_cn = global_lppl_validation_weight(
        descriptive_test_15d
    )

    oos_fields = global_lppl_oos_validation_fields(observations, drawdown_threshold_pct)
    production_available = oos_fields.get("productionEvidenceAvailable") is True
    threshold = int(
        optional_float(oos_fields.get("productionThreshold"))
        or GLOBAL_LPPL_ALERT_THRESHOLD
    )
    production_test_15d = (
        oos_fields.get("oosTest15d")
        if production_available and isinstance(oos_fields.get("oosTest15d"), dict)
        else {}
    )
    multiplier = optional_float(oos_fields.get("productionEffectiveWeightMultiplier")) or 0.0
    role = str(oos_fields.get("productionValidationRole") or "unvalidated")
    role_cn = str(oos_fields.get("productionValidationRoleCn") or "OOS证据不足")
    precision = optional_float(production_test_15d.get("precision"))
    recall = optional_float(production_test_15d.get("recall"))
    payload = {
        "symbol": symbol,
        "sourceSymbol": str(index_row.get("sourceSymbol") or symbol),
        "sampleSize": int(production_test_15d.get("sampleSize") or 0),
        "historyPoints": len(points),
        "threshold": threshold,
        "alertDays": int(production_test_15d.get("alertDays") or 0),
        "truePositives": int(production_test_15d.get("truePositives") or 0),
        "falsePositives": int(production_test_15d.get("falsePositives") or 0),
        "precision15d": round(precision, 1) if precision is not None else None,
        "recall15d": round(recall, 1) if recall is not None else None,
        "baseRate15d": production_test_15d.get("baseRate"),
        "avgMaxDrawdown15dWhenAlert": production_test_15d.get("avgMaxDrawdownWhenAlert"),
        "avgDrawdownLeadDaysWhenHit": production_test_15d.get("avgDrawdownLeadDaysWhenHit"),
        "effectiveWeightMultiplier": multiplier,
        "validationRole": role,
        "validationRoleCn": role_cn,
        "summary": (
            global_lppl_validation_summary(symbol, production_test_15d, multiplier, role_cn)
            if production_available
            else f"{symbol} production validation disabled: untouched OOS evidence is insufficient."
        ),
        "descriptiveFullSample": {
            "productionUse": False,
            "sampleSize": int(descriptive_test_15d.get("sampleSize") or 0),
            "threshold": descriptive_threshold,
            "alertDays": int(descriptive_test_15d.get("alertDays") or 0),
            "precision15d": descriptive_test_15d.get("precision"),
            "recall15d": descriptive_test_15d.get("recall"),
            "baseRate15d": descriptive_test_15d.get("baseRate"),
            "effectiveWeightMultiplier": descriptive_multiplier,
            "validationRole": descriptive_role,
            "validationRoleCn": descriptive_role_cn,
            "recommendedThreshold": descriptive_recommended,
            "calibrationGrid": descriptive_calibration_grid,
            "test15d": descriptive_test_15d,
        },
    }
    payload.update(oos_fields)
    return payload


def build_single_index_lppl_history_points(
    symbol: str,
    bars: list[MarketDailyBar],
) -> list[dict[str, Any]]:
    """Facade wrapper preserving the patch seam for global_lppl_index_row."""
    return _lppl_history.build_single_index_lppl_history_points(
        symbol,
        bars,
        row_builder=global_lppl_index_row,
    )


def parse_payload_date(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def macro_liquidity_score_at(
    series: dict[str, list[SeriesPoint]] | PreparedBhadialSeries,
    target: date,
) -> dict[str, Any] | None:
    row = bhadial_conditions_score_at(series, target)
    if (
        row is None
        or row.get("scoredFactorCount", 0) < 5
        or float(row.get("effectiveWeightCoverage") or 0.0) < 0.25
    ):
        return None
    return {
        "score": row["score"],
        "coverage": row["scoredFactorCount"],
        "effectiveWeightCoverage": row["effectiveWeightCoverage"],
    }


def add_macro_liquidity_equity_deltas(rows: list[dict[str, Any]]) -> None:
    for index, row in enumerate(rows):
        if index >= 3:
            prior = rows[index - 3]
            row["score3mChange"] = round(float(row["liquidityScore"]) - float(prior["liquidityScore"]), 1)
            current_spx = float(row["sp500"])
            prior_spx = float(prior["sp500"])
            row["sp500Trailing3m"] = round((current_spx / prior_spx - 1) * 100, 2) if prior_spx else None
        else:
            row["score3mChange"] = None
            row["sp500Trailing3m"] = None


def row_correlation(rows: list[dict[str, Any]], left_key: str, right_key: str) -> float | None:
    pairs = [
        (float(row[left_key]), float(row[right_key]))
        for row in rows
        if row.get(left_key) is not None and row.get(right_key) is not None
    ]
    if len(pairs) < 6:
        return None
    xs = [item[0] for item in pairs]
    ys = [item[1] for item in pairs]
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in pairs)
    x_var = sum((x - x_mean) ** 2 for x in xs)
    y_var = sum((y - y_mean) ** 2 for y in ys)
    if x_var <= 0 or y_var <= 0:
        return None
    return numerator / math.sqrt(x_var * y_var)


def macro_liquidity_lead_lag(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    specs = [("评分水平", "liquidityScore"), ("3M评分变化", "score3mChange")]
    horizons = [("forward1m", "1M"), ("forward3m", "3M"), ("forward6m", "6M")]
    matrix: list[dict[str, Any]] = []
    for label, signal_key in specs:
        row: dict[str, Any] = {"signal": label}
        for forward_key, horizon_label in horizons:
            corr = row_correlation(rows, signal_key, forward_key)
            row[forward_key] = round(corr, 3) if corr is not None else None
            row[f"{forward_key}Label"] = horizon_label
        matrix.append(row)
    return matrix


def liquidity_forward_return_buckets(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sample = [row for row in rows if row.get("forward3m") is not None]
    if len(sample) < 9:
        return []
    ordered = sorted(sample, key=lambda item: float(item["liquidityScore"]))
    labels = ["低评分", "中位评分", "高评分"]
    buckets: list[dict[str, Any]] = []
    for index, label in enumerate(labels):
        start = round(index * len(ordered) / 3)
        end = round((index + 1) * len(ordered) / 3)
        bucket = ordered[start:end]
        returns = [float(item["forward3m"]) for item in bucket if item.get("forward3m") is not None]
        scores = [float(item["liquidityScore"]) for item in bucket]
        buckets.append(
            {
                "label": label,
                "count": len(bucket),
                "scoreRange": f"{min(scores):.0f}-{max(scores):.0f}" if scores else "--",
                "avgForward3m": round(sum(returns) / len(returns), 2) if returns else None,
                "medianForward3m": round(median(returns), 2) if returns else None,
                "hitRate": round((sum(1 for value in returns if value > 0) / len(returns)) * 100) if returns else None,
            }
        )
    return buckets


def score_change_forward_return_buckets(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sample = [row for row in rows if row.get("score3mChange") is not None and row.get("forward3m") is not None]
    if len(sample) < 9:
        return []
    ordered = sorted(sample, key=lambda item: float(item["score3mChange"]))
    labels = ["评分下行", "变化不大", "评分上行"]
    buckets: list[dict[str, Any]] = []
    for index, label in enumerate(labels):
        start = round(index * len(ordered) / 3)
        end = round((index + 1) * len(ordered) / 3)
        bucket = ordered[start:end]
        changes = [float(item["score3mChange"]) for item in bucket]
        returns = [float(item["forward3m"]) for item in bucket if item.get("forward3m") is not None]
        drawdowns = [float(item["forward3mMaxDrawdown"]) for item in bucket if item.get("forward3mMaxDrawdown") is not None]
        buckets.append(
            {
                "label": label,
                "count": len(bucket),
                "changeRange": f"{min(changes):+.1f} to {max(changes):+.1f}" if changes else "--",
                "avgForward3m": round(sum(returns) / len(returns), 2) if returns else None,
                "hitRate": round((sum(1 for value in returns if value > 0) / len(returns)) * 100) if returns else None,
                "avgMaxDrawdown3m": round(sum(drawdowns) / len(drawdowns), 2) if drawdowns else None,
            }
        )
    return buckets


def rolling_forward_correlation(rows: list[dict[str, Any]], *, window_months: int = 24) -> dict[str, Any]:
    usable = [row for row in rows if row.get("forward3m") is not None]
    points: list[dict[str, Any]] = []
    for index in range(window_months - 1, len(usable)):
        sample = usable[index - window_months + 1 : index + 1]
        corr = row_correlation(sample, "liquidityScore", "forward3m")
        if corr is None:
            continue
        points.append({"date": usable[index]["date"], "correlation": round(corr, 3)})
    latest = points[-1]["correlation"] if points else None
    values = [float(point["correlation"]) for point in points]
    return {
        "windowMonths": window_months,
        "latest": latest,
        "points": points,
        "range": {"min": round(min(values), 3), "max": round(max(values), 3)} if values else {"min": None, "max": None},
    }


def liquidity_drawdown_risk(rows: list[dict[str, Any]]) -> dict[str, Any]:
    sample = [row for row in rows if row.get("forward3mMaxDrawdown") is not None]
    if not sample:
        return {"maxDrawdown": None, "worstDate": "", "avgDrawdownByBucket": []}
    worst = min(sample, key=lambda item: float(item["forward3mMaxDrawdown"]))
    level_buckets = liquidity_forward_return_buckets(rows)
    drawdown_buckets: list[dict[str, Any]] = []
    if len(level_buckets) == 3:
        ordered = sorted([row for row in sample if row.get("forward3m") is not None], key=lambda item: float(item["liquidityScore"]))
        for index, label in enumerate(["低评分", "中位评分", "高评分"]):
            start = round(index * len(ordered) / 3)
            end = round((index + 1) * len(ordered) / 3)
            bucket = ordered[start:end]
            drawdowns = [float(item["forward3mMaxDrawdown"]) for item in bucket if item.get("forward3mMaxDrawdown") is not None]
            drawdown_buckets.append(
                {
                    "label": label,
                    "avgMaxDrawdown3m": round(sum(drawdowns) / len(drawdowns), 2) if drawdowns else None,
                    "worstMaxDrawdown3m": round(min(drawdowns), 2) if drawdowns else None,
                }
            )
    return {
        "maxDrawdown": round(float(worst["forward3mMaxDrawdown"]), 2),
        "worstDate": str(worst["date"]),
        "avgDrawdownByBucket": drawdown_buckets,
    }


def macro_liquidity_current_signal(
    rows: list[dict[str, Any]],
    level_buckets: list[dict[str, Any]],
    change_buckets: list[dict[str, Any]],
    lead_lag: list[dict[str, Any]],
) -> dict[str, Any]:
    latest = rows[-1] if rows else {}
    latest_score = optional_float(latest.get("liquidityScore"))
    latest_change = optional_float(latest.get("score3mChange"))
    level_label = bucket_label_by_rank(rows, "liquidityScore", latest_score, ["低评分", "中位评分", "高评分"])
    change_label = bucket_label_by_rank(
        [row for row in rows if row.get("score3mChange") is not None],
        "score3mChange",
        latest_change,
        ["评分下行", "变化不大", "评分上行"],
    )
    level_bucket = find_bucket(level_buckets, level_label)
    change_bucket = find_bucket(change_buckets, change_label)
    expected_forward = optional_float(change_bucket.get("avgForward3m")) if change_bucket else None
    if expected_forward is None and level_bucket:
        expected_forward = optional_float(level_bucket.get("avgForward3m"))
    expected_drawdown = optional_float(change_bucket.get("avgMaxDrawdown3m")) if change_bucket else None
    hit_rate = optional_float(change_bucket.get("hitRate")) if change_bucket else None
    change_corr_3m = None
    for row in lead_lag:
        if row.get("signal") == "3M评分变化":
            change_corr_3m = optional_float(row.get("forward3m"))
            break
    confidence = signal_confidence(change_corr_3m, len(rows))
    verdict = current_signal_verdict(level_label, change_label, expected_forward, expected_drawdown, change_corr_3m)
    return {
        "available": True,
        "date": latest.get("date", ""),
        "score": latest_score,
        "score3mChange": latest_change,
        "levelBucket": level_label,
        "changeBucket": change_label,
        "expectedForward3m": round(expected_forward, 2) if expected_forward is not None else None,
        "expectedDrawdown3m": round(expected_drawdown, 2) if expected_drawdown is not None else None,
        "hitRate": round(hit_rate) if hit_rate is not None else None,
        "confidence": confidence["key"],
        "confidenceLabel": confidence["label"],
        "verdict": verdict,
        "cards": [
            {
                "label": "当前评分",
                "value": f"{latest_score:.1f}" if latest_score is not None else "--",
                "detail": f"{level_label} · {latest.get('date', '--')}",
                "tone": score_tone(latest_score),
            },
            {
                "label": "3M评分变化",
                "value": format_signed_number(latest_change, digits=1),
                "detail": change_label,
                "tone": "supportive" if latest_change is not None and latest_change > 0 else "restrictive" if latest_change is not None and latest_change < 0 else "neutral",
            },
            {
                "label": "相似样本3M",
                "value": f"{expected_forward:+.2f}%" if expected_forward is not None else "--",
                "detail": f"{round(hit_rate):.0f}% hit" if hit_rate is not None else "hit --",
                "tone": "supportive" if expected_forward is not None and expected_forward > 0 else "restrictive" if expected_forward is not None and expected_forward < 0 else "neutral",
            },
            {
                "label": "3M回撤风险",
                "value": f"{expected_drawdown:.2f}%" if expected_drawdown is not None else "--",
                "detail": "avg max drawdown",
                "tone": "restrictive" if expected_drawdown is not None and expected_drawdown < -5 else "neutral",
            },
            {
                "label": "信号置信度",
                "value": confidence["label"],
                "detail": f"3M变化corr {format_signed_number(change_corr_3m, digits=2)}",
                "tone": confidence["tone"],
            },
        ],
    }


def macro_liquidity_state_grid(rows: list[dict[str, Any]], current_signal: dict[str, Any]) -> list[dict[str, Any]]:
    labels_level = ["低评分", "中位评分", "高评分"]
    labels_change = ["评分下行", "变化不大", "评分上行"]
    change_rows = [row for row in rows if row.get("score3mChange") is not None]
    sample: list[dict[str, Any]] = []
    for row in rows:
        if row.get("forward3m") is None or row.get("score3mChange") is None:
            continue
        level_label = bucket_label_by_rank(rows, "liquidityScore", optional_float(row.get("liquidityScore")), labels_level)
        change_label = bucket_label_by_rank(change_rows, "score3mChange", optional_float(row.get("score3mChange")), labels_change)
        sample.append({**row, "levelBucket": level_label, "changeBucket": change_label})
    grid: list[dict[str, Any]] = []
    current_level = str(current_signal.get("levelBucket") or "")
    current_change = str(current_signal.get("changeBucket") or "")
    for level in labels_level:
        for change in labels_change:
            bucket = [row for row in sample if row["levelBucket"] == level and row["changeBucket"] == change]
            forwards = [float(row["forward3m"]) for row in bucket if row.get("forward3m") is not None]
            drawdowns = [float(row["forward3mMaxDrawdown"]) for row in bucket if row.get("forward3mMaxDrawdown") is not None]
            avg_forward = sum(forwards) / len(forwards) if forwards else None
            avg_drawdown = sum(drawdowns) / len(drawdowns) if drawdowns else None
            worst_drawdown = min(drawdowns) if drawdowns else None
            hit_rate = (sum(1 for value in forwards if value > 0) / len(forwards)) * 100 if forwards else None
            grid.append(
                {
                    "levelBucket": level,
                    "changeBucket": change,
                    "count": len(bucket),
                    "sampleShare": round((len(bucket) / len(sample)) * 100) if sample else 0,
                    "avgForward3m": round(avg_forward, 2) if avg_forward is not None else None,
                    "medianForward3m": round(median(forwards), 2) if forwards else None,
                    "hitRate": round(hit_rate) if hit_rate is not None else None,
                    "avgMaxDrawdown3m": round(avg_drawdown, 2) if avg_drawdown is not None else None,
                    "worstMaxDrawdown3m": round(worst_drawdown, 2) if worst_drawdown is not None else None,
                    "isCurrent": level == current_level and change == current_change,
                    "tone": "supportive" if avg_forward is not None and avg_forward > 0 else "restrictive" if avg_forward is not None and avg_forward < 0 else "neutral",
                }
            )
    return grid


def find_bucket(buckets: list[dict[str, Any]], label: str) -> dict[str, Any]:
    for bucket in buckets:
        if bucket.get("label") == label:
            return bucket
    return {}


def signal_confidence(correlation: float | None, sample_size: int) -> dict[str, str]:
    if correlation is None or sample_size < 36 or abs(correlation) < 0.2:
        return {"key": "low", "label": "低", "tone": "neutral"}
    if abs(correlation) >= 0.45 and sample_size >= 48:
        return {"key": "high", "label": "高", "tone": "supportive"}
    return {"key": "medium", "label": "中", "tone": "supportive"}


def current_signal_verdict(
    level_label: str,
    change_label: str,
    expected_forward: float | None,
    expected_drawdown: float | None,
    change_corr_3m: float | None,
) -> str:
    forward_text = f"相似变化样本未来3个月平均{expected_forward:+.2f}%" if expected_forward is not None else "相似变化样本收益不足"
    drawdown_text = f"平均回撤{expected_drawdown:.2f}%" if expected_drawdown is not None else "回撤样本不足"
    corr_text = f"3M变化信号相关{change_corr_3m:+.2f}" if change_corr_3m is not None else "变化信号相关不足"
    if change_label == "评分上行":
        return f"当前属于{level_label},但边际流动性正在改善; {forward_text}, {drawdown_text}, {corr_text}。"
    if change_label == "评分下行":
        return f"当前属于{level_label},且边际流动性转弱; {forward_text}, {drawdown_text}, {corr_text}, 风险资产承接需要更保守。"
    return f"当前属于{level_label},边际变化不大; {forward_text}, {drawdown_text}, {corr_text}, 更适合作为环境过滤器。"


def score_tone(score: float | None) -> str:
    if score is None:
        return "neutral"
    if score >= 55:
        return "supportive"
    if score <= 45:
        return "restrictive"
    return "neutral"


def macro_liquidity_equity_conclusion(corr_3m: float | None, high_low: float | None, buckets: list[dict[str, Any]]) -> str:
    if corr_3m is None or high_low is None:
        return "样本不足,暂不能判断宏观环境综合评分对S&P 500的前瞻性。"
    if corr_3m >= 0.25 and high_low > 0:
        return (
            f"过去5年样本显示,宏观环境综合评分与S&P 500未来3个月收益存在正向领先关系: "
            f"3M相关系数{corr_3m:+.2f},高评分桶相对低评分桶高{high_low:+.2f}个百分点。"
        )
    if corr_3m <= -0.25 and high_low < 0:
        return (
            f"过去5年样本显示,宏观环境高分后S&P 500未来3个月收益反而偏弱: "
            f"3M相关系数{corr_3m:+.2f},高低评分桶差{high_low:+.2f}个百分点。"
        )
    return (
        f"过去5年样本中,宏观环境综合评分对S&P 500未来3个月收益的前瞻性有限: "
        f"3M相关系数{corr_3m:+.2f},高低评分桶差{high_low:+.2f}个百分点; 更适合作为风险环境过滤器,不宜单独作为择时信号。"
    )


def format_correlation(value: float | None) -> str:
    return f"{value:+.2f}" if value is not None else "--"


def correlation_tone(value: float | None) -> str:
    if value is None or abs(value) < 0.15:
        return "neutral"
    return "supportive" if value > 0 else "restrictive"


def macro_liquidity_summary(score: float, constraint: dict[str, Any], offset: dict[str, Any], trend: dict[str, Any] | None = None) -> str:
    regime = macro_liquidity_regime(score)
    constraint_name = constraint.get("name", "关键拖累")
    constraint_value = constraint.get("value", "--")
    constraint_contribution = float(constraint.get("contribution") or 0)
    offset_name = offset.get("name", "关键缓冲")
    offset_value = offset.get("value", "--")
    offset_contribution = float(offset.get("contribution") or 0)
    return (
        f"{regime}: 最大拖累是{constraint_name}({constraint_value}, {constraint_contribution:+.1f}), "
        f"最大缓冲是{offset_name}({offset_value}, {offset_contribution:+.1f}); "
        f"{(trend or {}).get('summary') or '历史分位样本不足'}"
    )


def macro_liquidity_implications(score: float, constraint: dict[str, Any], offset: dict[str, Any]) -> list[dict[str, str]]:
    constraint_name = str(constraint.get("name") or "关键拖累")
    offset_name = str(offset.get("name") or "关键缓冲")
    if score <= 45:
        return [
            {"label": "久期", "tone": "restrictive", "text": f"{constraint_name}压制承接,长端抛售更容易放大。"},
            {"label": "风险资产", "tone": "restrictive", "text": "流动性低分位削弱估值缓冲,高贝塔资产更依赖盈利支撑。"},
            {"label": "融资压力", "tone": "watch", "text": f"{offset_name}提供局部缓冲,但不足以抵消现金抽水。"},
        ]
    if score >= 55:
        return [
            {"label": "久期", "tone": "supportive", "text": f"{offset_name}改善承接,久期回撤更容易被买盘吸收。"},
            {"label": "风险资产", "tone": "supportive", "text": "流动性分位偏高,风险资产估值缓冲较好。"},
            {"label": "融资压力", "tone": "neutral", "text": f"仍需监控{constraint_name},防止边际抽水反复。"},
        ]
    return [
        {"label": "久期", "tone": "neutral", "text": "流动性对久期影响中性,主要看通胀与政策路径。"},
        {"label": "风险资产", "tone": "neutral", "text": "风险资产缺少明确流动性方向,等待分位突破。"},
        {"label": "融资压力", "tone": "watch", "text": f"{constraint_name}与{offset_name}相互抵消,关注边际变化。"},
    ]


def macro_liquidity_regime(score: float) -> str:
    if score >= 70:
        return "流动性宽松"
    if score >= 55:
        return "边际宽松"
    if score > 45:
        return "中性"
    if score > 30:
        return "偏紧"
    return "紧缩压力"


def build_percentile_trends(ind: dict[str, Any], auctions: list[dict[str, object]]) -> list[dict[str, Any]]:
    series = ind.get("percentile_series", {})
    specs = [
        ("银行准备金", "FRED WRESBAL", "5Y", series.get("bank_reserves", []), 1_000_000, 2, "$T"),
        ("净流动性", "FRED WALCL - WTREGEN - RRPONTSYD", "5Y", series.get("net_liquidity", []), 1_000_000, 2, "$T"),
        ("流动性动量", "Net liquidity 1M change", "5Y", series.get("net_liquidity_momentum", []), 1_000_000, 2, "$T"),
        ("13周净流动性动量", "Net liquidity 13W change", "5Y", series.get("net_liquidity_13w_momentum", []), 1_000_000, 2, "$T"),
        ("TGA偏离度", "FRED WTREGEN - 52W median", "5Y", series.get("tga_deviation", []), 1_000_000, 2, "$T"),
        ("ON RRP缓冲风险", "FRED RRPONTSYD risk signal", "5Y", series.get("onrrp_buffer_risk", []), 1, 2, ""),
        ("SOFR-EFFR利差", "FRED SOFR - DFF", "5Y", series.get("sofr_effr_spread", []), 1, 1, "bp"),
        ("SOFR-OBFR回购摩擦", "FRED SOFR - OBFR", "5Y", series.get("collateral_repo_friction", []), 1, 1, "bp"),
        ("商票-TBill利差", "FRED DCPF3M - DTB3", "5Y", series.get("cp_tbill_spread", []), 1, 1, "bp"),
        ("资金分裂度(21D)", "SOFR corridor spread dispersion", "5Y", series.get("funding_fragmentation", []), 1, 2, ""),
        ("真实利率水平", "60% DFII5 + 40% DFII10", "5Y", series.get("real_rate_level", []), 1, 2, "%"),
        ("VIX", "FRED VIXCLS", "5Y", series.get("vix", []), 1, 2, ""),
        ("VIX期限结构", "FRED VIXCLS / VXVCLS", "5Y", series.get("vix_term_structure", []), 1, 2, ""),
        ("HY信用利差", "FRED BAMLH0A0HYM2", "5Y", series.get("hy_oas", []), 1, 2, "%"),
        ("HY-IG利差", "FRED HY OAS - IG OAS", "5Y", series.get("hy_ig_oas_spread", []), 1, 1, "bp"),
        ("HY信用偏好(HY/UST)", "FRED HY TR 63/126D relative return vs DGS10 duration proxy", "available up to 5Y", series.get("hy_credit_preference", []), 1, 2, ""),
        ("IG信用偏好(IG/UST)", "FRED IG TR 63/126D relative return vs DGS10 duration proxy", "available up to 5Y", series.get("ig_credit_preference", []), 1, 2, ""),
        ("金融条件指数(NFCI)", "FRED NFCI", "5Y", series.get("nfci", []), 1, 2, ""),
        ("银行股相对S&P500", "FRED NASDAQBANK / SP500", "5Y", series.get("regional_bank_vs_market", []), 1, 2, ""),
        ("风险资产/美债代理", "FRED SP500 63/126D relative return vs DGS10 duration proxy", "5Y", series.get("risk_vs_safe", []), 1, 2, ""),
        ("高Beta偏好(NDX/US500)", "FRED NASDAQXNDX / NASDAQNQUS500LCT", "5Y", series.get("high_beta_preference", []), 1, 2, ""),
        ("美元广义指数", "FRED DTWEXBGS", "5Y", series.get("dxy", []), 1, 2, ""),
        ("美元实现波动率", "FRED DTWEXBGS 63D realized vol", "5Y", series.get("dxy_realized_vol", []), 1, 1, "%"),
        ("原油波动偏离", "FRED OVXCLS - rolling median", "5Y", series.get("oil_vol_deviation", []), 1, 1, ""),
        ("天然气", "FRED DHHNGSP", "5Y", series.get("natgas", []), 1, 2, "$"),
    ]
    trends: list[dict[str, Any]] = []
    for name, source, window, points, divisor, digits, unit in specs:
        trend_points = historical_percentile_points(points, value_divisor=divisor, value_digits=digits)
        if trend_points:
            trends.append(percentile_trend_payload(name, source, window, unit, trend_points))
    auction_points = auction_percentile_points(auctions)
    if auction_points:
        trends.append(percentile_trend_payload("拍卖投标倍数", "TreasuryDirect auctioned securities", "available sample", "", auction_points))
    return trends


def percentile_trend_payload(name: str, source: str, window: str, unit: str, points: list[dict[str, Any]]) -> dict[str, Any]:
    latest = points[-1]
    prior = points[-2] if len(points) > 1 else None
    change = latest["percentile"] - prior["percentile"] if prior else None
    return {
        "name": name,
        "source": source,
        "window": window,
        "viewWindow": "3Y",
        "unit": unit,
        "latestPercentile": latest["percentile"],
        "change": change,
        "points": points,
    }


def build_percentile_movers(trends: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for trend in trends:
        change = trend.get("change")
        if not isinstance(change, int) or change == 0:
            continue
        rows.append(
            {
                "name": trend["name"],
                "percentile": trend["latestPercentile"],
                "change": change,
                "direction": "up" if change > 0 else "down",
                "source": trend["source"],
                "window": trend["window"],
            }
        )
    return sorted(rows, key=lambda item: abs(item["change"]), reverse=True)[:limit]


def build_percentile_alerts(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        percentile = item.get("percentile")
        if not isinstance(percentile, int):
            continue
        if 10 < percentile < 90:
            continue
        high = percentile >= 90
        severity = "extreme" if percentile >= 95 or percentile <= 5 else "watch"
        rows.append(
            {
                "name": item["name"],
                "value": item["value"],
                "percentile": percentile,
                "side": "high" if high else "low",
                "severity": severity,
                "source": item["source"],
                "message": "处于历史高分位区间" if high else "处于历史低分位区间",
            }
        )
    return rows




def build_auctions(auctions: list[dict[str, object]]) -> list[dict[str, str]]:
    def parse_date(item: dict[str, object]) -> date:
        raw = str(item.get("auctionDate") or "1900-01-01")[:10]
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            return date(1900, 1, 1)

    rows = []
    for item in sorted(auctions, key=parse_date, reverse=True)[:8]:
        security_type = str(item.get("securityType") or "")
        term = str(item.get("securityTerm") or "")
        amount = str(item.get("offeringAmount") or item.get("competitiveAccepted") or "")
        btc = str(item.get("bidToCoverRatio") or "")
        high_yield = str(item.get("highYield") or item.get("averageMedianYield") or item.get("averageMedianDiscountRate") or "")
        rows.append(
            {
                "type": f"{term} {security_type}".strip(),
                "size": money_billions(amount),
                "yield": format_yield(high_yield),
                "btc": btc[:4] if btc else "--",
                "rating": auction_rating(btc),
            }
        )
    return rows or [{"type": "TreasuryDirect", "size": "--", "yield": "--", "btc": "--", "rating": "暂无可解析拍卖"}]


def money_billions(raw: str) -> str:
    try:
        return f"${float(raw) / 1_000_000_000:.0f}B"
    except (TypeError, ValueError):
        return "--"






def money_from_raw_dollars(value: float) -> str:
    if abs(value) >= 1_000_000_000_000:
        return f"${value / 1_000_000_000_000:.2f}T"
    if abs(value) >= 1_000_000_000:
        return f"${value / 1_000_000_000:.0f}B"
    return f"${value / 1_000_000:.0f}M"




def auction_rating(raw_btc: str) -> str:
    try:
        btc = float(raw_btc)
    except (TypeError, ValueError):
        return "待结果"
    if btc >= 2.7:
        return "强劲"
    if btc >= 2.4:
        return "稳健"
    if btc >= 2.2:
        return "偏弱"
    return "疲弱"


def build_fiscal(
    ind: dict[str, Any],
    quarterly_refunding: QuarterlyRefunding | None = None,
    debt_limit_status: DebtLimitStatus | None = None,
) -> list[list[str]]:
    rows: list[list[str]] = []
    if quarterly_refunding:
        next_borrow = quarterly_refunding.next_quarter_borrowing_billions
        current_borrow = quarterly_refunding.current_quarter_borrowing_billions
        qra_value = f"{quarterly_refunding.quarter} · 下季借款 {money_billions_value(next_borrow)}"
        if next_borrow is None:
            qra_value = f"{quarterly_refunding.quarter} · 本季借款 {money_billions_value(current_borrow)}"
        rows.append(["季度再融资 (QRA)", qra_value, f"Policy Statement {quarterly_refunding.release_date.isoformat()}"])
        if current_borrow is not None or quarterly_refunding.current_quarter_cash_balance_billions is not None:
            rows.append(
                [
                    "本季借款 / 现金余额",
                    f"{money_billions_value(current_borrow)} / {money_billions_value(quarterly_refunding.current_quarter_cash_balance_billions)}",
                    "Treasury financing estimates",
                ]
            )
        if quarterly_refunding.buyback_total_billions is not None:
            rows.append(["Buybacks", f"up to {money_billions_value(quarterly_refunding.buyback_total_billions)}", "QRA tentative schedule"])
    if debt_limit_status:
        rows.append(["债务上限空间", money_from_millions(debt_limit_status.headroom_millions), f"Fiscal Data {debt_limit_status.record_date.isoformat()}"])
        rows.append(["受限债务 / 法定上限", f"{money_from_millions(debt_limit_status.debt_subject_to_limit_millions)} / {money_from_millions(debt_limit_status.statutory_limit_millions)}", "DTS Debt Subject to Limit"])
    return rows + [
        ["TGA 余额", f"${ind['tga_trillions']:.2f}T", "FRED WTREGEN"],
        ["10Y-2Y", f"{ind['s2s10']:.0f}bp", "曲线形态"],
        ["5s30s", f"{ind['s5s30']:.0f}bp", "长端供给压力代理"],
        ["10Y月变动", f"{ind['ten_year_m1_change_bp']:+.0f}bp", "长端动量"],
    ]


def build_positioning(
    *,
    cftc_positions: list[CftcTreasuryPosition],
    tic_holdings: TicHoldings | None,
    primary_dealer_stats: PrimaryDealerStats | None,
) -> dict[str, list[list[str]]]:
    if cftc_positions:
        cftc_rows = [
            [
                f"CFTC · {item.market}",
                f"杠杆基金净{direction_word(item.leveraged_net)} {compact_int(abs(item.leveraged_net))}张 ({item.leveraged_net_pct_oi:+.1f}% OI)",
                f"资管净{direction_word(item.asset_manager_net)} {compact_int(abs(item.asset_manager_net))}张 · {item.report_date.isoformat()}",
            ]
            for item in cftc_positions[:5]
        ]
        aggregate_net = sum(item.leveraged_net for item in cftc_positions)
        aggregate_oi = sum(item.open_interest for item in cftc_positions)
        aggregate_pct = (aggregate_net / aggregate_oi) * 100 if aggregate_oi else 0.0
        cftc_rows.append(
            [
                "CFTC · 国债期货合计",
                f"杠杆基金净{direction_word(aggregate_net)} {compact_int(abs(aggregate_net))}张 ({aggregate_pct:+.1f}% OI)",
                "周频COT financial futures,按最新报告日聚合",
            ]
        )
    else:
        cftc_rows = [
            ["CFTC 期货持仓", "待接COT周频文件", "未伪装为实时"],
            ["基差交易", "需经纪商/监管报告补充", "风险提示保留"],
        ]

    if tic_holdings:
        tic_rows = [
            [holding.country, money_trillions_from_billions(holding.value_billions), change_text(holding.monthly_change_billions)]
            for holding in tic_holdings.holdings[:5]
        ]
        if tic_holdings.total:
            tic_rows.append(
                [
                    "全球外资总持仓",
                    money_trillions_from_billions(tic_holdings.total.value_billions),
                    change_text(tic_holdings.total.monthly_change_billions),
                ]
            )
        if tic_holdings.official:
            tic_rows.append(
                [
                    "官方部门持仓",
                    money_trillions_from_billions(tic_holdings.official.value_billions),
                    change_text(tic_holdings.official.monthly_change_billions),
                ]
            )
    else:
        tic_rows = [
            ["TIC 海外持仓", "待接月频CSV/TXT", "滞后约六周"],
            ["全球外资总持仓", "--", "等待低频管线"],
        ]

    if primary_dealer_stats:
        dealer_rows = primary_dealer_rows(primary_dealer_stats)
    else:
        dealer_rows = [
            ["Primary dealers", "待接NY Fed周频API", "未伪装为实时"],
            ["UST repo / fails", "--", "等待Primary Dealer Statistics"],
        ]
    return {"cftc": cftc_rows, "tic": tic_rows, "dealers": dealer_rows}


def primary_dealer_rows(stats: PrimaryDealerStats) -> list[list[str]]:
    labels = [
        ("PDPOSGST-TOT", "Primary dealers · UST ex-TIPS", "净持仓"),
        ("PDGSWOEXTTOT", "Primary dealers · UST交易量", "周成交额"),
        ("PDSORA-UTSETTOT", "Primary dealers · UST repo", "融资余额"),
        ("PDSIOSB-UTSETTOT", "Primary dealers · UST borrowed", "借券/融资"),
        ("PDSOOS-UTSETTOT", "Primary dealers · UST lent", "出借证券"),
        ("PDSIRRA-UTSETTOT", "Primary dealers · UST reverse repo", "逆回购余额"),
    ]
    rows: list[list[str]] = []
    for key, label, note in labels:
        value = stats.metrics_millions.get(key)
        if value is None:
            continue
        rows.append([label, money_from_millions(value), f"{note} · {stats.as_of.isoformat()}"])
    return rows or [["Primary dealers", "本期关键指标未披露", stats.as_of.isoformat()]]


def format_optional_market_price(value: Any) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "--"
    if not math.isfinite(numeric) or numeric <= 0:
        return "--"
    return f"${numeric:.2f}"


def build_cross_market(ind: dict[str, Any]) -> dict[str, Any]:
    return {
        "yields": [
            ["美国 UST", rounded(ind["ten_year"])],
            ["德国 Bund", rounded(ind["bund_10y"])],
            ["英国 Gilt", rounded(ind["gilt_10y"])],
            ["日本 JGB", rounded(ind["jgb_10y"])],
        ],
        "risk": [
            ["标普 500", f"{ind['sp500']:.2f}", f"最新日变动 {ind['sp500_change_pct']:+.2f}%"],
            ["VIX", f"{ind['vix']:.2f}", "FRED VIXCLS"],
            ["美元广义指数", f"{ind['dxy']:.2f}", "FRED DTWEXBGS"],
            ["IG / HY 信用利差", f"{ind['ig_oas']:.2f}% / {ind['hy_oas']:.2f}%", "ICE BofA OAS"],
        ],
        "inflation": [
            ["CPI通胀", f"{ind['cpi_yoy']:.1f}%", "FRED CPIAUCSL YoY"],
            ["PCE通胀", f"{ind['pce_yoy']:.1f}%", "FRED PCEPI YoY"],
            ["核心PCE", f"{ind['core_pce_yoy']:.1f}%", "FRED PCEPILFE YoY"],
            ["达拉斯联储Trimmed Mean PCE", f"{ind['trimmed_mean_pce_yoy']:.1f}%", "FRED PCETRIM12M159SFRBDAL"],
            ["10年盈亏平衡通胀", f"{ind['breakeven_10y']:.2f}%", "FRED T10YIE"],
            ["10年实际利率", f"{ind['real_10y']:.2f}%", "FRED DFII10"],
            ["WTI 原油", f"${ind['wti']:.2f}", "FRED DCOILWTICO"],
            ["黄金现货", format_optional_market_price(ind.get("gold_spot")), "Stooq XAUUSD"],
            ["原油/黄金波动", f"OVX {ind['oil_vol']:.2f} / GVZ {ind['gold_vol']:.2f}", "CBOE volatility indexes via FRED"],
        ],
        "historySeries": build_cross_market_history_series(),
    }


def build_cross_market_history_series() -> list[dict[str, Any]]:
    return [
        {
            "id": "global",
            "label": "全球利率",
            "en": "Global Rates",
            "series": [
                history_series_target("美国10Y", "curve_yield", "10Y收益率", "10Y", "%", "U.S. Treasury yield curve XML"),
                history_series_target("德国10Y", "global_yield", "德国10Y", "IRLTLT01DEM156N", "%", "FRED IRLTLT01DEM156N"),
                history_series_target("英国10Y", "global_yield", "英国10Y", "IRLTLT01GBM156N", "%", "FRED IRLTLT01GBM156N"),
                history_series_target("日本10Y", "global_yield", "日本10Y", "IRLTLT01JPM156N", "%", "FRED IRLTLT01JPM156N"),
            ],
        },
        {
            "id": "risk",
            "label": "风险与美元",
            "en": "Risk & USD",
            "series": [
                history_series_target("S&P 500", "risk", "S&P 500", "SP500", "index", "FRED SP500"),
                history_series_target("VIX", "risk", "VIX", "VIXCLS", "index", "FRED VIXCLS"),
                history_series_target("VIX期限结构", "risk", "VIX期限结构", "vix_term_structure", "", "FRED VIXCLS / VXVCLS"),
                history_series_target("美元广义指数", "fx", "美元广义指数", "DTWEXBGS", "index", "FRED DTWEXBGS"),
                history_series_target("HY信用利差", "credit", "HY信用利差", "BAMLH0A0HYM2", "%", "FRED BAMLH0A0HYM2"),
                history_series_target("IG信用利差", "credit", "IG信用利差", "BAMLC0A0CM", "%", "FRED BAMLC0A0CM"),
            ],
        },
        {
            "id": "inflation",
            "label": "通胀与商品",
            "en": "Inflation & Commodities",
            "series": [
                history_series_target("CPI指数", "macro", "CPI指数", "CPIAUCSL", "index", "FRED CPIAUCSL"),
                history_series_target("PCE价格指数", "macro", "PCE价格指数", "PCEPI", "index", "FRED PCEPI"),
                history_series_target("核心PCE价格指数", "macro", "核心PCE价格指数", "PCEPILFE", "index", "FRED PCEPILFE"),
                history_series_target("达拉斯Trimmed Mean PCE", "inflation", "达拉斯联储Trimmed Mean PCE", "PCETRIM12M159SFRBDAL", "%YoY", "FRED PCETRIM12M159SFRBDAL"),
                history_series_target("10Y盈亏平衡通胀", "inflation", "10Y盈亏平衡通胀", "T10YIE", "%", "FRED T10YIE"),
                history_series_target("10Y实际利率", "real_rate", "10Y实际利率", "DFII10", "%", "FRED DFII10"),
                history_series_target("WTI原油", "commodity", "WTI原油", "DCOILWTICO", "$/bbl", "FRED DCOILWTICO"),
                history_series_target("OVX原油波动率", "volatility", "OVX原油波动率", "OVXCLS", "index", "FRED OVXCLS"),
                history_series_target("GVZ黄金波动率", "volatility", "GVZ黄金波动率", "GVZCLS", "index", "FRED GVZCLS"),
            ],
        },
    ]


def history_series_target(display_name: str, category: str, name: str, series_label: str, unit: str, source: str) -> dict[str, str]:
    return {
        "displayName": display_name,
        "category": category,
        "name": name,
        "label": series_label,
        "unit": unit,
        "source": source,
    }


def build_events(
    as_of: date,
    *,
    calendar_events: list[CalendarEvent],
    announced_auctions: list[dict[str, object]],
    quarterly_refunding: QuarterlyRefunding | None = None,
) -> list[list[str]]:
    rows: list[tuple[date, str, str]] = []
    for event in calendar_events:
        if event.date >= as_of:
            rows.append((event.date, event.title, event.importance))
    if quarterly_refunding:
        if quarterly_refunding.next_financing_estimates_date and quarterly_refunding.next_financing_estimates_date >= as_of:
            rows.append((quarterly_refunding.next_financing_estimates_date, "Treasury borrowing estimates / QRA pre-release", "中"))
        if quarterly_refunding.next_policy_statement_date and quarterly_refunding.next_policy_statement_date >= as_of:
            rows.append((quarterly_refunding.next_policy_statement_date, "Treasury quarterly refunding statement", "高"))
    for auction in announced_auctions:
        auction_date = parse_dashboard_date(auction.get("auctionDate"))
        if auction_date is None or auction_date < as_of:
            continue
        security_term = str(auction.get("securityTerm") or auction.get("term") or "").strip()
        security_type = str(auction.get("securityType") or auction.get("type") or "").strip()
        amount = parse_number(auction.get("offeringAmount"))
        title = "Treasury auction"
        detail = " ".join(part for part in (security_term, security_type) if part)
        if detail:
            title = f"{title} · {detail}"
        if amount is not None:
            title = f"{title} · {money_from_raw_dollars(amount)}"
        rows.append((auction_date, title, "中"))
    if not rows:
        rows = [(as_of, "每日收益率曲线/公开源更新", "中"), (as_of + timedelta(days=1), "检查FRED与Treasury最新发布", "中")]
    rows.sort(key=lambda item: (item[0], importance_rank(item[2]), item[1]))
    rows = select_event_rows(rows, limit=10)
    return [[event_date.isoformat(), title, importance] for event_date, title, importance in rows]


def is_core_event(row: tuple[date, str, str]) -> bool:
    title = row[1]
    return (
        title.startswith("FOMC ")
        or title.startswith("BLS ")
        or title.startswith("BEA ")
        or "QRA" in title
        or "quarterly refunding" in title
        or "borrowing estimates" in title
    )


def should_force_late_event(row: tuple[date, str, str], selected: list[tuple[date, str, str]]) -> bool:
    title = row[1]
    if is_qra_event_title(title):
        return True
    if title.startswith("FOMC "):
        return sum(1 for selected_row in selected if selected_row[1].startswith("FOMC ")) < 2
    if title.startswith("BLS "):
        return sum(1 for selected_row in selected if selected_row[1].startswith("BLS ")) < 3
    if title.startswith("BEA "):
        return sum(1 for selected_row in selected if selected_row[1].startswith("BEA ")) < 2
    return False


def is_qra_event_title(title: str) -> bool:
    return "QRA" in title or "quarterly refunding" in title or "borrowing estimates" in title


def select_event_rows(rows: list[tuple[date, str, str]], limit: int) -> list[tuple[date, str, str]]:
    selected = list(rows[:limit])
    for row in rows[limit:]:
        if not should_force_late_event(row, selected) or row in selected:
            continue
        replace_candidates = [index for index, selected_row in enumerate(selected) if not is_core_event(selected_row)]
        if not replace_candidates and is_qra_event_title(row[1]):
            replace_candidates = [
                index
                for index, selected_row in enumerate(selected)
                if not selected_row[1].startswith("FOMC ") and not is_qra_event_title(selected_row[1])
            ]
        if not replace_candidates:
            continue
        replace_index = max(replace_candidates, key=lambda index: (selected[index][0], selected[index][1]))
        selected[replace_index] = row
    selected.sort(key=lambda item: (item[0], importance_rank(item[2]), item[1]))
    return selected


def build_news(
    as_of: date,
    ind: dict[str, Any],
    quarterly_refunding: QuarterlyRefunding | None = None,
    official_news: list[NewsItem] | None = None,
) -> list[list[str]]:
    rows: list[list[str]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in sorted(official_news or [], key=lambda entry: (entry.date, entry.source, entry.title), reverse=True):
        row = [item.date.strftime("%m/%d"), item.source, item.title]
        key = (row[0], row[1], row[2])
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
        if len(rows) >= 5:
            return rows

    fallback_rows = [
        [as_of.strftime("%m/%d"), "U.S. Treasury", f"10Y {ind['ten_year']:.2f}%, 30Y {ind['thirty_year']:.2f}%"],
        [as_of.strftime("%m/%d"), "FRED", f"10Y TIPS {ind['real_10y']:.2f}%, 10Y BEI {ind['breakeven_10y']:.2f}%"],
    ]
    if quarterly_refunding:
        summary = qra_supply_note(quarterly_refunding)
        fallback_rows.append([quarterly_refunding.release_date.strftime("%m/%d"), "Treasury QRA", summary[:180]])
    for row in fallback_rows:
        key = (row[0], row[1], row[2])
        if key in seen:
            continue
        rows.append(row)
        if len(rows) >= 5:
            break
    return rows






def importance_rank(value: str) -> int:
    return {"高": 0, "中": 1, "低": 2}.get(value, 3)


def change_text(value: float | None) -> str:
    if value is None:
        return "月变动暂无"
    return f"月变动 {value:+.1f}B"


def load_content_overrides(path: Path = DEFAULT_OVERRIDES_PATH) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def apply_content_overrides(dashboard: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    if not overrides:
        return dashboard
    updated = copy.deepcopy(dashboard)
    if isinstance(overrides.get("ideas"), list):
        updated["ideas"] = overrides["ideas"]
    if isinstance(overrides.get("events"), list):
        updated["events"] = overrides["events"]
    if isinstance(overrides.get("news"), list):
        updated["news"] = overrides["news"]
    group_weights = overrides.get("groupWeights")
    if isinstance(group_weights, dict):
        for group in updated.get("groups", []):
            if group.get("id") in group_weights:
                group["weight"] = group_weights[group["id"]]
    factor_overrides = overrides.get("factorOverrides")
    if isinstance(factor_overrides, dict):
        for group in updated.get("groups", []):
            group_override = factor_overrides.get(group.get("id"))
            if not isinstance(group_override, dict):
                continue
            for factor in group.get("factors", []):
                patch = group_override.get(factor.get("n"))
                if isinstance(patch, dict):
                    factor.update(patch)
    return updated


def rounded(value: float) -> float:
    return round(value, 2)
