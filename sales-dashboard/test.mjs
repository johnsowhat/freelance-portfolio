// Run: node test.mjs
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { parseCSV, toOrders, windows, summarize, change } from "./analytics.js";

// CSV: quotes, commas and newlines inside fields, CRLF, BOM
const rows = parseCSV('﻿Name,Lineitem name\r\n#1,"Mug, ""big"""\r\n#2,"two\nlines"\r\n');
assert.deepEqual(rows, [{ name: "#1", "lineitem name": 'Mug, "big"' }, { name: "#2", "lineitem name": "two\nlines" }]);

assert.throws(() => toOrders(parseCSV("a,b\n1,2")), /Missing columns: name, created at/);
assert.throws(() => toOrders([]), /empty/);

// Multi-line-item order: order fields only on the first row (Shopify format)
const csv = `Name,Email,Financial Status,Created at,Total,Lineitem quantity,Lineitem name,Lineitem price
#1,A@x.com,paid,2030-01-01 10:00:00 -0700,30.00,1,Mug,10.00
#1,,,,,2,Beans,10.00
#2,a@x.com,paid,2030-01-03 10:00:00 -0700,10.00,1,Mug,10.00
#3,b@x.com,refunded,2030-01-03 11:00:00 -0700,99.00,1,Grinder,99.00
#4,c@x.com,pending,2030-01-02 11:00:00 -0700,5.00,1,Filters,5.00`;
const orders = toOrders(parseCSV(csv));
assert.equal(orders.length, 4);
assert.deepEqual(orders[0].items, [{ name: "Mug", qty: 1, price: 10 }, { name: "Beans", qty: 2, price: 10 }]);

const all = windows(orders, 0);
const s = summarize(all.current, all.from, all.to);
assert.equal(s.revenue, 40);                  // refunded and pending don't count
assert.equal(s.orders, 2);
assert.equal(s.aov, 20);
assert.equal(s.customers, 1);                 // emails are case-insensitive
assert.equal(s.repeatRate, 1);
assert.equal(s.refunded, 1);
assert.deepEqual(s.daily.map((d) => [d.date, d.revenue]), [["2030-01-01", 30], ["2030-01-02", 0], ["2030-01-03", 10]]);  // empty days filled
assert.deepEqual(s.products.map((p) => [p.name, p.revenue, p.qty]), [["Beans", 20, 2], ["Mug", 20, 2]]);

const w = windows(orders, 2);
assert.equal(w.from, "2030-01-02");
assert.deepEqual(w.current.map((o) => o.id).sort(), ["#2", "#3", "#4"]);
assert.equal(w.previous, null);               // only 1 day before the window: no full period to compare
assert.equal(change(110, 100).toFixed(2), "0.10");
assert.equal(change(5, 0), null);

// The bundled sample file parses and gives sensible numbers
const sample = toOrders(parseCSV(readFileSync(new URL("./sample-orders.csv", import.meta.url), "utf8")));
const w30 = windows(sample, 30);
const s30 = summarize(w30.current, w30.from, w30.to);
assert.equal(s30.daily.length, 30);
assert.ok(s30.revenue > 0 && s30.repeatRate > 0 && s30.repeatRate < 1 && w30.previous.length > 0);
console.log("All tests passed ✅", { orders: sample.length, revenue30: Math.round(s30.revenue) });
