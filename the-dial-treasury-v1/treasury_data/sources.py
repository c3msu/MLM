from __future__ import annotations

import csv
import html
import json
import math
import re
import shutil
import ssl
import subprocess
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, replace
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from functools import lru_cache
from io import BytesIO, StringIO
from typing import Iterable
import zipfile


FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
FRED_RELEASE_CALENDAR_URL = "https://fred.stlouisfed.org/releases/calendar?rid={release_id}&view=year&vs={year}-01-01&ve={year}-12-31&od=asc"
FRED_MACRO_RELEASES = {
    10: "Consumer Price Index",
    46: "Producer Price Index",
    50: "Employment Situation",
}
TREASURY_XML_URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
    "?data=daily_treasury_yield_curve&field_tdr_date_value_month={month_key}"
)
TREASURY_AUCTIONED_URL = "https://www.treasurydirect.gov/TA_WS/securities/auctioned?format=json"
TREASURY_ANNOUNCED_URL = "https://www.treasurydirect.gov/TA_WS/securities/announced?format=json"
NYFED_ACM_URL = "https://www.newyorkfed.org/medialibrary/media/research/data_indicators/ACMTermPremium.xls"
CFTC_FINANCIAL_FUTURES_URL = "https://www.cftc.gov/files/dea/history/fut_fin_txt_{year}.zip"
TIC_TABLE5_TXT_URL = "https://ticdata.treasury.gov/resource-center/data-chart-center/tic/Documents/slt_table5.txt"
FISCALDATA_DEBT_SUBJECT_LIMIT_URL = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts/debt_subject_to_limit"
FED_FOMC_CALENDAR_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
FEDERAL_RESERVE_BASE_URL = "https://www.federalreserve.gov"
FEDERAL_RESERVE_PRESS_RELEASE_RSS_URL = "https://www.federalreserve.gov/feeds/press_all.xml"
CHICAGO_FED_CALENDARS_URL = "https://www.chicagofed.org/utilities/about-us/federal-reserve-calendars"
BEA_RELEASE_SCHEDULE_URL = "https://www.bea.gov/news/schedule"
TREASURY_BASE_URL = "https://home.treasury.gov"
TREASURY_PRESS_RELEASES_URL = "https://home.treasury.gov/news/press-releases"
TREASURY_QRA_DOCS_URL = (
    "https://home.treasury.gov/policy-issues/financing-the-government/quarterly-refunding/"
    "most-recent-quarterly-refunding-documents"
)
NYFED_PD_ASOF_URL = "https://markets.newyorkfed.org/api/pd/list/asof.json"
NYFED_PD_LATEST_URL = "https://markets.newyorkfed.org/api/pd/latest/{seriesbreak}.json"
STOOQ_QUOTE_URL = "https://stooq.com/q/l/?s={symbol}&f=sd2t2ohlcv&h&e=csv"
FED_FUNDS_FUTURES_SYMBOL = "zq.f"
GOLD_SPOT_SYMBOL = "xauusd"

TENORS = ["1M", "3M", "6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "20Y", "30Y"]
TREASURY_XML_FIELDS = {
    "1M": "BC_1MONTH",
    "3M": "BC_3MONTH",
    "6M": "BC_6MONTH",
    "1Y": "BC_1YEAR",
    "2Y": "BC_2YEAR",
    "3Y": "BC_3YEAR",
    "5Y": "BC_5YEAR",
    "7Y": "BC_7YEAR",
    "10Y": "BC_10YEAR",
    "20Y": "BC_20YEAR",
    "30Y": "BC_30YEAR",
}
MONTH_NAMES = {
    "January": 1,
    "February": 2,
    "March": 3,
    "April": 4,
    "May": 5,
    "June": 6,
    "July": 7,
    "August": 8,
    "September": 9,
    "October": 10,
    "November": 11,
    "December": 12,
}
OFFICIAL_NEWS_KEYWORDS = (
    "fomc",
    "monetary policy",
    "interest rate",
    "discount rate",
    "federal funds",
    "balance sheet",
    "powell",
    "chair",
    "treasury international capital",
    "tic",
    "quarterly refunding",
    "borrowing",
    "marketable",
    "auction",
    "debt",
    "liquidity",
    "financial stability",
    "private credit",
    "inflation",
    "employment",
    "gdp",
    "personal income",
    "consumer price",
    "producer price",
)


@lru_cache(maxsize=1)
def https_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001
        return ssl.create_default_context()


@dataclass(frozen=True)
class SeriesPoint:
    date: date
    value: float


@dataclass(frozen=True)
class TimeSeries:
    series_id: str
    points: list[SeriesPoint]

    @property
    def latest(self) -> SeriesPoint:
        if not self.points:
            raise ValueError(f"{self.series_id} has no numeric observations")
        return self.points[-1]

    def value_at_or_before(self, target: date) -> SeriesPoint:
        for point in reversed(self.points):
            if point.date <= target:
                return point
        return self.points[0]


@dataclass(frozen=True)
class YieldCurveRecord:
    date: date
    values: dict[str, float]


@dataclass(frozen=True)
class AcmRecord:
    date: date
    term_premium_10y: float
    expected_rate_10y: float


@dataclass(frozen=True)
class CftcTreasuryPosition:
    report_date: date
    market: str
    open_interest: int
    dealer_net: int
    asset_manager_net: int
    leveraged_net: int
    leveraged_net_pct_oi: float


@dataclass(frozen=True)
class TicHolding:
    country: str
    value_billions: float
    monthly_change_billions: float | None


@dataclass(frozen=True)
class TicHoldings:
    period: str
    holdings: list[TicHolding]
    total: TicHolding | None
    official: TicHolding | None


@dataclass(frozen=True)
class CalendarEvent:
    date: date
    title: str
    source: str
    importance: str


@dataclass(frozen=True)
class NewsItem:
    date: date
    source: str
    title: str
    url: str


@dataclass(frozen=True)
class PrimaryDealerStats:
    as_of: date
    seriesbreak: str
    metrics_millions: dict[str, float]


@dataclass(frozen=True)
class FomcProjection:
    release_date: date
    median_fed_funds: dict[str, float]


@dataclass(frozen=True)
class QuarterlyRefunding:
    release_date: date
    quarter: str
    policy_statement_url: str
    financing_estimates_url: str | None
    next_policy_statement_date: date | None
    next_financing_estimates_date: date | None
    current_quarter_borrowing_billions: float | None = None
    next_quarter_borrowing_billions: float | None = None
    current_quarter_cash_balance_billions: float | None = None
    next_quarter_cash_balance_billions: float | None = None
    refunding_amount_billions: float | None = None
    refunding_new_cash_billions: float | None = None
    coupon_stance: str = ""
    bill_issuance: str = ""
    buyback_total_billions: float | None = None
    tga_peak: str = ""


@dataclass(frozen=True)
class DebtLimitStatus:
    record_date: date
    statutory_limit_millions: float
    debt_subject_to_limit_millions: float
    headroom_millions: float
    public_debt_millions: float
    intragov_holdings_millions: float
    debt_not_subject_millions: float


@dataclass(frozen=True)
class MarketQuote:
    symbol: str
    date: date
    close: float
    source: str

    @property
    def implied_rate(self) -> float:
        return 100 - self.close


def fetch_bytes(url: str, timeout: int = 30, retries: int = 2) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 TreasuryFactorDesk/1.0",
            "Accept": "application/octet-stream,application/zip,application/vnd.ms-excel,text/plain,*/*",
        },
    )
    context = https_context() if url.startswith("https://") else None
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
                return response.read()
        except (OSError, urllib.error.URLError) as exc:
            last_error = exc
            if attempt >= retries:
                break
            time.sleep(0.5 * (attempt + 1))
    if shutil.which("curl"):
        completed = subprocess.run(
            ["curl", "-L", "--fail", "--silent", "--show-error", "--max-time", str(timeout), url],
            check=True,
            capture_output=True,
            timeout=timeout + 5,
        )
        return completed.stdout
    raise last_error or RuntimeError(f"Failed to fetch {url}")


