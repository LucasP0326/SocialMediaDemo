"""Collect an English-language search sample and publish aggregate research data."""

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from sklearn.decomposition import NMF
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

PUBLIC_APPVIEW = "https://public.api.bsky.app/xrpc"
ENDPOINT = f"{PUBLIC_APPVIEW}/app.bsky.feed.searchPosts"
PDS = "https://bsky.social/xrpc"
COMMUNITY_FEEDS = (
    "at://did:plc:a2dpgfdjvuxxp5ni3hgd7wwi/app.bsky.feed.generator/discoelysium",
    "at://did:plc:ivfdfi43xkc34brkhe2qtfec/app.bsky.feed.generator/aaamdxr5d2snk",
    "at://did:plc:umwdrdb4cizbl5jyyj2dssmm/app.bsky.feed.generator/aaaeacrdbfktk",
    "at://did:plc:umwdrdb4cizbl5jyyj2dssmm/app.bsky.feed.generator/discoelysiumart",
    "at://did:plc:umwdrdb4cizbl5jyyj2dssmm/app.bsky.feed.generator/aaaedcvedvvwc",
    "at://did:plc:wez4mmcvrydqoscx35yymnhx/app.bsky.feed.generator/aaaki55luicja",
)
GAME_REFERENCE = re.compile(
    r"\b(?:disco[\s-]*elysium|revachol|kim\s*kitsuragi|harry\s*du\s*bois|"
    r"martinaise|cunoesse|klaasje|titus hardie|thought cabinet|tequila sunset)\b", re.I
)
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


