// Pure data logic for the dashboard: CSV parsing and sales metrics. No DOM, so it's testable in Node.

const REVENUE_STATUSES = new Set(["paid", "partially_paid", "partially_refunded"]);

export function parseCSV(text) {
  const rows = [];
  let row = [], field = "", quoted = false;
  text = text.replace(/^﻿/, "");
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') { field += '"'; i++; }
      else if (c === '"') quoted = false;
      else field += c;
    } else if (c === '"') quoted = true;
    else if (c === ",") { row.push(field); field = ""; }
    else if (c === "\n" || c === "\r") {
      if (c === "\r" && text[i + 1] === "\n") i++;
      row.push(field); rows.push(row); row = []; field = "";
    } else field += c;
  }
  if (field || row.length) { row.push(field); rows.push(row); }
  const [header, ...body] = rows.filter((r) => r.some((v) => v.trim()));
  if (!header) return [];
  const keys = header.map((h) => h.trim().toLowerCase());
  return body.map((r) => Object.fromEntries(keys.map((k, i) => [k, (r[i] ?? "").trim()])));
}

const NEEDED = ["name", "created at", "total", "lineitem name", "lineitem quantity", "lineitem price"];

/** Shopify order export rows (one per line item) -> orders. Throws a readable error on a wrong file. */
export function toOrders(rows) {
  const missing = NEEDED.filter((k) => rows.length && !(k in rows[0]));
  if (!rows.length || missing.length) {
    throw new Error(rows.length ? `This doesn't look like a Shopify orders export. Missing columns: ${missing.join(", ")}.` : "The file is empty.");
  }
  const byId = new Map();
  for (const r of rows) {
    let o = byId.get(r.name);
    if (!o) {
      o = { id: r.name, email: "", status: "", date: "", total: 0, items: [] };
      byId.set(r.name, o);
    }
    // order-level fields are only filled on the order's first row
    if (r["created at"]) o.date = r["created at"].slice(0, 10);
    if (r.email) o.email = r.email.toLowerCase();
    if (r["financial status"]) o.status = r["financial status"].toLowerCase();
    if (r.total) o.total = parseFloat(r.total) || 0;
    const qty = parseInt(r["lineitem quantity"], 10) || 0;
    if (r["lineitem name"] && qty) o.items.push({ name: r["lineitem name"], qty, price: parseFloat(r["lineitem price"]) || 0 });
  }
  return [...byId.values()].filter((o) => /^\d{4}-\d{2}-\d{2}$/.test(o.date));
}

const addDays = (iso, n) => {
  const d = new Date(iso + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
};

/** Orders of the last `days` days (relative to the newest order) and the same-length period before. */
export function windows(orders, days) {
  if (!orders.length) return { current: [], previous: [], from: "", to: "" };
  const to = orders.reduce((m, o) => (o.date > m ? o.date : m), "");
  const first = orders.reduce((m, o) => (o.date < m ? o.date : m), to);
  if (!days) return { current: orders, previous: null, from: first, to };
  const from = addDays(to, -(days - 1)), prevFrom = addDays(from, -days);
  return {
    current: orders.filter((o) => o.date >= from),
    previous: prevFrom >= first ? orders.filter((o) => o.date >= prevFrom && o.date < from) : null,  // only a full previous period
    from, to,
  };
}

export function summarize(orders, from, to) {
  const sold = orders.filter((o) => REVENUE_STATUSES.has(o.status));
  const revenue = sold.reduce((s, o) => s + o.total, 0);
  const perCustomer = new Map();
  for (const o of sold) if (o.email) perCustomer.set(o.email, (perCustomer.get(o.email) || 0) + 1);
  const repeat = [...perCustomer.values()].filter((n) => n > 1).length;

  const daily = new Map();
  for (let d = from; d && d <= to; d = addDays(d, 1)) daily.set(d, { date: d, revenue: 0, orders: 0 });
  for (const o of sold) {
    const day = daily.get(o.date);
    if (day) { day.revenue += o.total; day.orders += 1; }
  }

  const products = new Map();
  for (const o of sold) for (const it of o.items) {
    const p = products.get(it.name) || { name: it.name, revenue: 0, qty: 0 };
    p.revenue += it.qty * it.price; p.qty += it.qty;
    products.set(it.name, p);
  }

  return {
    revenue, orders: sold.length,
    aov: sold.length ? revenue / sold.length : 0,
    customers: perCustomer.size,
    repeatRate: perCustomer.size ? repeat / perCustomer.size : 0,
    refunded: orders.filter((o) => o.status === "refunded").length,
    daily: [...daily.values()],
    products: [...products.values()].sort((a, b) => b.revenue - a.revenue || a.name.localeCompare(b.name)),
  };
}

/** % change, or null when there's nothing to compare with. */
export const change = (now, before) => (before ? (now - before) / before : null);