def fetch_bytes_curl_first(url: str, timeout: int = 30, retries: int = 1) -> bytes:
    last_error: Exception | None = None
    if shutil.which("curl"):
        for attempt in range(retries + 1):
            try:
                completed = subprocess.run(
                    ["curl", "-L", "--fail", "--silent", "--show-error", "--max-time", str(timeout), url],
                    check=True,
                    capture_output=True,
                    timeout=timeout + 5,
                )
                return completed.stdout
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                last_error = exc
                if attempt >= retries:
                    break
                time.sleep(0.5 * (attempt + 1))
        raise last_error or RuntimeError(f"Failed to fetch {url}")
    return fetch_bytes(url, timeout=timeout, retries=0)


def fetch_text(url: str, timeout: int = 30, retries: int = 2) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 TreasuryFactorDesk/1.0",
            "Accept": "text/csv,application/xml,application/json,text/plain,*/*",
        },
    )
    context = https_context() if url.startswith("https://") else None
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
                return response.read().decode("utf-8", errors="replace")
        except (OSError, urllib.error.URLError) as exc:
            last_error = exc
            if attempt >= retries:
                break
            time.sleep(0.5 * (attempt + 1))
    if shutil.which("curl"):
        completed = subprocess.run(
            ["curl", "-L", "--fail", "--silent", "--show-error", "--max-time", str(timeout), url],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout + 5,
        )
        return completed.stdout
    raise last_error or RuntimeError(f"Failed to fetch {url}")


def fetch_text_curl_first(url: str, timeout: int = 30, retries: int = 1) -> str:
    last_error: Exception | None = None
    if shutil.which("curl"):
        for attempt in range(retries + 1):
            try:
                completed = subprocess.run(
                    ["curl", "-L", "--fail", "--silent", "--show-error", "--max-time", str(timeout), url],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=timeout + 5,
                )
                return completed.stdout
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                last_error = exc
                if attempt >= retries:
                    break
                time.sleep(0.5 * (attempt + 1))
        raise last_error or RuntimeError(f"Failed to fetch {url}")
    return fetch_text(url, timeout=timeout, retries=0)


def parse_fred_csv(content: str, series_id: str) -> TimeSeries:
    reader = csv.DictReader(StringIO(content))
    if not reader.fieldnames or "observation_date" not in reader.fieldnames:
        raise ValueError(f"FRED response for {series_id} did not contain observation_date")
    value_field = series_id if series_id in reader.fieldnames else reader.fieldnames[-1]
    points: list[SeriesPoint] = []
    for row in reader:
        raw_date = (row.get("observation_date") or "").strip()
        raw_value = (row.get(value_field) or "").strip()
        if not raw_date or raw_value in {"", "."}:
            continue
        try:
            points.append(SeriesPoint(datetime.strptime(raw_date, "%Y-%m-%d").date(), float(raw_value)))
        except ValueError:
            continue
    if not points:
        raise ValueError(f"FRED response for {series_id} did not contain numeric observations")
    points.sort(key=lambda item: item.date)
    return TimeSeries(series_id=series_id, points=points)


def fetch_fred_series(series_id: str, timeout: int = 30) -> TimeSeries:
    return parse_fred_csv(fetch_text(FRED_CSV_URL.format(series_id=series_id), timeout=timeout), series_id)


def parse_stooq_quote_csv(content: str, symbol: str) -> MarketQuote:
    reader = csv.DictReader(StringIO(content))
    if not reader.fieldnames or "Close" not in reader.fieldnames:
        raise ValueError(f"Stooq response for {symbol} did not contain Close")
    for row in reader:
        raw_date = (row.get("Date") or "").strip()
        raw_close = (row.get("Close") or "").strip()
        if raw_date in {"", "N/D"} or raw_close in {"", "N/D"}:
            continue
        return MarketQuote(
            symbol=(row.get("Symbol") or symbol).strip(),
            date=datetime.strptime(raw_date, "%Y-%m-%d").date(),
            close=float(raw_close),
            source="Stooq",
        )
    raise ValueError(f"Stooq response for {symbol} did not contain a numeric quote")


def fetch_stooq_quote(symbol: str, timeout: int = 15) -> MarketQuote:
    url = STOOQ_QUOTE_URL.format(symbol=symbol)
    return parse_stooq_quote_csv(fetch_text_curl_first(url, timeout=timeout), symbol.upper())


def fetch_fed_funds_futures_quote(timeout: int = 15) -> MarketQuote:
    return fetch_stooq_quote(FED_FUNDS_FUTURES_SYMBOL, timeout=timeout)


