# SocialMediaDemo

An exploratory, local-first research prototype for studying public Bluesky posts about *Disco Elysium* and political, social, and cultural discourse. It includes a rate-limited Bluesky public-API collector and a D3 dashboard. Account names and DIDs are never written to the collected dataset; authors are labeled with run-local pseudonyms.

## Quick start

1. Install Python 3.10+ and dependencies: `python -m pip install -r requirements.txt`.
2. Collect posts: `python scripts/scrape_bluesky.py --max-pages-per-query 2`.
3. Serve the dashboard locally from the repository root: `python -m http.server 8000` and open <http://localhost:8000>.
4. In the dashboard, choose the generated `data/bluesky_posts.json` file. Or use **Load demo data** to explore the interface with clearly labeled synthetic posts.

The collector queries Bluesky's public AppView `app.bsky.feed.searchPosts` endpoint, requiring both a *Disco Elysium* reference and a topic term. It paginates with cursors, deduplicates posts, waits between requests, and saves only post text, timestamps, language, topic-query tags, and run-local pseudonyms. It does not collect handles, DIDs, profile data, likes, reposts, or replies. Results are local research data; the `data/` directory is git-ignored.

Example options:

```bash
python scripts/scrape_bluesky.py --max-pages-per-query 5 --since 2024-01-01 --until 2025-01-01 --output data/sample.json
```

Use `--help` for all options. API availability and search coverage are controlled by Bluesky; this is not a complete census. Be considerate of API limits and the people whose public posts are included.

## Analysis and limitations

The dashboard assigns posts to transparent, overlapping topic categories using editable keyword dictionaries and scores sentiment using a small English-language lexicon. These are exploratory proxies, **not** validated topic modeling or reliable measures of a person's beliefs or emotional state. Irony, context, multilingual content, reclaimed language, and ambiguous terms can lead to errors. Review categories and results carefully; do not make claims about individuals or treat scores as ground truth. The date chart uses UTC dates. Synthetic demo data is not real Bluesky content.

The page runs locally in the browser and does not upload data. Avoid publishing raw post text: searchable quotations can identify authors even when account names are removed. Get appropriate ethics review and follow Bluesky's terms and applicable privacy rules before collecting, sharing, or publishing research data. Pseudonyms are only run-local labels, not a guarantee of anonymity.

## GitHub Pages dashboard

The published dashboard lives in `dashboard/`. It runs TF-IDF/NMF topic modeling and VADER sentiment scoring over a rolling 90-day English-language Bluesky search sample. The local prototype above remains available for private exploration. Pages receives only the built dashboard and the aggregate research dataset.

1. Merge this change into `main`.
2. In the repository's **Settings → Pages**, set **Build and deployment → Source** to **GitHub Actions**.
3. In **Actions → Refresh Bluesky dashboard**, choose **Run workflow** on `main`. Open the URL reported by the deployment job after it succeeds.

The workflow also runs every Monday at 14:23 UTC. When collection fails or the sample is empty, deployment is skipped and the previous successful site stays online. GitHub-hosted runners use their own network. A successful deployment requires Bluesky to accept their search requests.

For a local preview of the Pages dashboard, run the following in `dashboard/` with Python 3.12 and Node.js 24. Omit `--demo` to collect live posts on your connection.

```sh
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
npm ci
.venv/bin/python research.py --demo
npm run dev
```
