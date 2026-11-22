#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p dashboard/public
cp dashboard/samples/bluesky-aggregate.json dashboard/public/research.json
npm --prefix dashboard run build -- --base=./ --assetsDir=pages-assets
python .github/scripts/check_pages_data.py dashboard/dist/research.json
mkdir -p pages-assets
find pages-assets -maxdepth 1 -type f -delete
cp dashboard/dist/index.html dashboard/dist/research.json .
cp dashboard/dist/pages-assets/* pages-assets/
