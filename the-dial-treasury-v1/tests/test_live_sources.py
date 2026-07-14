import threading
import unittest
from contextlib import ExitStack
from unittest.mock import patch

import treasury_data.build_dashboard as dashboard_builder
from treasury_data.live_sources import LiveSourceTask, run_live_source_tasks


class LiveSourceRunnerTests(unittest.TestCase):
    def test_independent_lanes_enter_concurrently(self):
        barrier = threading.Barrier(2)

        def fetch(value):
            barrier.wait(timeout=1)
            return value

        results = run_live_source_tasks(
            [
                LiveSourceTask("treasury", "treasury", lambda: fetch("curve")),
                LiveSourceTask("fred", "fred", lambda: fetch("macro")),
            ],
            max_workers=2,
        )

        self.assertEqual([result.get() for result in results], ["curve", "macro"])

    def test_random_completion_order_does_not_change_result_order(self):
        keys = ["first", "second", "third"]
        started = {key: threading.Event() for key in keys}
        release = {key: threading.Event() for key in keys}
        completed = {key: threading.Event() for key in keys}
        completion_order: list[str] = []

        def fetch(key):
            started[key].set()
            if not release[key].wait(timeout=1):
                raise TimeoutError(f"release timeout for {key}")
            completion_order.append(key)
            completed[key].set()
            return key

        def release_out_of_order():
            for event in started.values():
                event.wait(timeout=1)
            for key in ("third", "first", "second"):
                release[key].set()
                completed[key].wait(timeout=1)

        controller = threading.Thread(target=release_out_of_order)
        controller.start()
        results = run_live_source_tasks(
            [LiveSourceTask(key, key, lambda key=key: fetch(key)) for key in keys],
            max_workers=3,
        )
        controller.join(timeout=1)

        self.assertFalse(controller.is_alive())
        self.assertEqual(completion_order, ["third", "first", "second"])
        self.assertEqual([result.key for result in results], keys)
        self.assertEqual([result.get() for result in results], keys)

    def test_failure_is_captured_and_does_not_cancel_same_lane(self):
        calls: list[str] = []

        def fail():
            calls.append("fail")
            raise RuntimeError("source down")

        def succeed():
            calls.append("succeed")
            return 42

        failed, succeeded = run_live_source_tasks(
            [
                LiveSourceTask("failed", "same-provider", fail),
                LiveSourceTask("succeeded", "same-provider", succeed),
            ]
        )

        self.assertEqual(calls, ["fail", "succeed"])
        with self.assertRaisesRegex(RuntimeError, "source down"):
            failed.get()
        self.assertEqual(succeeded.get(), 42)


class LiveDashboardParallelFetchTests(unittest.TestCase):
    def test_parallel_completion_keeps_canonical_source_status_order(self):
        barrier = threading.Barrier(2)
        release_curve = threading.Event()
        completion_order: list[str] = []

        def fetch_curve():
            barrier.wait(timeout=1)
            if not release_curve.wait(timeout=1):
                raise TimeoutError("curve release timeout")
            completion_order.append("curve")
            return []

        def fetch_fred(_series_ids, **_kwargs):
            barrier.wait(timeout=1)
            completion_order.append("fred")
            release_curve.set()
            return {}

        patches = {
            "fetch_treasury_auctions": [],
            "fetch_announced_auctions": [],
            "fetch_fomc_calendar_events": [],
            "fetch_fred_macro_release_events": [],
            "fetch_bea_release_events": [],
            "fetch_fomc_projection": None,
            "fetch_acm_term_premium": None,
            "fetch_cftc_treasury_positions": [],
            "fetch_tic_major_holders": None,
            "fetch_primary_dealer_stats": None,
            "fetch_quarterly_refunding": None,
            "fetch_debt_limit_status": None,
            "fetch_fed_funds_futures_quote": None,
            "fetch_gold_spot_quote": None,
            "fetch_cboe_option_open_interest": None,
            "fetch_federal_reserve_press_releases": [],
            "fetch_treasury_press_releases": [],
            "load_content_overrides": {},
            "fetch_bhadial_public_score": 43.4,
        }
        with ExitStack() as stack:
            for name, return_value in patches.items():
                stack.enter_context(patch.object(dashboard_builder, name, return_value=return_value))
            stack.enter_context(patch.object(dashboard_builder, "fetch_treasury_yield_curves", side_effect=fetch_curve))
            stack.enter_context(patch.object(dashboard_builder, "fetch_fred_series_bulk", side_effect=fetch_fred))
            stack.enter_context(
                patch.object(
                    dashboard_builder,
                    "fetch_daily_bars_with_stooq_fallback",
                    side_effect=RuntimeError("skip market fetch"),
                )
            )
            stack.enter_context(
                patch.object(
                    dashboard_builder,
                    "build_dashboard_from_inputs",
                    return_value={"sourceStatus": [], "macroLiquidity": {"score": 43.4}},
                )
            )

            dashboard = dashboard_builder.build_live_dashboard()

        self.assertEqual(completion_order, ["fred", "curve"])
        names = [item["name"] for item in dashboard["sourceStatus"]]
        self.assertEqual(names[0], "U.S. Treasury yield curve XML")
        self.assertEqual(names[1 : 1 + len(dashboard_builder.FRED_SERIES)], [f"FRED {series_id}" for series_id in dashboard_builder.FRED_SERIES])
        self.assertEqual(names[1 + len(dashboard_builder.FRED_SERIES)], "TreasuryDirect auctioned securities")


if __name__ == "__main__":
    unittest.main()
