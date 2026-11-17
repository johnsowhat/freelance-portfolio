"""Competitor price monitor: scrapes a shop's catalogue, saves a daily CSV snapshot,
compares it with the previous one and sends a report to Telegram. Pure Python stdlib.

Run:   BOT_TOKEN=... ADMIN_ID=... python3 monitor.py      (without them it only prints the report)
Test:  python3 monitor.py test

Demo target: books.toscrape.com, a public sandbox shop made for scraping practice.
For a real client, change BASE and the ITEM pattern to their competitor's site.
"""
import csv, json, os, re, sys, time, urllib.request, uuid
from datetime import date
from html import unescape
from pathlib import Path

BASE = "https://books.toscrape.com/catalogue/"
CURRENCY = "£"
MAX_PAGES = int(os.environ.get("MAX_PAGES", "50"))
DATA = Path(__file__).parent / "data"
TOKEN, ADMIN_ID = os.environ.get("BOT_TOKEN", ""), os.environ.get("ADMIN_ID")
FIELDS = ["title", "price", "rating", "in_stock", "url"]
RATING = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}
ITEM = re.compile(r'<article class="product_pod">.*?star-rating (\w+).*?<h3><a href="([^"]+)" title="([^"]+)"'
                  r'.*?price_color">[^\d]*([\d.]+)<.*?availability">(.*?)</p>', re.S)


# ---- Scraping ----
def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (price-monitor)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")

def parse(html):
    return [{"title": unescape(title), "price": float(price), "rating": RATING.get(stars, 0),
             "in_stock": "yes" if "In stock" in avail else "no", "url": BASE + href}
            for stars, href, title, price, avail in ITEM.findall(html)]

def scrape():
    items = []
    for n in range(1, MAX_PAGES + 1):
        html = fetch(f"{BASE}page-{n}.html")
        items += parse(html)
        print(f"page {n}: {len(items)} products", end="\r", flush=True)
        if 'class="next"' not in html:
            break
        time.sleep(0.3)  # be polite to the site
    print()
    return items


# ---- Snapshots & comparison ----
def save(items, path):
    DATA.mkdir(exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, FIELDS)
        w.writeheader()
        w.writerows(items)

def load(path):
    with open(path, encoding="utf-8") as f:
        return [{**row, "price": float(row["price"])} for row in csv.DictReader(f)]

def previous_snapshot(today):
    older = sorted(p for p in DATA.glob("*.csv") if p.stem < today)
    return older[-1] if older else None

def compare(old, new):
    old_by, new_by = {r["url"]: r for r in old}, {r["url"]: r for r in new}
    changes = [(r, old_by[u]["price"], r["price"]) for u, r in new_by.items()
               if u in old_by and r["price"] != old_by[u]["price"]]
    stock = [r for u, r in new_by.items() if u in old_by and r["in_stock"] != old_by[u]["in_stock"]]
    added = [r for u, r in new_by.items() if u not in old_by]
    removed = [r for u, r in old_by.items() if u not in new_by]
    return changes, stock, added, removed

def report(items, prev_name, changes, stock, added, removed):
    money = lambda x: f"{CURRENCY}{x:.2f}"
    avg = sum(r["price"] for r in items) / len(items)
    lines = [f"📊 Price report · {date.today():%b %d, %Y}",
             f"{len(items)} products · average {money(avg)} · {sum(r['in_stock'] == 'yes' for r in items)} in stock"]
    if not prev_name:
        cheapest = sorted(items, key=lambda r: r["price"])[:5]
        lines += ["", "First snapshot saved. Tomorrow's report will show what changed.",
                  "", "💸 Cheapest now:"] + [f"• {r['title'][:45]}: {money(r['price'])}" for r in cheapest]
        return "\n".join(lines)
    lines.append(f"Compared with {prev_name}")
    drops = sorted((c for c in changes if c[2] < c[1]), key=lambda c: c[2] - c[1])
    rises = sorted((c for c in changes if c[2] > c[1]), key=lambda c: c[1] - c[2])
    if not (changes or stock or added or removed):
        lines += ["", "✅ No changes since last check."]
    for title, group, fmt in [
        ("📉 Price drops", drops, lambda c: f"• {c[0]['title'][:45]}: {money(c[1])} → {money(c[2])} ({(c[2] - c[1]) / c[1]:+.0%})"),
        ("📈 Price rises", rises, lambda c: f"• {c[0]['title'][:45]}: {money(c[1])} → {money(c[2])} ({(c[2] - c[1]) / c[1]:+.0%})"),
        ("📦 Stock changes", stock, lambda r: f"• {r['title'][:45]}: {'back in stock' if r['in_stock'] == 'yes' else 'out of stock'}"),
        ("🆕 New products", added, lambda r: f"• {r['title'][:45]}: {money(r['price'])}"),
        ("🗑 Removed", removed, lambda r: f"• {r['title'][:45]}"),
    ]:
        if group:
            lines += ["", f"{title} ({len(group)}):"] + [fmt(x) for x in group[:10]]
            if len(group) > 10:
                lines.append(f"…and {len(group) - 10} more in the CSV")
    return "\n".join(lines)


