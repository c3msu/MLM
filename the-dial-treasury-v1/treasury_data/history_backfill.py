from __future__ import annotations

import math
from datetime import date
from pathlib import Path
from typing import Any

from .build_dashboard import (
    FRED_SERIES,
    build_net_liquidity_points,
    change_points,
    funding_fragmentation_points,
    onrrp_buffer_risk_points,
    parse_dashboard_date,
    parse_number,
    ratio_points,
    realized_volatility_points,
    rolling_median_deviation_points,
    spread_points,
    weighted_points,
    window_start,
)
from .history_store import DEFAULT_HISTORY_DB, save_historical_observations, save_history_backfill_run
from .sources import (
    TENORS,
    SeriesPoint,
    TimeSeries,
    YieldCurveRecord,
    fetch_fred_series_bulk,
    fetch_treasury_auctions,
    fetch_treasury_yield_curves,
)


FRED_SERIES_META: dict[str, tuple[str, str, str, str]] = {
    "DFII10": ("10Y实际利率", "%", "FRED DFII10", "real_rate"),
    "DFII5": ("5Y实际利率", "%", "FRED DFII5", "real_rate"),
    "T10YIE": ("10Y盈亏平衡通胀", "%", "FRED T10YIE", "inflation"),
    "DFF": ("EFFR", "%", "FRED DFF", "policy"),
    "SOFR": ("SOFR", "%", "FRED SOFR", "policy"),
    "OBFR": ("OBFR", "%", "FRED OBFR", "policy"),
    "IORB": ("IORB", "%", "FRED IORB", "policy"),
    "RRPONTSYAWARD": ("ON RRP Award Rate", "%", "FRED RRPONTSYAWARD", "policy"),
    "RPONTSYD": ("SRF使用量", "$B", "FRED RPONTSYD", "funding"),
    "WTREGEN": ("TGA", "$M", "FRED WTREGEN", "liquidity"),
    "WALCL": ("美联储资产负债表", "$M", "FRED WALCL", "liquidity"),
    "TREAST": ("SOMA Treasury持仓", "$M", "FRED TREAST", "liquidity"),
    "WRESBAL": ("银行准备金", "$M", "FRED WRESBAL", "liquidity"),
    "RRPONTSYD": ("ON RRP", "$M", "FRED RRPONTSYD", "liquidity"),
    "CPIAUCSL": ("CPI指数", "index", "FRED CPIAUCSL", "macro"),
    "PCEPI": ("PCE价格指数", "index", "FRED PCEPI", "macro"),
    "PCEPILFE": ("核心PCE价格指数", "index", "FRED PCEPILFE", "macro"),
    "PCETRIM12M159SFRBDAL": ("达拉斯联储Trimmed Mean PCE", "%YoY", "FRED PCETRIM12M159SFRBDAL", "inflation"),
    "PPIACO": ("PPI指数", "index", "FRED PPIACO", "macro"),
    "UNRATE": ("失业率", "%", "FRED UNRATE", "macro"),
    "PAYEMS": ("非农就业", "thousand persons", "FRED PAYEMS", "macro"),
    "GDPC1": ("实际GDP", "$B", "FRED GDPC1", "macro"),
    "SP500": ("S&P 500", "index", "FRED SP500", "risk"),
    "VIXCLS": ("VIX", "index", "FRED VIXCLS", "risk"),
    "VXVCLS": ("VIX 3M", "index", "FRED VXVCLS", "risk"),
    "DTWEXBGS": ("美元广义指数", "index", "FRED DTWEXBGS", "fx"),
    "DCPF3M": ("90日AA金融商票", "%", "FRED DCPF3M", "funding"),
    "DTB3": ("3个月TBill", "%", "FRED DTB3", "funding"),
    "NFCI": ("金融条件指数(NFCI)", "index", "FRED NFCI", "credit"),
    "BAMLH0A0HYM2": ("HY信用利差", "%", "FRED BAMLH0A0HYM2", "credit"),
    "BAMLC0A0CM": ("IG信用利差", "%", "FRED BAMLC0A0CM", "credit"),
    "IRLTLT01JPM156N": ("日本10Y", "%", "FRED IRLTLT01JPM156N", "global_yield"),
    "IRLTLT01DEM156N": ("德国10Y", "%", "FRED IRLTLT01DEM156N", "global_yield"),
    "IRLTLT01GBM156N": ("英国10Y", "%", "FRED IRLTLT01GBM156N", "global_yield"),
    "DCOILWTICO": ("WTI原油", "$/bbl", "FRED DCOILWTICO", "commodity"),
    "DHHNGSP": ("天然气", "$/MMBtu", "FRED DHHNGSP", "commodity"),
    "OVXCLS": ("OVX原油波动率", "index", "FRED OVXCLS", "volatility"),
    "GVZCLS": ("GVZ黄金波动率", "index", "FRED GVZCLS", "volatility"),
}


