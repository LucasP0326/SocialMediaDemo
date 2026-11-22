"""Collect an English-language search sample and publish aggregate research data."""

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
import hashlib
import hmac
import json
from pathlib import Path
import re
import secrets
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from sklearn.decomposition import NMF
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

ENDPOINT = "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts"
LENSES = {
    "Communism & labor": r"communis\w*|marxis\w*|socialis\w*|unions?|labor|labour|working class|class struggle",
    "Fascism & nationalism": r"fascis\w*|nationalis\w*|authoritarian\w*|supremac\w*",
    "Race & racism": r"racis\w*|racial\w*|xenophob\w*|colonialis\w*|white supremac\w*",
    "Gender & sexism": r"sexis\w*|misogyn\w*|patriarch\w*|feminis\w*|gender roles?",
    "LGBTQ+ identities": r"lgbtq?\w*|queer\w*|gay|lesbian\w*|bisexual\w*|transgender\w*|trans|nonbinary|homophob\w*|transphob\w*",
    "Politics & culture": r"politic\w*|capitalis\w*|liberalis\w*|ideolog\w*|cultur\w*|imperialis\w*|solidarity|inequality",
}
PATTERNS = {label: re.compile(rf"\b(?:{pattern})\b", re.I) for label, pattern in LENSES.items()}
SEARCH_TERMS = ("", "communism", "fascism", "racism", "sexism", "queer", "politics")
IDENTIFIERS = re.compile(
    r"https?://\S+|at://\S+|\bdid:[\w:.%-]+|@[\w.-]+|\b[\w-]+(?:\.[\w-]+)+\b",
    re.I,
)
STOP_WORDS = sorted(ENGLISH_STOP_WORDS | {"disco", "elysium", "game", "games", "playing"})


def fetch_page(params):
    for attempt in range(4):
        try:
            with urlopen(f"{ENDPOINT}?{urlencode(params)}", timeout=25) as response:
                return json.load(response)
        except HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == 3:
                raise
            retry_after = error.headers.get("Retry-After", "")
            time.sleep(min(int(retry_after), 120) if retry_after.isdigit() else 2 ** attempt)


def collect(since, until, pages):
    seen = set()
    results = []
    capped = 0
    queried = 0
    for term in SEARCH_TERMS:
        query = f'"Disco Elysium" {term}'.strip()
        params = {"q": query, "lang": "en", "sort": "latest", "limit": 100,
                  "since": f"{since}T00:00:00Z", "until": f"{until}T00:00:00Z"}
        cursors = set()
        for page in range(pages):
            payload = fetch_page(params)
            queried += 1
            for post in payload["posts"]:
                uri = post["uri"]
                if uri not in seen:
                    results.append(post)
                    seen.add(uri)
            cursor = payload.get("cursor")
            if not cursor or cursor in cursors:
                break
            if page == pages - 1:
                capped += 1
                break
            cursors.add(cursor)
            params["cursor"] = cursor
            time.sleep(0.3)
    return results, {"queries": len(SEARCH_TERMS), "pages": queried, "queriesAtPageLimit": capped}


def import_pages(paths):
    posts = {}
    for path in paths:
        try:
            with path.open(encoding="utf-8") as file:
                page = json.load(file)
            if not isinstance(page, dict) or not isinstance(page.get("posts"), list):
                raise ValueError("expected a Bluesky searchPosts response with a posts array")
            for post in page["posts"]:
                uri = post["uri"]
                if not uri.startswith("at://") or not post["author"]["did"].startswith("did:"):
                    raise ValueError("invalid post URI or author DID")
                if not isinstance(post["record"]["text"], str):
                    raise ValueError("invalid post text")
                datetime.fromisoformat(post["record"]["createdAt"])
                posts.setdefault(uri, post)
        except (OSError, AttributeError, TypeError, KeyError, ValueError) as error:
            raise ValueError(f"{path}: {error}") from error
    return list(posts.values()), {"importedPages": len(paths)}


def demo_posts():
    themes = [
        ("communism labor unions class struggle solidarity workers", (
            "I love how the workers find hope", "The broken promises are awful", "The strike is discussed in the harbor")),
        ("fascism nationalism authoritarian ideology belonging", (
            "I admire the writing about belonging", "The cruelty makes me furious", "The dialogue introduces a nationalist faction")),
        ("racism xenophobia colonialism prejudice racial stereotypes", (
            "The writing is thoughtful and humane", "The humiliation feels terrible", "The character discusses racial categories")),
        ("sexism misogyny gender roles patriarchy feminism", (
            "I appreciate the thoughtful dialogue", "I hate the cruel treatment", "The script refers to gender roles")),
        ("queer lgbtq transgender gay identity representation", (
            "I love the joyful representation", "The shame is painful", "The dialogue references queer identity")),
        ("politics capitalism ideology economics culture inequality", (
            "Brilliant writing about economic ideas", "The bleak inequality is horrible", "The scene discusses economic policy")),
    ]
    return [
        {"author": {"did": f"demo-{index % 17}"}, "record": {
            "text": f"Disco Elysium: {words}. {examples[index % 3]}.",
            "createdAt": f"2025-{1 + index % 6:02d}-15T00:00:00Z",
        }}
        for theme, (words, examples) in enumerate(themes)
        for index in range(10 + theme * 3)
    ]


