"""
Fetches Google Trends (via SerpApi) and BTC price (via CoinGecko),
then saves both to data/trends.json for the chart page.

Needs one environment variable: SERPAPI_KEY
Uses only the Python standard library - nothing to install.
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

TERMS = ["bitcoin", "buy bitcoin"]
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "trends.json")


def get_json(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "btc-search-watch/1.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception as e:  # network hiccup: wait and retry
            last = e
            time.sleep(5 * (i + 1))
    raise RuntimeError(f"Failed to fetch {url.split('?')[0]}: {last}")


def fetch_trends(api_key):
    params = {
        "engine": "google_trends",
        "data_type": "TIMESERIES",
        "q": ",".join(TERMS),
        "date": "today 12-m",  # weekly points for the past year
        "api_key": api_key,
    }
    data = get_json("https://serpapi.com/search.json?" + urllib.parse.urlencode(params))
    if "error" in data:
        raise RuntimeError("SerpApi error: " + data["error"])
    rows = []
    for point in data["interest_over_time"]["timeline_data"]:
        vals = {}
        for v in point["values"]:
            raw = v.get("extracted_value", v.get("value", 0))
            try:
                vals[v["query"]] = float(str(raw).replace("<1", "0.5"))
            except ValueError:
                vals[v["query"]] = 0.0
        rows.append({
            "t": int(point["timestamp"]),
            "partial": bool(point.get("partial_data", False)),
            **{term: vals.get(term, 0.0) for term in TERMS},
        })
    return rows


def fetch_price():
    url = ("https://api.coingecko.com/api/v3/coins/bitcoin/market_chart"
           "?vs_currency=usd&days=365&interval=daily")
    data = get_json(url)
    return [[int(ms // 1000), round(p, 2)] for ms, p in data["prices"]]


def spike_status(rows, term="bitcoin", lookback=8):
    """Latest complete week vs the average of the 8 weeks before it."""
    complete = [r for r in rows if not r["partial"]]
    if len(complete) < lookback + 1:
        return None
    latest = complete[-1][term]
    base = sum(r[term] for r in complete[-lookback - 1:-1]) / lookback
    ratio = latest / base if base else 0
    return {"term": term, "latest": latest, "baseline": round(base, 1), "ratio": round(ratio, 2)}


def main():
    key = os.environ.get("SERPAPI_KEY", "").strip()
    if not key:
        sys.exit("SERPAPI_KEY is not set. Add it under Settings > Secrets and variables > Actions.")
    trends = fetch_trends(key)
    try:
        price = fetch_price()
    except Exception as e:
        print("Price fetch failed, keeping previous price data:", e)
        price = []
        if os.path.exists(OUT):
            with open(OUT) as f:
                price = json.load(f).get("price", [])
    out = {
        "updated": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "terms": TERMS,
        "trends": trends,
        "price": price,
        "spike": spike_status(trends),
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"Saved {len(trends)} search weeks and {len(price)} price days. Spike check: {out['spike']}")


if __name__ == "__main__":
    main()
