"""Bounded, deterministic orchestration for independent live-source fetches.

Tasks sharing a lane run serially.  Separate lanes may run concurrently, which
lets callers keep requests to the same provider conservative while still
overlapping unrelated public sources.  Results are always returned in task
declaration order, never completion order.
"""
from __future__ import annotations

from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Callable, Iterable


DEFAULT_LIVE_SOURCE_WORKERS = 6


@dataclass(frozen=True)
class LiveSourceTask:
    """One patch-friendly source fetch assigned to a provider concurrency lane."""

    key: str
    lane: str
    fetch: Callable[[], Any]


@dataclass(frozen=True)
class LiveSourceResult:
    """Captured value or exception for a single live-source task."""

    key: str
    value: Any = None
    error: Exception | None = None

    def get(self) -> Any:
        if self.error is not None:
            raise self.error
        return self.value


def _run_lane(indexed_tasks: list[tuple[int, LiveSourceTask]]) -> list[tuple[int, LiveSourceResult]]:
    completed: list[tuple[int, LiveSourceResult]] = []
    for index, task in indexed_tasks:
        try:
            result = LiveSourceResult(key=task.key, value=task.fetch())
        except Exception as exc:  # noqa: BLE001 - source failures are data, not pool failures
            result = LiveSourceResult(key=task.key, error=exc)
        completed.append((index, result))
    return completed


def run_live_source_tasks(
    tasks: Iterable[LiveSourceTask],
    *,
    max_workers: int = DEFAULT_LIVE_SOURCE_WORKERS,
) -> list[LiveSourceResult]:
    """Run source tasks with bounded concurrency and deterministic result order.

    A provider lane occupies at most one worker, so same-lane requests never
    overlap.  An exception is captured on its own result and does not cancel
    later tasks in that lane or any other lane.
    """

    ordered_tasks = list(tasks)
    if not ordered_tasks:
        return []
    if max_workers < 1:
        raise ValueError("max_workers must be at least 1")

    keys = [task.key for task in ordered_tasks]
    if len(keys) != len(set(keys)):
        raise ValueError("live-source task keys must be unique")

    lanes: OrderedDict[str, list[tuple[int, LiveSourceTask]]] = OrderedDict()
    for index, task in enumerate(ordered_tasks):
        lanes.setdefault(task.lane, []).append((index, task))

    completed_by_index: dict[int, LiveSourceResult] = {}
    worker_count = min(max_workers, len(lanes))
    with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="live-source") as executor:
        futures = [executor.submit(_run_lane, lane_tasks) for lane_tasks in lanes.values()]
        for future in as_completed(futures):
            for index, result in future.result():
                completed_by_index[index] = result

    return [completed_by_index[index] for index in range(len(ordered_tasks))]
