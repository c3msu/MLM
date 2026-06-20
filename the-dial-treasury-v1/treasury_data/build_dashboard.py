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
from .fetch import *  # noqa: F401,F403  (facade re-export, Phase 1 refactor)
from .indicators import *  # noqa: F401,F403  (facade re-export, Phase 1 refactor)
from .scoring_bhadial import *  # noqa: F401,F403  (facade re-export, Phase 1 refactor)
from .scoring_spy_warning import *  # noqa: F401,F403  (facade re-export, Phase 1 refactor)
from .scoring_equity import *  # noqa: F401,F403  (facade re-export, Phase 1 refactor)
from .scoring_lppl import *  # noqa: F401,F403  (facade re-export, Phase 1 refactor)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OVERRIDES_PATH = PROJECT_ROOT / "content" / "overrides.json"
REMOTE_COMPATIBILITY_SOURCE = "us-treasury-bonds-monitor-luffa"
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

# 实际计入综合分的因子本地名(唯一真相): 去冗余后=22。覆盖率面板的 inScorecard 据此判定,
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
GLOBAL_LPPL_HISTORY_STEP = 1
GLOBAL_LPPL_ALERT_THRESHOLD = 65
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
        curve_records = fetch_treasury_yield_curves()
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
        fred = fetch_fred_series_bulk(FRED_SERIES)
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
        auctions = fetch_treasury_auctions()
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
        announced_auctions = fetch_announced_auctions()
        source_status.append({"name": "TreasuryDirect announced securities", "status": "ok", "latest": str(len(announced_auctions))})
    except Exception as exc:  # noqa: BLE001
        source_status.append({"name": "TreasuryDirect announced securities", "status": "warning", "latest": str(exc)})

    try:
        calendar_events = fetch_fomc_calendar_events()
        latest = max((event.date for event in calendar_events), default=None)
        source_status.append({"name": "Federal Reserve FOMC calendar", "status": "ok", "latest": latest.isoformat() if latest else "none"})
    except Exception as exc:  # noqa: BLE001
        source_status.append({"name": "Federal Reserve FOMC calendar", "status": "error", "latest": str(exc)})

    try:
        macro_events = fetch_fred_macro_release_events()
        calendar_events.extend(macro_events)
        latest = max((event.date for event in macro_events), default=None)
        source_status.append({"name": "FRED economic release calendar", "status": "ok", "latest": latest.isoformat() if latest else "none"})
    except Exception as exc:  # noqa: BLE001
        source_status.append({"name": "FRED economic release calendar", "status": "error", "latest": str(exc)})

    try:
        bea_events = fetch_bea_release_events()
        calendar_events.extend(bea_events)
        latest = max((event.date for event in bea_events), default=None)
        source_status.append({"name": "BEA release schedule", "status": "ok", "latest": latest.isoformat() if latest else "none"})
    except Exception as exc:  # noqa: BLE001
        source_status.append({"name": "BEA release schedule", "status": "error", "latest": str(exc)})

    try:
        fomc_projection = fetch_fomc_projection()
        source_status.append({"name": "Federal Reserve SEP projections", "status": "ok", "latest": fomc_projection.release_date.isoformat()})
    except Exception as exc:  # noqa: BLE001
        source_status.append({"name": "Federal Reserve SEP projections", "status": "warning", "latest": str(exc)})

    try:
        acm = fetch_acm_term_premium()
        source_status.append({"name": "NY Fed ACM term premium", "status": "ok", "latest": acm.date.isoformat()})
    except Exception as exc:  # noqa: BLE001
        source_status.append({"name": "NY Fed ACM term premium", "status": "error", "latest": str(exc)})

    try:
        cftc_positions = fetch_cftc_treasury_positions()
        latest = cftc_positions[0].report_date.isoformat() if cftc_positions else "none"
        source_status.append({"name": "CFTC financial futures COT", "status": "ok", "latest": latest})
    except Exception as exc:  # noqa: BLE001
        source_status.append({"name": "CFTC financial futures COT", "status": "error", "latest": str(exc)})

    try:
        tic_holdings = fetch_tic_major_holders()
        source_status.append({"name": "Treasury TIC major foreign holders", "status": "ok", "latest": tic_holdings.period})
    except Exception as exc:  # noqa: BLE001
        source_status.append({"name": "Treasury TIC major foreign holders", "status": "error", "latest": str(exc)})

    try:
        primary_dealer_stats = fetch_primary_dealer_stats()
        source_status.append({"name": "NY Fed primary dealer statistics", "status": "ok", "latest": primary_dealer_stats.as_of.isoformat()})
    except Exception as exc:  # noqa: BLE001
        source_status.append({"name": "NY Fed primary dealer statistics", "status": "error", "latest": str(exc)})

    try:
        quarterly_refunding = fetch_quarterly_refunding()
        source_status.append({"name": "U.S. Treasury quarterly refunding documents", "status": "ok", "latest": quarterly_refunding.release_date.isoformat()})
    except Exception as exc:  # noqa: BLE001
        source_status.append({"name": "U.S. Treasury quarterly refunding documents", "status": "error", "latest": str(exc)})

    try:
        debt_limit_status = fetch_debt_limit_status()
        source_status.append({"name": "Treasury Fiscal Data debt subject to limit", "status": "ok", "latest": debt_limit_status.record_date.isoformat()})
    except Exception as exc:  # noqa: BLE001
        source_status.append({"name": "Treasury Fiscal Data debt subject to limit", "status": "error", "latest": str(exc)})

    try:
        fed_funds_futures = fetch_fed_funds_futures_quote()
        source_status.append({"name": "Stooq 30-Day Fed Funds futures ZQ.F", "status": "ok", "latest": fed_funds_futures.date.isoformat()})
    except Exception as exc:  # noqa: BLE001
        source_status.append({"name": "Stooq 30-Day Fed Funds futures ZQ.F", "status": "warning", "latest": str(exc)})

    try:
        gold_quote = fetch_gold_spot_quote()
        source_status.append({"name": "Stooq gold spot XAUUSD", "status": "ok", "latest": gold_quote.date.isoformat()})
    except Exception as exc:  # noqa: BLE001
        source_status.append({"name": "Stooq gold spot XAUUSD", "status": "warning", "latest": str(exc)})

    equity_end = datetime.now(timezone.utc).date()
    equity_start = equity_end - timedelta(days=365 * 3 + 10)
    for symbol, asset_class in EQUITY_RISK_SYMBOLS.items():
        try:
            bars, status = fetch_daily_bars_with_stooq_fallback(
                symbol,
                start=equity_start,
                end=equity_end,
                asset_class=asset_class,
                timeout=14,
                limit=900,
            )
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
                bars, status = fetch_daily_bars_with_stooq_fallback(
                    str(spec["sourceSymbol"]),
                    start=equity_start,
                    end=equity_end,
                    asset_class=str(spec.get("assetClass") or "etf"),
                    timeout=14,
                    limit=900,
                    fallback_symbol=str(spec.get("fallbackSymbol") or ""),
                    output_symbol=symbol,
                )
                global_lppl_market_bars[symbol] = bars
                source_status.append({"name": f"Global LPPL {symbol} OHLCV", **status})
            except Exception as exc:  # noqa: BLE001
                source_status.append({"name": f"Global LPPL {symbol} OHLCV", "status": "warning", "latest": str(exc)})
            continue
        if spec.get("source") != "stooq":
            continue
        try:
            bars = fetch_stooq_daily_bars(str(spec["sourceSymbol"]), start=equity_start, end=equity_end, timeout=14)
            global_lppl_market_bars[symbol] = [MarketDailyBar(symbol=symbol, date=bar.date, open=bar.open, high=bar.high, low=bar.low, close=bar.close, volume=bar.volume, source=bar.source) for bar in bars]
            latest = bars[-1].date.isoformat() if bars else "none"
            source_status.append({"name": f"Global LPPL {symbol} OHLCV", "status": "ok", "latest": latest})
        except Exception as exc:  # noqa: BLE001
            source_status.append({"name": f"Global LPPL {symbol} OHLCV", "status": "warning", "latest": str(exc)})

    try:
        option_open_interest = fetch_cboe_option_open_interest("SPY")
        source_status.append({"name": "Cboe SPY option open interest", "status": "ok", "latest": option_open_interest.as_of.isoformat()})
    except Exception as exc:  # noqa: BLE001
        source_status.append({"name": "Cboe SPY option open interest", "status": "warning", "latest": str(exc)})

    try:
        fed_news = fetch_federal_reserve_press_releases()
        official_news.extend(fed_news)
        latest = max((item.date for item in fed_news), default=None)
        source_status.append({"name": "Federal Reserve press release RSS", "status": "ok", "latest": latest.isoformat() if latest else "none"})
    except Exception as exc:  # noqa: BLE001
        source_status.append({"name": "Federal Reserve press release RSS", "status": "warning", "latest": str(exc)})

    try:
        treasury_news = fetch_treasury_press_releases()
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
        benchmark_score = fetch_bhadial_public_score()
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
    )
    policy = build_policy(indicators)
    macro_liquidity = build_macro_liquidity_score(indicators)
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
    portfolio_overview = build_portfolio_overview(
        spy_early_warning=spy_early_warning,
        equity_short_term_risk=equity_short_term_risk,
        global_lppl_risk=global_lppl_risk,
        macro_liquidity=macro_liquidity,
        signal_validation=signal_validation,
        regional_monitor=regional_monitor,
    )
    bhadial_coverage = build_bhadial_coverage(groups)
    source_status = [
        {"name": "Fed path", "status": "modeled", "latest": "public futures proxy + curve/macro model" if fed_funds_futures else "curve/macro proxy"},
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
        "generatedAt": generated_at.replace(microsecond=0).isoformat(),
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
                "Fed path probabilities are model estimates derived from public Fed Funds futures proxy, real curve, and macro pressure, not CME FedWatch official probabilities.",
                "Fed and Treasury official public news headlines are fetched when available; broader full-text market news remains curated because reliable redistribution usually requires licensed feeds.",
                "Remote-site narrative compatibility factors are preserved as explicit real/proxy/modeled/manual sourceMode rows rather than disguised as fully live market feeds.",
                "Bhadial-style module factors are filled with real public or derived-public series where possible; unsupported ETF-relative factors are not synthesized from unrelated data.",
            ],
        },
        "sourceStatus": source_status,
        "conclusionSourceQuality": dict(CONCLUSION_SOURCE_QUALITY),
        "curve": curve,
        "decomposition": build_decomposition(indicators, acm=acm, fomc_projection=fomc_projection),
        "fedPath": build_fed_path(indicators),
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
    return apply_content_overrides(dashboard, overrides or {})


def build_decomposition(ind: dict[str, Any], acm: AcmRecord | None = None, fomc_projection: FomcProjection | None = None) -> dict[str, Any]:
    real_short = ind["dff"] - max(ind["breakeven_10y"], 0)
    if acm is not None:
        term_premium_value = f"{acm.term_premium_10y:+.2f}%"
        term_premium_note = f"NY Fed ACM 10Y期限溢价,最新日期 {acm.date.isoformat()}。"
        term_premium_driver = "NY Fed ACM"
    else:
        term_premium_value = f"{max(ind['ten_year'] - ind['dff'], -2):+.2f}%"
        term_premium_note = "ACM拉取失败时用10Y相对短端补偿近似。"
        term_premium_driver = "模型估算"
    return {
        "components": [
            {"index": "01", "name": "短端实际利率", "en": "E[real short rate]", "value": f"~{real_short:.1f}%", "note": "由有效联邦基金利率减去10Y盈亏平衡通胀近似。", "driver": "FRED DFF + T10YIE"},
            {"index": "02", "name": "短端通胀预期", "en": "E[π short]", "value": f"~{ind['breakeven_10y']:.2f}%", "note": "用10Y盈亏平衡通胀作为公开代理。", "driver": "FRED T10YIE"},
            {"index": "03", "name": "实际期限溢价", "en": "Real term premium", "value": term_premium_value, "note": term_premium_note, "driver": term_premium_driver},
            {"index": "04", "name": "通胀风险溢价", "en": "Inflation risk prem.", "value": f"{max(ind['breakeven_10y'] - 2.3, 0):+.2f}%", "note": "以盈亏平衡通胀相对2.3%锚的偏离近似。", "driver": "模型估算"},
        ],
        "attribution": [
            {"window": "1 周", "total": round(ind["ten_year_w1_change_bp"]), "real": round(ind["ten_year_w1_change_bp"] * 0.65), "inflation": round(ind["ten_year_w1_change_bp"] * 0.35), "term": 0, "risk": 0, "driver": "真实利率+通胀"},
            {"window": "1 月", "total": round(ind["ten_year_m1_change_bp"]), "real": round(ind["ten_year_m1_change_bp"] * 0.65), "inflation": round(ind["ten_year_m1_change_bp"] * 0.35), "term": 0, "risk": 0, "driver": "真实利率+通胀"},
        ],
        "frameworkNote": (
            "Clarida框架:长期名义利率 = 预期短端真实利率 + 预期短端通胀 + "
            "实际期限溢价 + 通胀风险溢价。核心用途不是机械相加,而是把收益率变化翻译成叙事变化。"
        ),
        "regimeRead": decomposition_regime_read(ind, term_premium_value),
        "policyRead": policy_path_read(ind, fomc_projection=fomc_projection),
        "marketMeasures": {
            "dff": f"{ind['dff']:.2f}%",
            "real10y": f"{ind['real_10y']:.2f}%",
            "breakeven10y": f"{ind['breakeven_10y']:.2f}%",
            "termPremium10y": term_premium_value,
        },
        "sources": build_expectation_sources(ind, fomc_projection=fomc_projection),
    }