def fetch_gold_spot_quote(timeout: int = 15) -> MarketQuote:
    return fetch_stooq_quote(GOLD_SPOT_SYMBOL, timeout=timeout)


def parse_fred_bulk_zip(content: bytes, series_ids: Iterable[str]) -> dict[str, TimeSeries]:
    series_list = list(series_ids)
    points: dict[str, list[SeriesPoint]] = {series_id: [] for series_id in series_list}
    for text in fred_csv_texts(content):
        reader = csv.DictReader(StringIO(text))
        if not reader.fieldnames or "observation_date" not in reader.fieldnames:
            continue
        wanted = [series_id for series_id in series_list if series_id in reader.fieldnames]
        if not wanted:
            continue
        for row in reader:
            row_date = parse_date_value(row.get("observation_date"))
            if row_date is None:
                continue
            for series_id in wanted:
                value = parse_optional_float(row.get(series_id))
                if value is not None:
                    points[series_id].append(SeriesPoint(row_date, value))
    parsed: dict[str, TimeSeries] = {}
    for series_id, series_points in points.items():
        if series_points:
            series_points.sort(key=lambda item: item.date)
            parsed[series_id] = TimeSeries(series_id=series_id, points=series_points)
    if not parsed:
        raise ValueError("FRED bulk daily.csv did not contain numeric observations")
    return parsed


def fred_csv_texts(content: bytes) -> list[str]:
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
            if not csv_names:
                raise ValueError("FRED bulk zip did not contain CSV files")
            return [archive.read(name).decode("utf-8-sig", errors="replace") for name in csv_names]
    except zipfile.BadZipFile:
        return [content.decode("utf-8-sig", errors="replace")]


def fetch_fred_series_bulk(series_ids: Iterable[str], timeout: int = 45, chunk_size: int = 12) -> dict[str, TimeSeries]:
    series_list = list(series_ids)
    parsed: dict[str, TimeSeries] = {}
    for index in range(0, len(series_list), chunk_size):
        chunk = series_list[index : index + chunk_size]
        content = fetch_bytes_curl_first(FRED_CSV_URL.format(series_id=",".join(chunk)), timeout=timeout)
        parsed.update(parse_fred_bulk_zip(content, chunk))
    return parsed


