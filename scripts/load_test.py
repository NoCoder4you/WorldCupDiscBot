#!/usr/bin/env python3
import argparse
import concurrent.futures
import json
import time
import urllib.error
import urllib.request


DEFAULT_ENDPOINTS = [
    "/api/ping",
    "/api/system",
    "/api/uptime",
    "/api/health",
]


def make_request(url, method="GET", payload=None, timeout=5):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
            return True, time.perf_counter() - start
    except urllib.error.URLError:
        return False, time.perf_counter() - start


def parse_args():
    parser = argparse.ArgumentParser(description="Simple load test for Flask API endpoints.")
    parser.add_argument("--base-url", default="http://localhost:5000", help="Base URL of the Flask app.")
    parser.add_argument("--duration", type=int, default=30, help="Duration in seconds.")
    parser.add_argument("--concurrency", type=int, default=10, help="Concurrent workers.")
    parser.add_argument("--timeout", type=int, default=5, help="Per-request timeout in seconds.")
    parser.add_argument("--endpoints", nargs="*", default=DEFAULT_ENDPOINTS, help="Endpoints to hit.")
    return parser.parse_args()


def main():
    args = parse_args()
    base = args.base_url.rstrip("/")
    endpoints = [f"{base}{path}" for path in args.endpoints]

    total = 0
    errors = 0
    latencies = []
    stop_at = time.time() + args.duration

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = []
        while time.time() < stop_at:
            for url in endpoints:
                futures.append(pool.submit(make_request, url, "GET", None, args.timeout))
            if len(futures) > args.concurrency * len(endpoints) * 4:
                done, futures = futures[: len(futures)], []
                for fut in concurrent.futures.as_completed(done):
                    ok, latency = fut.result()
                    total += 1
                    latencies.append(latency)
                    if not ok:
                        errors += 1

        for fut in concurrent.futures.as_completed(futures):
            ok, latency = fut.result()
            total += 1
            latencies.append(latency)
            if not ok:
                errors += 1

    latencies.sort()
    p50 = latencies[int(len(latencies) * 0.5)] if latencies else 0
    p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0
    print(f"Requests: {total}")
    print(f"Errors:   {errors}")
    print(f"P50:      {p50:.3f}s")
    print(f"P95:      {p95:.3f}s")


if __name__ == "__main__":
    main()