def model_topics(rows, count):
    if len(rows) < 3:
        return []
    vectorizer = TfidfVectorizer(stop_words=STOP_WORDS, min_df=2, max_features=6000)
    try:
        matrix = vectorizer.fit_transform(row["text"] for row in rows)
    except ValueError as error:
        if "empty vocabulary" in str(error) or "no terms remain" in str(error).lower():
            return []
        raise
    count = min(count, *matrix.shape)
    model = NMF(n_components=count, init="nndsvda", random_state=42, max_iter=500)
    weights = model.fit_transform(matrix)
    words = vectorizer.get_feature_names_out()
    for row, scores in zip(rows, weights):
        if scores.max() > 0:
            row["topic"] = int(scores.argmax())
    return [
        {"id": index, "terms": [str(words[i]) for i in component.argsort()[:-6:-1] if component[i] > 0]}
        for index, component in enumerate(model.components_)
    ]


def analyze(posts, since, until, topic_count, demo, search):
    salt = secrets.token_bytes(32)
    sentiment = SentimentIntensityAnalyzer()
    rows = []
    for post in posts:
        record = post["record"]
        created = datetime.fromisoformat(record["createdAt"]).astimezone(timezone.utc)
        if not since <= created.date() < until:
            continue
        content = IDENTIFIERS.sub(" ", record["text"]).strip()
        lenses = [label for label, pattern in PATTERNS.items() if pattern.search(content)]
        if not lenses:
            continue
        # Keep the pseudonym only in memory. Never publish a handle, DID, or post.
        account = hmac.new(salt, post["author"]["did"].encode(), hashlib.sha256).hexdigest()
        score = sentiment.polarity_scores(content)["compound"]
        tone = "positive" if score >= 0.05 else "negative" if score <= -0.05 else "neutral"
        rows.append({"text": content, "account": account, "month": created.strftime("%Y-%m"),
                     "topic": -1, "tone": tone, "lenses": tuple(lenses)})
    topics = model_topics(rows, topic_count)
    cells = defaultdict(Counter)
    for row in rows:
        cells[row["month"], row["topic"], row["lenses"]][row["tone"]] += 1
    return {
        "source": "synthetic" if demo else "bluesky",
        "since": str(since), "until": str(until), "search": search,
        "candidates": len(posts), "posts": len(rows),
        "accounts": len({row["account"] for row in rows}),
        "lenses": list(LENSES), "topics": topics,
        "cells": [
            {"month": month, "topic": topic, "lenses": lenses, "counts": dict(counts)}
            for (month, topic, lenses), counts in sorted(cells.items())
        ],
    }


def main():
    today = datetime.now(timezone.utc).date()
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--demo", action="store_true", help="generate synthetic posts without API access")
    source.add_argument("--import-page", action="append", type=Path, metavar="JSON",
                        help="analyze a saved searchPosts response (repeat for multiple pages)")
    parser.add_argument("--since", type=date.fromisoformat)
    parser.add_argument("--until", type=date.fromisoformat)
    parser.add_argument("--pages", type=int, default=3, help="maximum pages per query")
    parser.add_argument("--topics", type=int, default=6)
    parser.add_argument("--output", type=Path, default=Path("public/research.json"))
    args = parser.parse_args()
    if args.pages < 1 or args.topics < 1:
        parser.error("--pages and --topics must be positive")
    until = args.until or (date(2025, 7, 1) if args.demo else today + timedelta(days=1))
    since = args.since or (date(2025, 1, 1) if args.demo else until - timedelta(days=90))
    if since >= until:
        parser.error("--since must precede the exclusive --until date")
    try:
        if args.demo:
            posts, search = demo_posts(), None
        elif args.import_page:
            posts, search = import_pages(args.import_page)
        else:
            posts, search = collect(since, until, args.pages)
    except HTTPError as error:
        hint = " Try --import-page with a search response collected on another connection." if error.code == 403 else ""
        parser.exit(1, f"Bluesky search returned HTTP {error.code}.{hint}\n")
    except (URLError, OSError) as error:
        parser.exit(1, f"Bluesky collection failed: {error}\n")
    except ValueError as error:
        parser.exit(1, f"Unable to import Bluesky search page: {error}\n")
    output = analyze(posts, since, until, args.topics, args.demo, search)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=args.output.parent, delete=False) as file:
        json.dump(output, file, indent=2)
        file.write("\n")
    Path(file.name).replace(args.output)
    print(f"{output['posts']} relevant posts from {output['accounts']} accounts ({output['source']}).")


if __name__ == "__main__":
    main()