def parse_optional_float(raw: object) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, float) and math.isnan(raw):
        return None
    text = str(raw).strip().replace(",", "")
    if text in {"", ".", "nan", "NaN", "None"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_optional_int(raw: object) -> int | None:
    value = parse_optional_float(raw)
    if value is None:
        return None
    return int(value)


def parse_date_value(raw: object) -> date | None:
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    text = str(raw).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d", "%d-%b-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            try:
                return datetime.strptime(text[:10], fmt).date()
            except ValueError:
                continue
    return None


def select_latest_acm_record(rows: Iterable[dict[str, object]]) -> AcmRecord:
    records: list[AcmRecord] = []
    for row in rows:
        record_date = parse_date_value(row.get("DATE") or row.get("Date"))
        term_premium = parse_optional_float(row.get("ACMTP10"))
        expected_rate = parse_optional_float(row.get("ACMRNY10"))
        if record_date is None or term_premium is None or expected_rate is None:
            continue
        records.append(
            AcmRecord(
                date=record_date,
                term_premium_10y=term_premium,
                expected_rate_10y=expected_rate,
            )
        )
    if not records:
        raise ValueError("NY Fed ACM daily sheet did not contain complete ACMTP10/ACMRNY10 rows")
    return max(records, key=lambda item: item.date)


def parse_acm_excel_bytes(content: bytes) -> AcmRecord:
    import pandas as pd

    daily = pd.read_excel(BytesIO(content), sheet_name="ACM Daily")
    return select_latest_acm_record(daily.to_dict("records"))


def fetch_acm_term_premium(timeout: int = 45) -> AcmRecord:
    return parse_acm_excel_bytes(fetch_bytes(NYFED_ACM_URL, timeout=timeout))


def clean_cftc_market_name(raw: str) -> str:
    return raw.split(" - ", 1)[0].strip()


def is_treasury_futures_market(market: str) -> bool:
    upper = market.upper()
    return any(marker in upper for marker in ("TREASURY", "T-NOTE", "T-BOND", "UST "))


def parse_cftc_financial_futures_txt(content: str) -> list[CftcTreasuryPosition]:
    reader = csv.DictReader(StringIO(content))
    rows: list[tuple[date, dict[str, str]]] = []
    for row in reader:
        market = row.get("Market_and_Exchange_Names", "")
        report_date = parse_date_value(row.get("Report_Date_as_YYYY-MM-DD"))
        if report_date is not None and is_treasury_futures_market(market):
            rows.append((report_date, row))
    if not rows:
        raise ValueError("CFTC financial futures file did not contain Treasury futures rows")

    latest_date = max(item[0] for item in rows)
    positions: list[CftcTreasuryPosition] = []
    for report_date, row in rows:
        if report_date != latest_date:
            continue
        open_interest = parse_optional_int(row.get("Open_Interest_All")) or 0
        dealer_net = (parse_optional_int(row.get("Dealer_Positions_Long_All")) or 0) - (
            parse_optional_int(row.get("Dealer_Positions_Short_All")) or 0
        )
        asset_manager_net = (parse_optional_int(row.get("Asset_Mgr_Positions_Long_All")) or 0) - (
            parse_optional_int(row.get("Asset_Mgr_Positions_Short_All")) or 0
        )
        leveraged_net = (parse_optional_int(row.get("Lev_Money_Positions_Long_All")) or 0) - (
            parse_optional_int(row.get("Lev_Money_Positions_Short_All")) or 0
        )
        positions.append(
            CftcTreasuryPosition(
                report_date=report_date,
                market=clean_cftc_market_name(row.get("Market_and_Exchange_Names", "")),
                open_interest=open_interest,
                dealer_net=dealer_net,
                asset_manager_net=asset_manager_net,
                leveraged_net=leveraged_net,
                leveraged_net_pct_oi=round((leveraged_net / open_interest) * 100, 2) if open_interest else 0.0,
            )
        )
    positions.sort(key=lambda item: (-abs(item.leveraged_net), item.market))
    return positions


def parse_cftc_financial_zip(content: bytes) -> list[CftcTreasuryPosition]:
    with zipfile.ZipFile(BytesIO(content)) as archive:
        names = [name for name in archive.namelist() if name.lower().endswith(".txt")]
        if not names:
            raise ValueError("CFTC financial futures zip did not contain a text file")
        text = archive.read(names[0]).decode("latin-1")
    return parse_cftc_financial_futures_txt(text)


def fetch_cftc_treasury_positions(year: int | None = None, timeout: int = 45) -> list[CftcTreasuryPosition]:
    target_year = year or date.today().year
    try:
        content = fetch_bytes(CFTC_FINANCIAL_FUTURES_URL.format(year=target_year), timeout=timeout)
    except Exception:
        if year is not None:
            raise
        content = fetch_bytes(CFTC_FINANCIAL_FUTURES_URL.format(year=target_year - 1), timeout=timeout)
    return parse_cftc_financial_zip(content)


def parse_tic_table5_txt(content: str) -> TicHoldings:
    rows = [line.split("\t") for line in content.splitlines() if line.strip()]
    header_index = next((idx for idx, row in enumerate(rows) if row and row[0].strip().lower() == "country"), None)
    if header_index is None:
        raise ValueError("TIC table 5 text did not contain a Country header")
    header = [item.strip() for item in rows[header_index]]
    periods = header[1:]
    if not periods:
        raise ValueError("TIC table 5 text did not contain monthly columns")
    latest_period = periods[0]
    previous_index = 2 if len(periods) > 1 else None

    holdings: list[TicHolding] = []
    total: TicHolding | None = None
    official: TicHolding | None = None
    for row in rows[header_index + 1 :]:
        if len(row) < 2:
            continue
        country = row[0].strip()
        latest_value = parse_optional_float(row[1])
        if not country or latest_value is None:
            continue
        previous_value = parse_optional_float(row[previous_index]) if previous_index is not None and len(row) > previous_index else None
        monthly_change = round(latest_value - previous_value, 1) if previous_value is not None else None
        holding = TicHolding(country=country, value_billions=latest_value, monthly_change_billions=monthly_change)
        normalized = country.lower()
        if normalized == "grand total":
            total = holding
        elif normalized.startswith("of which: foreign official"):
            official = holding
        elif not normalized.startswith("of which:"):
            holdings.append(holding)
    return TicHoldings(period=latest_period, holdings=holdings, total=total, official=official)


def fetch_tic_major_holders(timeout: int = 30) -> TicHoldings:
    return parse_tic_table5_txt(fetch_text(TIC_TABLE5_TXT_URL, timeout=timeout))


def parse_debt_subject_to_limit_json(payload: object) -> DebtLimitStatus:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ValueError("Fiscal Data debt subject to limit payload did not contain data rows")
    rows = [row for row in payload["data"] if isinstance(row, dict)]
    record_dates = [parse_date_value(row.get("record_date")) for row in rows]
    record_date = max((item for item in record_dates if item is not None), default=None)
    if record_date is None:
        raise ValueError("Fiscal Data debt subject to limit payload did not contain a record date")

    public_debt = 0.0
    intragov = 0.0
    not_subject = 0.0
    other_subject = 0.0
    statutory_limit: float | None = None
    for row in rows:
        value = parse_optional_float(row.get("close_today_bal"))
        if value is None:
            continue
        category = str(row.get("debt_catg") or "").strip()
        if category == "Debt Held by the Public":
            public_debt += value
        elif category == "Intragovernmental Holdings":
            intragov += value
        elif category == "Debt Not Subject to Limit":
            not_subject += value
        elif category == "Other Debt Subject to Limit":
            other_subject += value
        elif category == "Statutory Debt Limit":
            statutory_limit = value

    if statutory_limit is None:
        raise ValueError("Fiscal Data debt subject to limit payload did not contain Statutory Debt Limit")
    debt_subject = public_debt + intragov + other_subject - not_subject
    return DebtLimitStatus(
        record_date=record_date,
        statutory_limit_millions=statutory_limit,
        debt_subject_to_limit_millions=round(debt_subject, 1),
        headroom_millions=round(statutory_limit - debt_subject, 1),
        public_debt_millions=public_debt,
        intragov_holdings_millions=intragov,
        debt_not_subject_millions=not_subject,
    )


def fetch_debt_limit_status(timeout: int = 30) -> DebtLimitStatus:
    latest_payload = fetch_json(f"{FISCALDATA_DEBT_SUBJECT_LIMIT_URL}?fields=record_date&sort=-record_date&page%5Bsize%5D=1", timeout=timeout)
    if not isinstance(latest_payload, dict) or not isinstance(latest_payload.get("data"), list) or not latest_payload["data"]:
        raise ValueError("Fiscal Data debt subject to limit latest-date lookup returned no rows")
    latest_date = str(latest_payload["data"][0].get("record_date") or "").strip()
    if not latest_date:
        raise ValueError("Fiscal Data debt subject to limit latest-date lookup returned no date")
    payload = fetch_json(
        f"{FISCALDATA_DEBT_SUBJECT_LIMIT_URL}?filter=record_date:eq:{latest_date}&page%5Bsize%5D=100&sort=src_line_nbr",
        timeout=timeout,
    )
    return parse_debt_subject_to_limit_json(payload)


def strip_html(raw: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", raw)).strip()


def normalized_text(raw: str) -> str:
    text = strip_html(raw)
    text = text.replace("\xa0", " ").replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", text).strip()


def treasury_absolute_url(href: str) -> str:
    if href.startswith("http"):
        return href
    return TREASURY_BASE_URL + href


def is_rates_relevant_news_title(title: str) -> bool:
    lowered = title.lower()
    for keyword in OFFICIAL_NEWS_KEYWORDS:
        if keyword in {"tic", "gdp", "cpi", "ppi"}:
            if re.search(rf"\b{re.escape(keyword)}\b", lowered):
                return True
            continue
        if keyword in lowered:
            return True
    return False


def parse_rss_pub_date(raw: str) -> date | None:
    if not raw.strip():
        return None
    try:
        return parsedate_to_datetime(raw.strip()).date()
    except (TypeError, ValueError):
        return None


def parse_iso_datetime_date(raw: str) -> date | None:
    if not raw.strip():
        return None
    try:
        return datetime.fromisoformat(raw.strip().replace("Z", "+00:00")).date()
    except ValueError:
        return None


def parse_official_rss_news_items(content: str, source: str) -> list[NewsItem]:
    root = ET.fromstring(content.lstrip("\ufeff").strip())
    items: list[NewsItem] = []
    seen: set[tuple[str, str]] = set()
    for item in root.findall(".//item"):
        title = normalized_text(item.findtext("title") or "")
        pub_date = parse_rss_pub_date(item.findtext("pubDate") or "")
        url = normalized_text(item.findtext("link") or "")
        if not title or pub_date is None or not is_rates_relevant_news_title(title):
            continue
        key = (title, url)
        if key in seen:
            continue
        seen.add(key)
        items.append(NewsItem(date=pub_date, source=source, title=title, url=url))
    items.sort(key=lambda entry: (entry.date, entry.title), reverse=True)
    return items


def parse_treasury_press_releases_html(content: str) -> list[NewsItem]:
    pattern = re.compile(
        r'<time\s+[^>]*datetime="([^"]+)"[^>]*>.*?</time>.*?'
        r'<h3[^>]*class="[^"]*featured-stories__headline[^"]*"[^>]*>\s*'
        r'<a\s+[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    items: list[NewsItem] = []
    seen: set[tuple[str, str]] = set()
    for raw_date, href, raw_title in pattern.findall(content):
        title = normalized_text(raw_title)
        release_date = parse_iso_datetime_date(raw_date)
        if release_date is None or not title or not is_rates_relevant_news_title(title):
            continue
        url = treasury_absolute_url(html.unescape(href))
        key = (title, url)
        if key in seen:
            continue
        seen.add(key)
        items.append(NewsItem(date=release_date, source="U.S. Treasury", title=title, url=url))
    items.sort(key=lambda entry: (entry.date, entry.title), reverse=True)
    return items


def fetch_federal_reserve_press_releases(timeout: int = 30) -> list[NewsItem]:
    return parse_official_rss_news_items(fetch_text_curl_first(FEDERAL_RESERVE_PRESS_RELEASE_RSS_URL, timeout=timeout), source="Federal Reserve")


def fetch_treasury_press_releases(timeout: int = 30) -> list[NewsItem]:
    return parse_treasury_press_releases_html(fetch_text_curl_first(TREASURY_PRESS_RELEASES_URL, timeout=timeout))


def parse_month_day_year(text: str) -> date | None:
    match = re.search(r"([A-Za-z]+)\s+(\d{1,2})\s*,\s*(\d{4})", normalized_text(text), re.IGNORECASE)
    if not match:
        return None
    month_raw, day_raw, year_raw = match.groups()
    month_number = MONTH_NAMES.get(month_raw[:1].upper() + month_raw[1:].lower())
    if month_number is None:
        return None
    return date(int(year_raw), month_number, int(day_raw))


def extract_sentence_containing(text: str, *needles: str) -> str:
    clean = normalized_text(text)
    sentences = re.split(r"(?<=[.!?])\s+", clean)
    lower_needles = [needle.lower() for needle in needles]
    for sentence in sentences:
        lowered = sentence.lower()
        if all(needle in lowered for needle in lower_needles):
            return sentence.strip()
    return ""


def parse_money_billions(raw: str) -> float | None:
    value = parse_optional_float(raw.replace("$", ""))
    return None if value is None else float(value)


def parse_quarterly_refunding_documents_html(content: str) -> QuarterlyRefunding:
    policy_url = ""
    financing_url: str | None = None
    quarter = ""
    release_date: date | None = None
    next_policy_date: date | None = None
    next_financing_date: date | None = None

    block_pattern = re.compile(
        r"(<h3[^>]*>\s*DOCUMENTS RELEASED.*?</h3>)(.*?)(?=<h3[^>]*>\s*DOCUMENTS RELEASED|$)",
        re.IGNORECASE | re.DOTALL,
    )
    for block_match in block_pattern.finditer(content):
        header = block_match.group(1)
        body = block_match.group(2)
        block_release_date = parse_month_day_year(header)
        next_release_match = re.search(r"The next release is scheduled for(.*?)\)", body, re.IGNORECASE | re.DOTALL)
        next_release_date = parse_month_day_year(next_release_match.group(1)) if next_release_match else None
        for href, raw_label in re.findall(r'<a\s+[^>]*href="([^"]+)"[^>]*>(.*?)</a>', body, re.IGNORECASE | re.DOTALL):
            label = normalized_text(raw_label)
            if label.lower().startswith("financing estimates:"):
                financing_url = treasury_absolute_url(html.unescape(href))
                next_financing_date = next_release_date
                if not quarter:
                    quarter = label.split(":", 1)[1].strip()
            elif label.lower().startswith("policy statement:"):
                policy_url = treasury_absolute_url(html.unescape(href))
                next_policy_date = next_release_date
                quarter = label.split(":", 1)[1].strip()
                release_date = block_release_date

    if not policy_url or release_date is None:
        raise ValueError("Treasury QRA documents page did not contain a policy statement link and release date")
    return QuarterlyRefunding(
        release_date=release_date,
        quarter=quarter,
        policy_statement_url=policy_url,
        financing_estimates_url=financing_url,
        next_policy_statement_date=next_policy_date,
        next_financing_estimates_date=next_financing_date,
    )


def parse_quarterly_refunding_financing_html(content: str, refunding: QuarterlyRefunding) -> QuarterlyRefunding:
    text = normalized_text(content)
    rows: list[tuple[float, float]] = []
    for match in re.finditer(
        r"During the [A-Za-z]+-[A-Za-z]+ \d{4}\s+quarter,\s+Treasury expects to borrow\s+\$([0-9,.]+)\s+billion.*?cash balance of\s+\$([0-9,.]+)\s+billion",
        text,
        re.IGNORECASE,
    ):
        borrowing = parse_money_billions(match.group(1))
        cash_balance = parse_money_billions(match.group(2))
        if borrowing is not None and cash_balance is not None:
            rows.append((borrowing, cash_balance))
    if not rows:
        return refunding
    current_borrowing, current_cash = rows[0]
    next_borrowing, next_cash = rows[1] if len(rows) > 1 else (None, None)
    return replace(
        refunding,
        current_quarter_borrowing_billions=current_borrowing,
        current_quarter_cash_balance_billions=current_cash,
        next_quarter_borrowing_billions=next_borrowing,
        next_quarter_cash_balance_billions=next_cash,
    )


def parse_quarterly_refunding_policy_html(content: str, refunding: QuarterlyRefunding) -> QuarterlyRefunding:
    text = normalized_text(content)
    refunding_match = re.search(
        r"offering\s+\$([0-9,.]+)\s+billion.*?raise new cash.*?\$([0-9,.]+)\s+billion",
        text,
        re.IGNORECASE,
    )
    refunding_amount = parse_money_billions(refunding_match.group(1)) if refunding_match else None
    new_cash = parse_money_billions(refunding_match.group(2)) if refunding_match else None
    coupon_stance = extract_sentence_containing(content, "nominal coupon", "auction sizes")
    bill_issuance = extract_sentence_containing(content, "bill", "offering sizes")
    tga_peak = extract_sentence_containing(content, "TGA", "peak")
    buyback_sentence = extract_sentence_containing(content, "purchase up to")
    buyback_values = [value for value in (parse_money_billions(raw) for raw in re.findall(r"\$([0-9,.]+)\s+billion", buyback_sentence)) if value is not None]
    next_announcement = parse_month_day_year(extract_sentence_containing(content, "next quarterly refunding announcement"))
    return replace(
        refunding,
        refunding_amount_billions=refunding_amount,
        refunding_new_cash_billions=new_cash,
        coupon_stance=coupon_stance,
        bill_issuance=bill_issuance,
        buyback_total_billions=round(sum(buyback_values), 1) if buyback_values else None,
        tga_peak=tga_peak,
        next_policy_statement_date=refunding.next_policy_statement_date or next_announcement,
    )


def fetch_quarterly_refunding(timeout: int = 30) -> QuarterlyRefunding:
    refunding = parse_quarterly_refunding_documents_html(fetch_text(TREASURY_QRA_DOCS_URL, timeout=timeout))
    if refunding.financing_estimates_url:
        refunding = parse_quarterly_refunding_financing_html(fetch_text(refunding.financing_estimates_url, timeout=timeout), refunding)
    refunding = parse_quarterly_refunding_policy_html(fetch_text(refunding.policy_statement_url, timeout=timeout), refunding)
    return refunding


def month_number_from_fomc_label(label: str, end_day: int | None = None, start_day: int | None = None) -> int | None:
    parts = [part.strip() for part in label.split("/") if part.strip()]
    if not parts:
        return None
    selected = parts[-1] if len(parts) > 1 and start_day is not None and end_day is not None and end_day < start_day else parts[0]
    matches = [name for name in MONTH_NAMES if selected.lower().startswith(name[:3].lower())]
    if not matches:
        return None
    return MONTH_NAMES[matches[0]]


def parse_fomc_calendar_html(content: str) -> list[CalendarEvent]:
    panel_pattern = re.compile(
        r'<div class="panel panel-default"><div class="panel-heading"><h4><a id="[^"]+">(\d{4}) FOMC Meetings</a></h4></div>(.*?)(?=<div class="panel panel-default"><div class="panel-heading"><h4><a id="[^"]+">\d{4} FOMC Meetings</a></h4></div>|$)',
        re.IGNORECASE | re.DOTALL,
    )
    month_pattern = re.compile(r'fomc-meeting__month[^>]*>\s*<strong>\s*([^<]+)', re.IGNORECASE | re.DOTALL)
    date_pattern = re.compile(r'fomc-meeting__date[^>]*>\s*([^<]+)</div>', re.IGNORECASE | re.DOTALL)
    events: list[CalendarEvent] = []
    for panel_match in panel_pattern.finditer(content):
        year = int(panel_match.group(1))
        panel_body = panel_match.group(2)
        blocks = re.split(r'<div class="(?=[^"]*\brow\b)(?=[^"]*\bfomc-meeting\b)[^"]*"[^>]*>', panel_body, flags=re.IGNORECASE)
        for block in blocks[1:]:
            month_match = month_pattern.search(block)
            date_match = date_pattern.search(block)
            if not month_match or not date_match:
                continue
            month_label = strip_html(month_match.group(1))
            date_label = strip_html(date_match.group(1))
            days = [int(item) for item in re.findall(r"\d{1,2}", date_label)]
            if not days:
                continue
            start_day = days[0]
            end_day = days[-1]
            month_number = month_number_from_fomc_label(month_label, end_day=end_day, start_day=start_day)
            if month_number is None:
                continue
            title = "FOMC decision + SEP" if "*" in date_label or "Projection Materials" in block else "FOMC decision"
            try:
                events.append(
                    CalendarEvent(
                        date=date(year, month_number, end_day),
                        title=title,
                        source="Federal Reserve FOMC calendar",
                        importance="高",
                    )
                )
            except ValueError:
                continue
    events.sort(key=lambda item: item.date)
    return events


def parse_chicago_fed_fomc_calendar_html(content: str) -> list[CalendarEvent]:
    table_match = re.search(
        r'<table[^>]*summary="FOMC Meeting Schedule"[^>]*>(.*?)</table>',
        content,
        re.IGNORECASE | re.DOTALL,
    )
    if not table_match:
        return []
    table = table_match.group(1)
    year_match = re.search(r"<th[^>]*>\s*(\d{4})\s*</th>", table, re.IGNORECASE | re.DOTALL)
    if not year_match:
        return []
    year = int(year_match.group(1))
    events: list[CalendarEvent] = []
    for raw_cell in re.findall(r"<td[^>]*>(.*?)</td>", table, re.IGNORECASE | re.DOTALL):
        label = normalized_text(raw_cell)
        days = [int(item) for item in re.findall(r"\d{1,2}", label)]
        if not days:
            continue
        start_day = days[0]
        end_day = days[-1]
        month_number = month_number_from_fomc_label(label, end_day=end_day, start_day=start_day)
        if month_number is None:
            continue
        title = "FOMC decision + SEP" if "*" in label else "FOMC decision"
        try:
            events.append(
                CalendarEvent(
                    date=date(year, month_number, end_day),
                    title=title,
                    source="Federal Reserve Bank of Chicago FOMC schedule",
                    importance="高",
                )
            )
        except ValueError:
            continue
    events.sort(key=lambda item: item.date)
    return events


def fetch_fomc_calendar_events(timeout: int = 30) -> list[CalendarEvent]:
    try:
        events = parse_fomc_calendar_html(fetch_text_curl_first(FED_FOMC_CALENDAR_URL, timeout=timeout))
        if events:
            return events
    except Exception:  # noqa: BLE001
        pass
    fallback_events = parse_chicago_fed_fomc_calendar_html(fetch_text_curl_first(CHICAGO_FED_CALENDARS_URL, timeout=timeout))
    if not fallback_events:
        raise ValueError("FOMC calendar did not contain meeting dates from Fed Board or Chicago Fed")
    return fallback_events



def parse_fred_release_calendar_html(content: str, title_prefix: str = "") -> list[CalendarEvent]:
    events: list[CalendarEvent] = []
    row_pattern = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
    date_pattern = re.compile(r'<span[^>]*font-weight:\s*bold[^>]*>([^<]+)</span>', re.IGNORECASE | re.DOTALL)
    release_pattern = re.compile(r'<a\s+href="/release\?rid=\d+"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
    current_date: date | None = None
    for row_match in row_pattern.finditer(content):
        row = row_match.group(1)
        for raw_date in date_pattern.findall(row):
            date_text = normalized_text(raw_date)
            try:
                current_date = datetime.strptime(date_text, "%A %B %d, %Y").date()
                break
            except ValueError:
                continue
        release_match = release_pattern.search(row)
        if current_date is None or not release_match:
            continue
        release_name = normalized_text(release_match.group(1))
        title = f"{title_prefix} {release_name}".strip()
        events.append(CalendarEvent(date=current_date, title=title, source="FRED release calendar", importance="高"))
    events.sort(key=lambda item: (item.date, item.title))
    return events


def fetch_fred_macro_release_events(today: date | None = None, timeout: int = 30) -> list[CalendarEvent]:
    target_year = (today or date.today()).year
    events_by_key: dict[tuple[date, str], CalendarEvent] = {}
    for release_id in FRED_MACRO_RELEASES:
        html_content = fetch_text_curl_first(FRED_RELEASE_CALENDAR_URL.format(release_id=release_id, year=target_year), timeout=timeout)
        for event in parse_fred_release_calendar_html(html_content, title_prefix="BLS"):
            events_by_key[(event.date, event.title)] = event
    return [events_by_key[key] for key in sorted(events_by_key)]


def parse_bea_release_schedule_html(content: str) -> list[CalendarEvent]:
    year_match = re.search(r"<th[^>]*>\s*Year\s+(\d{4})\s*</th>", content, re.IGNORECASE)
    target_year = int(year_match.group(1)) if year_match else date.today().year
    row_pattern = re.compile(r"<tr[^>]*scheduled-releases-type-[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
    date_pattern = re.compile(r'<div class="release-date">\s*([^<]+)\s*</div>', re.IGNORECASE | re.DOTALL)
    title_pattern = re.compile(r'<td[^>]*class="[^"]*\brelease-title\b[^"]*"[^>]*>(.*?)</td>', re.IGNORECASE | re.DOTALL)
    events: list[CalendarEvent] = []
    for row_match in row_pattern.finditer(content):
        row = row_match.group(1)
        date_match = date_pattern.search(row)
        title_match = title_pattern.search(row)
        if not date_match or not title_match:
            continue
        release_title = normalized_text(title_match.group(1))
        if not is_bea_market_moving_release(release_title):
            continue
        try:
            release_date = datetime.strptime(f"{normalized_text(date_match.group(1))} {target_year}", "%B %d %Y").date()
        except ValueError:
            continue
        events.append(
            CalendarEvent(
                date=release_date,
                title=f"BEA {release_title}",
                source="BEA release schedule",
                importance="高",
            )
        )
    events.sort(key=lambda item: (item.date, item.title))
    return events


def is_bea_market_moving_release(title: str) -> bool:
    return title.startswith("GDP ") or title.startswith("Personal Income and Outlays")


def fetch_bea_release_events(timeout: int = 30) -> list[CalendarEvent]:
    return parse_bea_release_schedule_html(fetch_text_curl_first(BEA_RELEASE_SCHEDULE_URL, timeout=timeout))


def parse_fomc_projection_html(content: str) -> FomcProjection:
    release_match = re.search(r"For release at.*?,\s*([A-Za-z]+ \d{1,2}, \d{4})", content, re.IGNORECASE)
    if not release_match:
        release_match = re.search(r"([A-Za-z]+ \d{1,2}, \d{4}): FOMC Projections", content, re.IGNORECASE)
    if not release_match:
        raise ValueError("FOMC projection page did not contain a release date")
    release_date = datetime.strptime(release_match.group(1), "%B %d, %Y").date()

    labels: list[str] = []
    for index in range(1, 5):
        match = re.search(rf'id="xt1b{index}"[^>]*>(.*?)</th>', content, re.IGNORECASE | re.DOTALL)
        if match:
            labels.append(strip_html(match.group(1)))
    if len(labels) != 4:
        raise ValueError("FOMC projection page did not contain median year headers")

    row_match = re.search(
        r"<tr>\s*<th[^>]*>\s*Federal funds rate\s*</th>(.*?)</tr>",
        content,
        re.IGNORECASE | re.DOTALL,
    )
    if not row_match:
        raise ValueError("FOMC projection page did not contain federal funds rate medians")
    values = [parse_optional_float(strip_html(cell)) for cell in re.findall(r"<td[^>]*>(.*?)</td>", row_match.group(1), re.IGNORECASE | re.DOTALL)[:4]]
    if len(values) != 4 or any(value is None for value in values):
        raise ValueError("FOMC projection page contained incomplete federal funds rate medians")
    return FomcProjection(release_date=release_date, median_fed_funds={label: float(value) for label, value in zip(labels, values)})


def latest_fomc_projection_url(calendar_html: str) -> str:
    links: list[tuple[date, str]] = []
    for href, raw_date in re.findall(r'href="([^"]*fomcprojtabl(\d{8})\.htm)"', calendar_html, re.IGNORECASE):
        projection_date = datetime.strptime(raw_date, "%Y%m%d").date()
        if href.startswith("http"):
            url = href
        else:
            url = FEDERAL_RESERVE_BASE_URL + href
        links.append((projection_date, url))
    if not links:
        raise ValueError("FOMC calendar did not contain projection materials HTML links")
    return max(links, key=lambda item: item[0])[1]


def fetch_fomc_projection(timeout: int = 30) -> FomcProjection:
    calendar_html = fetch_text_curl_first(FED_FOMC_CALENDAR_URL, timeout=timeout)
    return parse_fomc_projection_html(fetch_text_curl_first(latest_fomc_projection_url(calendar_html), timeout=timeout))


def parse_primary_dealer_stats_json(payload: object, seriesbreak: str = "") -> PrimaryDealerStats:
    if not isinstance(payload, dict):
        raise ValueError("NY Fed primary dealer payload was not a JSON object")
    pd_payload = payload.get("pd")
    if not isinstance(pd_payload, dict):
        raise ValueError("NY Fed primary dealer payload did not contain pd object")
    rows = pd_payload.get("timeseries")
    if not isinstance(rows, list):
        raise ValueError("NY Fed primary dealer payload did not contain timeseries rows")

    parsed_rows: list[tuple[date, str, float]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        as_of = parse_date_value(row.get("asofdate"))
        key_id = str(row.get("keyid") or "").strip()
        value = parse_optional_float(row.get("value"))
        if as_of is None or not key_id or value is None:
            continue
        parsed_rows.append((as_of, key_id, value))
    if not parsed_rows:
        raise ValueError("NY Fed primary dealer payload did not contain numeric observations")

    latest_date = max(item[0] for item in parsed_rows)
    metrics = {key_id: value for as_of, key_id, value in parsed_rows if as_of == latest_date}
    return PrimaryDealerStats(as_of=latest_date, seriesbreak=seriesbreak, metrics_millions=metrics)


def latest_primary_dealer_seriesbreak(timeout: int = 30) -> str:
    payload = fetch_json(NYFED_PD_ASOF_URL, timeout=timeout)
    if not isinstance(payload, dict):
        raise ValueError("NY Fed primary dealer as-of payload was not a JSON object")
    rows = payload.get("pd", {}).get("asofdates") if isinstance(payload.get("pd"), dict) else None
    if not isinstance(rows, list) or not rows:
        raise ValueError("NY Fed primary dealer as-of payload did not contain dates")
    latest = rows[0]
    if not isinstance(latest, dict) or not latest.get("seriesbreak"):
        raise ValueError("NY Fed primary dealer as-of payload did not contain a series break")
    return str(latest["seriesbreak"])


def fetch_primary_dealer_stats(timeout: int = 30) -> PrimaryDealerStats:
    seriesbreak = latest_primary_dealer_seriesbreak(timeout=timeout)
    payload = fetch_json(NYFED_PD_LATEST_URL.format(seriesbreak=seriesbreak), timeout=timeout)
    return parse_primary_dealer_stats_json(payload, seriesbreak=seriesbreak)


def parse_treasury_yield_xml(content: str) -> list[YieldCurveRecord]:
    root = ET.fromstring(content)
    namespaces = {
        "atom": "http://www.w3.org/2005/Atom",
        "m": "http://schemas.microsoft.com/ado/2007/08/dataservices/metadata",
        "d": "http://schemas.microsoft.com/ado/2007/08/dataservices",
    }
    records: list[YieldCurveRecord] = []
    for props in root.findall(".//m:properties", namespaces):
        date_node = props.find("d:NEW_DATE", namespaces)
        if date_node is None or not date_node.text:
            continue
        values: dict[str, float] = {}
        for tenor, field_name in TREASURY_XML_FIELDS.items():
            node = props.find(f"d:{field_name}", namespaces)
            if node is None or node.text in {None, ""}:
                continue
            try:
                values[tenor] = float(node.text)
            except ValueError:
                continue
        if set(TENORS).issubset(values):
            records.append(
                YieldCurveRecord(
                    date=datetime.strptime(date_node.text[:10], "%Y-%m-%d").date(),
                    values={tenor: values[tenor] for tenor in TENORS},
                )
            )
    records.sort(key=lambda item: item.date)
    return records


def month_keys(end: date, months_back: int) -> list[str]:
    keys: list[str] = []
    year = end.year
    month = end.month
    for _ in range(months_back):
        keys.append(f"{year:04d}{month:02d}")
        month -= 1
        if month == 0:
            year -= 1
            month = 12
    return keys


def fetch_treasury_yield_curves(today: date | None = None, months_back: int = 4, timeout: int = 30) -> list[YieldCurveRecord]:
    today = today or date.today()
    by_date: dict[date, YieldCurveRecord] = {}
    for key in month_keys(today, months_back):
        content = fetch_text(TREASURY_XML_URL.format(month_key=key), timeout=timeout)
        for record in parse_treasury_yield_xml(content):
            by_date[record.date] = record
    return [by_date[key] for key in sorted(by_date)]


def fetch_json(url: str, timeout: int = 30) -> object:
    return json.loads(fetch_text(url, timeout=timeout))


def fetch_json_curl_first(url: str, timeout: int = 30) -> object:
    return json.loads(fetch_text_curl_first(url, timeout=timeout))


def fetch_treasury_auctions(timeout: int = 30) -> list[dict[str, object]]:
    auctioned = fetch_json_curl_first(TREASURY_AUCTIONED_URL, timeout=timeout)
    if not isinstance(auctioned, list):
        raise ValueError("TreasuryDirect auctioned endpoint did not return a list")
    return [item for item in auctioned if isinstance(item, dict)]


def fetch_announced_auctions(timeout: int = 30) -> list[dict[str, object]]:
    announced = fetch_json_curl_first(TREASURY_ANNOUNCED_URL, timeout=timeout)
    if not isinstance(announced, list):
        raise ValueError("TreasuryDirect announced endpoint did not return a list")
    return [item for item in announced if isinstance(item, dict)]


def nearest_record(records: Iterable[YieldCurveRecord], target: date) -> YieldCurveRecord:
    ordered = sorted(records, key=lambda item: item.date)
    if not ordered:
        raise ValueError("No yield curve records available")
    chosen = ordered[0]
    for record in ordered:
        if record.date <= target:
            chosen = record
        else:
            break
    return chosen
