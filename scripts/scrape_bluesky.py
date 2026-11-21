#!/usr/bin/env python3
"""Collect public Bluesky search results for exploratory Disco Elysium research.

Only run-local pseudonyms are saved; account DIDs and handles are never persisted.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

API_URL = "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts"
TOPICS: dict[str, list[str]] = {
    "communism & class": ["communism", "communist", "socialism", "socialist", "class struggle", "working class", "capitalism", "labor"],
    "fascism & nationalism": ["fascism", "fascist", "nazi", "nationalism", "authoritarian", "revachol"],
    "race & colonialism": ["racism", "racist", "race", "colonialism", "colonial", "imperialism", "indigenous"],
    "gender & feminism": ["sexism", "sexist", "feminism", "feminist", "misogyny", "gender"],
    "LGBTQ+ identities": ["lgbtq", "queer", "gay", "lesbian", "trans", "nonbinary", "bisexual", "homophobia"],
    "culture & ideology": ["politics", "political", "ideology", "discourse", "culture", "identity", "representation"],
}
GAME_TERMS = ('"Disco Elysium"', '"DiscoElysium"')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-pages-per-query", type=int, default=3, help="Maximum 100-post pages per game/topic query (default: 3).")
    parser.add_argument("--since", help="Optional inclusive UTC date (YYYY-MM-DD).")
    parser.add_argument("--until", help="Optional exclusive UTC date (YYYY-MM-DD).")
    parser.add_argument("--output", type=Path, default=Path("data/bluesky_posts.json"), help="Output JSON file (default: data/bluesky_posts.json).")
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds to wait between API requests (default: 1).")
    parser.add_argument("--language", default="en", help="Preferred language tag (default: en); use 'all' to include every language.")
    args = parser.parse_args()
    if args.max_pages_per_query < 1 or args.delay < 0:
        parser.error("--max-pages-per-query must be positive and --delay cannot be negative")
    for key in ("since", "until"):
        if getattr(args, key):
            try:
                datetime.strptime(getattr(args, key), "%Y-%m-%d")
            except ValueError:
                parser.error(f"--{key} must use YYYY-MM-DD format")
    return args


def post_text(post: dict[str, Any]) -> str:
    record = post.get("record") or {}
    return " ".join((record.get("text") or "").split())


def main() -> None:
    args = parse_args()
    posts: dict[str, dict[str, Any]] = {}
    author_ids: dict[str, str] = {}
    session = requests.Session()
    session.headers.update({"User-Agent": "SocialMediaDemo-ResearchPrototype/1.0"})

    for topic, terms in TOPICS.items():
        for term in terms:
            for game in GAME_TERMS:
                query = f"{game} {term}"
                cursor: str | None = None
                for _ in range(args.max_pages_per_query):
                    params: dict[str, Any] = {"q": query, "limit": 100}
                    if cursor:
                        params["cursor"] = cursor
                    if args.since:
                        params["since"] = args.since
                    if args.until:
                        params["until"] = args.until
                    try:
                        response = session.get(API_URL, params=params, timeout=30)
                        response.raise_for_status()
                        payload = response.json()
                    except requests.RequestException as exc:
                        print(f"Request failed for {query!r}: {exc}")
                        break
                    for post in payload.get("posts", []):
                        text = post_text(post)
                        author = (post.get("author") or {}).get("did")
                        uri = post.get("uri")
                        if not text or not author or not uri:
                            continue
                        langs = (post.get("record") or {}).get(" langs") or (post.get("record") or {}).get("langs") or []
                        if args.language != "all" and langs and args.language not in langs:
                            continue
                        pseudonym = author_ids.setdefault(author, f"Participant {len(author_ids) + 1:04d}")
                        entry = posts.setdefault(uri, {
                            "id": uri,
                            "author": pseudonym,
                            "text": text,
                            "createdAt": (post.get("record") or {}).get("createdAt") or post.get("indexedAt"),
                            "language": ", ".join(langs) if langs else "unknown",
                            "topics": [],
                        })
                        if topic not in entry["topics"]:
                            entry["topics"].append(topic)
                    cursor = payload.get("cursor")
                    if not cursor or not payload.get("posts"):
                        break
                    time.sleep(args.delay)

    # Replace internal URIs with local opaque IDs, so the file contains no account or post URLs.
    output = []
    for index, entry in enumerate(posts.values(), start=1):
        entry["id"] = f"post-{index:06d}"
        output.append(entry)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({
        "metadata": {
            "source": "Bluesky public AppView search",
            "collectedAt": datetime.now(timezone.utc).isoformat(),
            "postCount": len(output),
            "pseudonymScope": "this collection run only",
            "analysisNote": "Search-based sample; not a complete census. Text is public user-generated content.",
        },
        "posts": output,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {len(output)} unique posts from {len(author_ids)} pseudonymized authors to {args.output}")


if __name__ == "__main__":
    main()
