#!/usr/bin/env python3
import argparse
import json
import sys
import time
import urllib.parse
import urllib.request


BUDGETS_MS = {
    "search_p95_ms": 300.0,
    "one_hop_ms": 700.0,
    "detail_ms": 700.0,
    "two_hop_ms": 1500.0,
}


def get_json(url: str):
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def timed_get_json(url: str):
    start = time.perf_counter()
    payload = get_json(url)
    elapsed_ms = (time.perf_counter() - start) * 1000
    return payload, elapsed_ms


def percentile_95(values: list[float]) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95 + 0.999999) - 1))
    return ordered[index]


def median(values: list[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def api_url(base_url: str, path: str, params: dict[str, str | int]) -> str:
    return urllib.parse.urljoin(base_url.rstrip("/") + "/", path.lstrip("/")) + "?" + urllib.parse.urlencode(params)


def select_entity(results: list[dict], query: str) -> dict | None:
    if not results:
        return None
    return next((item for item in results if item.get("name") == query), results[0])


def warn_if_over_budget(metrics: dict[str, float]) -> None:
    for key, budget in BUDGETS_MS.items():
        value = metrics.get(key)
        if value is not None and value > budget:
            print(f"warning: {key}={value:.1f} exceeds budget {budget:.1f}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Measure graph API search, detail, one-hop and two-hop latency.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--query", required=True)
    args = parser.parse_args(argv)

    search_url = api_url(
        args.base_url,
        "/api/graph/search",
        {"project_id": args.project_id, "query": args.query, "limit": 20},
    )

    try:
        warmup_results = get_json(search_url)
        entity = select_entity(warmup_results, args.query)
        if entity is None:
            print("no search result", file=sys.stderr)
            return 1

        search_times: list[float] = []
        for _ in range(5):
            results, elapsed_ms = timed_get_json(search_url)
            search_times.append(elapsed_ms)
            entity = select_entity(results, args.query)
            if entity is None:
                print("no search result", file=sys.stderr)
                return 1

        entity_id = str(entity["id"])
        one_hop_url = api_url(
            args.base_url,
            "/api/graph/neighborhood",
            {"project_id": args.project_id, "entity_id": entity_id, "depth": 1, "limit": 50},
        )
        two_hop_url = api_url(
            args.base_url,
            "/api/graph/neighborhood",
            {"project_id": args.project_id, "entity_id": entity_id, "depth": 2, "limit": 100},
        )
        detail_url = api_url(
            args.base_url,
            f"/api/entities/{urllib.parse.quote(entity_id, safe='')}",
            {"project_id": args.project_id},
        )

        _, one_hop_ms = timed_get_json(one_hop_url)
        _, detail_ms = timed_get_json(detail_url)
        _, two_hop_ms = timed_get_json(two_hop_url)
    except Exception as error:
        print(f"request failed: {error}", file=sys.stderr)
        return 1

    metrics = {
        "search_p50_ms": median(search_times),
        "search_p95_ms": percentile_95(search_times),
        "one_hop_ms": one_hop_ms,
        "detail_ms": detail_ms,
        "two_hop_ms": two_hop_ms,
    }
    warn_if_over_budget(metrics)
    for key in ("search_p50_ms", "search_p95_ms", "one_hop_ms", "detail_ms", "two_hop_ms"):
        print(f"{key}={metrics[key]:.1f}")
    print(f"entity_id={entity_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
