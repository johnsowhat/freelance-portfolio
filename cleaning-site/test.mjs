// Run: node test.mjs
import assert from "node:assert/strict";
import { quote, PRICES } from "./pricing.js";

assert.equal(quote().total, PRICES.minimum);                     // tiny home: minimum price applies
const std = quote({ bedrooms: 3, bathrooms: 2 });
assert.equal(std.home, 90 + 2 * 25 + 30);                        // 170
assert.equal(std.total, 170);
const deep = quote({ bedrooms: 3, bathrooms: 2, type: "deep" });
assert.equal(deep.home, 272);
const weekly = quote({ bedrooms: 3, bathrooms: 2, frequency: "weekly", extras: ["oven", "oven", "windows"] });
assert.equal(weekly.addOns, 80);                                 // duplicates counted once
assert.equal(weekly.subtotal, 250);
assert.equal(weekly.discount, 50);
assert.equal(weekly.total, 200);
// bad input from the page never breaks the price
const bad = quote({ bedrooms: "abc", bathrooms: -3, type: "hack", frequency: "daily", extras: ["gold"] });
assert.ok(Number.isFinite(bad.total) && bad.total >= PRICES.minimum && bad.baths === 1);
assert.equal(quote({ bedrooms: 50 }).beds, 8);
assert.ok(quote({ bedrooms: 4, bathrooms: 3, type: "move" }).hours > quote({ bedrooms: 1 }).hours);
console.log("All tests passed ✅");