# ---- Telegram ----
def telegram(method, body, content_type):
    req = urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/{method}", body, {"Content-Type": content_type})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)

def send_report(text, csv_path):
    telegram("sendMessage", json.dumps({"chat_id": ADMIN_ID, "text": text[:4000]}).encode(), "application/json")
    b = uuid.uuid4().hex
    body = (f'--{b}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n{ADMIN_ID}\r\n'
            f'--{b}\r\nContent-Disposition: form-data; name="document"; filename="prices-{csv_path.name}"\r\n'
            f'Content-Type: text/csv\r\n\r\n').encode() + csv_path.read_bytes() + f'\r\n--{b}--\r\n'.encode()
    telegram("sendDocument", body, f"multipart/form-data; boundary={b}")


def main():
    items = scrape()
    if not items:
        sys.exit("No products found: the site layout may have changed. Check the ITEM pattern.")
    today = date.today().isoformat()
    prev = previous_snapshot(today)
    path = DATA / f"{today}.csv"
    save(items, path)
    text = report(items, prev and prev.stem, *compare(load(prev), items) if prev else ([], [], [], []))
    print(text)
    if TOKEN and ADMIN_ID:
        send_report(text, path)
        print("\nSent to Telegram ✅")


def make_demo_yesterday():
    """The sandbox shop never changes prices, so for a demo video we write a fake 'yesterday'
    snapshot with some different prices; today's real run then shows a full report."""
    import random
    from datetime import timedelta
    today = DATA / f"{date.today()}.csv"
    if not today.exists():
        sys.exit("Run `python3 monitor.py` once first.")
    rows, rnd = load(today), random.Random(7)
    for r in rnd.sample(rows, 12):
        r["price"] = round(r["price"] * rnd.choice([0.8, 0.9, 1.15, 1.25]), 2)
    for r in rnd.sample(rows, 3):
        r["in_stock"] = "no"
    rows = [r for r in rows if r not in rnd.sample(rows, 4)]  # these will show up as "new" today
    save(rows, DATA / f"{date.today() - timedelta(days=1)}.csv")
    print("Demo 'yesterday' snapshot written. Now run: python3 monitor.py")


def self_test():
    html = ('<article class="product_pod"><p class="star-rating Four"></p><h3><a href="x_1/index.html" '
            'title="Tom &amp; Jerry">Tom</a></h3><p class="price_color">Â£10.50</p>'
            '<p class="instock availability"> In stock </p></article>') * 2
    rows = parse(html)
    assert rows[0] == {"title": "Tom & Jerry", "price": 10.5, "rating": 4, "in_stock": "yes", "url": BASE + "x_1/index.html"}

    a = {"title": "A", "price": 10.0, "rating": 3, "in_stock": "yes", "url": "a"}
    b = {"title": "B", "price": 20.0, "rating": 3, "in_stock": "yes", "url": "b"}
    c = {"title": "C", "price": 5.0, "rating": 3, "in_stock": "yes", "url": "c"}
    old, new = [a, b], [{**a, "price": 8.0}, {**b, "in_stock": "no"}, c]
    changes, stock, added, removed = compare(old, new)
    assert [(x[1], x[2]) for x in changes] == [(10.0, 8.0)] and [r["url"] for r in stock] == ["b"]
    assert added == [c] and removed == []
    text = report(new, "2030-01-01", changes, stock, added, removed)
    assert "£10.00 → £8.00 (-20%)" in text and "out of stock" in text and "New products (1)" in text
    assert "No changes" in report(old, "2030-01-01", [], [], [], [])
    assert "First snapshot" in report(old, None, [], [], [], [])

    global DATA  # CSV round-trip keeps prices as numbers
    import tempfile
    DATA = Path(tempfile.mkdtemp())
    save(new, DATA / "2030-01-02.csv")
    assert load(DATA / "2030-01-02.csv")[0]["price"] == 8.0 and previous_snapshot("2030-01-03").stem == "2030-01-02"
    print("All tests passed ✅")


if __name__ == "__main__":
    {"test": self_test, "demo": make_demo_yesterday}.get(sys.argv[1] if sys.argv[1:] else "", main)()