def fetch_public_history(today: date | None = None, years: int = 5) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    today = today or date.today()
    curve_records = fetch_treasury_yield_curves(today=today, months_back=years * 12 + 2)
    fred = fetch_fred_series_bulk(FRED_SERIES)
    source_errors: list[dict[str, str]] = []
    try:
        auctions = fetch_treasury_auctions()
    except Exception as exc:  # noqa: BLE001
        auctions = []
        source_errors.append({"name": "TreasuryDirect auctioned securities", "error": str(exc), "severity": "warning"})
    observations = build_historical_observations(curve_records, fred, auctions, today=today, years=years)
    meta = {
        "curveRecordCount": len(curve_records),
        "fredSeriesCount": len(fred),
        "auctionRecordCount": len(auctions),
        "sourceErrors": source_errors,
        "observationCount": len(observations),
        "startDate": window_start(today, years=years).isoformat(),
        "endDate": today.isoformat(),
    }
    return observations, meta


def backfill_public_history(
    db_path: Path = DEFAULT_HISTORY_DB,
    *,
    years: int = 5,
    today: date | None = None,
) -> dict[str, Any]:
    observations, meta = fetch_public_history(today=today, years=years)
    saved = save_historical_observations(observations, db_path)
    summary = {**meta, "savedObservationCount": saved, "database": str(db_path)}
    summary["backfillRunId"] = save_history_backfill_run(summary, db_path, years=years)
    return summary


def build_historical_observations(
    curve_records: list[YieldCurveRecord],
    fred: dict[str, TimeSeries],
    auctions: list[dict[str, object]],
    *,
    today: date | None = None,
    years: int = 5,
) -> list[dict[str, Any]]:
    today = today or date.today()
    start = window_start(today, years=years)
    observations: list[dict[str, Any]] = []
    observations.extend(curve_observations(curve_records, start, today))
    observations.extend(fred_observations(fred, start, today))
    observations.extend(derived_observations(fred, start, today))
    observations.extend(auction_observations(auctions, start, today))
    return observations


def curve_observations(curve_records: list[YieldCurveRecord], start: date, end: date) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in sorted(curve_records, key=lambda item: item.date):
        if record.date < start or record.date > end:
            continue
        for tenor in TENORS:
            value = record.values.get(tenor)
            if is_valid_number(value):
                rows.append(history_row(record.date, "curve_yield", f"{tenor}收益率", float(value), "%", "U.S. Treasury yield curve XML", tenor))
        spreads = {
            "2s10s斜率": spread(record, "10Y", "2Y", 100),
            "5s30s斜率": spread(record, "30Y", "5Y", 100),
            "3M10Y斜率": spread(record, "10Y", "3M", 100),
        }
        for name, value in spreads.items():
            if is_valid_number(value):
                rows.append(history_row(record.date, "curve_spread", name, float(value), "bp", "U.S. Treasury yield curve XML"))
    return rows


def fred_observations(fred: dict[str, TimeSeries], start: date, end: date) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for series_id, series in fred.items():
        meta = FRED_SERIES_META.get(series_id)
        if meta is None:
            continue
        name, unit, source, category = meta
        rows.extend(point_rows(series.points, start, end, category, name, unit, source, series_id))
    return rows