def decomposition_regime_read(ind: dict[str, Any], term_premium_value: str) -> str:
    monthly_move = ind["ten_year_m1_change_bp"]
    direction = "上行" if monthly_move >= 0 else "下行"
    hard_combo = ind["real_10y"] >= 2.0 and ind["breakeven_10y"] >= 2.35
    combo_text = "真实利率和通胀补偿同时偏高,这是名义久期最难缠的组合" if hard_combo else "当前更多是单一驱动,需要观察真实利率与通胀补偿是否共振"
    return (
        f"10Y过去一个月{direction}{monthly_move:+.0f}bp,真实利率{ind['real_10y']:.2f}%、"
        f"通胀补偿{ind['breakeven_10y']:.2f}%、期限溢价{term_premium_value}共同解释长端定价。"
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
    inflation_pressure = max(ind["cpi_yoy"], ind["pce_yoy"], ind["core_pce_yoy"], ind["trimmed_mean_pce_yoy"])
    path_bias = "加息尾部升温" if ind["two_year_m1_change_bp"] > 10 or inflation_pressure > 3 else "持平为主"
    futures_rate = ind.get("fed_funds_futures_implied_rate")
    if futures_rate is not None:
        futures_value = f"{ind['fed_funds_futures_symbol']} implied {futures_rate:.2f}%"
        futures_note = (
            f"Stooq public quote dated {ind['fed_funds_futures_date']}; futures price "
            f"{ind['fed_funds_futures_close']:.2f} implies average fed-funds rate near {futures_rate:.2f}%. "
            "Meeting probabilities remain model-converted, not official CME FedWatch."
        )
        futures_name = "30-Day Fed Funds futures · public proxy"
    else:
        futures_value = path_bias
        futures_note = "由2Y再定价、CPI/PCE通胀跟踪与曲线压力生成,不是CME FedWatch官方概率。"
        futures_name = "公开曲线代理 · Fed path model"
    survey_anchor = "公开调查待接入"
    return [
        {"name": "美联储 SEP · 点阵图", "value": sep_value, "note": sep_note},
        {"name": futures_name, "value": futures_value, "note": futures_note},
        {"name": "调查 SPF / Blue Chip", "value": survey_anchor, "note": "调查预期通常低频且滞后;当前本地版保留为授权/后续公共源接入边界。"},
    ]


def build_fed_path(ind: dict[str, Any]) -> list[dict[str, int | str]]:
    inflation_pressure = max(ind["cpi_yoy"], ind["pce_yoy"], ind["core_pce_yoy"], ind["trimmed_mean_pce_yoy"])
    pressure = max(0, min(100, int(40 + ind["two_year_m1_change_bp"] * 0.9 + (inflation_pressure - 3.0) * 12)))
    if ind.get("fed_funds_futures_implied_rate") is not None:
        futures_gap_bp = (ind["fed_funds_futures_implied_rate"] - ind["dff"]) * 100
        pressure = max(0, min(100, int(pressure + futures_gap_bp * 0.35)))
    meetings = ["6/17", "7/29", "9/16", "10/28", "12/9"]
    path = []
    for idx, meeting in enumerate(meetings):
        hike = max(0, min(90, int(pressure * idx / 4)))
        cut = max(1, int(8 - pressure / 18 - idx))
        hold = max(0, 100 - hike - cut)
        path.append({"m": meeting, "hike": hike, "hold": hold, "cut": cut})
    return path


def inflation_tracking_score(ind: dict[str, Any]) -> int:
    broad = max(ind["cpi_yoy"], ind["pce_yoy"])
    core = max(ind["core_pce_yoy"], ind["trimmed_mean_pce_yoy"])
    if broad >= 3.5 or core >= 3.0:
        return -2
    if broad >= 2.8 or core >= 2.5:
        return -1
    if broad <= 2.2 and core <= 2.2:
        return 1
    return 0


def build_groups(
    ind: dict[str, Any],
    *,
    auctions: list[dict[str, object]],
    cftc_positions: list[CftcTreasuryPosition],
    tic_holdings: TicHoldings | None,
    acm: AcmRecord | None,
    primary_dealer_stats: PrimaryDealerStats | None,
    quarterly_refunding: QuarterlyRefunding | None,
    debt_limit_status: DebtLimitStatus | None,
    official_news: list[NewsItem],
) -> list[dict[str, Any]]:
    inflation_score = inflation_tracking_score(ind)
    ppi_score = -2 if ind["ppi_yoy"] >= 5.0 else -1 if ind["ppi_yoy"] >= 3.0 else 0
    two_year_score = -2 if ind["two_year_m1_change_bp"] >= 30 else -1 if ind["two_year_m1_change_bp"] >= 10 else 0
    sofr_spread_pct = ind["percentiles"].get("sofr_effr_spread")
    sofr_spread_score = -1 if sofr_spread_pct is not None and sofr_spread_pct >= 80 else 0
    bank_reserves_pct = ind["percentiles"].get("bank_reserves")
    bank_reserves_score = -1 if bank_reserves_pct is not None and bank_reserves_pct <= 20 else 1 if bank_reserves_pct is not None and bank_reserves_pct >= 60 else 0
    net_liquidity_pct = ind["percentiles"].get("net_liquidity")
    net_liquidity_score = -1 if net_liquidity_pct is not None and net_liquidity_pct <= 20 else 1 if net_liquidity_pct is not None and net_liquidity_pct >= 60 else 0
    net_liquidity_momentum_pct = ind["percentiles"].get("net_liquidity_momentum")
    net_liquidity_momentum_score = -1 if ind["net_liquidity_m1_change_trillions"] < -0.05 else 1 if ind["net_liquidity_m1_change_trillions"] > 0.05 else 0
    net_liquidity_13w_pct = ind["percentiles"].get("net_liquidity_13w_momentum")
    net_liquidity_13w_score = -1 if ind["net_liquidity_13w_change_trillions"] < -0.15 else 1 if ind["net_liquidity_13w_change_trillions"] > 0.15 else 0
    tga_deviation_pct = ind["percentiles"].get("tga_deviation")
    tga_deviation_score = -1 if ind["tga_deviation_trillions"] > 0.15 or (tga_deviation_pct is not None and tga_deviation_pct >= 80) else 1 if ind["tga_deviation_trillions"] < -0.15 else 0
    onrrp_buffer_risk_pct = ind["percentiles"].get("onrrp_buffer_risk")
    onrrp_buffer_risk_score = -2 if ind["onrrp_buffer_risk"] >= 0.75 else -1 if ind["onrrp_buffer_risk"] >= 0.35 else 0
    sofr_obfr_pct = ind["percentiles"].get("collateral_repo_friction")
    sofr_obfr_score = high_pressure_score(sofr_obfr_pct)
    sofr_iorb_pct = ind["percentiles"].get("corridor_sofr_iorb")
    sofr_iorb_score = high_pressure_score(sofr_iorb_pct)
    sofr_rrp_pct = ind["percentiles"].get("corridor_sofr_rrp")
    sofr_rrp_score = high_pressure_score(sofr_rrp_pct)
    effr_iorb_pct = ind["percentiles"].get("effr_iorb_spread")
    effr_iorb_score = high_pressure_score(effr_iorb_pct)
    cp_tbill_pct = ind["percentiles"].get("cp_tbill_spread")
    cp_tbill_score = high_pressure_score(cp_tbill_pct)
    fragmentation_pct = ind["percentiles"].get("funding_fragmentation")
    fragmentation_score = high_pressure_score(fragmentation_pct)
    real_rate_level_pct = ind["percentiles"].get("real_rate_level")
    real_curve_pct = ind["percentiles"].get("real_curve")
    nfci_pct = ind["percentiles"].get("nfci")
    nfci_score = -1 if ind["nfci"] > 0 or (nfci_pct is not None and nfci_pct >= 80) else 1 if ind["nfci"] < -0.5 and (nfci_pct is None or nfci_pct <= 35) else 0
    hy_ig_pct = ind["percentiles"].get("hy_ig_oas_spread")
    hy_ig_score = high_pressure_score(hy_ig_pct)
    vix_term_pct = ind["percentiles"].get("vix_term_structure")
    vix_term_score = -1 if ind["vix_term_structure"] > 1 or (vix_term_pct is not None and vix_term_pct >= 80) else 0
    dxy_vol_pct = ind["percentiles"].get("dxy_realized_vol")
    dxy_vol_score = high_pressure_score(dxy_vol_pct)
    oil_vol_dev_pct = ind["percentiles"].get("oil_vol_deviation")
    oil_vol_dev_score = high_pressure_score(oil_vol_dev_pct)
    natgas_pct = ind["percentiles"].get("natgas")
    natgas_score = high_pressure_score(natgas_pct)
    hy_credit_preference_pct = ind["percentiles"].get("hy_credit_preference")
    hy_credit_preference_score = low_preference_score(hy_credit_preference_pct)
    ig_credit_preference_pct = ind["percentiles"].get("ig_credit_preference")
    ig_credit_preference_score = low_preference_score(ig_credit_preference_pct)
    regional_bank_pct = ind["percentiles"].get("regional_bank_vs_market")
    regional_bank_score = low_preference_score(regional_bank_pct)
    risk_vs_safe_pct = ind["percentiles"].get("risk_vs_safe")
    risk_vs_safe_score = low_preference_score(risk_vs_safe_pct)
    high_beta_pct = ind["percentiles"].get("high_beta_preference")
    high_beta_score = low_preference_score(high_beta_pct)
    auction_signal = auction_demand_signal(auctions)
    cftc_net = sum(item.leveraged_net for item in cftc_positions)
    cftc_score = 1 if cftc_net < -150_000 else -1 if cftc_net > 150_000 else 0
    cftc_tag = f"杠杆基金净{direction_word(cftc_net)} {compact_int(abs(cftc_net))}" if cftc_positions else "待接低频解析"
    tic_change = tic_holdings.total.monthly_change_billions if tic_holdings and tic_holdings.total else None
    tic_score = -1 if tic_change is not None and tic_change < -50 else 1 if tic_change is not None and tic_change > 50 else 0
    tic_tag = f"{tic_holdings.period} 总量 {money_trillions_from_billions(tic_holdings.total.value_billions)}" if tic_holdings and tic_holdings.total else "待接月频解析"
    acm_score = 1 if acm and acm.term_premium_10y > 0.35 else 0
    acm_tag = f"ACM {acm.term_premium_10y:+.2f}%" if acm else f"10Y-EFFR {ind['ten_year'] - ind['dff']:+.2f}%"
    if quarterly_refunding:
        current_borrow = quarterly_refunding.current_quarter_borrowing_billions
        next_borrow = quarterly_refunding.next_quarter_borrowing_billions
        qra_score = -1 if current_borrow is not None and next_borrow is not None and next_borrow > current_borrow else 0
        qra_tag = f"{quarterly_refunding.quarter} · {money_billions_value(next_borrow or current_borrow)}"
        qra_note = qra_supply_note(quarterly_refunding)
    else:
        qra_score = 0
        qra_tag = "待接Treasury QRA"
        qra_note = "官方季度再融资文档不可用时不填入估计值。"
    if debt_limit_status:
        debt_headroom_score = -2 if debt_limit_status.headroom_millions < 500_000 else -1 if debt_limit_status.headroom_millions < 1_000_000 else 0
        debt_headroom_tag = money_from_millions(debt_limit_status.headroom_millions)
        debt_headroom_note = (
            f"Fiscal Data {debt_limit_status.record_date.isoformat()}: statutory limit "
            f"{money_from_millions(debt_limit_status.statutory_limit_millions)}, "
            f"debt subject to limit {money_from_millions(debt_limit_status.debt_subject_to_limit_millions)}."
        )
    else:
        debt_headroom_score = 0
        debt_headroom_tag = "待接Fiscal Data"
        debt_headroom_note = "DTS Debt Subject to Limit不可用时不填入估计值。"
    return [
        {
            "id": "g1",
            "name": "货币政策",
            "en": "Monetary Policy",
            "weight": 25,
            "factors": [
                {"n": "联邦基金目标利率", "tag": ind["target_range"], "v": "限制性", "score": -1, "note": f"有效联邦基金利率 {ind['dff']:.2f}%,仍处限制性区间。"},
                {"n": "2Y 市场政策代理", "tag": f"1月 {ind['two_year_m1_change_bp']:+.0f}bp", "v": "偏鹰" if two_year_score < 0 else "中性", "score": two_year_score, "curve": 1 if two_year_score < 0 else 0, "note": "用2Y收益率月度变化代理政策路径再定价。"},
                fed_path_compatibility_factor(ind),
                chair_transition_compatibility_factor(official_news),
                {"n": "SOFR 融资锚", "tag": f"{ind['sofr']:.2f}%", "v": "高位", "score": -1, "note": "SOFR 仍在限制性区间,压制久期估值。"},
                {
                    "n": "SOFR-EFFR利差",
                    "tag": f"{ind['sofr_effr_spread_bp']:+.0f}bp · {percentile_label(sofr_spread_pct)}",
                    "v": "融资压力" if sofr_spread_score < 0 else "正常",
                    "score": sofr_spread_score,
                    "note": "参考The Dial Funding思路,用SOFR相对EFFR利差的5年历史百分位代理担保融资压力。",
                },
                bhadial_factor(
                    module="Funding",
                    name="SOFR-OBFR回购摩擦",
                    tag=f"{ind['sofr_obfr_spread_bp']:+.0f}bp · {percentile_label(sofr_obfr_pct)}",
                    value="回购偏紧" if sofr_obfr_score < 0 else "正常",
                    score=sofr_obfr_score,
                    source_mode="derived-public",
                    note="Bhadial Funding的Collateral/Repo Friction: SOFR-OBFR,衡量担保回购相对无担保隔夜融资的压力。",
                ),
                bhadial_factor(
                    module="Funding",
                    name="SOFR-IORB走廊摩擦",
                    tag=f"{ind['sofr_iorb_spread_bp']:+.0f}bp · {percentile_label(sofr_iorb_pct)}",
                    value="接近上沿" if sofr_iorb_score < 0 else "正常",
                    score=sofr_iorb_score,
                    source_mode="derived-public",
                    note="Bhadial Funding的Corridor Friction 1: SOFR-IORB,衡量市场担保融资利率相对准备金利率上沿的位置。",
                ),
                bhadial_factor(
                    module="Funding",
                    name="SOFR-ON RRP走廊摩擦",
                    tag=f"{ind['sofr_rrp_award_spread_bp']:+.0f}bp · {percentile_label(sofr_rrp_pct)}",
                    value="高于地板" if sofr_rrp_score < 0 else "正常",
                    score=sofr_rrp_score,
                    source_mode="derived-public",
                    note="Bhadial Funding的Corridor Friction 2: SOFR-ON RRP award,衡量市场利率相对美联储隔夜逆回购利率地板的压力。",
                ),
                bhadial_factor(
                    module="Funding",
                    name="EFFR-IORB利差",
                    tag=f"{ind['effr_iorb_spread_bp']:+.0f}bp · {percentile_label(effr_iorb_pct)}",
                    value="银行资金偏紧" if effr_iorb_score < 0 else "正常",
                    score=effr_iorb_score,
                    source_mode="derived-public",
                    note="Bhadial Funding的EFFR-IORB Spread: 有效联邦基金利率相对准备金利率,观察银行间资金是否接近走廊上沿。",
                ),
                bhadial_factor(
                    module="Funding",
                    name="商票-TBill利差",
                    tag=f"{ind['cp_tbill_spread_bp']:+.0f}bp · {percentile_label(cp_tbill_pct)}",
                    value="短融承压" if cp_tbill_score < 0 else "正常",
                    score=cp_tbill_score,
                    source_mode="derived-public",
                    note="Bhadial Funding的CP-TBill Spread: FRED 90日AA金融商票减3个月TBill,反映短期私人信用相对无风险利率的压力。",
                ),
                bhadial_factor(
                    module="Funding",
                    name="资金分裂度(21D)",
                    tag=f"{ind['funding_fragmentation_21d']:.2f} · {percentile_label(fragmentation_pct)}",
                    value="分裂" if fragmentation_score < 0 else "一致",
                    score=fragmentation_score,
                    source_mode="derived-public",
                    note="Bhadial Funding Fragmentation近似: 对SOFR-OBFR、SOFR-IORB、SOFR-ON RRP三条走廊利差做稳健z-score离散度并用21日EMA平滑。",
                ),
                {"n": "SOMA Treasury持仓", "tag": f"${ind['soma_treasury_trillions']:.2f}T", "v": "QT存量约束", "score": 0, "note": "以FRED TREAST跟踪美联储持有的美国国债规模,比WALCL总资产更贴近计划中的SOMA Treasury held outright。"},
                {"n": "资产负债表 / 总资产", "tag": f"WALCL ${ind['walcl_trillions']:.2f}T", "v": "中性", "score": 0, "note": "以FRED WALCL跟踪美联储资产负债表总规模。"},
            ],
        },
        {
            "id": "g2",
            "name": "宏观基本面",
            "en": "Macro Fundamentals",
            "weight": 25,
            "factors": [
                {
                    "n": "通胀跟踪",
                    "tag": (
                        f"CPI {ind['cpi_yoy']:.1f}% / PCE {ind['pce_yoy']:.1f}% / "
                        f"核心PCE {ind['core_pce_yoy']:.1f}% / Dallas Trimmed PCE {ind['trimmed_mean_pce_yoy']:.1f}%"
                    ),
                    "v": "全面偏热" if inflation_score <= -2 else "偏热" if inflation_score < 0 else "温和",
                    "score": inflation_score,
                    "note": "同时跟踪FRED CPIAUCSL、PCEPI、PCEPILFE与Dallas Fed Trimmed Mean PCE(PCETRIM12M159SFRBDAL); PCE和核心PCE更贴近Fed通胀框架,Dallas Trimmed PCE过滤极端分项噪声,适合作为政策反应函数中的底层通胀趋势观察项。",
                },
                {"n": "PPI 生产者物价", "tag": f"{ind['ppi_yoy']:.1f}% 同比", "v": "偏热" if ppi_score < 0 else "中性", "score": ppi_score, "note": "PPIACO同比衡量生产端通胀压力。"},
                {"n": "劳动力市场", "tag": f"失业率 {ind['unrate']:.1f}%", "v": "降温" if ind["unrate"] >= 4.2 else "韧性", "score": 1 if ind["unrate"] >= 4.2 else -1, "note": "失业率升温利多久期,劳动力韧性压制降息。"},
                {"n": "非农就业", "tag": f"{ind['payroll_change_k']:+.0f}k", "v": "稳健" if ind["payroll_change_k"] > 100 else "降温", "score": -1 if ind["payroll_change_k"] > 100 else 1, "curve": 1 if ind["payroll_change_k"] > 100 else 0, "note": "PAYEMS月差作为新增就业代理。"},
                growth_momentum_compatibility_factor(ind),
            ],
        },
        {
            "id": "g3",
            "name": "供给与技术面",
            "en": "Supply & Technicals",
            "weight": 15,
            "factors": [
                long_bond_auction_compatibility_factor(auctions),
                {"n": "发行节奏 / QRA", "tag": qra_tag, "v": "供给增加" if qra_score < 0 else "中性", "score": qra_score, "curve": 1 if qra_score < 0 else 0, "note": qra_note},
                {"n": "债务上限空间", "tag": debt_headroom_tag, "v": "紧张" if debt_headroom_score < 0 else "充足", "score": debt_headroom_score, "curve": 1 if debt_headroom_score < 0 else 0, "note": debt_headroom_note},
                {"n": "10Y 收益率动量", "tag": f"1月 {ind['ten_year_m1_change_bp']:+.0f}bp", "v": "上行", "score": -1 if ind["ten_year_m1_change_bp"] > 10 else 0, "curve": 1 if ind["s5s30"] > 50 else 0, "note": "10Y月度上行代表供给/期限溢价压力。"},
                {"n": "5s30s 曲线", "tag": f"{ind['s5s30']:.0f}bp", "v": "偏陡", "score": -1 if ind["s5s30"] > 60 else 0, "curve": 1, "note": "长端相对5Y更高,供给和期限溢价压力偏强。"},
                bhadial_factor(
                    module="Treasury",
                    name="10Y-3M曲线",
                    tag=f"{ind['s10s3m']:.0f}bp",
                    value="正斜率" if ind["s10s3m"] > 0 else "倒挂",
                    score=0,
                    curve=1 if ind["s10s3m"] > 100 else -1 if ind["s10s3m"] < -100 else 0,
                    source_mode="real-public",
                    note="Bhadial Treasury的10Y-3M Spread,用U.S. Treasury curve直接计算长短端斜率。",
                ),
                bhadial_factor(
                    module="Treasury",
                    name="30Y-10Y期限溢价",
                    tag=f"{ind['s30s10']:.0f}bp",
                    value="长端补偿" if ind["s30s10"] > 30 else "平坦",
                    score=0,
                    curve=1 if ind["s30s10"] > 45 else 0,
                    source_mode="real-public",
                    note="Bhadial Treasury的30Y-10Y Term Premium公开代理,用30Y减10Y衡量超长端期限补偿和需求变化。",
                ),
                bhadial_factor(
                    module="Treasury",
                    name="曲线曲率(绝对值)",
                    tag=f"{ind['curve_curvature_abs_bp']:.0f}bp",
                    value="曲线变形" if ind["curve_curvature_abs_bp"] > 80 else "平稳",
                    score=-1 if ind["curve_curvature_abs_bp"] > 80 else 0,
                    curve=1 if ind["curve_curvature_abs_bp"] > 80 else 0,
                    source_mode="derived-public",
                    note="Bhadial Treasury的Curve Curvature Abs近似: |2*10Y - 2Y - 30Y|,用于识别长端重新定价时的曲线折点。",
                ),
                {"n": "TGA 与现金管理", "tag": f"${ind['tga_trillions']:.2f}T", "v": "抽水" if ind["tga_trillions"] > 0.7 else "中性", "score": -1 if ind["tga_trillions"] > 0.7 else 0, "note": "TGA高位会边际抽走银行体系流动性。"},
            ],
        },
        {
            "id": "g4",
            "name": "需求与持仓",
            "en": "Demand & Positioning",
            "weight": 15,
            "factors": [
                {
                    "n": "拍卖需求",
                    "tag": auction_signal["tag"],
                    "v": auction_signal["label"],
                    "score": auction_signal["score"],
                    "note": auction_signal["note"],
                },
                {"n": "TIC 海外持仓", "tag": tic_tag, "v": "走弱" if tic_score < 0 else "改善" if tic_score > 0 else "中性", "score": tic_score, "curve": 1 if tic_score < 0 else 0, "note": "TIC主要海外持有者为月频且滞后,用于衡量外资边际需求。"},
                {"n": "CFTC 杠杆基金持仓", "tag": cftc_tag, "v": "反向利多" if cftc_score > 0 else "偏空" if cftc_score < 0 else "中性", "score": cftc_score, "curve": -1 if cftc_score > 0 else 0, "note": "CFTC financial futures COT聚合国债期货杠杆基金净仓位。"},
                primary_dealer_inventory_compatibility_factor(primary_dealer_stats),
            ],
        },
        {
            "id": "g5",
            "name": "相对价值",
            "en": "Relative Value",
            "weight": 10,
            "factors": [
                {"n": "期限溢价 (ACM)", "tag": acm_tag, "v": "估值转吸引" if acm_score > 0 else "中性", "score": acm_score, "curve": -1 if acm_score > 0 else 0, "note": "NY Fed ACM期限溢价高位时,长端估值补偿更充分。"},
                {"n": "实际利率", "tag": f"10Y TIPS {ind['real_10y']:.2f}%", "v": "偏高", "score": 1 if ind["real_10y"] > 2.0 else 0, "curve": -1, "note": "高实际利率提升长期债估值吸引力。"},
                bhadial_factor(
                    module="Rates",
                    name="真实利率水平",
                    tag=f"{ind['real_rate_level']:.2f}% · {percentile_label(real_rate_level_pct)}",
                    value="融资偏紧" if ind["real_rate_level"] > 2 else "中性",
                    score=1 if ind["real_rate_level"] > 2 else 0,
                    curve=-1 if ind["real_rate_level"] > 2 else 0,
                    source_mode="derived-public",
                    note="Bhadial Rates的Real Rate Level: 60% 5Y TIPS + 40% 10Y TIPS;宏观上越高越紧,在本久期计分中代表估值补偿更高。",
                ),
                bhadial_factor(
                    module="Rates",
                    name="真实曲线(10Y-5Y)",
                    tag=f"{ind['real_curve_10y5y_bp']:+.0f}bp · {percentile_label(real_curve_pct)}",
                    value="正斜率" if ind["real_curve_10y5y_bp"] > 0 else "倒挂",
                    score=0,
                    curve=1 if ind["real_curve_10y5y_bp"] > 25 else -1 if ind["real_curve_10y5y_bp"] < -25 else 0,
                    source_mode="derived-public",
                    note="Bhadial Rates的Real Curve: 10Y TIPS - 5Y TIPS,用于区分真实利率曲线的增长预期与期限补偿。",
                ),
                {"n": "盈亏平衡通胀", "tag": f"10Y BEI {ind['breakeven_10y']:.2f}%", "v": "偏高", "score": -1 if ind["breakeven_10y"] > 2.4 else 0, "note": "通胀补偿高位不利名义久期。"},
                {"n": "2s10s 曲线", "tag": f"{ind['s2s10']:.0f}bp", "v": "正斜率", "score": 0, "curve": 1 if ind["s2s10"] > 25 else 0, "note": "正斜率意味着衰退信号缓和,长端承压更明显。"},
                manual_placeholder_compatibility_factor("互换利差", "待接swap spread", "手动", "原站保留互换利差维度;本地未接入授权互换曲线,默认不改变评分,可在计分卡手动调整。"),
            ],
        },
        {
            "id": "g6",
            "name": "情绪与流动性",
            "en": "Sentiment & Liquidity",
            "weight": 10,
            "factors": [
                {
                    "n": "10Y实现波动率",
                    "tag": f"20D {ind['ten_year_realized_vol_20d_bp']:.1f}bp ann.",
                    "v": "高波动" if ind["ten_year_realized_vol_20d_bp"] > 95 else "中性",
                    "score": -1 if ind["ten_year_realized_vol_20d_bp"] > 95 else 0,
                    "note": "由U.S. Treasury curve 10Y日度收益率变动计算20日年化实现波动率,作为MOVE授权数据不可用时的公开代理。",
                },
                market_liquidity_compatibility_factor(ind),
                manual_placeholder_compatibility_factor("新老券利差", "待接on/off-run spread", "手动", "原站保留新老券利差维度;本地未接入逐券报价和融资微观数据,默认不改变评分,可手动维护。"),
                {
                    "n": "银行准备金",
                    "tag": f"${ind['bank_reserves_trillions']:.2f}T · {percentile_label(bank_reserves_pct)}",
                    "v": "宽松" if bank_reserves_score > 0 else "偏紧" if bank_reserves_score < 0 else "中性",
                    "score": bank_reserves_score,
                    "note": "FRED WRESBAL按5年历史百分位衡量银行体系准备金缓冲。",
                },
                {
                    "n": "净流动性",
                    "tag": f"${ind['net_liquidity_trillions']:.2f}T · {percentile_label(net_liquidity_pct)}",
                    "v": "宽松" if net_liquidity_score > 0 else "偏紧" if net_liquidity_score < 0 else "中性",
                    "score": net_liquidity_score,
                    "note": "参考The Dial Net Liquidity,用WALCL - TGA - ON RRP计算公开代理并按5年历史百分位评分。",
                },
                {
                    "n": "流动性动量",
                    "tag": f"1月 {ind['net_liquidity_m1_change_trillions']:+.2f}T · {percentile_label(net_liquidity_momentum_pct)}",
                    "v": "扩张" if net_liquidity_momentum_score > 0 else "收缩" if net_liquidity_momentum_score < 0 else "中性",
                    "score": net_liquidity_momentum_score,
                    "note": "净流动性1个月变化的历史百分位,用于补充The Dial Liquidity Momentum思路。",
                },
                bhadial_factor(
                    module="Liquidity",
                    name="13周净流动性动量",
                    tag=f"13周 {ind['net_liquidity_13w_change_trillions']:+.2f}T · {percentile_label(net_liquidity_13w_pct)}",
                    value="扩张" if net_liquidity_13w_score > 0 else "收缩" if net_liquidity_13w_score < 0 else "中性",
                    score=net_liquidity_13w_score,
                    source_mode="derived-public",
                    note="Bhadial Liquidity的Net Liquidity Momentum (13W): WALCL - TGA - ON RRP的13周绝对变化,捕捉QT、财政和RRP迁移的中期动量。",
                ),
                bhadial_factor(
                    module="Liquidity",
                    name="TGA偏离度",
                    tag=f"{ind['tga_deviation_trillions']:+.2f}T · {percentile_label(tga_deviation_pct)}",
                    value="抽水偏强" if tga_deviation_score < 0 else "释放" if tga_deviation_score > 0 else "正常",
                    score=tga_deviation_score,
                    source_mode="derived-public",
                    note="Bhadial Liquidity的TGA Deviation: TGA相对52周滚动中位数的偏离;正值代表财政现金累积并抽走准备金。",
                ),
                {"n": "ON RRP", "tag": f"${ind['rrp_trillions']:.3f}T", "v": "低位", "score": -1 if ind["rrp_trillions"] < 0.05 else 0, "note": "RRP接近枯竭时,流动性缓冲下降。"},
                bhadial_factor(
                    module="Liquidity",
                    name="ON RRP缓冲风险",
                    tag=f"{ind['onrrp_buffer_risk']:.2f} · {percentile_label(onrrp_buffer_risk_pct)}",
                    value="接近耗尽" if onrrp_buffer_risk_score < 0 else "有缓冲",
                    score=onrrp_buffer_risk_score,
                    source_mode="derived-public",
                    note="Bhadial Liquidity的ON RRP Buffer Risk: $100B以下用squared transformation刻画非线性耗尽风险,避免把RRP低位误读为宽松。",
                ),
                {"n": "信用利差", "tag": f"HY {ind['hy_oas']:.2f}% / IG {ind['ig_oas']:.2f}%", "v": "偏紧" if ind["hy_oas"] < 4 else "承压", "score": 0 if ind["hy_oas"] < 4 else -1, "note": "FRED ICE BofA OAS用于代理信用风险与风险偏好。"},
                bhadial_factor(
                    module="Credit",
                    name="金融条件指数(NFCI)",
                    tag=f"{ind['nfci']:+.2f} · {percentile_label(nfci_pct)}",
                    value="宽松" if nfci_score > 0 else "偏紧" if nfci_score < 0 else "中性",
                    score=nfci_score,
                    source_mode="real-public",
                    note="Bhadial Credit的NFCI: Chicago Fed National Financial Conditions Index,正值表示金融条件紧于均值,负值表示宽松。",
                ),
                bhadial_factor(
                    module="Credit",
                    name="HY-IG利差",
                    tag=f"{ind['hy_ig_oas_spread_bp']:+.0f}bp · {percentile_label(hy_ig_pct)}",
                    value="信用分层" if hy_ig_score < 0 else "正常",
                    score=hy_ig_score,
                    source_mode="derived-public",
                    note="补齐Bhadial Credit的信用分层维度;本地用FRED HY OAS - IG OAS作为公开信用相对压力代理。",
                ),
                bhadial_factor(
                    module="Credit",
                    name="HY信用偏好(HY/UST)",
                    tag=f"{ind['hy_credit_preference']:.2f} · {percentile_label(hy_credit_preference_pct)}",
                    value="偏好改善" if hy_credit_preference_score > 0 else "信用承压" if hy_credit_preference_score < 0 else "中性",
                    score=hy_credit_preference_score,
                    source_mode="proxy-public",
                    note="Bhadial HY Credit的公开代理: FRED ICE US High Yield total return index相对10Y美债价格代理,用于替代HYG/IEI ETF历史。",
                ),
                bhadial_factor(
                    module="Credit",
                    name="IG信用偏好(IG/UST)",
                    tag=f"{ind['ig_credit_preference']:.2f} · {percentile_label(ig_credit_preference_pct)}",
                    value="承接改善" if ig_credit_preference_score > 0 else "信用承压" if ig_credit_preference_score < 0 else "中性",
                    score=ig_credit_preference_score,
                    source_mode="proxy-public",
                    note="Bhadial IG Credit的公开代理: FRED ICE US Corporate total return index相对10Y美债价格代理,用于替代LQD/IEF ETF历史。",
                ),
                bhadial_factor(
                    module="Credit",
                    name="银行股相对S&P500",
                    tag=f"{ind['regional_bank_vs_market']:.2f} · {percentile_label(regional_bank_pct)}",
                    value="银行改善" if regional_bank_score > 0 else "银行承压" if regional_bank_score < 0 else "中性",
                    score=regional_bank_score,
                    source_mode="proxy-public",
                    note="Bhadial Regional Banks vs SPY的公开代理: FRED NASDAQ Bank Index相对S&P 500;不是KRE/SPY ETF精确替代,但能捕捉银行股相对风险偏好。",
                ),
                bhadial_factor(
                    module="Risk",
                    name="VIX期限结构",
                    tag=f"{ind['vix_term_structure']:.2f} · VIX3M {ind['vix_3m']:.2f}",
                    value="倒挂" if vix_term_score < 0 else "contango",
                    score=vix_term_score,
                    source_mode="derived-public",
                    note="Bhadial Risk的VIX Term Structure: VIX / VIX 3M,大于1代表波动率倒挂和风险偏好承压。",
                ),
                bhadial_factor(
                    module="Risk",
                    name="风险资产/美债代理",
                    tag=f"{ind['risk_vs_safe']:.2f} · {percentile_label(risk_vs_safe_pct)}",
                    value="risk-on" if risk_vs_safe_score > 0 else "risk-off" if risk_vs_safe_score < 0 else "中性",
                    score=risk_vs_safe_score,
                    source_mode="proxy-public",
                    note="Bhadial Risk vs Safe的公开代理: FRED S&P 500相对DGS10派生的10Y美债价格代理;用于替代SPY/TLT ETF历史。",
                ),
                bhadial_factor(
                    module="Risk",
                    name="高Beta偏好(NDX/US500)",
                    tag=f"{ind['high_beta_preference']:.2f} · {percentile_label(high_beta_pct)}",
                    value="高Beta占优" if high_beta_score > 0 else "高Beta退潮" if high_beta_score < 0 else "中性",
                    score=high_beta_score,
                    source_mode="proxy-public",
                    note="Bhadial High-Beta Preference的公开代理: FRED Nasdaq-100 Total Return相对Nasdaq US 500 Large Cap Total Return,用于替代IWM/SPY ETF历史。",
                ),
                bhadial_factor(
                    module="External",
                    name="美元实现波动率",
                    tag=f"{ind['dxy_realized_vol']:.1f}% · {percentile_label(dxy_vol_pct)}",
                    value="外部冲击" if dxy_vol_score < 0 else "稳定",
                    score=dxy_vol_score,
                    source_mode="derived-public",
                    note="Bhadial External的FX Realized Volatility近似: 对FRED美元广义指数计算63日年化实现波动率。",
                ),
                bhadial_factor(
                    module="External",
                    name="原油波动偏离",
                    tag=f"{ind['oil_vol_deviation']:.1f} · {percentile_label(oil_vol_dev_pct)}",
                    value="油市冲击" if oil_vol_dev_score < 0 else "正常",
                    score=oil_vol_dev_score,
                    source_mode="derived-public",
                    note="Bhadial External的Oil Volatility Deviation: OVX相对约1年滚动中位数的正偏离,只在恐慌高于常态时计压。",
                ),
                bhadial_factor(
                    module="External",
                    name="天然气",
                    tag=f"${ind['natgas']:.2f} · {percentile_label(natgas_pct)}",
                    value="能源压力" if natgas_score < 0 else "正常",
                    score=natgas_score,
                    source_mode="real-public",
                    note="Bhadial External的Natural Gas: FRED Henry Hub现货价格,用于补充能源冲击而非只看原油。",
                ),
            ],
        },
    ]


def compatibility_factor(
    *,
    name: str,
    tag: str,
    value: str,
    score: int,
    note: str,
    source_mode: str,
    curve: int | None = None,
) -> dict[str, Any]:
    factor: dict[str, Any] = {
        "n": name,
        "tag": tag,
        "v": value,
        "score": score,
        "note": note,
        "sourceMode": source_mode,
        "compatibilityWith": REMOTE_COMPATIBILITY_SOURCE,
    }
    if curve is not None:
        factor["curve"] = curve
    return factor


def build_conclusion_audit(groups: list[dict[str, Any]], source_status: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    total_weight = sum(max(0.0, _float_or_zero(group.get("weight"))) for group in groups)
    duration_score = 0.0
    curve_score = 0.0
    drivers: list[dict[str, Any]] = []
    group_diagnostics: list[dict[str, Any]] = []

    for group in groups:
        factors = [factor for factor in group.get("factors", []) if isinstance(factor, dict)]
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


def high_pressure_score(percentile: int | None, *, high_score: int = -1, extreme_score: int = -2) -> int:
    if percentile is None:
        return 0
    if percentile >= 95:
        return extreme_score
    if percentile >= 80:
        return high_score
    return 0


def low_preference_score(percentile: int | None) -> int:
    if percentile is None:
        return 0
    if percentile <= 10:
        return -2
    if percentile <= 25:
        return -1
    if percentile >= 80:
        return 1
    return 0


def fed_path_compatibility_factor(ind: dict[str, Any]) -> dict[str, Any]:
    path = build_fed_path(ind)
    terminal = path[-1] if path else {"m": "--", "hike": 0, "hold": 100, "cut": 0}
    hike = int(terminal.get("hike") or 0)
    hold = int(terminal.get("hold") or 0)
    cut = int(terminal.get("cut") or 0)
    if hike >= 50:
        score, value, curve = -2, "偏加息", 1
    elif hike >= 20:
        score, value, curve = -1, "加息尾部", 1
    elif cut >= 20:
        score, value, curve = 1, "偏降息", -1
    else:
        score, value, curve = 0, "中性", 0
    return compatibility_factor(
        name="隐含政策路径",
        tag=f"{terminal.get('m', '--')} 加息{hike}% / 持平{hold}% / 降息{cut}%",
        value=value,
        score=score,
        curve=curve,
        source_mode="modeled",
        note="对齐原站Fed Funds期货/OIS维度;本地用公开Fed Funds期货代理、2Y曲线再定价和通胀压力建模,非CME官方概率。",
    )


def chair_transition_compatibility_factor(official_news: list[NewsItem]) -> dict[str, Any]:
    chair_news = None
    for item in sorted(official_news, key=lambda row: row.date, reverse=True):
        title = item.title.lower()
        if "chair" in title and ("oath" in title or "sworn" in title or "chairman" in title or "chair pro tempore" in title):
            chair_news = item
            break
    if chair_news:
        return compatibility_factor(
            name="新任主席倾向",
            tag=f"{chair_news.date.strftime('%m/%d')} {chair_news.source}",
            value="待判断",
            score=0,
            source_mode="official-news",
            note="官方新闻确认主席/代理主席相关变化;政策倾向不由标题自动推断,默认中性并保留手动评分入口。",
        )
    return compatibility_factor(
        name="新任主席倾向",
        tag="未检测官方主席变动",
        value="手动",
        score=0,
        source_mode="manual-placeholder",
        note="原站包含主席倾向叙事;本地未从官方新闻检测到主席变化时不自动给方向,可手动评分。",
    )


def growth_momentum_compatibility_factor(ind: dict[str, Any]) -> dict[str, Any]:
    payroll = float(ind.get("payroll_change_k") or 0)
    unrate = float(ind.get("unrate") or 0)
    if payroll > 125 and unrate < 4.5:
        score, value, curve = -1, "稳健", 1
    elif payroll < 50 or unrate >= 4.5:
        score, value, curve = 1, "降温", -1
    else:
        score, value, curve = 0, "中性", 0
    return compatibility_factor(
        name="增长动能",
        tag=f"PAYEMS {payroll:+.0f}k / U-3 {unrate:.1f}%",
        value=value,
        score=score,
        curve=curve,
        source_mode="proxy-public",
        note="对齐原站增长动能因子;用公开非农月差和失业率代理活动强弱,避免主观填写。",
    )


def long_bond_auction_compatibility_factor(auctions: list[dict[str, object]]) -> dict[str, Any]:
    long_bond = None
    for row in sorted(auctions, key=lambda item: str(item.get("auctionDate") or ""), reverse=True):
        term = str(row.get("securityTerm") or "")
        security_type = str(row.get("securityType") or "")
        if ("30" in term and ("Year" in term or "年" in term)) and "TIPS" not in security_type.upper():
            long_bond = row
            break
    if not long_bond:
        return compatibility_factor(
            name="30年期拍卖",
            tag="待接近期30Y auction",
            value="手动",
            score=0,
            curve=0,
            source_mode="manual-placeholder",
            note="原站重点跟踪30年期拍卖质量;TreasuryDirect样本未含近期30Y时默认中性,可手动评分。",
        )
    bid_to_cover = parse_number(long_bond.get("bidToCoverRatio"))
    high_yield = format_yield(str(long_bond.get("highYield") or long_bond.get("averageMedianYield") or ""))
    score = -2 if bid_to_cover is not None and bid_to_cover < 2.35 else -1 if bid_to_cover is not None and bid_to_cover < 2.5 else 0
    return compatibility_factor(
        name="30年期拍卖",
        tag=f"{high_yield} · {bid_to_cover:.2f}x" if bid_to_cover is not None else f"{high_yield} · btc待解析",
        value="疲弱" if score < 0 else "中性",
        score=score,
        curve=2 if score <= -2 else 1 if score < 0 else 0,
        source_mode="real-public",
        note="对齐原站30年期拍卖因子;用TreasuryDirect中标利率和投标倍数衡量长端需求。",
    )


def primary_dealer_inventory_compatibility_factor(stats: PrimaryDealerStats | None) -> dict[str, Any]:
    value = stats.metrics_millions.get("PDPOSGST-TOT") if stats else None
    if value is None:
        return compatibility_factor(
            name="一级交易商持仓",
            tag="待接NY Fed周频",
            value="手动",
            score=0,
            source_mode="manual-placeholder",
            note="原站保留交易商库存维度;NY Fed primary dealer数据不可用时默认中性。",
        )
    score = -1 if value >= 650_000 else 0
    return compatibility_factor(
        name="一级交易商持仓",
        tag=f"{money_from_millions(value)} · {stats.as_of.isoformat()}",
        value="库存高" if score < 0 else "中性",
        score=score,
        source_mode="real-public",
        note="NY Fed primary dealer UST ex-TIPS净持仓;库存高可能代表交易商资产负债表承接压力。",
    )


def manual_placeholder_compatibility_factor(name: str, tag: str, value: str, note: str) -> dict[str, Any]:
    return compatibility_factor(name=name, tag=tag, value=value, score=0, source_mode="manual-placeholder", note=note)


def market_liquidity_compatibility_factor(ind: dict[str, Any]) -> dict[str, Any]:
    realized_vol = float(ind.get("ten_year_realized_vol_20d_bp") or 0)
    hy_oas = float(ind.get("hy_oas") or 0)
    stressed = realized_vol > 95 or hy_oas > 4.0
    return compatibility_factor(
        name="市场流动性",
        tag=f"10Y vol {realized_vol:.1f} / HY {hy_oas:.2f}%",
        value="轻度承压" if stressed else "正常",
        score=-1 if stressed else 0,
        curve=1 if stressed else 0,
        source_mode="proxy-public",
        note="原站市场流动性因子的公开代理:10Y实现波动率和HY信用利差同时观察,暂不伪装为订单簿深度或买卖价差。",
    )


def build_policy(ind: dict[str, Any]) -> dict[str, list[list[str]]]:
    return {
        "rates": [
            ["联邦基金目标区间", ind["target_range"], "由DFF近似推断"],
            ["有效联邦基金利率", f"{ind['dff']:.2f}%", "FRED DFF"],
            ["SOFR", f"{ind['sofr']:.2f}%", "FRED SOFR"],
            ["SOFR-EFFR利差", f"{ind['sofr_effr_spread_bp']:+.0f}bp", percentile_label(ind["percentiles"].get("sofr_effr_spread"))],
            ["2Y收益率", f"{ind['two_year']:.2f}%", "政策路径市场代理"],
            ["10Y收益率", f"{ind['ten_year']:.2f}%", "长端定价锚"],
            ["1月2Y变化", f"{ind['two_year_m1_change_bp']:+.0f}bp", "政策再定价"],
        ],
        "plumbing": [
            ["美联储资产负债表", f"${ind['walcl_trillions']:.2f}T", "FRED WALCL"],
            ["SOMA Treasury持仓", f"${ind['soma_treasury_trillions']:.2f}T", "FRED TREAST"],
            ["银行准备金", f"${ind['bank_reserves_trillions']:.2f}T", f"FRED WRESBAL · {percentile_label(ind['percentiles'].get('bank_reserves'))}"],
            ["净流动性", f"${ind['net_liquidity_trillions']:.2f}T", f"WALCL-TGA-RRP · {percentile_label(ind['percentiles'].get('net_liquidity'))}"],
            ["SOFR", f"{ind['sofr']:.2f}%", "隔夜融资"],
            ["ON RRP", f"${ind['rrp_trillions']:.3f}T", "FRED RRPONTSYD"],
            ["财政部一般账户", f"${ind['tga_trillions']:.2f}T", "FRED WTREGEN"],
            ["流动性结论", "边际偏紧" if ind["rrp_trillions"] < 0.05 else "中性", "公开数据代理"],
        ],
    }


def build_percentiles(ind: dict[str, Any], auctions: list[dict[str, object]]) -> dict[str, Any]:
    auction_signal = auction_demand_signal(auctions)
    items = [
        {"name": "银行准备金", "value": f"${ind['bank_reserves_trillions']:.2f}T", "percentile": ind["percentiles"].get("bank_reserves"), "source": "FRED WRESBAL", "window": "5Y"},
        {"name": "净流动性", "value": f"${ind['net_liquidity_trillions']:.2f}T", "percentile": ind["percentiles"].get("net_liquidity"), "source": "FRED WALCL - WTREGEN - RRPONTSYD", "window": "5Y"},
        {"name": "流动性动量", "value": f"{ind['net_liquidity_m1_change_trillions']:+.2f}T", "percentile": ind["percentiles"].get("net_liquidity_momentum"), "source": "Net liquidity 1M change", "window": "5Y"},
        {"name": "13周净流动性动量", "value": f"{ind['net_liquidity_13w_change_trillions']:+.2f}T", "percentile": ind["percentiles"].get("net_liquidity_13w_momentum"), "source": "Net liquidity 13W change", "window": "5Y"},
        {"name": "TGA偏离度", "value": f"{ind['tga_deviation_trillions']:+.2f}T", "percentile": ind["percentiles"].get("tga_deviation"), "source": "FRED WTREGEN - 52W median", "window": "5Y"},
        {"name": "ON RRP缓冲风险", "value": f"{ind['onrrp_buffer_risk']:.2f}", "percentile": ind["percentiles"].get("onrrp_buffer_risk"), "source": "FRED RRPONTSYD risk signal", "window": "5Y"},
        {"name": "SOFR-EFFR利差", "value": f"{ind['sofr_effr_spread_bp']:+.0f}bp", "percentile": ind["percentiles"].get("sofr_effr_spread"), "source": "FRED SOFR - DFF", "window": "5Y"},
        {"name": "商票-TBill利差", "value": f"{ind['cp_tbill_spread_bp']:+.0f}bp", "percentile": ind["percentiles"].get("cp_tbill_spread"), "source": "FRED DCPF3M - DTB3", "window": "5Y"},
        {"name": "资金分裂度(21D)", "value": f"{ind['funding_fragmentation_21d']:.2f}", "percentile": ind["percentiles"].get("funding_fragmentation"), "source": "SOFR corridor spread dispersion", "window": "5Y"},
        {"name": "真实利率水平", "value": f"{ind['real_rate_level']:.2f}%", "percentile": ind["percentiles"].get("real_rate_level"), "source": "60% DFII5 + 40% DFII10", "window": "5Y"},
        {"name": "VIX", "value": f"{ind['vix']:.2f}", "percentile": ind["percentiles"].get("vix"), "source": "FRED VIXCLS", "window": "5Y"},
        {"name": "VIX期限结构", "value": f"{ind['vix_term_structure']:.2f}", "percentile": ind["percentiles"].get("vix_term_structure"), "source": "FRED VIXCLS / VXVCLS", "window": "5Y"},
        {"name": "HY信用利差", "value": f"{ind['hy_oas']:.2f}%", "percentile": ind["percentiles"].get("hy_oas"), "source": "FRED BAMLH0A0HYM2", "window": "5Y"},
        {"name": "HY-IG利差", "value": f"{ind['hy_ig_oas_spread_bp']:+.0f}bp", "percentile": ind["percentiles"].get("hy_ig_oas_spread"), "source": "FRED HY OAS - IG OAS", "window": "5Y"},
        {"name": "HY信用偏好(HY/UST)", "value": f"{ind['hy_credit_preference']:.2f}", "percentile": ind["percentiles"].get("hy_credit_preference"), "source": "FRED HY TR / DGS10 price proxy", "window": "available up to 5Y"},
        {"name": "IG信用偏好(IG/UST)", "value": f"{ind['ig_credit_preference']:.2f}", "percentile": ind["percentiles"].get("ig_credit_preference"), "source": "FRED IG TR / DGS10 price proxy", "window": "available up to 5Y"},
        {"name": "金融条件指数(NFCI)", "value": f"{ind['nfci']:+.2f}", "percentile": ind["percentiles"].get("nfci"), "source": "FRED NFCI", "window": "5Y"},
        {"name": "银行股相对S&P500", "value": f"{ind['regional_bank_vs_market']:.2f}", "percentile": ind["percentiles"].get("regional_bank_vs_market"), "source": "FRED NASDAQBANK / SP500", "window": "5Y"},
        {"name": "风险资产/美债代理", "value": f"{ind['risk_vs_safe']:.2f}", "percentile": ind["percentiles"].get("risk_vs_safe"), "source": "FRED SP500 / DGS10 price proxy", "window": "5Y"},
        {"name": "高Beta偏好(NDX/US500)", "value": f"{ind['high_beta_preference']:.2f}", "percentile": ind["percentiles"].get("high_beta_preference"), "source": "FRED NASDAQXNDX / NASDAQNQUS500LCT", "window": "5Y"},
        {"name": "美元广义指数", "value": f"{ind['dxy']:.2f}", "percentile": ind["percentiles"].get("dxy"), "source": "FRED DTWEXBGS", "window": "5Y"},
        {"name": "美元实现波动率", "value": f"{ind['dxy_realized_vol']:.1f}%", "percentile": ind["percentiles"].get("dxy_realized_vol"), "source": "FRED DTWEXBGS 63D realized vol", "window": "5Y"},
        {"name": "原油波动偏离", "value": f"{ind['oil_vol_deviation']:.1f}", "percentile": ind["percentiles"].get("oil_vol_deviation"), "source": "FRED OVXCLS - rolling median", "window": "5Y"},
        {"name": "天然气", "value": f"${ind['natgas']:.2f}", "percentile": ind["percentiles"].get("natgas"), "source": "FRED DHHNGSP", "window": "5Y"},
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


def build_macro_liquidity_score(ind: dict[str, Any]) -> dict[str, Any]:
    snapshot = bhadial_conditions_snapshot(ind)
    score = snapshot["score"]
    components = snapshot["components"]
    modules = snapshot["modules"]
    drivers = sorted(components, key=lambda item: abs(item["contribution"]), reverse=True)[:4]
    constraint = min(components, key=lambda item: item["contribution"]) if components else {}
    offset = max(components, key=lambda item: item["contribution"]) if components else {}
    drag_components = [item for item in components if item["contribution"] < -0.01]
    buffer_components = [item for item in components if item["contribution"] > 0.01]
    neutral_components = [item for item in components if -0.01 <= item["contribution"] <= 0.01]
    focus_components = sorted(components, key=lambda item: abs(item["contribution"]), reverse=True)[:5]
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
        "scoredFactorCount": sum(len(module["factors"]) for module in BHADIAL_CONDITION_MODULES),
        "observedFactorCount": snapshot["observedFactorCount"],
        "proxyFactorCount": 5,
        "modules": modules,
        "summary": macro_liquidity_summary(score, constraint, offset, trend),
        "trend": trend,
        "constraint": constraint,
        "offset": offset,
        "balance": balance,
        "focusComponents": focus_components,
        "hiddenComponentCount": max(0, len(components) - len(focus_components)),
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
        "points": points,
    }


def macro_liquidity_history_points(series: dict[str, list[SeriesPoint]]) -> list[dict[str, Any]]:
    dated_component_points: list[SeriesPoint] = []
    for key in BHADIAL_CONDITION_SERIES_KEYS:
        dated_component_points.extend(clean_points(series.get(key, [])))
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
        score_row = macro_liquidity_score_at(series, target)
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
    percentile_text = f"p{percentile}" if percentile is not None else "p--"
    score_change_text = format_signed_number(score_3m_change, digits=1)
    percentile_change_text = format_signed_number(float(percentile_3m_change), digits=0) if percentile_3m_change is not None else "--"
    if direction == "上行":
        return f"历史分位{percentile_text},3M综合分{score_change_text},分位{percentile_change_text}pct; 低位改善正在形成边际支撑。"
    if direction == "下行":
        return f"历史分位{percentile_text},3M综合分{score_change_text},分位{percentile_change_text}pct; 趋势转弱会放大低分位约束。"
    if direction == "震荡":
        return f"历史分位{percentile_text},3M综合分{score_change_text},分位{percentile_change_text}pct; 当前位置优先按区间震荡处理。"
    return f"历史分位{percentile_text},历史趋势样本不足; 暂以当前分项拖累和缓冲为主。"


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


REGIONAL_MONITOR_ORDER = ["us", "korea", "hongkong", "taiwan", "japan"]
REGION_STATUS_SEVERITY = {"risk": 3, "watch": 2, "quiet": 1, "missing": 0, "": 0}


def build_regional_monitor(global_lppl_risk: dict[str, Any] | None) -> dict[str, Any]:
    """Group the per-index LPPL factors into first-class regions (US groups SPY+QQQ)
    so the dashboard can surface region-distinguished factors at the top level instead
    of burying HK/TW/JP as 'ETF proxy' sub-rows. Purely a regrouping of existing index
    rows — each row already embeds its own history/backtest/forwardSignal/validation."""
    indices = global_lppl_risk.get("indices") if isinstance(global_lppl_risk, dict) else None
    if not isinstance(indices, list) or not indices:
        return {"available": False, "reason": "缺少逐指数LPPL数据,暂不能按地区拆分。", "regions": []}

    grouped: dict[str, list[dict[str, Any]]] = {}
    meta: dict[str, dict[str, str]] = {}
    for row in indices:
        if not isinstance(row, dict):
            continue
        key = str(row.get("regionKey") or "").strip() or "other"
        grouped.setdefault(key, []).append(row)
        if key not in meta:
            meta[key] = {
                "name": str(row.get("regionName") or row.get("region") or key),
                "nameCn": str(row.get("regionNameCn") or row.get("regionName") or key),
            }

    ordered_keys = [key for key in REGIONAL_MONITOR_ORDER if key in grouped]
    ordered_keys += [key for key in grouped if key not in REGIONAL_MONITOR_ORDER]

    regions: list[dict[str, Any]] = []
    for key in ordered_keys:
        rows = grouped[key]
        region = {
            "key": key,
            "name": meta[key]["name"],
            "nameCn": meta[key]["nameCn"],
            "indices": rows,
            "aggregate": regional_monitor_aggregate(rows),
        }
        if region["aggregate"]["availableCount"] > 0:
            region["factorAlert"] = build_region_factor_alert(region)
            region["allocation"] = build_region_allocation(region)
            if region["key"] == "us" and len(region["indices"]) >= 2:
                region["internalRotation"] = build_us_internal_rotation(region)
        regions.append(region)
    available_regions = [region for region in regions if region["aggregate"]["availableCount"] > 0]
    alerting = [region for region in available_regions if region["aggregate"]["status"] == "risk"]
    diversification = build_regional_diversification(regions)
    return {
        "available": bool(available_regions),
        "asOf": str(global_lppl_risk.get("asOf") or ""),
        "method": (
            "Region-grouped LPPL bubble factors (US groups SPY+QQQ; Korea/HK/Taiwan/Japan via US-listed "
            "ETF proxies). Each region carries its own indices' bubble fit, critical-date window, validation "
            "and forward signal; region status is the worst constituent status."
        ),
        "regionOrder": [region["key"] for region in regions],
        "alertingRegions": [region["key"] for region in alerting],
        "summary": regional_monitor_summary(available_regions, alerting),
        "rotation": build_regional_rotation(regions, diversification),
        "diversification": diversification,
        "regions": regions,
    }


def regional_monitor_aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    available = [row for row in rows if row.get("available") and optional_float(row.get("score")) is not None]
    statuses = [str(row.get("status") or "") for row in available]
    worst_status = max(statuses, key=lambda s: REGION_STATUS_SEVERITY.get(s, 0)) if statuses else "missing"
    worst_cn = next((str(row.get("statusCn") or "") for row in available if str(row.get("status")) == worst_status), "缺失")
    scores = [optional_float(row.get("score")) for row in available]
    scores = [value for value in scores if value is not None]
    # Nearest critical window only counts rows that are actually flagged (risk/watch).
    flagged_days = [
        optional_float(row.get("daysToCritical"))
        for row in available
        if str(row.get("status")) in {"risk", "watch"} and optional_float(row.get("daysToCritical")) is not None
    ]
    factor_rows = [row.get("priceFactors") for row in available if isinstance(row.get("priceFactors"), dict) and row["priceFactors"].get("available")]
    return {
        "status": worst_status,
        "statusCn": worst_cn,
        "maxScore": round(max(scores), 1) if scores else None,
        "minDaysToCritical": min(flagged_days) if flagged_days else None,
        "availableCount": len(available),
        "indexCount": len(rows),
        "priceFactors": regional_price_factor_rollup(factor_rows),
    }


def regional_price_factor_rollup(factor_rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not factor_rows:
        return {"available": False}
    return_3m = average_optional([row.get("return3m") for row in factor_rows])
    realized_vol = average_optional([row.get("realizedVol") for row in factor_rows])
    relative_rows = [row.get("relativeStrength3m") for row in factor_rows if not row.get("isBenchmark")]
    relative_strength = average_optional(relative_rows)
    drawdowns = [optional_float(row.get("drawdownFromHigh")) for row in factor_rows]
    drawdowns = [value for value in drawdowns if value is not None]
    # Region market-state = worst constituent state (stressed > neutral > constructive).
    state_severity = {"stressed": 2, "neutral": 1, "constructive": 0}
    states = [str(row.get("marketState") or "neutral") for row in factor_rows]
    worst_state = max(states, key=lambda s: state_severity.get(s, 1)) if states else "neutral"
    worst_state_cn = {"stressed": "承压", "neutral": "中性", "constructive": "偏强"}[worst_state]
    # return3m / realizedVol / relativeStrength3m on each row are already percentages
    # (pct_metric scaled at the index level), so average-then-round here — do not rescale.
    return {
        "available": True,
        "return3m": round(return_3m, 2) if return_3m is not None else None,
        "realizedVol": round(realized_vol, 2) if realized_vol is not None else None,
        "relativeStrength3m": round(relative_strength, 2) if relative_strength is not None else None,
        "worstDrawdownFromHigh": round(min(drawdowns), 1) if drawdowns else None,
        "marketState": worst_state,
        "marketStateCn": worst_state_cn,
    }


REGIONAL_DIVERSIFICATION_MIN_OVERLAP = 26


def region_weekly_returns(representative: dict[str, Any]) -> dict[date, float]:
    """Weekly returns for a region derived from its representative index's daily history closes."""
    history = representative.get("history") if isinstance(representative.get("history"), dict) else {}
    points = history.get("points", []) if isinstance(history, dict) else []
    close_points: list[SeriesPoint] = []
    for point in points:
        if not isinstance(point, dict):
            continue
        close = optional_float(point.get("close"))
        try:
            point_date = date.fromisoformat(str(point.get("date")))
        except (TypeError, ValueError):
            continue
        if close is not None and close > 0:
            close_points.append(SeriesPoint(date=point_date, value=close))
    if len(close_points) < REGIONAL_DIVERSIFICATION_MIN_OVERLAP + 1:
        return {}
    sorted_closes = SortedSeries(close_points)
    week_dates = weekly_dates(close_points, years=5)
    returns: dict[date, float] = {}
    previous_close: float | None = None
    for target in week_dates:
        close = sorted_closes.value_at_or_before(target)
        if close is not None and previous_close is not None and previous_close > 0:
            returns[target] = close / previous_close - 1
        if close is not None:
            previous_close = close
    return returns


def build_regional_diversification(regions: list[dict[str, Any]]) -> dict[str, Any]:
    """Pairwise correlation of regions' weekly returns → which regions co-move (redundant
    risk) and which diversify. Lower average correlation = better diversifier."""
    returns_by_key: dict[str, dict[date, float]] = {}
    name_by_key: dict[str, str] = {}
    for region in regions:
        if region.get("aggregate", {}).get("availableCount", 0) <= 0:
            continue
        representative = regional_representative_index(region.get("indices", []) if isinstance(region.get("indices"), list) else [])
        if representative is None:
            continue
        weekly = region_weekly_returns(representative)
        if weekly:
            returns_by_key[region["key"]] = weekly
            name_by_key[region["key"]] = str(region.get("nameCn") or region.get("name") or region["key"])
    keys = sorted(returns_by_key)
    if len(keys) < 2:
        return {"available": False, "reason": "可用地区不足两个,暂不能做相关性分析。", "matrix": []}

    matrix: list[dict[str, Any]] = []
    corr_lookup: dict[tuple[str, str], float] = {}
    for index, first in enumerate(keys):
        for second in keys[index + 1:]:
            shared = sorted(set(returns_by_key[first]) & set(returns_by_key[second]))
            if len(shared) < REGIONAL_DIVERSIFICATION_MIN_OVERLAP:
                continue
            corr = pearson_correlation([returns_by_key[first][d] for d in shared], [returns_by_key[second][d] for d in shared])
            if corr is None:
                continue
            corr_lookup[(first, second)] = corr
            matrix.append({"a": first, "aCn": name_by_key[first], "b": second, "bCn": name_by_key[second], "corr": round(corr, 2)})
    if not matrix:
        return {"available": False, "reason": "地区周度收益重叠不足,暂不能做相关性分析。", "matrix": []}

    region_stats: list[dict[str, Any]] = []
    for key in keys:
        pair_corrs = [corr for (a, b), corr in corr_lookup.items() if key in (a, b)]
        if pair_corrs:
            region_stats.append({"key": key, "nameCn": name_by_key[key], "avgCorr": round(sum(pair_corrs) / len(pair_corrs), 2)})
    region_stats.sort(key=lambda item: item["avgCorr"])
    most_correlated = max(matrix, key=lambda item: item["corr"])
    best_diversifier = region_stats[0] if region_stats else None
    summary_parts = [
        f"{most_correlated['aCn']}与{most_correlated['bCn']}相关性最高({most_correlated['corr']:+.2f}, 同涨同跌、分散价值低)"
    ]
    if best_diversifier is not None:
        summary_parts.append(f"{best_diversifier['nameCn']}平均相关性最低({best_diversifier['avgCorr']:+.2f}, 分散价值最高)")
    return {
        "available": True,
        "method": "各地区代表指数周度收益两两 Pearson 相关; 高相关=同向风险冗余, 低/负相关=分散价值。",
        "matrix": matrix,
        "regionStats": region_stats,
        "mostCorrelatedPair": most_correlated,
        "bestDiversifier": best_diversifier,
        "summary": "; ".join(summary_parts) + "。",
    }


def regional_monitor_summary(available_regions: list[dict[str, Any]], alerting: list[dict[str, Any]]) -> str:
    if not available_regions:
        return "暂无可用地区LPPL样本。"
    if alerting:
        names = "、".join(region["nameCn"] for region in alerting)
        return f"{len(available_regions)}个地区在监控; {names}出现泡沫临界风险,其余地区相对平静。"
    return f"{len(available_regions)}个地区在监控,均未触发泡沫临界风险。"


# Factor ids whose high readings mean MORE risk (used to gate evidence-backed caution).
REGIONAL_RISK_FACTOR_IDS = {"lpplScore", "realizedVol"}


def regional_representative_index(indices: list[dict[str, Any]]) -> dict[str, Any] | None:
    validated = [
        row for row in indices
        if isinstance(row, dict)
        and isinstance(row.get("factorValidation"), dict)
        and row["factorValidation"].get("available")
    ]
    if not validated:
        return None
    return next(
        (row for row in validated if str(row.get("symbol") or "").upper() == GLOBAL_LPPL_US_BENCHMARK_SYMBOL),
        validated[0],
    )


def region_validated_leading_factors(factor_validation: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Factors that PASSED this region's own walk-forward OOS test as leading with lift>1 —
    i.e. proven early-warning power for that region's equity. Used to gate conviction."""
    if not isinstance(factor_validation, dict) or not factor_validation.get("available"):
        return []
    leading: list[dict[str, Any]] = []
    for factor in factor_validation.get("factors", []):
        if not isinstance(factor, dict):
            continue
        lift = optional_float(factor.get("lift"))
        if str(factor.get("classification")) == "leading" and lift is not None and lift > 1.0:
            leading.append(
                {
                    "id": str(factor.get("id") or ""),
                    "labelCn": str(factor.get("labelCn") or factor.get("label") or ""),
                    "lift": round(lift, 2),
                    "oosIc3m": optional_float(factor.get("oosIc3m")),
                    "leadTimeDays": optional_float(factor.get("leadTimeDays")),
                }
            )
    return sorted(leading, key=lambda item: item["lift"] or 0.0, reverse=True)


def composite_qualifies_as_alert(composite: dict[str, Any]) -> bool:
    if not isinstance(composite, dict) or not composite.get("available"):
        return False
    if composite.get("currentValue") is None or composite.get("alertThreshold") is None:
        return False
    if composite.get("beatsBestSingleFactor") is True:
        return True
    return str(composite.get("classification")) == "leading" and (optional_float(composite.get("lift")) or 0.0) > 1.0


def build_region_factor_alert(region: dict[str, Any]) -> dict[str, Any]:
    """Live early-warning: compare a region's CURRENT reading of its strongest OOS-validated
    leading RISK signal to its calibrated alert threshold. Prefers the evidence-weighted
    COMPOSITE when the composite is validated and at least matches the best single factor;
    otherwise falls back to the single strongest validated risk factor."""
    representative = regional_representative_index(region.get("indices", []) if isinstance(region.get("indices"), list) else [])
    if representative is None:
        return {"available": False}
    factor_validation = representative.get("factorValidation") if isinstance(representative.get("factorValidation"), dict) else {}
    composite = factor_validation.get("composite") if isinstance(factor_validation.get("composite"), dict) else {}

    if composite_qualifies_as_alert(composite):
        source, label, factor_id = "composite", "证据加权综合信号", "regionComposite"
        current = optional_float(composite.get("currentValue"))
        threshold = optional_float(composite.get("alertThreshold"))
        hit = optional_float(composite.get("hitRateOos"))
        base = optional_float(composite.get("baseRate"))
        lead = optional_float(composite.get("leadTimeDays"))
        lift = optional_float(composite.get("lift"))
        breach_count_total = composite.get("breachCountTotal")
        hit_rate_total = optional_float(composite.get("breachHitRateTotal"))
        breach_events = composite.get("breachEvents", [])
        digits = 2
    else:
        validated = region_validated_leading_factors(factor_validation)
        risk_validated = [factor for factor in validated if factor["id"] in REGIONAL_RISK_FACTOR_IDS]
        if not risk_validated:
            return {"available": False}
        top = risk_validated[0]
        factor_row = next(
            (item for item in factor_validation.get("factors", []) if isinstance(item, dict) and item.get("id") == top["id"]),
            {},
        )
        source, label, factor_id = "factor", top["labelCn"], top["id"]
        threshold = optional_float(factor_row.get("alertThreshold"))
        current = region_current_factor_reading(top["id"], representative)
        hit = optional_float(factor_row.get("hitRateOos"))
        base = optional_float(factor_row.get("baseRate"))
        lead = optional_float(factor_row.get("leadTimeDays"))
        lift = optional_float(top.get("lift"))
        breach_count_total = factor_row.get("alertCountTotal")
        hit_rate_total = optional_float(factor_row.get("hitRateTotal"))
        breach_events = factor_row.get("breachEvents", [])
        digits = 1

    if threshold is None or current is None:
        return {"available": False}
    if current >= threshold:
        state, state_cn = "breached", "已突破"
    elif current >= threshold * 0.9:
        state, state_cn = "approaching", "逼近"
    else:
        state, state_cn = "normal", "正常"
    evidence = ""
    if hit is not None and base is not None:
        evidence = f"历史命中 {hit * 100:.0f}% vs 基准 {base * 100:.0f}%"
        if lead is not None:
            evidence += f"、提前{lead:.0f}天"
    track_record = ""
    if breach_count_total is not None and hit_rate_total is not None:
        track_record = f"历史共突破{int(breach_count_total)}次, 命中{hit_rate_total * 100:.0f}%"
    state_word = "突破" if state == "breached" else "逼近" if state == "approaching" else "低于"
    return {
        "available": True,
        "source": source,
        "factorId": factor_id,
        "factorLabelCn": label,
        "current": round(current, digits),
        "threshold": round(threshold, digits),
        "state": state,
        "stateCn": state_cn,
        "lift": lift,
        "leadTimeDays": lead,
        "evidence": evidence,
        "breachCountTotal": breach_count_total,
        "breachHitRateTotal": hit_rate_total,
        "breachEvents": breach_events[-12:] if isinstance(breach_events, list) else [],
        "trackRecord": track_record,
        "message": (
            f"{label} {current:.{digits}f} {state_word}验证阈值 {threshold:.{digits}f}"
            + (f"; {evidence}" if evidence else "")
            + (f"; {track_record}" if track_record else "")
        ),
    }


def region_current_factor_reading(factor_id: str, representative: dict[str, Any]) -> float | None:
    """Current reading of a validated factor on its representative index, in the SAME units
    the validation series used (realizedVol as annualized %, lpplScore 0-100)."""
    if factor_id == "realizedVol":
        price_factors = representative.get("priceFactors") if isinstance(representative.get("priceFactors"), dict) else {}
        return optional_float(price_factors.get("realizedVol"))
    if factor_id == "lpplScore":
        return optional_float(representative.get("score"))
    return None


def build_region_allocation(region: dict[str, Any]) -> dict[str, Any]:
    aggregate = region.get("aggregate", {}) if isinstance(region.get("aggregate"), dict) else {}
    price_factors = aggregate.get("priceFactors", {}) if isinstance(aggregate.get("priceFactors"), dict) else {}
    bubble_status = str(aggregate.get("status") or "")
    market_state = str(price_factors.get("marketState") or "neutral")
    relative_strength = optional_float(price_factors.get("relativeStrength3m"))
    representative = regional_representative_index(region.get("indices", []) if isinstance(region.get("indices"), list) else [])
    validated = region_validated_leading_factors(representative.get("factorValidation") if representative else None)

    days_to_critical = optional_float(aggregate.get("minDaysToCritical"))
    caution = 0.0
    drivers: list[str] = []
    if bubble_status == "risk":
        caution += 40.0
        drivers.append("泡沫临界风险")
    elif bubble_status == "watch":
        caution += 18.0
        drivers.append("泡沫观察区")
    if market_state == "stressed":
        caution += 30.0
        drivers.append("市场承压(跌破趋势+深回撤)")
    elif market_state == "neutral":
        caution += 10.0
    else:
        drivers.append("市场偏强")
    if relative_strength is not None:
        # Strong momentum tempers but does NOT cancel a validated bubble warning — a leading
        # signal fires while price is still rising, so cap the relief at -8.
        if relative_strength <= -5.0:
            caution += 10.0
            drivers.append(f"跑输美国 {relative_strength:.0f}%")
        elif relative_strength >= 5.0:
            caution -= 8.0
            drivers.append(f"跑赢美国 +{relative_strength:.0f}%")
    # Evidence-backed conviction: a validated leading risk factor while bubble is flagged.
    if validated and bubble_status in {"risk", "watch"} and any(f["id"] in REGIONAL_RISK_FACTOR_IDS for f in validated):
        caution += 12.0
        drivers.append("已验证领先因子佐证")
    # Live trigger: the validated leading risk factor has BREACHED its calibrated threshold.
    factor_alert = region.get("factorAlert") if isinstance(region.get("factorAlert"), dict) else {}
    if factor_alert.get("available") and factor_alert.get("state") == "breached":
        caution += 15.0
        drivers.append(f"{factor_alert.get('factorLabelCn') or '领先因子'}突破验证阈值")
    # Imminent LPPL critical window adds urgency.
    if days_to_critical is not None and days_to_critical <= 30:
        caution += 10.0
        drivers.append(f"临界窗口仅{days_to_critical:.0f}天")
    caution = max(0.0, min(100.0, caution))

    # Overweight requires a genuinely constructive trend AND low caution — not merely the
    # absence of acute risk; a bubble-watch or neutral-trend region stays at most neutral.
    if caution >= 50.0:
        stance, stance_cn, band = "underweight", "减持", [50, 75]
    elif caution <= 10.0 and market_state == "constructive":
        stance, stance_cn, band = "overweight", "增持", [100, 115]
    else:
        stance, stance_cn, band = "neutral", "中性", [80, 100]

    # Conviction is high only when the region has a factor with PROVEN OOS lead power.
    confidence = "high" if validated else ("medium" if drivers else "low")
    confidence_cn = {"high": "高", "medium": "中", "low": "低"}[confidence]
    return {
        "stance": stance,
        "stanceCn": stance_cn,
        "cautionScore": round(caution, 1),
        "exposureBandPct": band,
        "confidence": confidence,
        "confidenceCn": confidence_cn,
        "drivers": drivers,
        "validatedLeadingFactors": validated,
        "rationale": build_region_alloc_rationale(region, stance_cn, bubble_status, aggregate, price_factors, validated),
    }


def build_region_alloc_rationale(
    region: dict[str, Any],
    stance_cn: str,
    bubble_status: str,
    aggregate: dict[str, Any],
    price_factors: dict[str, Any],
    validated: list[dict[str, Any]],
) -> str:
    name = str(region.get("nameCn") or region.get("name") or "")
    bubble_cn = str(aggregate.get("statusCn") or "--")
    state_cn = str(price_factors.get("marketStateCn") or "--")
    parts = [f"{name}: 泡沫{bubble_cn}、市场{state_cn}".replace("泡沫泡沫", "泡沫")]
    relative_strength = optional_float(price_factors.get("relativeStrength3m"))
    if relative_strength is not None:
        parts.append(f"相对美国{relative_strength:+.0f}%")
    if validated:
        top = validated[0]
        lead = top.get("leadTimeDays")
        lead_text = f"、提前{lead:.0f}天" if lead is not None else ""
        parts.append(f"{top['labelCn']}为本地区已验证领先因子(OOS lift {top['lift']}{lead_text}),信号可信")
    else:
        parts.append("尚无 OOS 验证领先因子,信号置信偏低")
    return "; ".join(parts) + f" → {stance_cn}。"


REGIONAL_CORRELATION_CLUSTER_THRESHOLD = 0.7


def cluster_correlated_regions(keys: list[str], diversification: dict[str, Any] | None) -> list[list[str]]:
    """Union-find grouping of regions whose pairwise weekly-return correlation is high
    (>= threshold) — co-moving regions are effectively ONE risk exposure."""
    if not keys:
        return []
    matrix = diversification.get("matrix", []) if isinstance(diversification, dict) else []
    parent = {key: key for key in keys}

    def find(node: str) -> str:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    key_set = set(keys)
    for pair in matrix:
        if not isinstance(pair, dict):
            continue
        a, b = str(pair.get("a")), str(pair.get("b"))
        if a in key_set and b in key_set and (optional_float(pair.get("corr")) or 0.0) >= REGIONAL_CORRELATION_CLUSTER_THRESHOLD:
            parent[find(b)] = find(a)
    groups: dict[str, list[str]] = {}
    for key in keys:
        groups.setdefault(find(key), []).append(key)
    # Preserve input order within and across clusters.
    ordered = sorted(groups.values(), key=lambda members: keys.index(members[0]))
    return [sorted(members, key=keys.index) for members in ordered]


US_INTERNAL_BROAD_SYMBOL = "SPY"
US_INTERNAL_TECH_SYMBOL = "QQQ"


def us_index_risk_points(index: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """A small, scale-free risk tally for a US index from its bubble status, LPPL score
    and realized volatility (each compared head-to-head against the other index)."""
    price_factors = index.get("priceFactors") if isinstance(index.get("priceFactors"), dict) else {}
    return 0, {
        "symbol": str(index.get("symbol") or "").upper(),
        "statusSeverity": REGION_STATUS_SEVERITY.get(str(index.get("status") or ""), 0),
        "statusCn": str(index.get("statusCn") or ""),
        "lpplScore": optional_float(index.get("score")),
        "realizedVol": optional_float(price_factors.get("realizedVol")),
        "marketStateCn": str(price_factors.get("marketStateCn") or ""),
    }


def build_us_internal_rotation(us_region: dict[str, Any]) -> dict[str, Any]:
    """US-internal factor rotation: compare broad (SPY) vs tech (QQQ) on bubble status,
    LPPL score and realized vol → tilt toward the lower-risk sleeve. Descriptive risk-control
    overlay within the US bucket, not a return forecast."""
    indices = {str(i.get("symbol") or "").upper(): i for i in us_region.get("indices", []) if isinstance(i, dict)}
    broad = indices.get(US_INTERNAL_BROAD_SYMBOL)
    tech = indices.get(US_INTERNAL_TECH_SYMBOL)
    if not broad or not tech:
        return {"available": False, "reason": "美国地区缺少 SPY/QQQ 双指数,暂不能内部轮动。"}
    _, broad_stats = us_index_risk_points(broad)
    _, tech_stats = us_index_risk_points(tech)

    drivers: list[str] = []
    broad_points = 0
    tech_points = 0

    def compare(value_broad: float | None, value_tech: float | None, label: str, fmt: str = "{:.0f}") -> None:
        nonlocal broad_points, tech_points
        if value_broad is None or value_tech is None:
            return
        if value_tech > value_broad:
            tech_points += 1
            drivers.append(f"科技{label}更高({fmt.format(value_tech)} vs {fmt.format(value_broad)})")
        elif value_broad > value_tech:
            broad_points += 1
            drivers.append(f"宽基{label}更高({fmt.format(value_broad)} vs {fmt.format(value_tech)})")

    compare(float(broad_stats["statusSeverity"]), float(tech_stats["statusSeverity"]), "泡沫状态")
    compare(broad_stats["lpplScore"], tech_stats["lpplScore"], "LPPL评分")
    compare(broad_stats["realizedVol"], tech_stats["realizedVol"], "已实现波动")

    if tech_points > broad_points:
        tilt, tilt_cn = "broad", "偏宽基(SPY)、减科技(QQQ)"
        riskier = "科技(QQQ)"
    elif broad_points > tech_points:
        tilt, tilt_cn = "tech", "偏科技(QQQ)、减宽基(SPY)"
        riskier = "宽基(SPY)"
    else:
        tilt, tilt_cn = "balanced", "宽基/科技均衡"
        riskier = ""
    rationale = (
        f"美股内部: {riskier}风险读数更高 → {tilt_cn}" + (f"; 依据: {'、'.join(drivers)}" if drivers else "")
        if riskier
        else f"美股内部: 宽基与科技风险读数相当 → {tilt_cn}"
    )
    return {
        "available": True,
        "tilt": tilt,
        "tiltCn": tilt_cn,
        "broadPoints": broad_points,
        "techPoints": tech_points,
        "broad": broad_stats,
        "tech": tech_stats,
        "drivers": drivers,
        "rationale": rationale,
        "method": "美股内部因子轮动: SPY宽基 vs QQQ科技, 逐项(泡沫/LPPL/波动)比较风险读数, 倾向风险更低的一侧。描述性风控叠加, 非收益预测。",
    }


def merged_cluster_band(bands: list[Any]) -> list[float] | None:
    """Element-wise min of member exposure bands — correlated regions share the tightest
    (most conservative) single allocation band rather than each cutting independently."""
    valid = [band for band in bands if isinstance(band, list) and len(band) == 2]
    if not valid:
        return None
    return [min(band[0] for band in valid), min(band[1] for band in valid)]


def build_regional_rotation(regions: list[dict[str, Any]], diversification: dict[str, Any] | None = None) -> dict[str, Any]:
    scored = [
        region for region in regions
        if isinstance(region.get("allocation"), dict) and region["aggregate"].get("availableCount", 0) > 0
    ]
    if not scored:
        return {"available": False, "favorRegions": [], "reduceRegions": [], "reduceClusters": [], "summary": "暂无地区配置建议。"}
    name_by_key = {region["key"]: region["nameCn"] for region in scored}
    favor = [region["key"] for region in scored if region["allocation"]["stance"] == "overweight"]
    reduce_regions = [region["key"] for region in scored if region["allocation"]["stance"] == "underweight"]
    ranked = sorted(scored, key=lambda region: region["allocation"]["cautionScore"])

    # Merge risk budget: co-moving reduce-regions count as one exposure, not independent cuts.
    reduce_clusters_keys = cluster_correlated_regions(reduce_regions, diversification)
    band_by_key = {
        region["key"]: region["allocation"].get("exposureBandPct")
        for region in scored
        if isinstance(region["allocation"].get("exposureBandPct"), list)
    }
    reduce_clusters = [
        {
            "regions": cluster,
            "names": [name_by_key.get(key, key) for key in cluster],
            "merged": len(cluster) > 1,
            # Correlated regions share ONE risk budget: the cluster's allowance is the tightest
            # member band (element-wise min), applied to the cluster as a single exposure — not
            # N independent cuts that would over-reduce a single underlying bet.
            "exposureBandPct": merged_cluster_band([band_by_key.get(key) for key in cluster]),
        }
        for cluster in reduce_clusters_keys
    ]
    independent_cuts = len(reduce_clusters)
    redundant = any(cluster["merged"] for cluster in reduce_clusters)

    favor_names = "、".join(region["nameCn"] for region in scored if region["key"] in favor)
    reduce_names = "、".join(region["nameCn"] for region in scored if region["key"] in reduce_regions)
    if favor_names and reduce_names:
        summary = f"地区轮动: 增持{favor_names}; 减持{reduce_names}(泡沫/承压且多有已验证领先因子佐证)。"
    elif reduce_names:
        summary = f"地区轮动: 建议减持{reduce_names}; 其余维持中性。"
    elif favor_names:
        summary = f"地区轮动: 可增持{favor_names}; 其余维持中性。"
    else:
        summary = "地区轮动: 各地区均维持中性,无显著倾斜。"
    if redundant and len(reduce_regions) > independent_cuts:
        merged_notes = []
        for cluster in reduce_clusters:
            if not cluster["merged"]:
                continue
            band = cluster.get("exposureBandPct")
            band_text = f"共享仓位带 {band[0]:.0f}-{band[1]:.0f}%" if isinstance(band, list) and len(band) == 2 else ""
            merged_notes.append("+".join(cluster["names"]) + (f"({band_text})" if band_text else ""))
        summary += (
            f" 注意: {'、'.join(merged_notes)}高度相关, 实为同一风险敞口, "
            f"{len(reduce_regions)}个减持其实只是{independent_cuts}个独立风险预算——同簇地区共享一个减仓额度, 勿叠加减仓。"
        )
    return {
        "available": True,
        "favorRegions": favor,
        "reduceRegions": reduce_regions,
        "reduceClusters": reduce_clusters,
        "independentReduceCount": independent_cuts,
        "ranking": [region["key"] for region in ranked],
        "summary": summary,
        "method": "风险-轮动叠加层: 据泡沫状态、市场状态(趋势/回撤)、相对美国强弱合成谨慎度,并以各地区自身 OOS 验证的领先因子决定置信; 高相关减持地区合并为同一风险预算。属风险控制叠加,非收益预测。",
    }


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
        return unavailable_global_lppl_risk(index_rows, "全球LPPL逐市场评估需要至少一个可回放指数样本; 当前公开日线源不足。")

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
        "indices": index_rows,
        "indexValidation": index_validation,
        "breadthConfirmation": breadth_confirmation,
        "history": {
            "available": False,
            "points": [],
            "summary": "Top-level aggregate LPPL history is disabled; use perIndexHistory or indices[].history.",
        },
        "backtest": {
            "available": False,
            "sampleSize": 0,
            "threshold": GLOBAL_LPPL_ALERT_THRESHOLD,
            "horizonTests": [],
            "summary": "Top-level aggregate LPPL backtest is disabled; use perIndexBacktests or indices[].backtest.",
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


def unavailable_global_lppl_risk(index_rows: list[dict[str, Any]], reason: str) -> dict[str, Any]:
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
        "indices": index_rows,
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
        "perIndexHistory": {},
        "perIndexBacktests": {},
        "lookAheadGuard": {"scoreUse": "independent; not included in equityShortTermRisk."},
    }


def global_lppl_index_row(
    spec: dict[str, Any],
    bars: list[MarketDailyBar],
    *,
    as_of: date | None = None,
    fast: bool = False,
) -> dict[str, Any]:
    symbol = str(spec.get("symbol") or "").upper()
    clean = normalize_market_bars({symbol: bars}).get(symbol, [])
    target_index = bar_index_at_or_before(clean, as_of) if as_of else (len(clean) - 1 if clean else None)
    if target_index is None or target_index + 1 < GLOBAL_LPPL_MIN_OBSERVATIONS:
        return {
            "symbol": symbol,
            "name": str(spec.get("name") or symbol),
            "region": str(spec.get("region") or ""),
        "regionKey": str(spec.get("regionKey") or ""),
        "regionName": str(spec.get("regionName") or spec.get("region") or ""),
        "regionNameCn": str(spec.get("regionNameCn") or ""),
        "proxyNote": str(spec.get("proxyNote") or ""),
        "proxyNoteCn": str(spec.get("proxyNoteCn") or ""),
            "available": False,
            "score": None,
            "confidence": 0.0,
            "status": "missing",
            "statusCn": "缺失",
            "criticalDate": None,
            "daysToCritical": None,
            "fitR2": None,
            "windowDays": None,
            "observations": len(clean),
            "source": str(spec.get("source") or ""),
            "sourceSymbol": str(spec.get("sourceSymbol") or symbol),
            "sourceQuality": str(spec.get("sourceQuality") or "low"),
            "reason": "source unavailable or sample shorter than LPPL minimum window",
        }
    fit = fit_global_lppl_signal(clean[: target_index + 1], fast=fast)
    latest = clean[target_index]
    if not fit.get("available"):
        return {
            "symbol": symbol,
            "name": str(spec.get("name") or symbol),
            "region": str(spec.get("region") or ""),
        "regionKey": str(spec.get("regionKey") or ""),
        "regionName": str(spec.get("regionName") or spec.get("region") or ""),
        "regionNameCn": str(spec.get("regionNameCn") or ""),
        "proxyNote": str(spec.get("proxyNote") or ""),
        "proxyNoteCn": str(spec.get("proxyNoteCn") or ""),
            "available": False,
            "score": None,
            "confidence": 0.0,
            "status": "missing",
            "statusCn": "缺失",
            "criticalDate": None,
            "daysToCritical": None,
            "fitR2": None,
            "windowDays": None,
            "observations": target_index + 1,
            "source": str(spec.get("source") or ""),
            "sourceSymbol": str(spec.get("sourceSymbol") or symbol),
            "sourceQuality": str(spec.get("sourceQuality") or "low"),
            "asOf": latest.date.isoformat(),
            "reason": str(fit.get("reason") or "LPPL fit unavailable"),
        }
    score = bounded_score(float(fit["score"]))
    confidence = max(0.0, min(1.0, float(fit.get("confidence") or 0.0)))
    status, status_cn = global_lppl_status(score, confidence)
    days_to_critical = int(fit["daysToCritical"])
    critical_date = latest.date + timedelta(days=days_to_critical)
    return {
        "symbol": symbol,
        "name": str(spec.get("name") or symbol),
        "region": str(spec.get("region") or ""),
        "regionKey": str(spec.get("regionKey") or ""),
        "regionName": str(spec.get("regionName") or spec.get("region") or ""),
        "regionNameCn": str(spec.get("regionNameCn") or ""),
        "proxyNote": str(spec.get("proxyNote") or ""),
        "proxyNoteCn": str(spec.get("proxyNoteCn") or ""),
        "available": True,
        "score": round(score, 1),
        "confidence": round(confidence, 2),
        "status": status,
        "statusCn": status_cn,
        "criticalDate": critical_date.isoformat(),
        "daysToCritical": days_to_critical,
        "daysToCriticalRange": fit.get("daysToCriticalRange"),
        "fitR2": round(float(fit["fitR2"]), 3),
        "fitSse": round(float(fit.get("fitSse") or 0.0), 6),
        "lpplImprovementPct": round(float(fit.get("lpplImprovementPct") or 0.0), 1),
        "oscillationCount": round(float(fit.get("oscillationCount") or 0.0), 2),
        "passesLpplCoreDiagnostics": bool(fit.get("passesLpplCoreDiagnostics")),
        "passesLpplDiagnostics": bool(fit.get("passesLpplDiagnostics")),
        "residualDiagnostics": fit.get("residualDiagnostics"),
        "fitEnsemble": fit.get("fitEnsemble"),
        "windowDays": int(fit["windowDays"]),
        "windowDaysRange": fit.get("windowDaysRange"),
        "selectionBasis": str(fit.get("selectionBasis") or "fit_quality"),
        "observations": target_index + 1,
        "asOf": latest.date.isoformat(),
        "source": str(spec.get("source") or ""),
        "sourceSymbol": str(spec.get("sourceSymbol") or symbol),
        "sourceQuality": str(spec.get("sourceQuality") or "low"),
        "weight": float(spec.get("weight") or 0.0),
        "trailingReturn63d": pct_metric(fit.get("trailingReturn63d")),
        "acceleration": pct_metric(fit.get("acceleration")),
        "bubbleCoefficient": round(float(fit.get("bubbleCoefficient") or 0.0), 4),
        "oscillationAmplitude": round(float(fit.get("oscillationAmplitude") or 0.0), 4),
        "reason": str(fit.get("reason") or ""),
    }


def build_global_lppl_per_index_histories(
    index_rows: list[dict[str, Any]],
    bars_by_symbol: dict[str, list[MarketDailyBar]],
) -> dict[str, Any]:
    histories: dict[str, Any] = {}
    for row in index_rows:
        symbol = str(row.get("symbol") or "").upper()
        if not symbol:
            continue
        histories[symbol] = build_global_lppl_single_index_history(row, bars_by_symbol.get(symbol, []))
    return histories


def build_global_lppl_single_index_history(
    index_row: dict[str, Any],
    bars: list[MarketDailyBar],
) -> dict[str, Any]:
    symbol = str(index_row.get("symbol") or "").upper()
    clean = normalize_market_bars({symbol: bars}).get(symbol, [])
    if len(clean) < GLOBAL_LPPL_MIN_OBSERVATIONS:
        return {"available": False, "symbol": symbol, "points": [], "summary": "source unavailable or sample shorter than LPPL minimum window"}
    score_points = build_single_index_lppl_history_points(symbol, clean)
    if not score_points:
        return {"available": False, "symbol": symbol, "points": [], "summary": "LPPL history replay produced no valid fit points"}
    first_index = bar_index_at_or_before(clean, parse_lppl_point_date(score_points[0].get("date")) or clean[0].date)
    base_close = clean[first_index if first_index is not None else 0].close
    points: list[dict[str, Any]] = []
    for point in score_points:
        point_date = parse_lppl_point_date(point.get("date"))
        bar_index = bar_index_at_or_before(clean, point_date) if point_date else None
        if bar_index is None:
            continue
        close = clean[bar_index].close
        enriched = {
            "date": clean[bar_index].date.isoformat(),
            "score": point["score"],
            "close": round(close, 2),
            "indexedClose": round(100 * close / base_close, 2) if base_close > 0 else None,
        }
        for key in (
            "criticalDate",
            "daysToCritical",
            "passesLpplCoreDiagnostics",
            "passesLpplDiagnostics",
            "lpplImprovementPct",
            "oscillationCount",
        ):
            if key in point:
                enriched[key] = point[key]
        points.append(enriched)
    if len(points) < 2:
        return {"available": False, "symbol": symbol, "points": points, "summary": "LPPL history replay has fewer than two chartable points"}
    clip_state = build_lppl_clip_state(points)
    return {
        "available": True,
        "symbol": symbol,
        "name": str(index_row.get("name") or symbol),
        "sourceSymbol": str(index_row.get("sourceSymbol") or symbol),
        "summary": f"{symbol} LPPL replay; risk score and indexed own-market price are shown on separate axes.",
        "points": points,
        "dateRange": {"start": points[0]["date"], "end": points[-1]["date"]},
        "clipState": clip_state,
    }


def parse_lppl_point_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def build_lppl_clip_state(points: list[dict[str, Any]], *, lookback: int = 20) -> dict[str, Any]:
    observations: list[dict[str, Any]] = []
    for point in points:
        if not isinstance(point, dict):
            continue
        point_date = parse_lppl_point_date(point.get("date"))
        critical_date = parse_lppl_point_date(point.get("criticalDate"))
        if point_date is None or critical_date is None:
            continue
        observations.append(
            {
                "date": point_date,
                "criticalDate": critical_date,
                "score": optional_float(point.get("score")),
                "passesCore": bool(point.get("passesLpplCoreDiagnostics")),
            }
        )
    if len(observations) < 5:
        return {
            "available": False,
            "clipLock": False,
            "status": "insufficient",
            "statusCn": "样本不足",
            "sampleSize": len(observations),
            "summary": "CLIP requires at least five replay points with critical dates.",
        }
    recent = observations[-max(5, lookback):]
    critical_ordinals = sorted(item["criticalDate"].toordinal() for item in recent)
    q20 = lppl_percentile(critical_ordinals, 0.20)
    q50 = lppl_percentile(critical_ordinals, 0.50)
    q80 = lppl_percentile(critical_ordinals, 0.80)
    tc_window_days = max(0, int(round(q80 - q20)))
    latest_observation = max(item["date"] for item in recent)
    median_lead_days = int(round(q50 - latest_observation.toordinal()))
    core_pass_ratio = sum(1 for item in recent if item["passesCore"]) / len(recent)
    clip_lock = tc_window_days <= 30 and 5 <= median_lead_days <= 180 and core_pass_ratio >= 0.50
    converging = tc_window_days <= 60 and 5 <= median_lead_days <= 252 and core_pass_ratio >= 0.35
    if clip_lock:
        status, status_cn = "locked", "CLIP锁定"
    elif converging:
        status, status_cn = "converging", "CLIP收敛"
    elif median_lead_days < 0:
        status, status_cn = "expired", "临界已过"
    else:
        status, status_cn = "scattered", "临界分散"
    return {
        "available": True,
        "clipLock": clip_lock,
        "status": status,
        "statusCn": status_cn,
        "sampleSize": len(recent),
        "lookback": max(5, lookback),
        "tcMedian": date.fromordinal(int(round(q50))).isoformat(),
        "tcQ20": date.fromordinal(int(round(q20))).isoformat(),
        "tcQ80": date.fromordinal(int(round(q80))).isoformat(),
        "tcWindowDays": tc_window_days,
        "medianLeadDays": median_lead_days,
        "corePassRatio": round(core_pass_ratio, 3),
        "summary": (
            f"CLIP {status_cn}: recent tc 20-80% window {tc_window_days} days, "
            f"median lead {median_lead_days} days, core pass {core_pass_ratio:.0%}."
        ),
    }


def build_global_lppl_per_index_backtests(
    histories: dict[str, Any],
    bars_by_symbol: dict[str, list[MarketDailyBar]],
) -> dict[str, Any]:
    backtests: dict[str, Any] = {}
    for symbol, history in histories.items():
        points = history.get("points", []) if isinstance(history, dict) else []
        backtests[symbol] = build_global_lppl_backtest(points, bars_by_symbol.get(symbol, []), symbol=symbol)
    return backtests


def attach_global_lppl_per_index_payloads(
    index_rows: list[dict[str, Any]],
    histories: dict[str, Any],
    backtests: dict[str, Any],
) -> list[dict[str, Any]]:
    enriched_rows: list[dict[str, Any]] = []
    for row in index_rows:
        enriched = dict(row)
        symbol = str(enriched.get("symbol") or "").upper()
        enriched["history"] = histories.get(symbol, {"available": False, "symbol": symbol, "points": []})
        enriched["backtest"] = backtests.get(symbol, {"available": False, "sampleSize": 0, "horizonTests": []})
        history_clip = enriched["history"].get("clipState") if isinstance(enriched.get("history"), dict) else None
        if isinstance(history_clip, dict):
            enriched["clipState"] = history_clip
        enriched_rows.append(enriched)
    return enriched_rows


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
    backtest = row.get("backtest") if isinstance(row.get("backtest"), dict) else {}
    validation = row.get("validation") if isinstance(row.get("validation"), dict) else {}
    threshold = optional_float(backtest.get("threshold") if isinstance(backtest, dict) else None)
    if threshold is None:
        threshold = optional_float(validation.get("threshold") if isinstance(validation, dict) else None)
    if threshold is None:
        threshold = GLOBAL_LPPL_ALERT_THRESHOLD
    threshold_distance = model_score - threshold
    days_to_critical = optional_float(row.get("daysToCritical"))
    confidence = max(0.0, min(1.0, optional_float(row.get("confidence")) or 0.0))
    validation_multiplier = optional_float(validation.get("effectiveWeightMultiplier")) if isinstance(validation, dict) else None
    if validation_multiplier is None:
        validation_multiplier = optional_float(row.get("effectiveWeightMultiplier"))
    validation_multiplier = max(0.0, min(1.0, validation_multiplier if validation_multiplier is not None else 0.75))
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
            adjusted["effectiveWeightMultiplier"] = 0.75
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
    summary = f"{len(rows)} indices replayed; {validated} validated, {weak} weak by own-market 15D drawdown audit."
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
    calibration_grid = [
        equity_backtest_threshold_test(candidate_threshold, observations, drawdown_threshold_pct, horizon=15)
        for candidate_threshold in (55, 60, 65, 70, 75, 80, 85, 90)
    ]
    recommended = global_lppl_recommended_threshold(calibration_grid, len(observations))
    threshold = int(recommended.get("threshold") or GLOBAL_LPPL_ALERT_THRESHOLD)
    test_15d = equity_backtest_threshold_test(threshold, observations, drawdown_threshold_pct, horizon=15)
    multiplier, role, role_cn = global_lppl_validation_weight(test_15d)
    precision = optional_float(test_15d.get("precision"))
    recall = optional_float(test_15d.get("recall"))
    payload = {
        "symbol": symbol,
        "sourceSymbol": str(index_row.get("sourceSymbol") or symbol),
        "sampleSize": len(observations),
        "historyPoints": len(points),
        "threshold": threshold,
        "alertDays": int(test_15d.get("alertDays") or 0),
        "truePositives": int(test_15d.get("truePositives") or 0),
        "falsePositives": int(test_15d.get("falsePositives") or 0),
        "precision15d": round(precision, 1) if precision is not None else None,
        "recall15d": round(recall, 1) if recall is not None else None,
        "baseRate15d": test_15d.get("baseRate"),
        "avgMaxDrawdown15dWhenAlert": test_15d.get("avgMaxDrawdownWhenAlert"),
        "avgDrawdownLeadDaysWhenHit": test_15d.get("avgDrawdownLeadDaysWhenHit"),
        "effectiveWeightMultiplier": multiplier,
        "validationRole": role,
        "validationRoleCn": role_cn,
        "summary": global_lppl_validation_summary(symbol, test_15d, multiplier, role_cn),
    }
    payload.update(global_lppl_oos_validation_fields(observations, drawdown_threshold_pct))
    return payload


def global_lppl_oos_validation_fields(
    observations: list[dict[str, Any]],
    drawdown_threshold_pct: float,
) -> dict[str, Any]:
    """Out-of-sample audit: the recommended threshold is chosen on the first 65%
    of the replay and then evaluated only on the untouched last 35%."""
    split_index = max(1, min(len(observations) - 1, int(len(observations) * SIGNAL_VALIDATION_OOS_SPLIT)))
    calibration_obs = observations[:split_index]
    evaluation_obs = observations[split_index:]
    if len(calibration_obs) < 20 or len(evaluation_obs) < 10:
        return {"oosAvailable": False}
    oos_grid = [
        equity_backtest_threshold_test(candidate_threshold, calibration_obs, drawdown_threshold_pct, horizon=15)
        for candidate_threshold in (55, 60, 65, 70, 75, 80, 85, 90)
    ]
    oos_recommended = global_lppl_recommended_threshold(oos_grid, len(calibration_obs))
    oos_threshold = int(oos_recommended.get("threshold") or GLOBAL_LPPL_ALERT_THRESHOLD)
    oos_test = equity_backtest_threshold_test(oos_threshold, evaluation_obs, drawdown_threshold_pct, horizon=15)
    oos_precision = optional_float(oos_test.get("precision"))
    oos_recall = optional_float(oos_test.get("recall"))
    return {
        "oosAvailable": True,
        "oosThreshold": oos_threshold,
        "oosSampleSize": len(evaluation_obs),
        "oosAlertDays": int(oos_test.get("alertDays") or 0),
        "precision15dOos": round(oos_precision, 1) if oos_precision is not None else None,
        "recall15dOos": round(oos_recall, 1) if oos_recall is not None else None,
        "baseRate15dOos": oos_test.get("baseRate"),
    }


def build_single_index_lppl_history_points(symbol: str, bars: list[MarketDailyBar]) -> list[dict[str, Any]]:
    if len(bars) < GLOBAL_LPPL_MIN_OBSERVATIONS:
        return []
    points: list[dict[str, Any]] = []
    start_index = GLOBAL_LPPL_MIN_OBSERVATIONS - 1
    step = max(1, GLOBAL_LPPL_HISTORY_STEP)
    replay_indices = list(range(start_index, len(bars), step))
    if replay_indices[-1] != len(bars) - 1:
        replay_indices.append(len(bars) - 1)
    spec = {"symbol": symbol, "name": symbol, "region": symbol, "sourceQuality": "validation", "sourceSymbol": symbol}
    for index in replay_indices:
        target = bars[index].date
        row = global_lppl_index_row(spec, bars, as_of=target, fast=True)
        score = optional_float(row.get("score"))
        if row.get("available") and score is not None:
            point = {"date": target.isoformat(), "score": round(bounded_score(score), 1)}
            for key in (
                "criticalDate",
                "daysToCritical",
                "passesLpplCoreDiagnostics",
                "passesLpplDiagnostics",
                "lpplImprovementPct",
                "oscillationCount",
            ):
                if key in row:
                    point[key] = row[key]
            points.append(point)
    return points


def build_global_lppl_validation_observations(
    points: list[dict[str, Any]],
    bars: list[MarketDailyBar],
    drawdown_threshold_pct: float,
) -> list[dict[str, Any]]:
    index_by_date = {bar.date: index for index, bar in enumerate(bars)}
    observations: list[dict[str, Any]] = []
    for point in points:
        try:
            point_date = date.fromisoformat(str(point.get("date") or ""))
        except ValueError:
            continue
        score = optional_float(point.get("score"))
        index = index_by_date.get(point_date)
        if score is None or index is None or index + 1 >= len(bars):
            continue
        row = {"date": point_date.isoformat(), "score": round(bounded_score(score), 1)}
        for horizon in (5, 10, 15, 20):
            row[f"forward{horizon}d"] = equity_forward_return_pct(bars, index, horizon)
            drawdown = equity_forward_max_drawdown_pct(bars, index, horizon)
            row[f"maxDrawdown{horizon}d"] = drawdown
            row[f"drawdownEvent{horizon}d"] = drawdown is not None and drawdown <= drawdown_threshold_pct
            row[f"drawdownLeadDays{horizon}d"] = equity_forward_drawdown_lead_days(bars, index, horizon, drawdown_threshold_pct)
        observations.append(row)
    return observations


def global_lppl_validation_weight(test_15d: dict[str, Any]) -> tuple[float, str, str]:
    alert_days = optional_float(test_15d.get("alertDays")) or 0.0
    precision = optional_float(test_15d.get("precision"))
    base_rate = optional_float(test_15d.get("baseRate")) or 0.0
    if alert_days < 3 or precision is None:
        return 0.75, "thin", "样本偏少"
    if precision >= max(60.0, base_rate + 15.0):
        return 1.0, "validated", "验证支持"
    if precision >= base_rate + 5.0:
        return 0.85, "mixed", "部分支持"
    return 0.60, "weak", "历史偏弱"


def global_lppl_validation_summary(symbol: str, test_15d: dict[str, Any], multiplier: float, role_cn: str) -> str:
    return (
        f"{symbol} own-market 15D audit: threshold {test_15d.get('threshold')}, "
        f"precision {format_optional_percent_value(test_15d.get('precision'))}, "
        f"recall {format_optional_percent_value(test_15d.get('recall'))}, "
        f"false {test_15d.get('falsePositives', 0)}, weight x{multiplier:.2f} ({role_cn})."
    )


def global_lppl_status(score: float, confidence: float) -> tuple[str, str]:
    if score >= GLOBAL_LPPL_ALERT_THRESHOLD and confidence >= 0.35:
        return "risk", "泡沫风险"
    if score >= 45:
        return "watch", "观察"
    return "quiet", "低风险"


def global_lppl_regime(score: float) -> tuple[str, str]:
    if score >= 70:
        return "High Risk", "高风险"
    if score >= GLOBAL_LPPL_ALERT_THRESHOLD:
        return "Risk", "泡沫风险"
    if score >= 45:
        return "Watch", "观察"
    return "Quiet", "低风险"


def build_global_lppl_backtest(
    history_points: list[dict[str, Any]],
    market_bars: list[MarketDailyBar],
    *,
    symbol: str = "SPY",
    threshold: int = GLOBAL_LPPL_ALERT_THRESHOLD,
    drawdown_threshold_pct: float = -2.0,
) -> dict[str, Any]:
    symbol = symbol.upper()
    clean_bars = normalize_market_bars({symbol: market_bars}).get(symbol, [])
    if len(clean_bars) < 30 or not history_points:
        return {"available": False, "sampleSize": 0, "threshold": threshold, "horizonTests": [], "summary": f"{symbol}或LPPL历史样本不足。"}
    index_by_date = {bar.date: index for index, bar in enumerate(clean_bars)}
    observations: list[dict[str, Any]] = []
    for point in history_points:
        try:
            point_date = date.fromisoformat(str(point.get("date") or ""))
        except ValueError:
            continue
        score = optional_float(point.get("score"))
        index = index_by_date.get(point_date)
        if score is None or index is None or index + 1 >= len(clean_bars):
            continue
        row = {"date": point_date.isoformat(), "score": round(bounded_score(score), 1)}
        for horizon in (5, 10, 15, 20):
            row[f"forward{horizon}d"] = equity_forward_return_pct(clean_bars, index, horizon)
            drawdown = equity_forward_max_drawdown_pct(clean_bars, index, horizon)
            row[f"maxDrawdown{horizon}d"] = drawdown
            row[f"drawdownEvent{horizon}d"] = drawdown is not None and drawdown <= drawdown_threshold_pct
            row[f"drawdownLeadDays{horizon}d"] = equity_forward_drawdown_lead_days(clean_bars, index, horizon, drawdown_threshold_pct)
        observations.append(row)
    if not observations:
        return {"available": False, "sampleSize": 0, "threshold": threshold, "horizonTests": [], "summary": f"LPPL历史点没有足够后续{symbol}交易日。"}
    calibration_grid = [
        equity_backtest_threshold_test(candidate_threshold, observations, drawdown_threshold_pct, horizon=15)
        for candidate_threshold in (55, 60, 65, 70, 75, 80, 85, 90)
    ]
    recommended_threshold_test = global_lppl_recommended_threshold(calibration_grid, len(observations))
    threshold = int(recommended_threshold_test.get("threshold") or threshold)
    horizon_tests = [
        equity_backtest_threshold_test(threshold, observations, drawdown_threshold_pct, horizon=horizon)
        for horizon in (5, 10, 15, 20)
    ]
    preferred = next((row for row in horizon_tests if row["horizon"] == 15), horizon_tests[-1])
    alert_cluster_test = equity_backtest_alert_cluster_test(
        threshold,
        observations,
        drawdown_threshold_pct,
        horizon=15,
    )
    summary = (
        f"{symbol} LPPL score≥{threshold}历史告警{preferred.get('alertDays', 0)}次; "
        f"15D精确率{format_optional_percent_value(preferred.get('precision'))}, "
        f"误报{preferred.get('falsePositives', 0)}次; "
        f"最大误报簇{alert_cluster_test.get('maxFalseClusterDays', 0)}个点。"
    )
    return {
        "available": True,
        "sampleSize": len(observations),
        "threshold": threshold,
        "drawdownEvent": f"next 5/10/15/20 trading days max drawdown <= {drawdown_threshold_pct:.1f}%",
        "horizonTests": horizon_tests,
        "calibrationGrid": calibration_grid,
        "recommendedThreshold": recommended_threshold_test,
        "alertClusterTest": alert_cluster_test,
        "summary": summary,
    }


def global_lppl_recommended_threshold(calibration_grid: list[dict[str, Any]], sample_size: int) -> dict[str, Any]:
    candidates = [
        row
        for row in calibration_grid
        if (optional_float(row.get("alertDays")) or 0.0) >= max(3.0, min(10.0, sample_size / 25.0))
    ]
    if not candidates:
        candidates = [
            row
            for row in calibration_grid
            if (optional_float(row.get("alertDays")) or 0.0) > 0
        ]
    if not candidates:
        return {}
    base_rate = max(optional_float(row.get("baseRate")) or 0.0 for row in candidates)
    min_precision = max(45.0, base_rate + 8.0)
    qualifying = [row for row in candidates if (optional_float(row.get("precision")) or 0.0) >= min_precision]
    if not qualifying:
        qualifying = candidates

    def threshold_score(row: dict[str, Any]) -> tuple[float, float, float, float]:
        precision = optional_float(row.get("precision")) or 0.0
        recall = optional_float(row.get("recall")) or 0.0
        alert_days = optional_float(row.get("alertDays")) or 0.0
        threshold = optional_float(row.get("threshold")) or 0.0
        return (precision, recall, alert_days, threshold)

    selected = dict(max(qualifying, key=threshold_score))
    selected.update(
        {
            "key": "globalLpplRecommendedThreshold",
            "label": "LPPL推荐告警阈值",
            "labelEn": "Global LPPL Recommended Threshold",
            "useCase": "用历史SPY前瞻回撤验证后选择; 优先提高精确率,再考虑覆盖率。",
        }
    )
    return selected


def parse_payload_date(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def macro_liquidity_score_at(series: dict[str, list[SeriesPoint]], target: date) -> dict[str, Any] | None:
    row = bhadial_conditions_score_at(series, target)
    if row is None or row.get("observedFactorCount", 0) < 5:
        return None
    return {"score": row["score"], "coverage": row["observedFactorCount"]}


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
        ("HY信用偏好(HY/UST)", "FRED HY TR / DGS10 price proxy", "available up to 5Y", series.get("hy_credit_preference", []), 1, 2, ""),
        ("IG信用偏好(IG/UST)", "FRED IG TR / DGS10 price proxy", "available up to 5Y", series.get("ig_credit_preference", []), 1, 2, ""),
        ("金融条件指数(NFCI)", "FRED NFCI", "5Y", series.get("nfci", []), 1, 2, ""),
        ("银行股相对S&P500", "FRED NASDAQBANK / SP500", "5Y", series.get("regional_bank_vs_market", []), 1, 2, ""),
        ("风险资产/美债代理", "FRED SP500 / DGS10 price proxy", "5Y", series.get("risk_vs_safe", []), 1, 2, ""),
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


def auction_percentile_points(auctions: list[dict[str, object]], display_years: int = 3, max_points: int = 52) -> list[dict[str, Any]]:
    dated: list[tuple[date, float]] = []
    for auction in auctions:
        auction_date = parse_dashboard_date(auction.get("auctionDate"))
        btc = parse_number(auction.get("bidToCoverRatio"))
        if auction_date is not None and btc is not None and math.isfinite(btc):
            dated.append((auction_date, btc))
    dated.sort(key=lambda item: item[0])
    if not dated:
        return []
    display_start = window_start(dated[-1][0], years=display_years)
    visible_indices = [index for index, item in enumerate(dated) if item[0] >= display_start]
    sampled_visible_indices = sampled_indices(len(visible_indices), max_points)
    rows: list[dict[str, Any]] = []
    for visible_index in sampled_visible_indices:
        index = visible_indices[visible_index]
        auction_date, btc = dated[index]
        values = [item[1] for item in dated[: index + 1]]
        percentile = historical_percentile(btc, values)
        if percentile is None:
            continue
        rows.append({"date": auction_date.isoformat(), "value": round(btc, 2), "percentile": percentile})
    return rows


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


def auction_demand_signal(auctions: list[dict[str, object]]) -> dict[str, Any]:
    dated: list[tuple[date, float, str]] = []
    for auction in auctions:
        auction_date = parse_dashboard_date(auction.get("auctionDate"))
        btc = parse_number(auction.get("bidToCoverRatio"))
        if auction_date is None or btc is None:
            continue
        security_term = str(auction.get("securityTerm") or auction.get("term") or "").strip()
        security_type = str(auction.get("securityType") or auction.get("type") or "").strip()
        label = " ".join(part for part in (security_term, security_type) if part) or "Treasury auction"
        dated.append((auction_date, btc, label))
    if not dated:
        return {
            "tag": "TreasuryDirect",
            "label": "待结果",
            "score": 0,
            "note": "TreasuryDirect拍卖数据不可用时不填入历史百分位。",
            "value": "--",
            "percentile": None,
        }
    dated.sort(key=lambda item: item[0])
    latest_date, latest_btc, latest_label = dated[-1]
    percentile = historical_percentile(latest_btc, [item[1] for item in dated])
    score = 1 if percentile is not None and percentile >= 70 else -1 if percentile is not None and percentile <= 30 else 0
    label = "强劲" if score > 0 else "偏弱" if score < 0 else "中性"
    return {
        "tag": f"{latest_label} BTC {latest_btc:.2f} · {percentile_label(percentile)}",
        "label": label,
        "score": score,
        "note": f"TreasuryDirect最新拍卖 {latest_date.isoformat()} bid-to-cover相对可用历史样本的百分位。",
        "value": f"{latest_btc:.2f}",
        "percentile": percentile,
    }


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


def money_billions_value(value: float | None) -> str:
    if value is None:
        return "--"
    return f"${value:.0f}B"


def qra_supply_note(refunding: QuarterlyRefunding) -> str:
    parts = [f"官方QRA {refunding.release_date.isoformat()}"]
    if refunding.current_quarter_borrowing_billions is not None:
        parts.append(f"本季借款 {money_billions_value(refunding.current_quarter_borrowing_billions)}")
    if refunding.next_quarter_borrowing_billions is not None:
        parts.append(f"下季借款 {money_billions_value(refunding.next_quarter_borrowing_billions)}")
    if refunding.refunding_new_cash_billions is not None:
        parts.append(f"refunding新现金 {money_billions_value(refunding.refunding_new_cash_billions)}")
    if refunding.coupon_stance:
        parts.append(refunding.coupon_stance)
    return "; ".join(parts)


def parse_number(raw: object) -> float | None:
    if raw is None:
        return None
    try:
        return float(str(raw).replace(",", "").strip())
    except ValueError:
        return None


def parse_dashboard_date(raw: object) -> date | None:
    if raw is None:
        return None
    text = str(raw).strip()[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def money_from_raw_dollars(value: float) -> str:
    if abs(value) >= 1_000_000_000_000:
        return f"${value / 1_000_000_000_000:.2f}T"
    if abs(value) >= 1_000_000_000:
        return f"${value / 1_000_000_000:.0f}B"
    return f"${value / 1_000_000:.0f}M"


def format_yield(raw: str) -> str:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return "--"
    return f"{value:.3f}%"


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
            ["黄金现货", f"${ind['gold_spot']:.2f}", "Stooq XAUUSD"],
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


def build_ideas(
    ind: dict[str, Any],
    *,
    macro_liquidity: dict[str, Any] | None = None,
    macro_liquidity_equity: dict[str, Any] | None = None,
    quarterly_refunding: QuarterlyRefunding | None = None,
    conclusion_audit: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    liquidity_score = optional_float(macro_liquidity.get("score")) if macro_liquidity else None
    liquidity_regime = macro_liquidity.get("regime") if macro_liquidity else "待评分"
    liquidity_text = f"宏观环境评分{liquidity_score:.1f}({liquidity_regime})" if isinstance(liquidity_score, (int, float)) else f"宏观环境{liquidity_regime}"
    qra_text = "QRA待接入"
    qra_borrowing = None
    if quarterly_refunding:
        qra_borrowing = quarterly_refunding.next_quarter_borrowing_billions
        next_borrow = money_billions_value(qra_borrowing)
        next_date = quarterly_refunding.next_policy_statement_date.isoformat() if quarterly_refunding.next_policy_statement_date else "待公布"
        qra_text = f"QRA下季借款{next_borrow},下一次政策声明{next_date}"
    inflation_tracker = (
        f"CPI {ind['cpi_yoy']:.1f}% / PCE {ind['pce_yoy']:.1f}% / "
        f"核心PCE {ind['core_pce_yoy']:.1f}% / Dallas Trimmed PCE {ind['trimmed_mean_pce_yoy']:.1f}%"
    )
    inflation_max = max(ind["cpi_yoy"], ind["pce_yoy"], ind["core_pce_yoy"], ind["trimmed_mean_pce_yoy"], ind["ppi_yoy"])
    inflation_core_max = max(ind["pce_yoy"], ind["core_pce_yoy"], ind["trimmed_mean_pce_yoy"])
    inflation_hot = inflation_max >= 3.0
    inflation_cool = inflation_core_max <= 2.4 and ind["ppi_yoy"] <= 2.5
    two_year_change = ind["two_year_m1_change_bp"]
    macro_tight = liquidity_score is not None and liquidity_score < 45
    qra_supply_heavy = qra_borrowing is not None and qra_borrowing >= 500
    qra_supply_light = qra_borrowing is not None and qra_borrowing <= 350
    curve_already_steep = ind["s5s30"] >= 95
    two_year_vs_effr_bp = (ind["two_year"] - ind["dff"]) * 100
    cuts_priced = two_year_vs_effr_bp <= -60 and two_year_change <= -25
    energy_hot = ind["wti"] >= 80 or ind.get("wti_shock", 0.0) >= 0.10
    energy_soft = ind["wti"] <= 75 or ind.get("wti_shock", 0.0) <= -0.10
    bei_rich = ind["breakeven_10y"] >= 2.55

    if inflation_cool and two_year_change <= -15 and not macro_tight:
        duration_idea = {
            "title": "加回久期",
            "tag": "LONG 久期",
            "text": (
                f"{inflation_tracker}进入反通胀组合,2Y月变动{two_year_change:+.0f}bp显示政策路径向降息重新定价。"
                f"{liquidity_text}改善了承接环境,可把组合久期逐步加回至基准附近;若核心PCE或Dallas Trimmed PCE重新上行,暂停加仓。"
            ),
            "source": "货币政策 · 宏观基本面 · 宏观环境评分",
        }
    elif inflation_hot or two_year_change >= 15 or macro_tight:
        duration_idea = {
            "title": "战术减久期",
            "tag": "SHORT 久期",
            "text": (
                f"{inflation_tracker}仍对久期不友好,2Y月变动{two_year_change:+.0f}bp显示政策路径重新定价。"
                f"{liquidity_text}提示承接环境不算宽松,组合久期维持低于基准,等待PCE/核心PCE降温或2Y回落再加回。"
            ),
            "source": "货币政策 · 宏观基本面 · 宏观环境评分",
        }
    else:
        duration_idea = {
            "title": "久期区间防守",
            "tag": "HOLD 久期",
            "text": (
                f"{inflation_tracker}与2Y月变动{two_year_change:+.0f}bp没有形成单边信号。"
                f"{liquidity_text}要求久期保持接近基准,用PCE/核心PCE和2Y再定价确认下一次方向。"
            ),
            "source": "货币政策 · 宏观基本面 · 宏观环境评分",
        }

    if qra_supply_light and curve_already_steep:
        curve_idea = {
            "title": "5s30s转区间交易",
            "tag": "CURVE 观望",
            "text": (
                f"5s30s已在{ind['s5s30']:.0f}bp,{qra_text}; 曲线已充分反映长端供给压力,不追做陡。"
                "更适合逢陡降风险或用期权表达尾部供给风险,等待QRA重新上修或长端回落后再加仓。"
            ),
            "source": "供给与技术面 · QRA · 期限溢价",
        }
    elif qra_supply_heavy and curve_already_steep:
        curve_idea = {
            "title": "做陡持有但降杠杆",
            "tag": "CURVE 降杠杆",
            "text": (
                f"5s30s当前{ind['s5s30']:.0f}bp,{qra_text}; 供给压力仍在,但曲线已经偏陡。"
                "保留核心做陡逻辑,同时降低新增追价,用QRA和长端拍卖结果确认是否续持。"
            ),
            "source": "供给与技术面 · QRA · 期限溢价",
        }
    elif qra_supply_heavy or ind["s5s30"] <= 45:
        curve_idea = {
            "title": "做陡 5s30s 曲线",
            "tag": "CURVE 做陡",
            "text": (
                f"5s30s当前{ind['s5s30']:.0f}bp,{qra_text}; 前端由政策锚定,长端更直接承受赤字、息票供给和期限溢价压力。"
                "若长端空头挤压或QRA低于预期,需要降低做陡敞口。"
            ),
            "source": "供给与技术面 · QRA · 期限溢价",
        }
    else:
        curve_idea = {
            "title": "5s30s轻仓观察",
            "tag": "CURVE 中性",
            "text": (
                f"5s30s当前{ind['s5s30']:.0f}bp,{qra_text}; 供给信号和曲线位置没有给出足够不对称性。"
                "维持轻仓或用事件驱动交易,等QRA、30Y拍卖和期限溢价方向确认。"
            ),
            "source": "供给与技术面 · QRA · 期限溢价",
        }

    if cuts_priced:
        front_end_idea = {
            "title": "前端谨慎 · 降息预期已定价",
            "tag": "FRONT-END 谨慎",
            "text": (
                f"2Y收益率{ind['two_year']:.2f}%已较EFFR低{abs(two_year_vs_effr_bp):.0f}bp,且月变动{two_year_change:+.0f}bp,说明降息预期已经较多反映。"
                "前端仍可用于防守,但不应简单视作高确定性carry;若就业或核心PCE反弹,前端回撤风险会放大。"
            ),
            "source": "货币政策 · SOFR/EFFR · 前端曲线",
        }
    elif ind["two_year"] >= 3.0 and ind["sofr"] >= 3.0 and ind["dff"] >= 3.0:
        front_end_idea = {
            "title": "前端持有 · 吃 carry",
            "tag": "LONG 前端",
            "text": (
                f"2Y收益率{ind['two_year']:.2f}%,SOFR {ind['sofr']:.2f}%、EFFR {ind['dff']:.2f}%仍提供前端票息。"
                "相对长端,前端对供给冲击和期限溢价更不敏感,适合作为风险预算内的现金替代。"
            ),
            "source": "货币政策 · SOFR/EFFR · 前端曲线",
        }
    else:
        front_end_idea = {
            "title": "前端中性 · 等待再定价",
            "tag": "FRONT-END 中性",
            "text": (
                f"2Y收益率{ind['two_year']:.2f}%,SOFR {ind['sofr']:.2f}%、EFFR {ind['dff']:.2f}%没有形成明确carry优势。"
                "前端更适合作为流动性仓位,等待政策路径或资金利率重新拉开风险补偿。"
            ),
            "source": "货币政策 · SOFR/EFFR · 前端曲线",
        }

    if inflation_cool and energy_soft and bei_rich:
        breakeven_idea = {
            "title": "降低盈亏平衡通胀",
            "tag": "RV 降通胀补偿",
            "text": (
                f"{inflation_tracker}降温,WTI ${ind['wti']:.2f}未提供能源上行确认,但10Y BEI仍有{ind['breakeven_10y']:.2f}%。"
                "盈亏平衡通胀的风险回报转弱,更适合减仓或等待能源/核心PCE重新加速。"
            ),
            "source": "跨市场 · T10YIE · WTI",
        }
    elif inflation_hot and (energy_hot or not bei_rich):
        breakeven_idea = {
            "title": "战术做多盈亏平衡通胀",
            "tag": "RV 通胀",
            "text": (
                f"10Y BEI {ind['breakeven_10y']:.2f}%、WTI ${ind['wti']:.2f}共同跟踪通胀补偿。"
                "若能源冲击或进口价格继续传导,盈亏平衡比名义久期更直接;油价回落或PCE/核心PCE降温是退出信号。"
            ),
            "source": "跨市场 · T10YIE · WTI",
        }
    elif bei_rich and not inflation_hot:
        breakeven_idea = {
            "title": "通胀补偿转防守",
            "tag": "RV 观望",
            "text": (
                f"10Y BEI {ind['breakeven_10y']:.2f}%已经偏高,而{inflation_tracker}没有同步恶化。"
                "盈亏平衡更适合等待回调后再布局,或只保留小额尾部对冲。"
            ),
            "source": "跨市场 · T10YIE · WTI",
        }
    else:
        breakeven_idea = {
            "title": "小仓位通胀对冲",
            "tag": "RV 对冲",
            "text": (
                f"10Y BEI {ind['breakeven_10y']:.2f}%、WTI ${ind['wti']:.2f}没有形成强单边信号。"
                "保留小仓位通胀对冲即可,加仓需要能源冲击或PCE/核心PCE重新上行确认。"
            ),
            "source": "跨市场 · T10YIE · WTI",
        }
    confidence_fields = investment_view_confidence_fields(conclusion_audit)
    equity_impact = investment_view_equity_impact(macro_liquidity_equity)
    return [
        {**idea, "horizon": "3-6M", "horizonCn": "3-6个月", **confidence_fields, "equityImpact": equity_impact}
        for idea in [
        duration_idea,
        curve_idea,
        front_end_idea,
        breakeven_idea,
        ]
    ]


def investment_view_equity_impact(panel: dict[str, Any] | None, *, min_sample: int = 6) -> dict[str, Any]:
    if not isinstance(panel, dict) or not panel.get("available"):
        return unavailable_equity_impact("S&P 500历史样本不可用,不形成SPY影响结论。")
    rows = [row for row in panel.get("series", []) if isinstance(row, dict)]
    current_signal = panel.get("currentSignal") if isinstance(panel.get("currentSignal"), dict) else {}
    current_level = str(current_signal.get("levelBucket") or "")
    current_change = str(current_signal.get("changeBucket") or "")
    if not rows or not current_level or not current_change:
        return unavailable_equity_impact("同类宏观环境标签缺失,不形成SPY影响结论。")
    usable = [
        row
        for row in rows
        if row.get("forward3m") is not None
        and row.get("score3mChange") is not None
        and optional_float(row.get("liquidityScore")) is not None
    ]
    change_rows = [row for row in usable if optional_float(row.get("score3mChange")) is not None]
    sample = []
    for row in usable:
        level_label = bucket_label_by_rank(rows, "liquidityScore", optional_float(row.get("liquidityScore")), ["低评分", "中位评分", "高评分"])
        change_label = bucket_label_by_rank(change_rows, "score3mChange", optional_float(row.get("score3mChange")), ["评分下行", "变化不大", "评分上行"])
        if level_label == current_level and change_label == current_change:
            sample.append(row)
    if len(sample) < min_sample:
        return unavailable_equity_impact(
            f"历史同类环境样本不足({len(sample)}/{min_sample}),不形成SPY影响结论。"
        )
    forward_1m = numeric_values(sample, "forward1m")
    forward_3m = numeric_values(sample, "forward3m")
    forward_6m = numeric_values(sample, "forward6m")
    drawdowns = numeric_values(sample, "forward3mMaxDrawdown")
    median_3m = median(forward_3m)
    hit_rate_3m = (sum(1 for value in forward_3m if value > 0) / len(forward_3m)) * 100
    avg_drawdown = sum(drawdowns) / len(drawdowns) if drawdowns else None
    confidence = equity_impact_confidence(len(sample), forward_3m, str(current_signal.get("confidence") or ""))
    tone = "positive" if median_3m > 0.5 and hit_rate_3m >= 55 else "negative" if median_3m < -0.5 and hit_rate_3m <= 45 else "mixed"
    return {
        "available": True,
        "proxy": "S&P 500 price-index proxy for SPY",
        "basis": "同类宏观评分水平 + 3M评分变化",
        "levelBucket": current_level,
        "changeBucket": current_change,
        "sampleSize": len(sample),
        "forward1mMedian": round(median(forward_1m), 2) if forward_1m else None,
        "forward3mMedian": round(median_3m, 2),
        "forward6mMedian": round(median(forward_6m), 2) if forward_6m else None,
        "hitRate3m": round(hit_rate_3m),
        "avgMaxDrawdown3m": round(avg_drawdown, 2) if avg_drawdown is not None else None,
        "confidence": confidence["key"],
        "confidenceLabel": confidence["label"],
        "tone": tone,
        "summary": (
            f"历史同类环境下,S&P 500价格指数代理SPY未来3M中位回报{median_3m:+.2f}%,"
            f"胜率{hit_rate_3m:.0f}%,样本{len(sample)}; 仅为历史统计,不构成方向承诺。"
        ),
    }


def numeric_values(rows: list[dict[str, Any]], key: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        value = optional_float(row.get(key))
        if value is not None:
            values.append(value)
    return values


def investment_view_confidence_fields(conclusion_audit: dict[str, Any] | None) -> dict[str, str]:
    confidence = conclusion_audit.get("confidence") if isinstance(conclusion_audit, dict) else {}
    confidence = confidence if isinstance(confidence, dict) else {}
    level = str(confidence.get("level") or "medium")
    if level not in {"high", "medium", "low"}:
        level = "medium"
    label = {"high": "高可信", "medium": "中等可信", "low": "低可信"}[level]
    evidence_quality = optional_float(confidence.get("evidenceQuality"))
    proxy_share = optional_float(confidence.get("proxyContributionShare"))
    concentration = optional_float(confidence.get("concentration"))
    note_parts: list[str] = []
    if evidence_quality is not None:
        note_parts.append(f"证据质量 {evidence_quality:.2f}")
    if proxy_share is not None:
        note_parts.append(f"代理/模型占比 {proxy_share:.0%}")
    if concentration is not None:
        note_parts.append(f"单因子集中度 {concentration:.0%}")
    recommendation = conclusion_audit.get("weightRecommendation") if isinstance(conclusion_audit, dict) else None
    if isinstance(recommendation, str) and recommendation:
        note_parts.append(recommendation)
    return {
        "confidenceLevel": level,
        "confidenceLabel": label,
        "confidenceNote": "; ".join(note_parts) if note_parts else "结论审计暂无异常。",
    }


def direction_word(value: float) -> str:
    return "多" if value >= 0 else "空"


def compact_int(value: float) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.0f}k"
    return f"{value:.0f}"


def money_trillions_from_billions(value: float) -> str:
    return f"${value / 1_000:.2f}T"


def money_from_millions(value: float) -> str:
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.2f}T"
    if abs(value) >= 1_000:
        return f"${value / 1_000:.1f}B"
    return f"${value:.0f}M"


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




class BhadialWeeklyReplay:
    """Point-in-time weekly factor replay over pre-sorted score series.

    Mirrors bhadial_factor_score_at / bhadial_conditions_score_at semantics
    (including the Funding EMA(5) smoothing) but uses bisect lookups and
    memoized month-end module scores so a 5Y weekly replay stays fast."""

    def __init__(self, series: dict[str, list[SeriesPoint]]):
        self.sorted_series: dict[str, SortedSeries] = {
            key: SortedSeries(series.get(key) or []) for key in BHADIAL_CONDITION_SERIES_KEYS
        }
        self._factor_cache: dict[tuple[str, date], tuple[float, bool]] = {}
        self._module_raw_cache: dict[tuple[str, date], tuple[float, int]] = {}
        self._month_ends_cache: dict[str, list[date]] = {}

    def factor_score_at(self, spec: dict[str, Any], target: date) -> tuple[float, bool]:
        cache_key = (str(spec["id"]), target)
        cached = self._factor_cache.get(cache_key)
        if cached is not None:
            return cached
        sorted_points = self.sorted_series.get(str(spec["scoreKey"]))
        current = sorted_points.value_at_or_before(target) if sorted_points is not None else None
        if current is None:
            row = (50.0, False)
        else:
            method = str(spec["method"])
            direction = str(spec["direction"])
            if method == "risk_signal":
                bounded = max(0.0, min(1.0, current))
                score = (1 - bounded) * 100 if direction == "lower_better" else bounded * 100
            elif method == "shock_only" and current <= 0:
                score = 50.0
            else:
                score = score_from_percentile(sorted_points.percentile_at(target), direction)
            row = (max(0.0, min(100.0, score)), True)
        self._factor_cache[cache_key] = row
        return row

    def module_raw_score_at(self, module: dict[str, Any], target: date) -> tuple[float, int]:
        cache_key = (str(module["name"]), target)
        cached = self._module_raw_cache.get(cache_key)
        if cached is not None:
            return cached
        total = 0.0
        total_weight = 0.0
        observed = 0
        for spec in module["factors"]:
            score, was_observed = self.factor_score_at(spec, target)
            weight = float(spec["weight"])
            total += score * weight
            total_weight += weight
            if was_observed:
                observed += 1
        row = (total / max(total_weight, 1e-9), observed)
        self._module_raw_cache[cache_key] = row
        return row

    def module_month_ends(self, module: dict[str, Any]) -> list[date]:
        key = str(module["name"])
        cached = self._month_ends_cache.get(key)
        if cached is not None:
            return cached
        month_ends: dict[tuple[int, int], date] = {}
        for spec in module["factors"]:
            sorted_points = self.sorted_series.get(str(spec["scoreKey"]))
            if sorted_points is None:
                continue
            for point_date in sorted_points.dates:
                month_key = (point_date.year, point_date.month)
                existing = month_ends.get(month_key)
                if existing is None or point_date > existing:
                    month_ends[month_key] = point_date
        result = [month_ends[month_key] for month_key in sorted(month_ends)]
        self._month_ends_cache[key] = result
        return result

    def module_ema_score_at(self, module: dict[str, Any], target: date, *, span: int = 5) -> float | None:
        start = window_start(target, years=5)
        point_dates = [point_date for point_date in self.module_month_ends(module) if start <= point_date <= target]
        if target not in point_dates:
            point_dates.append(target)
        alpha = 2 / (span + 1)
        ema: float | None = None
        for point_date in sorted(point_dates):
            score, _ = self.module_raw_score_at(module, point_date)
            ema = score if ema is None else alpha * score + (1 - alpha) * ema
        return ema

    def composite_at(self, target: date, *, include_components: bool = False) -> dict[str, Any]:
        composite_total = 0.0
        weight_total = 0.0
        observed_total = 0
        components: list[dict[str, Any]] = []
        for module in BHADIAL_CONDITION_MODULES:
            module_score, observed = self.module_raw_score_at(module, target)
            if module.get("smooth") == "ema5":
                ema = self.module_ema_score_at(module, target, span=5)
                if ema is not None:
                    module_score = ema
            module_weight = bhadial_module_weight(str(module["name"]))
            composite_total += module_score * module_weight
            weight_total += module_weight
            observed_total += observed
            if include_components:
                for spec in module["factors"]:
                    score, _ = self.factor_score_at(spec, target)
                    components.append(
                        {
                            "id": str(spec["id"]),
                            "module": str(module["name"]),
                            "moduleCn": str(module["nameCn"]),
                            "remoteName": str(spec["remoteName"]),
                            "name": str(spec["name"]),
                            "score": round(score, 1),
                            "value": "",
                            "source": str(spec["source"]),
                        }
                    )
        return {
            "score": composite_total / max(weight_total, 1e-9),
            "observedFactorCount": observed_total,
            "components": components,
        }




def unavailable_signal_validation(reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "reason": reason,
        "factors": [],
        "composites": [],
        "clusters": [],
        "effectiveWeights": [],
    }


def build_signal_validation(
    indicators: dict[str, Any],
    *,
    equity_short_term_risk: dict[str, Any] | None = None,
) -> dict[str, Any]:
    series = indicators.get("percentile_series") if isinstance(indicators.get("percentile_series"), dict) else {}
    sp500_points = clean_points(series.get("sp500", []))
    week_targets = weekly_dates(sp500_points, years=5)
    if len(week_targets) < SIGNAL_VALIDATION_MIN_WEEKS:
        return unavailable_signal_validation("S&P 500周度样本不足,暂不能执行走出样本验证。")
    prices_sorted = SortedSeries(sp500_points)
    replay = BhadialWeeklyReplay(series)

    factor_series: dict[str, list[SeriesPoint]] = {}
    factor_rows: list[dict[str, Any]] = []
    for module in BHADIAL_CONDITION_MODULES:
        for spec in module["factors"]:
            points = []
            for target in week_targets:
                score, observed = replay.factor_score_at(spec, target)
                if observed:
                    points.append(SeriesPoint(date=target, value=score))
            factor_series[str(spec["id"])] = points
            row = signal_validation_metric_row(
                row_id=str(spec["id"]),
                label=str(spec["remoteName"]),
                label_cn=str(spec["name"]),
                module=str(module["name"]),
                signal_points=points,
                price_points=sp500_points,
                prices_sorted=prices_sorted,
                direction="higher_better",
            )
            if row is not None:
                factor_rows.append(row)

    clusters = redundancy_clusters(
        {factor_id: points for factor_id, points in factor_series.items() if len(points) >= MIN_SIGNAL_VALIDATION_POINTS}
    )
    cluster_rows = [
        {"id": f"c{index + 1}", "factorIds": members}
        for index, members in enumerate(clusters)
    ]
    cluster_lookup = {member: row["id"] for row in cluster_rows for member in row["factorIds"]}
    for row in factor_rows:
        row["clusterId"] = cluster_lookup.get(row["id"])

    composite_points: list[SeriesPoint] = []
    weekly_components: dict[date, list[dict[str, Any]]] = {}
    for target in week_targets:
        composite = replay.composite_at(target, include_components=True)
        if int(composite.get("observedFactorCount", 0)) < 5:
            continue
        composite_points.append(SeriesPoint(date=target, value=float(composite["score"])))
        weekly_components[target] = composite["components"]

    change_points: list[SeriesPoint] = [
        SeriesPoint(date=current.date, value=current.value - composite_points[index - 13].value)
        for index, current in enumerate(composite_points)
        if index >= 13
    ]

    sleeve_series: dict[str, list[SeriesPoint]] = {str(spec["key"]): [] for spec in SPY_WARNING_COMPONENT_SLEEVES}
    spy_warning_points: list[SeriesPoint] = []
    rule_fires: dict[str, list[dict[str, Any]]] = {}
    rule_meta: dict[str, dict[str, Any]] = {}
    composite_by_date = {point.date: point.value for point in composite_points}
    change_by_date = {point.date: point.value for point in change_points}
    for point in composite_points:
        components = weekly_components.get(point.date, [])
        component_by_id = {str(item.get("id")): item for item in components}
        for spec in SPY_WARNING_COMPONENT_SLEEVES:
            sleeve = build_spy_component_sleeve(spec, component_by_id)
            if sleeve.get("available"):
                sleeve_series[str(spec["key"])].append(SeriesPoint(date=point.date, value=float(sleeve["score"])))
        score_change = change_by_date.get(point.date)
        trailing_values = trailing_return_values(prices_sorted, [point.date], days=91)
        signal = {
            "date": point.date.isoformat(),
            "conditionsScore": composite_by_date.get(point.date),
            "score3mChange": score_change,
            "levelBucket": "",
            "changeBucket": "",
            "expectedForward3m": None,
            "expectedDrawdown3m": None,
            "sp500Trailing3m": trailing_values[0],
            "hitRate": None,
            "confidence": "replay",
        }
        snapshot = spy_early_warning_snapshot(
            {"score": round(point.value, 1), "components": components},
            {"asOf": point.date.isoformat(), "currentSignal": signal},
        )
        score = optional_float(snapshot.get("score")) if snapshot.get("available") else None
        if score is not None:
            spy_warning_points.append(SeriesPoint(date=point.date, value=score))
            amplifier_items = snapshot.get("amplifiers") if isinstance(snapshot.get("amplifiers"), list) else []
            dampener_items = snapshot.get("dampeners") if isinstance(snapshot.get("dampeners"), list) else []
            for kind, items in (("amplifier", amplifier_items), ("dampener", dampener_items)):
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    key = str(item.get("key") or "")
                    if not key:
                        continue
                    effect = optional_float(item.get("scoreBoost"))
                    if effect is None:
                        effect = optional_float(item.get("scoreOffset"))
                    rule_meta.setdefault(
                        key,
                        {"label": str(item.get("label") or key), "kind": kind, "scoreEffect": effect or 0.0},
                    )
                    rule_fires.setdefault(key, []).append(
                        {"date": point.date, "trailing3m": trailing_values[0]}
                    )

    amplifier_audit = build_spy_warning_rule_audit(
        rule_fires,
        rule_meta,
        [item.date for item in spy_warning_points],
        prices_sorted,
    )

    composite_specs: list[dict[str, Any]] = [
        {
            "id": "bhadialComposite",
            "label": "Conditions Score (weekly)",
            "labelCn": "宏观环境评分(周度)",
            "points": composite_points,
            "direction": "higher_better",
        },
        {
            "id": "bhadialChange13w",
            "label": "Conditions Score 13W change",
            "labelCn": "宏观评分13周变化",
            "points": change_points,
            "direction": "higher_better",
        },
        {
            "id": "spyEarlyWarning",
            "label": "SPY Early Warning (weekly replay)",
            "labelCn": "SPY预警(周度回放)",
            "points": spy_warning_points,
            "direction": "higher_risk",
        },
    ]
    sleeve_labels = {str(spec["key"]): str(spec["label"]) for spec in SPY_WARNING_COMPONENT_SLEEVES}
    for sleeve_key, points in sleeve_series.items():
        composite_specs.append(
            {
                "id": f"sleeve:{sleeve_key}",
                "label": sleeve_key,
                "labelCn": sleeve_labels.get(sleeve_key, sleeve_key),
                "points": points,
                "direction": "higher_risk",
            }
        )

    composite_rows: list[dict[str, Any]] = []
    for spec in composite_specs:
        row = signal_validation_metric_row(
            row_id=str(spec["id"]),
            label=str(spec["label"]),
            label_cn=str(spec["labelCn"]),
            module="composite",
            signal_points=spec["points"],
            price_points=sp500_points,
            prices_sorted=prices_sorted,
            direction=str(spec["direction"]),
        )
        if row is not None:
            composite_rows.append(row)

    equity_row = build_equity_signal_validation_row(equity_short_term_risk)
    if equity_row is not None:
        composite_rows.append(equity_row)

    weights = effective_weights(BHADIAL_CONDITION_MODULES, BHADIAL_MODULE_WEIGHTS, clusters)

    predictive_lens = build_bhadial_predictive_lens(
        replay,
        week_targets,
        factor_series,
        weights,
        prices_sorted,
    )
    if predictive_lens.get("available"):
        predictive_row = signal_validation_metric_row(
            row_id="bhadialPredictive",
            label="Predictive lens (leading factors)",
            label_cn="预测镜头(领先因子)",
            module="composite",
            signal_points=predictive_lens["points"],
            price_points=sp500_points,
            prices_sorted=prices_sorted,
            direction="higher_better",
        )
        if predictive_row is not None:
            composite_rows.append(predictive_row)
    predictive_payload = {key: value for key, value in predictive_lens.items() if key != "points"}
    return {
        "available": True,
        "asOf": week_targets[-1].isoformat(),
        "method": (
            "Weekly point-in-time replay of all condition factors and composite overlays against forward "
            "S&P 500 returns; thresholds and ICs are split into calibration (first 65%) and out-of-sample "
            "(last 35%) slices; alert hit rates are compared with the unconditional base rate."
        ),
        "weeklyObservationCount": len(week_targets),
        "oosSplitPct": round(SIGNAL_VALIDATION_OOS_SPLIT * 100),
        "drawdownRule": f"{SIGNAL_VALIDATION_DRAWDOWN_DAYS}D内最大回撤≤{SIGNAL_VALIDATION_DRAWDOWN_PCT:.0f}%",
        "factors": factor_rows,
        "composites": composite_rows,
        "clusters": cluster_rows,
        "effectiveWeights": weights,
        "predictiveLens": predictive_payload,
        "amplifierAudit": amplifier_audit,
    }


def build_bhadial_predictive_lens(
    replay: "BhadialWeeklyReplay",
    week_targets: list[date],
    factor_series: dict[str, list[SeriesPoint]],
    weight_rows: list[dict[str, Any]],
    prices_sorted: SortedSeries,
    *,
    min_factors: int = 3,
    min_calibration_ic: float = 0.10,
) -> dict[str, Any]:
    """Predictive-lens composite: factors are selected by their CALIBRATION-slice
    forward IC only (never the OOS slice, so the lens's OOS metrics stay honest),
    weighted by redundancy-adjusted effective weights, and replayed with each
    factor's publicationLagDays applied so only truly-available data enters."""
    spec_by_id = {
        str(spec["id"]): spec
        for module in BHADIAL_CONDITION_MODULES
        for spec in module["factors"]
    }
    selected: list[dict[str, Any]] = []
    for factor_id in sorted(factor_series):
        points = factor_series[factor_id]
        if len(points) < MIN_SIGNAL_VALIDATION_POINTS:
            continue
        split_index = max(1, int(len(points) * SIGNAL_VALIDATION_OOS_SPLIT))
        calibration = points[:split_index]
        signal_values: list[float | None] = [point.value for point in calibration]
        ic_1m = spearman_ic(signal_values, [prices_sorted.forward_return_pct(point.date, days=30) for point in calibration])
        ic_3m = spearman_ic(signal_values, [prices_sorted.forward_return_pct(point.date, days=91) for point in calibration])
        # 2026-06-18: 要求 1M 与 3M 校准段 IC 同时达标(取 min,而非之前的 max 取优)。
        # 旧逻辑只需单一horizon偶然相关即入选,导致选入同步/滞后因子(VIX/油气冲击),
        # 样本外 IC 反转至 -0.49。改为多horizon一致性筛选以降低过拟合。
        if ic_1m is None or ic_3m is None:
            continue
        consistent_ic = min(ic_1m, ic_3m)
        if consistent_ic < min_calibration_ic:
            continue
        selected.append({"id": factor_id, "calibrationIc": round(consistent_ic, 3)})
    if len(selected) < min_factors:
        return {
            "available": False,
            "reason": f"校准段达标的领先因子不足{min_factors}个,预测镜头暂不发布。",
            "selectedFactors": selected,
            "points": [],
        }
    weight_by_id = {str(row["id"]): float(row["effectiveWeight"]) for row in weight_rows}
    points: list[SeriesPoint] = []
    for target in week_targets:
        total = 0.0
        weight_total = 0.0
        for item in selected:
            spec = spec_by_id.get(item["id"])
            if spec is None:
                continue
            lag = int(spec.get("publicationLagDays") or 1)
            score, observed = replay.factor_score_at(spec, target - timedelta(days=lag))
            if not observed:
                continue
            weight = weight_by_id.get(item["id"], 0.0)
            total += score * weight
            weight_total += weight
        if weight_total > 0:
            points.append(SeriesPoint(date=target, value=total / weight_total))
    for item in selected:
        item["effectiveWeight"] = weight_by_id.get(item["id"], 0.0)
    latest_score = round(points[-1].value, 1) if points else None
    return {
        "available": bool(points),
        "method": (
            "Leading factors chosen on the calibration slice only, requiring BOTH 1M and 3M "
            f"forward IC >= {min_calibration_ic:.2f} (multi-horizon consistency, not best-of), "
            "weighted by redundancy-adjusted effective weights, replayed with per-factor publication lags."
        ),
        "selectedFactors": selected,
        "latestScore": latest_score,
        "points": points,
    }


def build_equity_signal_validation_row(equity_short_term_risk: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(equity_short_term_risk, dict):
        return None
    trend = equity_short_term_risk.get("trend")
    if not isinstance(trend, dict) or not trend.get("available"):
        return None
    signal_points: list[SeriesPoint] = []
    price_points: list[SeriesPoint] = []
    for row in trend.get("points", []):
        if not isinstance(row, dict):
            continue
        try:
            target = date.fromisoformat(str(row.get("date") or ""))
        except ValueError:
            continue
        score = optional_float(row.get("score"))
        close = optional_float(row.get("spyClose"))
        if score is None or close is None or close <= 0:
            continue
        signal_points.append(SeriesPoint(date=target, value=score))
        price_points.append(SeriesPoint(date=target, value=close))
    if len(signal_points) < MIN_SIGNAL_VALIDATION_POINTS:
        return None
    return signal_validation_metric_row(
        row_id="equityShortTermRisk",
        label="Equity Short-Term Risk (daily)",
        label_cn="股票短周期风险(日度)",
        module="composite",
        signal_points=signal_points,
        price_points=price_points,
        prices_sorted=SortedSeries(price_points),
        direction="higher_risk",
        drawdown_threshold_pct=SIGNAL_VALIDATION_EQUITY_DRAWDOWN_PCT,
        drawdown_horizon_days=SIGNAL_VALIDATION_EQUITY_DRAWDOWN_DAYS,
    )


PORTFOLIO_OVERVIEW_LPPL_RISK_BAND = [60, 85]
PORTFOLIO_OVERVIEW_LPPL_WATCH_BAND = [85, 100]


def portfolio_overview_evidence(row: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {"available": False, "note": "证据不足: 该层尚无走出样本验证。"}
    return {
        "available": True,
        "oosHitRate": optional_float(row.get("hitRateOos")),
        "baseRate": optional_float(row.get("baseRate")),
        "lift": optional_float(row.get("lift")),
        "leadTimeDays": optional_float(row.get("leadTimeDays")),
        "sampleSize": row.get("observationCount"),
        "classification": str(row.get("classification") or ""),
    }


def portfolio_overview_layer(
    *,
    layer: str,
    label: str,
    label_cn: str,
    horizon: str,
    horizon_cn: str,
    score: float | None,
    regime: str,
    regime_cn: str,
    stance: str,
    exposure_band: list[Any] | None,
    evidence: dict[str, Any],
    note: str = "",
) -> dict[str, Any]:
    band: list[float] | None = None
    if isinstance(exposure_band, (list, tuple)) and len(exposure_band) == 2:
        low = optional_float(exposure_band[0])
        high = optional_float(exposure_band[1])
        if low is not None and high is not None:
            band = [low, high]
    return {
        "layer": layer,
        "label": label,
        "labelCn": label_cn,
        "horizon": horizon,
        "horizonCn": horizon_cn,
        "score": round(score, 1) if score is not None else None,
        "regime": regime,
        "regimeCn": regime_cn,
        "stance": stance,
        "exposureBandPct": band,
        "evidence": evidence,
        "note": note,
    }


def global_lppl_overview_state(global_lppl_risk: dict[str, Any] | None) -> dict[str, Any]:
    rows = global_lppl_risk.get("indices") if isinstance(global_lppl_risk, dict) else []
    rows = [row for row in rows if isinstance(row, dict) and row.get("available")] if isinstance(rows, list) else []
    risk_rows = [row for row in rows if str(row.get("status")) == "risk"]
    watch_rows = [row for row in rows if str(row.get("status")) == "watch"]
    if risk_rows:
        band = list(PORTFOLIO_OVERVIEW_LPPL_RISK_BAND)
        regime, regime_cn = "Risk", "泡沫风险"
        stance = "界定下行(领式/保护性认沽),不盲目追高风险指数"
    elif watch_rows:
        band = list(PORTFOLIO_OVERVIEW_LPPL_WATCH_BAND)
        regime, regime_cn = "Watch", "观察"
        stance = "维持仓位,跟踪临界窗口收敛"
    else:
        band = [100, 100]
        regime, regime_cn = "Quiet", "低风险"
        stance = "无泡沫形态约束"
    alert_symbols = [str(row.get("symbol") or "") for row in risk_rows]
    days = [optional_float(row.get("daysToCritical")) for row in risk_rows + watch_rows]
    days = [value for value in days if value is not None]
    scores = [optional_float(row.get("score")) for row in rows]
    scores = [value for value in scores if value is not None]
    return {
        "band": band,
        "regime": regime,
        "regimeCn": regime_cn,
        "stance": stance,
        "alertSymbols": alert_symbols,
        "minDaysToCritical": min(days) if days else None,
        "maxScore": max(scores) if scores else None,
        "observedIndexCount": len(rows),
    }


def global_lppl_overview_evidence(global_lppl_risk: dict[str, Any] | None) -> dict[str, Any]:
    validation = global_lppl_risk.get("indexValidation") if isinstance(global_lppl_risk, dict) else {}
    rows = validation.get("rows") if isinstance(validation, dict) else []
    spy_row = next((row for row in rows if isinstance(row, dict) and str(row.get("symbol")) == "SPY"), None)
    if not isinstance(spy_row, dict) or not spy_row.get("oosAvailable"):
        return {"available": False, "note": "证据不足: LPPL单指数OOS验证不可用。"}
    hit = optional_float(spy_row.get("precision15dOos"))
    base = optional_float(spy_row.get("baseRate15dOos"))
    hit = hit / 100 if hit is not None else None
    base = base / 100 if base is not None else None
    return {
        "available": True,
        "oosHitRate": round(hit, 3) if hit is not None else None,
        "baseRate": round(base, 3) if base is not None else None,
        "lift": round(hit / base, 2) if hit is not None and base else None,
        "leadTimeDays": optional_float(spy_row.get("avgDrawdownLeadDaysWhenHit")),
        "sampleSize": spy_row.get("oosSampleSize"),
        "classification": "",
    }


def portfolio_overview_us_internal_tilt(regional_monitor: dict[str, Any] | None) -> dict[str, Any]:
    """Surface the US-internal broad(SPY)-vs-tech(QQQ) tilt in the headline overview, so the
    US equity band is paired with a within-US sleeve lean."""
    if not isinstance(regional_monitor, dict) or not regional_monitor.get("available"):
        return {"available": False}
    regions = regional_monitor.get("regions", []) if isinstance(regional_monitor.get("regions"), list) else []
    us = next((r for r in regions if isinstance(r, dict) and r.get("key") == "us"), None)
    internal = us.get("internalRotation") if isinstance(us, dict) and isinstance(us.get("internalRotation"), dict) else {}
    if not internal.get("available"):
        return {"available": False}
    return {
        "available": True,
        "tilt": internal.get("tilt"),
        "tiltCn": internal.get("tiltCn"),
        "rationale": internal.get("rationale"),
    }


def portfolio_overview_regional_tilt(regional_monitor: dict[str, Any] | None) -> dict[str, Any]:
    """Surface the global regional rotation + active validated-factor breaches as a separate
    dimension in the headline overview (distinct axis from the US equity exposure band)."""
    if not isinstance(regional_monitor, dict) or not regional_monitor.get("available"):
        return {"available": False}
    rotation = regional_monitor.get("rotation", {}) if isinstance(regional_monitor.get("rotation"), dict) else {}
    regions = regional_monitor.get("regions", []) if isinstance(regional_monitor.get("regions"), list) else []
    name_by_key = {str(r.get("key")): str(r.get("nameCn") or r.get("name") or r.get("key")) for r in regions if isinstance(r, dict)}
    breached = [
        {"key": str(r.get("key")), "nameCn": name_by_key.get(str(r.get("key")), str(r.get("key"))),
         "factorLabelCn": str(r["factorAlert"].get("factorLabelCn") or ""),
         "source": str(r["factorAlert"].get("source") or "factor"),
         "current": r["factorAlert"].get("current"), "threshold": r["factorAlert"].get("threshold"),
         "trackRecord": str(r["factorAlert"].get("trackRecord") or "")}
        for r in regions
        if isinstance(r, dict) and isinstance(r.get("factorAlert"), dict)
        and r["factorAlert"].get("available") and r["factorAlert"].get("state") == "breached"
    ]
    composite_breaches = [b for b in breached if b["source"] == "composite"]
    favor = [name_by_key.get(k, k) for k in rotation.get("favorRegions", [])]
    reduce_regions = [name_by_key.get(k, k) for k in rotation.get("reduceRegions", [])]
    parts: list[str] = []
    if favor:
        parts.append("增持 " + "、".join(favor))
    if reduce_regions:
        parts.append("减持 " + "、".join(reduce_regions))
    if not parts:
        parts.append("各地区维持中性")
    if breached:
        parts.append(f"{len(breached)}个地区信号突破验证阈值(" + "、".join(b["nameCn"] for b in breached) + ")")
    if composite_breaches:
        parts.append(f"其中{len(composite_breaches)}个由已验证综合信号驱动(" + "、".join(b["nameCn"] for b in composite_breaches) + ")")
    return {
        "available": True,
        "horizon": "1-3M",
        "horizonCn": "1-3个月(地区轮动)",
        "favorRegions": rotation.get("favorRegions", []),
        "reduceRegions": rotation.get("reduceRegions", []),
        "breachedRegions": breached,
        "compositeBreachCount": len(composite_breaches),
        "summary": "; ".join(parts) + "。",
    }


def build_portfolio_overview(
    *,
    spy_early_warning: dict[str, Any] | None,
    equity_short_term_risk: dict[str, Any] | None,
    global_lppl_risk: dict[str, Any] | None,
    macro_liquidity: dict[str, Any] | None,
    signal_validation: dict[str, Any] | None,
    regional_monitor: dict[str, Any] | None = None,
) -> dict[str, Any]:
    evidence_by_id: dict[str, dict[str, Any]] = {}
    if isinstance(signal_validation, dict) and signal_validation.get("available"):
        evidence_by_id = {
            str(row.get("id")): row
            for row in signal_validation.get("composites", [])
            if isinstance(row, dict)
        }

    rows: list[dict[str, Any]] = []

    est = equity_short_term_risk if isinstance(equity_short_term_risk, dict) else {}
    est_alloc = est.get("allocation") if isinstance(est.get("allocation"), dict) else {}
    est_score = optional_float(est.get("score"))
    if est_score is not None:
        rows.append(
            portfolio_overview_layer(
                layer="equityShortTermRisk",
                label="Equity Short-Term Risk",
                label_cn="短周期股票风险",
                horizon=str(est_alloc.get("horizon") or "1-10d"),
                horizon_cn=str(est_alloc.get("horizonCn") or "1-10个交易日"),
                score=est_score,
                regime=str(est_alloc.get("regime") or ""),
                regime_cn=str(est_alloc.get("regimeCn") or ""),
                stance=str(est_alloc.get("hedgeAction") or est_alloc.get("stance") or ""),
                exposure_band=est_alloc.get("exposureBandPct"),
                evidence=portfolio_overview_evidence(evidence_by_id.get("equityShortTermRisk")),
            )
        )

    sew = spy_early_warning if isinstance(spy_early_warning, dict) else {}
    sew_alloc = sew.get("allocation") if isinstance(sew.get("allocation"), dict) else {}
    sew_score = optional_float(sew.get("score"))
    if sew_score is not None:
        rows.append(
            portfolio_overview_layer(
                layer="spyEarlyWarning",
                label="SPY Early Warning",
                label_cn="SPY宏观预警",
                horizon=str(sew_alloc.get("horizon") or "1-3M"),
                horizon_cn=str(sew_alloc.get("horizonCn") or "1-3个月"),
                score=sew_score,
                regime=str(sew.get("regime") or ""),
                regime_cn=str(sew.get("regimeCn") or ""),
                stance=str(sew_alloc.get("hedgeAction") or sew_alloc.get("stance") or ""),
                exposure_band=sew_alloc.get("exposureBandPct"),
                evidence=portfolio_overview_evidence(evidence_by_id.get("spyEarlyWarning")),
            )
        )

    lppl_state = global_lppl_overview_state(global_lppl_risk)
    if lppl_state["observedIndexCount"] > 0:
        lppl_note = ""
        if lppl_state["alertSymbols"]:
            lppl_note = "告警指数: " + ", ".join(lppl_state["alertSymbols"])
            if lppl_state["minDaysToCritical"] is not None:
                lppl_note += f"; 最近临界窗口≈{lppl_state['minDaysToCritical']:.0f}天"
        rows.append(
            portfolio_overview_layer(
                layer="globalLppl",
                label="Global LPPL Bubble Monitor",
                label_cn="全球LPPL泡沫监测",
                horizon="tc-window",
                horizon_cn="临界窗口",
                score=lppl_state["maxScore"],
                regime=lppl_state["regime"],
                regime_cn=lppl_state["regimeCn"],
                stance=lppl_state["stance"],
                exposure_band=lppl_state["band"],
                evidence=global_lppl_overview_evidence(global_lppl_risk),
                note=lppl_note,
            )
        )

    macro = macro_liquidity if isinstance(macro_liquidity, dict) else {}
    macro_score = optional_float(macro.get("score"))
    if macro_score is not None:
        rows.append(
            portfolio_overview_layer(
                layer="bhadialComposite",
                label="Macro Conditions (nowcast)",
                label_cn="宏观环境评分",
                horizon="3-6M",
                horizon_cn="3-6个月",
                score=macro_score,
                regime=str(macro.get("regime") or ""),
                regime_cn=str(macro.get("regimeCn") or macro.get("regime") or ""),
                stance="背景层: 影响久期/曲线观点,不直接给权益仓位",
                exposure_band=None,
                evidence=portfolio_overview_evidence(evidence_by_id.get("bhadialComposite")),
            )
        )

    scored_rows = [row for row in rows if row.get("score") is not None]
    if len(scored_rows) < 2:
        return {
            "available": False,
            "summary": "组合总览需要至少两层可用信号。",
            "layers": rows,
            "conflicts": [],
            "suggestedEquityExposureBand": None,
        }

    bands = [row["exposureBandPct"] for row in rows if row.get("exposureBandPct")]
    suggested_band = None
    binding_layer = None
    if bands:
        low = min(band[0] for band in bands)
        high = min(band[1] for band in bands)
        suggested_band = [round(max(0.0, low), 0), round(max(low, min(high, 110.0)), 0)]
        for row in rows:
            band = row.get("exposureBandPct")
            if band and band[1] == high:
                binding_layer = str(row.get("labelCn") or row.get("layer"))
                break

    conflicts: list[dict[str, Any]] = []
    lppl_alerting = bool(lppl_state["alertSymbols"]) if lppl_state["observedIndexCount"] > 0 else False
    if sew_score is not None and est_score is not None:
        if sew_score < 60 and est_score >= 75:
            conflicts.append(
                {
                    "layers": ["spyEarlyWarning", "equityShortTermRisk"],
                    "description": f"宏观预警温和({sew_score:.0f})但短周期强告警({est_score:.0f})",
                    "resolution": "维持核心仓位,但为未来1-2周加战术性保护(对冲或减高Beta),不必战略性减仓。",
                }
            )
        if sew_score >= 60 and est_score < 40:
            conflicts.append(
                {
                    "layers": ["spyEarlyWarning", "equityShortTermRisk"],
                    "description": f"宏观预警偏高({sew_score:.0f})但短周期无压力({est_score:.0f})",
                    "resolution": "利用市场平静期分批降低风险敞口,而非等待回撤后被动卖出。",
                }
            )
    if lppl_alerting and sew_score is not None and sew_score < 40:
        conflicts.append(
            {
                "layers": ["globalLppl", "spyEarlyWarning"],
                "description": "泡沫形态告警与建设性宏观并存",
                "resolution": "保留上行参与,用期权界定下行(领式或保护性认沽),避免直接清仓错过泡沫后段。",
            }
        )

    if suggested_band:
        band_text = f"建议权益仓位区间{suggested_band[0]:.0f}-{suggested_band[1]:.0f}%(常规仓位=100%)"
        if binding_layer:
            band_text += f", 当前约束层: {binding_layer}"
    else:
        band_text = "暂无可合成的仓位区间"
    conflict_text = f"; 检测到{len(conflicts)}个跨层冲突,见冲突说明" if conflicts else "; 三个时间层无显著冲突"
    return {
        "available": True,
        "asOf": str(sew.get("asOf") or est.get("asOf") or ""),
        "method": (
            "Combines the 1-10d tactical, 1-3M macro-warning, and LPPL tc-window layers; the suggested band "
            "takes the most conservative layer (element-wise minimum). Evidence columns come from the weekly "
            "walk-forward signalValidation harness; layers without OOS validation are marked 证据不足."
        ),
        "summary": band_text + conflict_text + "。每层命中率均为走出样本(OOS)统计,与无条件基准率对照。",
        "layers": rows,
        "conflicts": conflicts,
        "suggestedEquityExposureBand": suggested_band,
        "bindingLayer": binding_layer,
        "regionalTilt": portfolio_overview_regional_tilt(regional_monitor),
        "usInternalTilt": portfolio_overview_us_internal_tilt(regional_monitor),
    }
