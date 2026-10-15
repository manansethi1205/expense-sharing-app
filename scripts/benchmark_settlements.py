"""Reproducible local latency/memory measurements; not a worst-case performance guarantee."""

import json
import platform
import random
import statistics
import time
import tracemalloc
from pathlib import Path

from app.domain.settlements import suggest_transfers


def benchmark():
    randomizer = random.Random(20261016)
    results = []
    for size in (8, 12, 16, 17):
        cases = []
        for _ in range(3):
            values = [randomizer.randint(1, 100000) * (-1 if i % 2 else 1) for i in range(size - 1)]
            values.append(-sum(values))
            cases.append(dict(enumerate(values, start=1)))
        elapsed = []
        for positions in cases:
            start = time.perf_counter()
            plan = suggest_transfers(positions)
            elapsed.append((time.perf_counter() - start) * 1000)
        # Trace memory separately: tracemalloc itself significantly slows the exponential loop.
        tracemalloc.start()
        suggest_transfers(cases[0])
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        results.append(
            {
                "nonzero_positions": size,
                "strategy": plan.strategy,
                "median_ms": round(statistics.median(elapsed), 3),
                "max_ms": round(max(elapsed), 3),
                "peak_traced_mib": round(peak / 1024**2, 3),
            }
        )
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "method": "3 seeded cases per size, latency without tracing; separate peak-memory run; includes DP reconstruction",
        "results": results,
    }


if __name__ == "__main__":
    result = benchmark()
    Path("benchmark-results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