def create_session(identifier, app_password):
    request = Request(
        f"{PDS}/com.atproto.server.createSession",
        data=json.dumps({"identifier": identifier, "password": app_password}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=25) as response:
            token = json.load(response)["accessJwt"]
        if not isinstance(token, str) or not token:
            raise ValueError("missing token")
        return token
    except HTTPError as error:
        raise RuntimeError(f"Bluesky sign-in returned HTTP {error.code}. Verify the handle and app password.") from None
    except (KeyError, ValueError, TypeError):
        raise RuntimeError("Bluesky sign-in returned an invalid session response.") from None


def fetch_page(params, token=None):
    endpoint = f"{PDS}/app.bsky.feed.searchPosts" if token else ENDPOINT
    request = Request(f"{endpoint}?{urlencode(params)}", headers={"Accept": "application/json"})
    if token:
        request.add_unredirected_header("Authorization", f"Bearer {token}")
    for attempt in range(4):
        try:
            with urlopen(request, timeout=25) as response:
                return json.load(response)
        except HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == 3:
                raise
            retry_after = error.headers.get("Retry-After", "")
            time.sleep(min(int(retry_after), 120) if retry_after.isdigit() else 2 ** attempt)


def collect(since, until, pages, token=None):
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
            payload = fetch_page(params, token)
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


def public_json(method, params):
    with urlopen(f"{PUBLIC_APPVIEW}/{method}?{urlencode(params)}", timeout=15) as response:
        return json.load(response)


def game_reference(record):
    embed = record.get("embed") or {}
    media = embed.get("media", embed)
    image_descriptions = (item.get("alt", "") for item in media.get("images", ()))
    return any(GAME_REFERENCE.search(part) for part in (record["text"], *image_descriptions))


def thread_posts(seed):
    try:
        payload = public_json("app.bsky.feed.getPostThread", {"uri": seed["uri"], "depth": 2, "parentHeight": 0})
    except URLError:
        return None
    pending = list(payload["thread"].get("replies", ()))
    results = []
    while pending:
        node = pending.pop()
        if (post := node.get("post")) and "en" in post["record"].get("langs", ()):
            results.append(post)
        pending.extend(node.get("replies", ()))
    return results


def early_profile(did):
    try:
        profile = public_json("app.bsky.actor.getProfile", {"actor": did})
    except URLError:
        return None
    return profile if profile.get("createdAt", "").startswith("2023") else None


def early_author_posts(profile):
    params = {"actor": profile["did"], "limit": 100, "filter": "posts_with_replies"}
    posts = {}
    for _ in range(10):
        try:
            payload = public_json("app.bsky.feed.getAuthorFeed", params)
        except URLError:
            break
        for item in payload["feed"]:
            post = item["post"]
            record = post["record"]
            if (post["author"]["did"] == profile["did"] and record["createdAt"].startswith("2023")
                    and "en" in record.get("langs", ()) and game_reference(record)):
                posts.setdefault(post["uri"], post)
        cursor = payload.get("cursor")
        if not cursor or cursor == params.get("cursor"):
            break
        params["cursor"] = cursor
    return posts


def collect_feeds(pages, thread_limit, since):
    posts = {}
    page_count = 0
    for feed in COMMUNITY_FEEDS:
        params = {"feed": feed, "limit": 100}
        cursors = set()
        for _ in range(pages):
            payload = public_json("app.bsky.feed.getFeed", params)
            page_count += 1
            for item in payload["feed"]:
                post = item["post"]
                record = post["record"]
                if "en" in record.get("langs", ()) and game_reference(record):
                    posts.setdefault(post["uri"], post)
            cursor = payload.get("cursor")
            if not cursor or cursor in cursors:
                break
            cursors.add(cursor)
            params["cursor"] = cursor
    archival_posts = 0
    threads_read = 0
    with ThreadPoolExecutor(max_workers=4) as workers:
        if since.year <= 2023:
            early_authors = sorted({
                post["author"]["did"] for post in posts.values()
                if post["record"]["createdAt"][:4] <= "2024"
            })[:40]
            profiles = [profile for profile in workers.map(early_profile, early_authors) if profile]
            profiles.sort(key=lambda profile: (profile.get("postsCount", float("inf")), profile["did"]))
            feed_count = len(posts)
            for archived in workers.map(early_author_posts, profiles[:6]):
                posts.update(archived)
            archival_posts = len(posts) - feed_count
        seeds = sorted(
            (post for post in posts.values() if post.get("replyCount", 0) > 0),
            key=lambda post: post["record"]["createdAt"],
        )[:thread_limit]
        before_replies = len(posts)
        for replies in workers.map(thread_posts, seeds):
            if replies is not None:
                threads_read += 1
                for reply in replies:
                    posts.setdefault(reply["uri"], reply)
    return list(posts.values()), {
        "communityFeeds": len(COMMUNITY_FEEDS), "pages": page_count,
        "threadsRead": threads_read, "threadsAttempted": len(seeds),
        "additionalReplies": len(posts) - before_replies, "archivalPosts": archival_posts,
        "includesGeneralDiscussion": True,
        "collectedOn": str(datetime.now(timezone.utc).date()),
    }


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
    model = NMF(n_components=count, init="nndsvda", solver="mu", random_state=42, max_iter=500)
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
        if not content or (not lenses and not (search or {}).get("includesGeneralDiscussion")):
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
    source.add_argument("--community-feeds", action="store_true", help="collect from public Disco Elysium feeds")
    source.add_argument("--import-page", action="append", type=Path, metavar="JSON",
                        help="analyze a saved searchPosts response (repeat for multiple pages)")
    parser.add_argument("--since", type=date.fromisoformat)
    parser.add_argument("--until", type=date.fromisoformat)
    parser.add_argument("--pages", type=int, default=3, help="maximum pages per query")
    parser.add_argument("--topics", type=int, default=6)
    parser.add_argument("--threads", type=int, default=100, help="maximum community-feed threads to expand")
    parser.add_argument("--output", type=Path, default=Path("public/research.json"))
    args = parser.parse_args()
    if args.pages < 1 or args.topics < 1 or args.threads < 0:
        parser.error("--pages and --topics must be positive and --threads cannot be negative")
    until = args.until or (date(2025, 7, 1) if args.demo else today + timedelta(days=1))
    since = args.since or (date(2025, 1, 1) if args.demo else until - timedelta(days=90))
    if since >= until:
        parser.error("--since must precede the exclusive --until date")
    token = None
    try:
        if args.demo:
            posts, search = demo_posts(), None
        elif args.import_page:
            posts, search = import_pages(args.import_page)
        elif args.community_feeds:
            posts, search = collect_feeds(args.pages, args.threads, since)
        else:
            identifier = os.getenv("BLUESKY_HANDLE")
            app_password = os.getenv("BLUESKY_APP_PASSWORD")
            if bool(identifier) != bool(app_password):
                raise RuntimeError("Set both BLUESKY_HANDLE and BLUESKY_APP_PASSWORD for authenticated Bluesky search.")
            if identifier:
                token = create_session(identifier, app_password)
            posts, search = collect(since, until, args.pages, token)
    except HTTPError as error:
        if args.community_feeds:
            parser.exit(1, f"Bluesky community feed returned HTTP {error.code}.\n")
        hint = ""
        if error.code in (401, 403) and not token:
            hint = " Configure BLUESKY_HANDLE and BLUESKY_APP_PASSWORD for authenticated search."
        elif error.code in (401, 403):
            hint = " Bluesky rejected the authenticated search."
        parser.exit(1, f"Bluesky search returned HTTP {error.code}.{hint}\n")
    except RuntimeError as error:
        parser.exit(1, f"{error}\n")
    except (URLError, OSError) as error:
        parser.exit(1, f"Bluesky collection failed: {error}\n")
    except ValueError as error:
        parser.exit(1, f"Unable to read Bluesky search JSON: {error}\n")
    output = analyze(posts, since, until, args.topics, args.demo, search)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=args.output.parent, delete=False) as file:
        json.dump(output, file, indent=2)
        file.write("\n")
    Path(file.name).replace(args.output)
    print(f"{output['posts']} relevant posts from {output['accounts']} accounts ({output['source']}).")


if __name__ == "__main__":
    main()
