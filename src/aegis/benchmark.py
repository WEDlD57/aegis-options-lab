"""Local-process measurements, explicitly not exchange/network latency."""

import gc
import os
import platform
from statistics import median
from time import perf_counter_ns

from .book import Order, OrderBook


def percentile(values: list[int], fraction: float) -> int:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))]


def benchmark_matching(iterations: int = 20_000) -> dict:
    if iterations < 1:
        raise ValueError("positive iteration count required")
    book = OrderBook("BENCH")
    samples: list[int] = []
    for i in range(200):
        book.submit(Order(f"warm-{i}", "BENCH", "maker", -1, 100, 1))
        book.submit(Order(f"warm-t-{i}", "BENCH", "taker", 1, 100, 1), immediate_or_cancel=True)
    gc.collect()
    wall_start = perf_counter_ns()
    for i in range(iterations):
        book.submit(Order(f"m-{i}", "BENCH", "maker", -1, 100, 1))
        taker = Order(f"t-{i}", "BENCH", "taker", 1, 100, 1)
        start = perf_counter_ns()
        fills, _ = book.submit(taker, immediate_or_cancel=True)
        samples.append(perf_counter_ns() - start)
        if len(fills) != 1:
            raise AssertionError("benchmark did not execute exactly one fill")
    wall = (perf_counter_ns() - wall_start) / 1e9
    return {"measurement": "one IOC taker submission matching one resting order",
            "iterations": iterations, "warmup_iterations": 200,
            "median_ns": int(median(samples)), "p95_ns": percentile(samples, 0.95),
            "p99_ns": percentile(samples, 0.99), "wall_seconds_including_setup": wall,
            "gc_enabled": gc.isenabled(), "python": platform.python_version(),
            "implementation": platform.python_implementation(), "platform": platform.platform(),
            "logical_cpus": os.cpu_count(),
            "scope": "Python in-process microbenchmark; no network, broker, serialization, or production latency claim"}
