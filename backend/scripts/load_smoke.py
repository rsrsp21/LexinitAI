"""Concurrent, threshold-enforced API infrastructure smoke load."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests


def percentile(values: list[float], value: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = max(0, min(len(ordered) - 1, math.ceil(value * len(ordered)) - 1))
    return round(ordered[index], 2)


def request_once(url: str, timeout: float) -> dict:
    started = time.perf_counter()
    try:
        response = requests.get(url, timeout=timeout)
        return {
            "status": response.status_code,
            "duration_ms": (time.perf_counter() - started) * 1000,
            "error": None,
        }
    except requests.RequestException as exc:
        return {
            "status": 0,
            "duration_ms": (time.perf_counter() - started) * 1000,
            "error": type(exc).__name__,
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:5055")
    parser.add_argument("--requests", type=int, default=500)
    parser.add_argument("--concurrency", type=int, default=25)
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument("--max-error-rate", type=float, default=0.01)
    parser.add_argument("--max-p95-ms", type=float, default=1500)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.requests < 1 or args.concurrency < 1:
        parser.error("requests and concurrency must be positive")

    urls = [
        f"{args.base_url.rstrip('/')}/api/v1/health/live" if index % 4 else
        f"{args.base_url.rstrip('/')}/api/v1/health/ready"
        for index in range(args.requests)
    ]
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [executor.submit(request_once, url, args.timeout) for url in urls]
        results = [future.result() for future in as_completed(futures)]
    elapsed = time.perf_counter() - started

    durations = [result["duration_ms"] for result in results]
    failures = [result for result in results if result["error"] or result["status"] >= 500 or result["status"] == 0]
    error_rate = len(failures) / len(results)
    report = {
        "requests": len(results),
        "concurrency": args.concurrency,
        "elapsed_seconds": round(elapsed, 2),
        "throughput_requests_per_second": round(len(results) / elapsed, 2),
        "status_counts": {
            str(status): sum(1 for result in results if result["status"] == status)
            for status in sorted({result["status"] for result in results})
        },
        "error_rate_percent": round(error_rate * 100, 3),
        "latency_ms": {
            "mean": round(statistics.fmean(durations), 2),
            "p50": percentile(durations, 0.50),
            "p95": percentile(durations, 0.95),
            "p99": percentile(durations, 0.99),
            "max": round(max(durations), 2),
        },
        "thresholds": {
            "max_error_rate_percent": args.max_error_rate * 100,
            "max_p95_ms": args.max_p95_ms,
        },
    }
    passed = error_rate <= args.max_error_rate and report["latency_ms"]["p95"] <= args.max_p95_ms
    report["status"] = "passed" if passed else "failed"
    rendered = json.dumps(report, indent=2)
    print(rendered)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