def derived_observations(fred: dict[str, TimeSeries], start: date, end: date) -> list[dict[str, Any]]:
    net_liquidity = build_net_liquidity_points(fred)
    momentum = change_points(net_liquidity, days=30)
    momentum_13w = change_points(net_liquidity, days=91)
    tga_deviation = rolling_median_deviation_points(fred.get("WTREGEN"), window_days=364)
    onrrp_risk = onrrp_buffer_risk_points(fred.get("RRPONTSYD"))
    sofr_effr = spread_points(fred.get("SOFR"), fred.get("DFF"), multiplier=100)
    sofr_obfr = spread_points(fred.get("SOFR"), fred.get("OBFR"), multiplier=100)
    sofr_iorb = spread_points(fred.get("SOFR"), fred.get("IORB"), multiplier=100)
    sofr_rrp = spread_points(fred.get("SOFR"), fred.get("RRPONTSYAWARD"), multiplier=100)
    effr_iorb = spread_points(fred.get("DFF"), fred.get("IORB"), multiplier=100)
    cp_tbill = spread_points(fred.get("DCPF3M"), fred.get("DTB3"), multiplier=100)
    fragmentation = funding_fragmentation_points(fred.get("SOFR"), fred.get("OBFR"), fred.get("IORB"), fred.get("RRPONTSYAWARD"))
    real_level = weighted_points(fred.get("DFII5"), fred.get("DFII10"), 0.6, 0.4)
    real_curve = spread_points(fred.get("DFII10"), fred.get("DFII5"), multiplier=100)
    hy_ig = spread_points(fred.get("BAMLH0A0HYM2"), fred.get("BAMLC0A0CM"), multiplier=100)
    vix_term = ratio_points(fred.get("VIXCLS"), fred.get("VXVCLS"))
    dxy_vol = realized_volatility_points(fred.get("DTWEXBGS"), window=63)
    oil_vol_deviation = rolling_median_deviation_points(fred.get("OVXCLS"), window_days=365, positive_only=True)
    rows: list[dict[str, Any]] = []
    rows.extend(point_rows(net_liquidity, start, end, "liquidity", "净流动性", "$M", "FRED WALCL - WTREGEN - RRPONTSYD", "net_liquidity"))
    rows.extend(point_rows(momentum, start, end, "liquidity", "流动性动量", "$M", "Net liquidity 1M change", "net_liquidity_momentum"))
    rows.extend(point_rows(momentum_13w, start, end, "liquidity", "13周净流动性动量", "$M", "Net liquidity 13W change", "net_liquidity_13w_momentum"))
    rows.extend(point_rows(tga_deviation, start, end, "liquidity", "TGA偏离度", "$M", "FRED WTREGEN - 52W median", "tga_deviation"))
    rows.extend(point_rows(onrrp_risk, start, end, "liquidity", "ON RRP缓冲风险", "", "FRED RRPONTSYD risk signal", "onrrp_buffer_risk"))
    rows.extend(point_rows(sofr_effr, start, end, "policy", "SOFR-EFFR利差", "bp", "FRED SOFR - DFF", "sofr_effr_spread"))
    rows.extend(point_rows(sofr_obfr, start, end, "funding", "SOFR-OBFR回购摩擦", "bp", "FRED SOFR - OBFR", "sofr_obfr_spread"))
    rows.extend(point_rows(sofr_iorb, start, end, "funding", "SOFR-IORB走廊摩擦", "bp", "FRED SOFR - IORB", "sofr_iorb_spread"))
    rows.extend(point_rows(sofr_rrp, start, end, "funding", "SOFR-ON RRP走廊摩擦", "bp", "FRED SOFR - RRPONTSYAWARD", "sofr_rrp_award_spread"))
    rows.extend(point_rows(effr_iorb, start, end, "funding", "EFFR-IORB利差", "bp", "FRED DFF - IORB", "effr_iorb_spread"))
    rows.extend(point_rows(cp_tbill, start, end, "funding", "商票-TBill利差", "bp", "FRED DCPF3M - DTB3", "cp_tbill_spread"))
    rows.extend(point_rows(fragmentation, start, end, "funding", "资金分裂度(21D)", "", "SOFR corridor spread dispersion", "funding_fragmentation_21d"))
    rows.extend(point_rows(real_level, start, end, "real_rate", "真实利率水平", "%", "60% DFII5 + 40% DFII10", "real_rate_level"))
    rows.extend(point_rows(real_curve, start, end, "real_rate", "真实曲线(10Y-5Y)", "bp", "FRED DFII10 - DFII5", "real_curve_10y5y"))
    rows.extend(point_rows(hy_ig, start, end, "credit", "HY-IG利差", "bp", "FRED HY OAS - IG OAS", "hy_ig_oas_spread"))
    rows.extend(point_rows(vix_term, start, end, "risk", "VIX期限结构", "", "FRED VIXCLS / VXVCLS", "vix_term_structure"))
    rows.extend(point_rows(dxy_vol, start, end, "fx", "美元实现波动率", "%", "FRED DTWEXBGS 63D realized vol", "dxy_realized_vol"))
    rows.extend(point_rows(oil_vol_deviation, start, end, "volatility", "原油波动偏离", "", "FRED OVXCLS - rolling median", "oil_vol_deviation"))
    return rows


def auction_observations(auctions: list[dict[str, object]], start: date, end: date) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for auction in auctions:
        auction_date = parse_dashboard_date(auction.get("auctionDate"))
        btc = parse_number(auction.get("bidToCoverRatio"))
        if auction_date is None or auction_date < start or auction_date > end or not is_valid_number(btc):
            continue
        security_term = str(auction.get("securityTerm") or auction.get("term") or "").strip()
        security_type = str(auction.get("securityType") or auction.get("type") or "").strip()
        label = " ".join(part for part in (security_term, security_type) if part) or "Treasury auction"
        rows.append(history_row(auction_date, "auction", "拍卖投标倍数", float(btc), "", "TreasuryDirect auctioned securities", label))
    return rows


def point_rows(
    points: list[SeriesPoint],
    start: date,
    end: date,
    category: str,
    name: str,
    unit: str,
    source: str,
    label: str = "",
) -> list[dict[str, Any]]:
    return [
        history_row(point.date, category, name, point.value, unit, source, label)
        for point in points
        if start <= point.date <= end and is_valid_number(point.value)
    ]


def spread(record: YieldCurveRecord, left: str, right: str, multiplier: float = 1.0) -> float | None:
    left_value = record.values.get(left)
    right_value = record.values.get(right)
    if left_value is None or right_value is None:
        return None
    return (left_value - right_value) * multiplier


def history_row(
    row_date: date,
    category: str,
    name: str,
    value: float,
    unit: str,
    source: str,
    label: str = "",
) -> dict[str, Any]:
    return {
        "date": row_date.isoformat(),
        "category": category,
        "name": name,
        "label": label,
        "value": value,
        "unit": unit,
        "source": source,
    }


def is_valid_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))
