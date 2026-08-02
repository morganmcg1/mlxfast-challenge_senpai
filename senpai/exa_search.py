#!/usr/bin/env python3
import argparse
import json
import os
import sys
from pathlib import Path
from urllib.request import Request, urlopen


def api_key() -> str:
    if key := os.environ.get("EXA_API_KEY"):
        return key
    for line in Path(__file__).with_name(".env").read_text().splitlines():
        if line.startswith("EXA_API_KEY="):
            return line.split("=", 1)[1].strip().strip("'\"")
    raise SystemExit("EXA_API_KEY is not set")


def search(query: str, category: str | None = None, num_results: int = 10) -> dict:
    payload = {
        "query": query,
        "numResults": num_results,
        "contents": {"highlights": True},
    }
    if category:
        payload["category"] = category

    request = Request(
        "https://api.exa.ai/search",
        data=json.dumps(payload).encode(),
        headers={"x-api-key": api_key(), "content-type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def main() -> None:
    parser = argparse.ArgumentParser(description="Search the web with Exa")
    parser.add_argument("query")
    parser.add_argument("--category", help='Exa category, such as "publication"')
    parser.add_argument("-n", "--num-results", type=int, default=10)
    args = parser.parse_args()
    json.dump(search(args.query, args.category, args.num_results), sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
