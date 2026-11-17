"""Writes sample-orders.csv: a made-up coffee shop's orders in Shopify's order-export format
(one row per line item; order fields only on the first row). Fictional data for the demo."""
import csv, random
from datetime import datetime, timedelta

PRODUCTS = [("Ethiopia Yirgacheffe 12oz", 19.0), ("Colombia Huila 12oz", 17.0), ("House Espresso Blend 2lb", 38.0),
            ("Decaf Swiss Water 12oz", 18.0), ("Cold Brew Packs (6)", 24.0), ("Pour-Over Kettle", 64.0),
            ("Ceramic Dripper", 28.0), ("Paper Filters (100)", 8.0), ("Burr Grinder", 129.0), ("Gift Card", 50.0),
            ("Travel Mug", 32.0), ("Kenya AA 12oz", 22.0)]
WEIGHTS = [16, 14, 12, 6, 9, 3, 4, 8, 2, 3, 5, 7]
FIELDS = ["Name", "Email", "Financial Status", "Created at", "Currency", "Subtotal", "Shipping", "Total",
          "Lineitem quantity", "Lineitem name", "Lineitem price", "Billing Province"]
STATES = ["CA", "NY", "TX", "WA", "OR", "IL", "CO", "MA", "FL", "GA"]

rnd = random.Random(42)
start = datetime(2026, 8, 20)
customers = [f"customer{i}@example.com" for i in range(1, 700)]
rows, number = [], 1001
for day in range(90):
    date = start + timedelta(days=day)
    base = 10 + day * 0.09 + (5 if date.weekday() in (4, 5) else 0)  # growth + weekend bump
    if day in range(75, 79):
        base *= 1.9  # a holiday sale spike
    for _ in range(max(1, int(rnd.gauss(base, 3)))):
        # 35% of orders come from a small loyal group: that's what makes "repeat customers" real
        email = rnd.choice(customers[:120]) if rnd.random() < 0.35 else rnd.choice(customers)
        items = {}
        for p in rnd.choices(PRODUCTS, WEIGHTS, k=rnd.choice([1, 1, 1, 2, 2, 3])):
            items[p] = items.get(p, 0) + 1
        subtotal = sum(price * q for (name, price), q in items.items())
        shipping = 0.0 if subtotal >= 50 else 6.0
        status = rnd.choices(["paid", "refunded", "pending"], [96, 3, 1])[0]
        t = date + timedelta(minutes=rnd.randint(7 * 60, 23 * 60))
        for i, ((name, price), q) in enumerate(items.items()):
            first = i == 0
            rows.append({"Name": f"#{number}", "Email": email if first else "",
                         "Financial Status": status if first else "", "Created at": t.strftime("%Y-%m-%d %H:%M:%S -0700") if first else "",
                         "Currency": "USD" if first else "", "Subtotal": f"{subtotal:.2f}" if first else "",
                         "Shipping": f"{shipping:.2f}" if first else "", "Total": f"{subtotal + shipping:.2f}" if first else "",
                         "Lineitem quantity": q, "Lineitem name": name, "Lineitem price": f"{price:.2f}",
                         "Billing Province": rnd.choice(STATES) if first else ""})
        number += 1

with open("sample-orders.csv", "w", newline="") as f:
    w = csv.DictWriter(f, FIELDS)
    w.writeheader()
    w.writerows(rows)
print(f"{number - 1001} orders, {len(rows)} rows")
