import unittest
from datetime import date
from io import BytesIO
import zipfile

from treasury_data.sources import (
    DebtLimitStatus,
    FomcProjection,
    QuarterlyRefunding,
    fetch_federal_reserve_press_releases,
    fetch_fomc_calendar_events,
    parse_official_rss_news_items,
    parse_bea_release_schedule_html,
    parse_chicago_fed_fomc_calendar_html,
    parse_fomc_calendar_html,
    parse_fomc_projection_html,
    parse_fred_bulk_zip,
    parse_fred_release_calendar_html,
    parse_nasdaq_historical_json,
    parse_primary_dealer_stats_json,
    parse_debt_subject_to_limit_json,
    parse_stooq_daily_csv,
    parse_stooq_quote_csv,
    parse_treasury_press_releases_html,
    parse_quarterly_refunding_documents_html,
    parse_quarterly_refunding_financing_html,
    parse_quarterly_refunding_policy_html,
    select_latest_acm_record,
    parse_cftc_financial_futures_txt,
    parse_fred_csv,
    parse_tic_table5_txt,
    parse_treasury_yield_xml,
)


class SourceParsingTests(unittest.TestCase):
    def test_parse_fred_csv_ignores_missing_values_and_uses_latest_numeric(self):
        content = "\n".join(
            [
                "observation_date,DGS10",
                "2026-05-14,4.47",
                "2026-05-15,.",
                "2026-05-18,4.61",
            ]
        )

        series = parse_fred_csv(content, "DGS10")

        self.assertEqual(series.series_id, "DGS10")
        self.assertEqual(series.latest.date, date(2026, 5, 18))
        self.assertEqual(series.latest.value, 4.61)
        self.assertEqual(len(series.points), 2)

    def test_parse_fred_bulk_zip_extracts_daily_series(self):
        content = BytesIO()
        with zipfile.ZipFile(content, "w") as archive:
            archive.writestr(
                "daily.csv",
                "\n".join(
                    [
                        "observation_date,DFII10,T10YIE,DFF",
                        "2026-05-18,2.13,2.48,3.63",
                        "2026-05-19,.,2.49,3.64",
                    ]
                ),
            )
            archive.writestr(
                "monthly.csv",
                "\n".join(
                    [
                        "observation_date,CPIAUCSL",
                        "2026-04-01,324.9",
                    ]
                ),
            )

        series = parse_fred_bulk_zip(content.getvalue(), ["DFII10", "T10YIE", "DFF", "CPIAUCSL"])

        self.assertEqual(series["DFII10"].latest.date, date(2026, 5, 18))
        self.assertEqual(series["DFII10"].latest.value, 2.13)
        self.assertEqual(series["T10YIE"].latest.date, date(2026, 5, 19))
        self.assertEqual(series["T10YIE"].latest.value, 2.49)
        self.assertEqual(series["DFF"].latest.value, 3.64)
        self.assertEqual(series["CPIAUCSL"].latest.date, date(2026, 4, 1))
        self.assertEqual(series["CPIAUCSL"].latest.value, 324.9)

    def test_parse_fred_bulk_zip_accepts_direct_multi_series_csv(self):
        content = "\n".join(
            [
                "observation_date,DFII10,T10YIE,WRESBAL",
                "2026-05-13,2.10,2.45,3000000",
                "2026-05-20,2.18,2.40,3100000",
            ]
        ).encode("utf-8")

        series = parse_fred_bulk_zip(content, ["DFII10", "T10YIE", "WRESBAL"])

        self.assertEqual(series["DFII10"].latest.date, date(2026, 5, 20))
        self.assertEqual(series["DFII10"].latest.value, 2.18)
        self.assertEqual(series["WRESBAL"].latest.value, 3_100_000.0)

    def test_parse_stooq_quote_csv_extracts_public_futures_quote(self):
        content = "\n".join(
            [
                "Symbol,Date,Time,Open,High,Low,Close,Volume",
                "ZQ.F,2026-05-19,23:00:00,96.37,96.3725,96.37,96.37,",
            ]
        )

        quote = parse_stooq_quote_csv(content, "ZQ.F")

        self.assertEqual(quote.symbol, "ZQ.F")
        self.assertEqual(quote.date, date(2026, 5, 19))
        self.assertEqual(quote.close, 96.37)
        self.assertAlmostEqual(quote.implied_rate, 3.63)

    def test_parse_stooq_daily_csv_extracts_global_index_ohlcv_rows(self):
        content = "\n".join(
            [
                "Date,Open,High,Low,Close,Volume",
                "2026-06-04,9876.5,9910.0,9800.0,9888.0,123456",
                "2026-06-05,9888.0,9902.0,9700.0,9725.5,",
            ]
        )

        bars = parse_stooq_daily_csv(content, "^hsi", source_url="https://stooq.com/q/d/l/?s=^hsi")

        self.assertEqual([bar.date for bar in bars], [date(2026, 6, 4), date(2026, 6, 5)])
        self.assertEqual(bars[0].symbol, "^HSI")
        self.assertEqual(bars[0].volume, 123456)
        self.assertIsNone(bars[1].volume)
        self.assertEqual(bars[1].close, 9725.5)

    def test_parse_nasdaq_historical_json_extracts_descending_ohlcv_rows(self):
        content = """
        {
          "data": {
            "tradesTable": {
              "rows": [
                {"date": "06/05/2026", "close": "$737.55", "volume": "93,989,420", "open": "$752.31", "high": "$752.82", "low": "$735.525"},
                {"date": "06/04/2026", "close": "$757.09", "volume": "49,923,040", "open": "$752.10", "high": "$758.31", "low": "$751.47"},
                {"date": "06/03/2026", "close": "$754.24", "volume": "N/A", "open": "$758.15", "high": "$758.80", "low": "$753.57"}
              ]
            }
          }
        }
        """

        bars = parse_nasdaq_historical_json(content, "SPY", source_url="https://api.nasdaq.com/api/quote/SPY/historical")

        self.assertEqual([bar.date for bar in bars], [date(2026, 6, 3), date(2026, 6, 4), date(2026, 6, 5)])
        self.assertEqual(bars[0].symbol, "SPY")
        self.assertEqual(bars[0].volume, None)
        self.assertEqual(bars[-1].close, 737.55)
        self.assertEqual(bars[-1].volume, 93_989_420)

    def test_parse_official_rss_news_items_extracts_recent_headlines(self):
        content = """<?xml version="1.0" encoding="utf-8"?>
        <rss version="2.0">
          <channel>
            <item>
              <title><![CDATA[Federal Reserve issues FOMC statement]]></title>
              <link><![CDATA[https://www.federalreserve.gov/newsevents/pressreleases/monetary20260617a.htm]]></link>
              <pubDate><![CDATA[Wed, 17 Jun 2026 18:00:00 GMT]]></pubDate>
            </item>
            <item>
              <title>Federal Reserve Board announces approval of application</title>
              <link>https://www.federalreserve.gov/newsevents/pressreleases/orders20260601a.htm</link>
              <pubDate>Mon, 01 Jun 2026 14:00:00 GMT</pubDate>
            </item>
          </channel>
        </rss>
        """

        news = parse_official_rss_news_items(content, source="Federal Reserve")

        self.assertEqual(len(news), 1)
        self.assertEqual(news[0].date, date(2026, 6, 17))
        self.assertEqual(news[0].source, "Federal Reserve")
        self.assertEqual(news[0].title, "Federal Reserve issues FOMC statement")
        self.assertEqual(news[0].url, "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260617a.htm")

    def test_parse_treasury_press_releases_html_extracts_relevant_headlines(self):
        content = """
        <span class="date-format"><time datetime="2026-05-20T14:30:00Z" class="datetime">May 20, 2026</time></span>
        <h3 class="featured-stories__headline"><a href="/news/press-releases/sb0503">Treasury Disrupts Sanctions Network</a></h3>
        <span class="date-format"><time datetime="2026-05-18T20:00:00Z" class="datetime">May 18, 2026</time></span>
        <h3 class="featured-stories__headline"><a href="/news/press-releases/sb0499">Treasury International Capital Data for March</a></h3>
        <span class="date-format"><time datetime="2026-05-06T12:30:00Z" class="datetime">May 6, 2026</time></span>
        <h3 class="featured-stories__headline"><a href="/news/press-releases/sb0489">Quarterly Refunding Statement of Deputy Assistant Secretary for Federal Finance Brian Smith</a></h3>
        """

        news = parse_treasury_press_releases_html(content)

        self.assertEqual([item.date for item in news], [date(2026, 5, 18), date(2026, 5, 6)])
        self.assertEqual(news[0].source, "U.S. Treasury")
        self.assertEqual(news[0].title, "Treasury International Capital Data for March")
        self.assertEqual(news[0].url, "https://home.treasury.gov/news/press-releases/sb0499")

    def test_parse_treasury_yield_xml_extracts_supported_tenors(self):
        xml = """<?xml version="1.0" encoding="utf-8"?>
        <feed xmlns:d="http://schemas.microsoft.com/ado/2007/08/dataservices"
              xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata"
              xmlns="http://www.w3.org/2005/Atom">
          <entry><content><m:properties>
            <d:NEW_DATE m:type="Edm.DateTime">2026-05-15T00:00:00</d:NEW_DATE>
            <d:BC_1MONTH m:type="Edm.Double">3.70</d:BC_1MONTH>
            <d:BC_3MONTH m:type="Edm.Double">3.69</d:BC_3MONTH>
            <d:BC_6MONTH m:type="Edm.Double">3.77</d:BC_6MONTH>
            <d:BC_1YEAR m:type="Edm.Double">3.79</d:BC_1YEAR>
            <d:BC_2YEAR m:type="Edm.Double">3.95</d:BC_2YEAR>
            <d:BC_3YEAR m:type="Edm.Double">3.96</d:BC_3YEAR>
            <d:BC_5YEAR m:type="Edm.Double">4.07</d:BC_5YEAR>
            <d:BC_7YEAR m:type="Edm.Double">4.24</d:BC_7YEAR>
            <d:BC_10YEAR m:type="Edm.Double">4.42</d:BC_10YEAR>
            <d:BC_20YEAR m:type="Edm.Double">4.97</d:BC_20YEAR>
            <d:BC_30YEAR m:type="Edm.Double">4.98</d:BC_30YEAR>
          </m:properties></content></entry>
        </feed>"""

        records = parse_treasury_yield_xml(xml)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].date, date(2026, 5, 15))
        self.assertEqual(records[0].values["10Y"], 4.42)
        self.assertEqual(records[0].values["30Y"], 4.98)

    def test_select_latest_acm_record_uses_latest_complete_daily_row(self):
        rows = [
            {"DATE": "2026-05-14", "ACMTP10": 0.31, "ACMRNY10": 4.08},
            {"DATE": "2026-05-15", "ACMTP10": "", "ACMRNY10": 4.09},
            {"DATE": "18-May-2026", "ACMTP10": 0.37, "ACMRNY10": 4.24},
        ]

        record = select_latest_acm_record(rows)

        self.assertEqual(record.date, date(2026, 5, 18))
        self.assertEqual(record.term_premium_10y, 0.37)
        self.assertEqual(record.expected_rate_10y, 4.24)

    def test_parse_cftc_financial_futures_txt_filters_latest_treasury_contracts(self):
        content = "\n".join(
            [
                '"Market_and_Exchange_Names","Report_Date_as_YYYY-MM-DD","Open_Interest_All","Dealer_Positions_Long_All","Dealer_Positions_Short_All","Asset_Mgr_Positions_Long_All","Asset_Mgr_Positions_Short_All","Lev_Money_Positions_Long_All","Lev_Money_Positions_Short_All"',
                '"CANADIAN DOLLAR - CHICAGO MERCANTILE EXCHANGE",2026-05-12,1000,10,20,30,40,50,60',
                '"ULTRA UST 10Y - CHICAGO BOARD OF TRADE",2026-05-05,2000,100,80,400,100,90,300',
                '"ULTRA UST 10Y - CHICAGO BOARD OF TRADE",2026-05-12,2500,110,90,420,120,100,350',
                '"U.S. TREASURY BONDS - CHICAGO BOARD OF TRADE",2026-05-12,3000,120,140,500,200,150,500',
            ]
        )

        positions = parse_cftc_financial_futures_txt(content)

        self.assertEqual([item.market for item in positions], ["U.S. TREASURY BONDS", "ULTRA UST 10Y"])
        self.assertEqual(positions[0].report_date, date(2026, 5, 12))
        self.assertEqual(positions[0].leveraged_net, -350)
        self.assertEqual(positions[0].asset_manager_net, 300)
        self.assertAlmostEqual(positions[0].leveraged_net_pct_oi, -11.67, places=2)

    def test_parse_tic_table5_txt_extracts_latest_major_holders(self):
        content = "\n".join(
            [
                "Major Foreign Holders of Treasury Securities",
                "Country\t2026-03\t2026-02\t2025-03",
                "Japan\t1191.6\t1239.3\t1134.7",
                "United Kingdom\t926.9\t894.2\t779.3",
                "China, Mainland\t652.3\t665.6\t765.4",
                "Grand Total\t9348.7\t9487.1\t8500.0",
                "Of Which: Foreign Official\t3902.2\t3950.0\t3600.0",
            ]
        )

        tic = parse_tic_table5_txt(content)

        self.assertEqual(tic.period, "2026-03")
        self.assertEqual(tic.holdings[0].country, "Japan")
        self.assertEqual(tic.holdings[0].value_billions, 1191.6)
        self.assertEqual(tic.holdings[0].monthly_change_billions, -47.7)
        self.assertEqual(tic.total.value_billions, 9348.7)
        self.assertEqual(tic.official.value_billions, 3902.2)

    def test_parse_fomc_calendar_html_extracts_meeting_decision_dates(self):
        html = """
        <div class="panel panel-default"><div class="panel-heading"><h4><a id="42828">2026 FOMC Meetings</a></h4></div>
          <div class="fomc-meeting--shaded row fomc-meeting" ">
            <div class="fomc-meeting--shaded fomc-meeting__month col-xs-5"><strong>June</strong></div>
            <div class="fomc-meeting__date col-xs-4">16-17*</div>
            <div><strong>Projection Materials</strong></div>
          </div>
          <div class="row fomc-meeting" ">
            <div class="fomc-meeting__month col-xs-5"><strong>July</strong></div>
            <div class="fomc-meeting__date col-xs-4">28-29</div>
          </div>
        </div>
        <div class="panel panel-default"><div class="panel-heading"><h4><a id="45694">2027 FOMC Meetings</a></h4></div>
          <div class="row fomc-meeting">
            <div class="fomc-meeting__month col-xs-5"><strong>January</strong></div>
            <div class="fomc-meeting__date col-xs-4">26-27</div>
          </div>
        </div>
        """

        events = parse_fomc_calendar_html(html)

        self.assertEqual(events[0].date, date(2026, 6, 17))
        self.assertEqual(events[0].title, "FOMC decision + SEP")
        self.assertEqual(events[0].source, "Federal Reserve FOMC calendar")
        self.assertEqual(events[0].importance, "高")
        self.assertEqual(events[1].date, date(2026, 7, 29))
        self.assertEqual(events[1].title, "FOMC decision")
        self.assertEqual(events[2].date, date(2027, 1, 27))

    def test_fetch_fomc_calendar_events_uses_curl_first_board_fetch(self):
        from treasury_data import sources

        html = """
        <div class="panel panel-default"><div class="panel-heading"><h4><a id="42828">2026 FOMC Meetings</a></h4></div>
          <div class="fomc-meeting--shaded row fomc-meeting" ">
            <div class="fomc-meeting__month col-xs-5"><strong>June</strong></div>
            <div class="fomc-meeting__date col-xs-4">16-17*</div>
            <div><strong>Projection Materials</strong></div>
          </div>
        </div>
        """
        original_fetch_text = sources.fetch_text
        original_fetch_curl_first = sources.fetch_text_curl_first
        try:
            sources.fetch_text = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("urllib fetch should not be used"))
            sources.fetch_text_curl_first = lambda *args, **kwargs: html

            events = fetch_fomc_calendar_events()
        finally:
            sources.fetch_text = original_fetch_text
            sources.fetch_text_curl_first = original_fetch_curl_first

        self.assertEqual(events[0].date, date(2026, 6, 17))
        self.assertEqual(events[0].title, "FOMC decision + SEP")

    def test_fetch_federal_reserve_press_releases_uses_curl_first_fetch(self):
        from treasury_data import sources

        rss = """<?xml version="1.0" encoding="utf-8"?>
        <rss version="2.0"><channel><item>
          <title>Federal Reserve issues FOMC statement</title>
          <link>https://www.federalreserve.gov/newsevents/pressreleases/monetary20260617a.htm</link>
          <pubDate>Wed, 17 Jun 2026 18:00:00 GMT</pubDate>
        </item></channel></rss>
        """
        original_fetch_text = sources.fetch_text
        original_fetch_curl_first = sources.fetch_text_curl_first
        try:
            sources.fetch_text = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("urllib fetch should not be used"))
            sources.fetch_text_curl_first = lambda *args, **kwargs: rss

            news = fetch_federal_reserve_press_releases()
        finally:
            sources.fetch_text = original_fetch_text
            sources.fetch_text_curl_first = original_fetch_curl_first

        self.assertEqual(news[0].title, "Federal Reserve issues FOMC statement")

    def test_parse_chicago_fed_fomc_calendar_html_extracts_fallback_schedule(self):
        html = """
        <h2>FOMC Meetings</h2>
        <table summary="FOMC Meeting Schedule">
          <thead><tr><th>2026</th></tr></thead>
          <tbody>
            <tr><td>June 16&ndash;17*</td></tr>
            <tr><td>July 28&ndash;29</td></tr>
          </tbody>
        </table>
        """

        events = parse_chicago_fed_fomc_calendar_html(html)

        self.assertEqual(events[0].date, date(2026, 6, 17))
        self.assertEqual(events[0].title, "FOMC decision + SEP")
        self.assertEqual(events[0].source, "Federal Reserve Bank of Chicago FOMC schedule")
        self.assertEqual(events[1].date, date(2026, 7, 29))
        self.assertEqual(events[1].title, "FOMC decision")

    def test_parse_fred_release_calendar_html_extracts_macro_release_dates(self):
        html = """
        <tr>
          <td colspan="2"><span style="font-weight: bold;">Wednesday June 10, 2026</span></td>
        </tr>
        <tr>
          <td>7:30 am</td>
          <td><a href="/release?rid=10">Consumer Price Index</a></td>
        </tr>
        <tr>
          <td colspan="2"><span style="font-weight: bold;">Thursday June 11, 2026</span></td>
        </tr>
        <tr>
          <td>7:30 am</td>
          <td><a href="/release?rid=46">Producer Price Index</a></td>
        </tr>
        """

        events = parse_fred_release_calendar_html(html, title_prefix="BLS")

        self.assertEqual(events[0].date, date(2026, 6, 10))
        self.assertEqual(events[0].title, "BLS Consumer Price Index")
        self.assertEqual(events[0].source, "FRED release calendar")
        self.assertEqual(events[0].importance, "高")
        self.assertEqual(events[1].date, date(2026, 6, 11))
        self.assertEqual(events[1].title, "BLS Producer Price Index")

    def test_parse_bea_release_schedule_html_extracts_gdp_and_pce_events(self):
        html = """
        <table id="release-schedule-table">
          <thead><tr><th>Year 2026</th><th></th><th>Release</th></tr></thead>
          <tbody>
            <tr class="scheduled-releases-type-press">
              <td class="scheduled-date"><div class="release-date">May 28</div></td>
              <td><div class="icon-letter"><span class="caps">N</span><span class="tail">ews</span></div></td>
              <td class="release-title">GDP (Second Estimate) and Corporate Profits, 1st Quarter 2026</td>
            </tr>
            <tr class="scheduled-releases-type-press">
              <td class="scheduled-date"><div class="release-date">May 28</div></td>
              <td><div class="icon-letter"><span class="caps">N</span><span class="tail">ews</span></div></td>
              <td class="release-title">Personal Income and Outlays, April 2026</td>
            </tr>
            <tr class="scheduled-releases-type-data">
              <td class="scheduled-date"><div class="release-date">July 7</div></td>
              <td><div class="icon-letter"><span class="caps">D</span><span class="tail">ata</span></div></td>
              <td class="release-title">U.S. Trade in Services, Expanded Detail, 2025</td>
            </tr>
          </tbody>
        </table>
        """

        events = parse_bea_release_schedule_html(html)

        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].date, date(2026, 5, 28))
        self.assertEqual(events[0].title, "BEA GDP (Second Estimate) and Corporate Profits, 1st Quarter 2026")
        self.assertEqual(events[0].source, "BEA release schedule")
        self.assertEqual(events[0].importance, "高")
        self.assertEqual(events[1].title, "BEA Personal Income and Outlays, April 2026")

    def test_parse_primary_dealer_stats_json_keeps_latest_numeric_metrics(self):
        payload = {
            "pd": {
                "timeseries": [
                    {"asofdate": "2026-04-29", "keyid": "PDPOSGST-TOT", "value": "499000"},
                    {"asofdate": "2026-05-06", "keyid": "PDPOSGST-TOT", "value": "500420"},
                    {"asofdate": "2026-05-06", "keyid": "PDSORA-UTSETTOT", "value": "3190705"},
                    {"asofdate": "2026-05-06", "keyid": "PDSIRRA-UTSETTOT", "value": "*"},
                ]
            }
        }

        stats = parse_primary_dealer_stats_json(payload, seriesbreak="SBN2024")

        self.assertEqual(stats.as_of, date(2026, 5, 6))
        self.assertEqual(stats.seriesbreak, "SBN2024")
        self.assertEqual(stats.metrics_millions["PDPOSGST-TOT"], 500420.0)
        self.assertEqual(stats.metrics_millions["PDSORA-UTSETTOT"], 3190705.0)
        self.assertNotIn("PDSIRRA-UTSETTOT", stats.metrics_millions)

    def test_parse_fomc_projection_html_extracts_fed_funds_medians(self):
        html = """
        <p>For release at 2:00 p.m., EDT, March 18, 2026</p>
        <th class="colhead" headers="xt1a2" id="xt1b1">2026</th>
        <th class="colhead" headers="xt1a2" id="xt1b2">2027</th>
        <th class="colhead" headers="xt1a2" id="xt1b3">2028</th>
        <th class="colhead" headers="xt1a2" id="xt1b4">Longer run</th>
        <tr>
          <th class="stub" headers="xt1a1 xt1r9" id="xt1r10">Federal funds rate</th>
          <td class="data" headers="xt1a2 xt1b1 xt1r9 xt1r10">3.4</td>
          <td class="data" headers="xt1a2 xt1b2 xt1r9 xt1r10">3.1</td>
          <td class="data" headers="xt1a2 xt1b3 xt1r9 xt1r10">3.1</td>
          <td class="data" headers="xt1a2 xt1b4 xt1r9 xt1r10">3.1</td>
        </tr>
        """

        projection = parse_fomc_projection_html(html)

        self.assertIsInstance(projection, FomcProjection)
        self.assertEqual(projection.release_date, date(2026, 3, 18))
        self.assertEqual(projection.median_fed_funds["2026"], 3.4)
        self.assertEqual(projection.median_fed_funds["Longer run"], 3.1)

    def test_parse_quarterly_refunding_documents_and_releases(self):
        documents_html = """
        <h3>DOCUMENTS RELEASED at 3:00 PM Monday,&nbsp;may 4, 2026</h3>
        <p><a href="/news/press-releases/sb0485">Financing Estimates: 2026 - 2nd Quarter</a></p>
        <p>(The next release is scheduled for August 3, 2026)</p>
        <h3>DOCUMENTS RELEASED at 8:30 AM Wednesday, may 6, 2026</h3>
        <p><a href="/news/press-releases/sb0489">Policy Statement: 2026 - 2nd Quarter</a></p>
        <p>(The next release is scheduled for August 5<strong>,</strong> 2026)</p>
        """
        financing_html = """
        <p>During the April-June 2026 quarter, Treasury expects to borrow $189 billion in privately-held net marketable debt,
        assuming an end-of-June cash balance of $900 billion.</p>
        <p>During the July-September 2026 quarter, Treasury expects to borrow $671 billion in privately-held net marketable debt,
        assuming an end-of-September cash balance of $950 billion.</p>
        """
        policy_html = """
        <p>The U.S. Department of the Treasury is offering $125 billion of Treasury securities to refund approximately
        $83.3 billion of privately-held Treasury notes maturing on May 15, 2026. This issuance will raise new cash from
        private investors of approximately $41.7 billion.</p>
        <p>Treasury anticipates maintaining nominal coupon and FRN auction sizes for at least the next several quarters.</p>
        <p>Based on current forecasts, Treasury expects to further increase offering sizes of shorter-dated benchmark bills
        over the coming weeks.</p>
        <p>Treasury estimates that the size of the Treasury General Account (TGA) could peak at $1 trillion
        (plus or minus $50 billion) in late July.</p>
        <p>Treasury anticipates that, over the course of the upcoming quarter, it will purchase up to $38 billion in
        off-the-run securities across buckets for liquidity support and up to $25 billion in the 1-month to 2-year
        maturity bucket for cash management purposes.</p>
        <p>The next quarterly refunding announcement will take place on Wednesday, August 5, 2026.</p>
        """

        refunding = parse_quarterly_refunding_documents_html(documents_html)
        refunding = parse_quarterly_refunding_financing_html(financing_html, refunding)
        refunding = parse_quarterly_refunding_policy_html(policy_html, refunding)

        self.assertIsInstance(refunding, QuarterlyRefunding)
        self.assertEqual(refunding.release_date, date(2026, 5, 6))
        self.assertEqual(refunding.quarter, "2026 - 2nd Quarter")
        self.assertEqual(refunding.policy_statement_url, "https://home.treasury.gov/news/press-releases/sb0489")
        self.assertEqual(refunding.financing_estimates_url, "https://home.treasury.gov/news/press-releases/sb0485")
        self.assertEqual(refunding.next_policy_statement_date, date(2026, 8, 5))
        self.assertEqual(refunding.next_financing_estimates_date, date(2026, 8, 3))
        self.assertEqual(refunding.current_quarter_borrowing_billions, 189.0)
        self.assertEqual(refunding.next_quarter_borrowing_billions, 671.0)
        self.assertEqual(refunding.current_quarter_cash_balance_billions, 900.0)
        self.assertEqual(refunding.next_quarter_cash_balance_billions, 950.0)
        self.assertEqual(refunding.refunding_amount_billions, 125.0)
        self.assertEqual(refunding.refunding_new_cash_billions, 41.7)
        self.assertIn("maintaining nominal coupon", refunding.coupon_stance)
        self.assertIn("increase offering sizes", refunding.bill_issuance)
        self.assertEqual(refunding.buyback_total_billions, 63.0)
        self.assertIn("$1 trillion", refunding.tga_peak)

    def test_parse_debt_subject_to_limit_json_computes_headroom(self):
        payload = {
            "data": [
                {"record_date": "2026-05-18", "debt_catg": "Debt Held by the Public", "close_today_bal": "31317917"},
                {"record_date": "2026-05-18", "debt_catg": "Intragovernmental Holdings", "close_today_bal": "7691083"},
                {"record_date": "2026-05-18", "debt_catg": "Debt Not Subject to Limit", "debt_catg_desc": "Other Debt (-)", "close_today_bal": "474"},
                {"record_date": "2026-05-18", "debt_catg": "Debt Not Subject to Limit", "debt_catg_desc": "Unamortized Discount (-)", "close_today_bal": "172435"},
                {"record_date": "2026-05-18", "debt_catg": "Debt Not Subject to Limit", "debt_catg_desc": "Federal Financing Bank (-)", "close_today_bal": "4093"},
                {"record_date": "2026-05-18", "debt_catg": "Other Debt Subject to Limit", "debt_catg_desc": "Guaranteed Debt of Government Agencies", "close_today_bal": "0"},
                {"record_date": "2026-05-18", "debt_catg": "Statutory Debt Limit", "close_today_bal": "41103996"},
            ]
        }

        status = parse_debt_subject_to_limit_json(payload)

        self.assertIsInstance(status, DebtLimitStatus)
        self.assertEqual(status.record_date, date(2026, 5, 18))
        self.assertEqual(status.statutory_limit_millions, 41103996.0)
        self.assertEqual(status.debt_subject_to_limit_millions, 38831998.0)
        self.assertEqual(status.headroom_millions, 2271998.0)
        self.assertEqual(status.public_debt_millions, 31317917.0)
        self.assertEqual(status.intragov_holdings_millions, 7691083.0)


if __name__ == "__main__":
    unittest.main()
