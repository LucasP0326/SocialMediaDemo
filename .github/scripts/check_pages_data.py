"""Fail the deploy if the generated research dataset is empty or unexpected."""

import json
from pathlib import Path
import sys


dataset = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if (
    set(dataset) != {"source", "since", "until", "search", "candidates", "posts",
                     "accounts", "lenses", "topics", "cells"}
    or dataset["source"] != "bluesky"
    or not dataset["search"]
    or dataset["search"].get("queries", 0) <= 0
    or dataset["posts"] <= 0
):
    sys.exit("Pages requires a nonempty live Bluesky search aggregate.")

count = 0
for cell in dataset["cells"]:
    if set(cell) != {"month", "topic", "lenses", "counts"} or (
        cell["counts"].keys() - {"negative", "neutral", "positive"}
    ):
        sys.exit("Pages aggregate contains an unexpected field.")
    count += sum(cell["counts"].values())

if count != dataset["posts"]:
    sys.exit("Pages aggregate counts do not add up.")
print(f"Verified aggregate of {count} Bluesky posts.")
