// Instant quote logic. Edit the numbers for each client; the page and tests use this module.

export const PRICES = {
  base: 90,                 // studio / 1 bed / 1 bath, standard clean
  perBedroom: 25,           // each bedroom after the first
  perBathroom: 30,          // each bathroom after the first
  type: { standard: 1, deep: 1.6, move: 1.9 },                  // multipliers
  frequency: { once: 0, monthly: 0.1, biweekly: 0.15, weekly: 0.2 },  // discounts on recurring cleans
  extras: { fridge: 35, oven: 35, windows: 45, laundry: 25, cabinets: 40 },
  minimum: 100,
};

export const LABELS = {
  type: { standard: "Standard clean", deep: "Deep clean", move: "Move-in / move-out" },
  frequency: { once: "One time", monthly: "Monthly", biweekly: "Every 2 weeks", weekly: "Weekly" },
  extras: { fridge: "Inside fridge", oven: "Inside oven", windows: "Interior windows", laundry: "Laundry & folding", cabinets: "Inside cabinets" },
};

const clampInt = (v, lo, hi) => Math.min(hi, Math.max(lo, Math.round(Number(v) || 0)));

/** Quote for a cleaning. Unknown options fall back to defaults instead of producing NaN. */
export function quote({ bedrooms = 1, bathrooms = 1, type = "standard", frequency = "once", extras = [] } = {}) {
  const beds = clampInt(bedrooms, 0, 8), baths = clampInt(bathrooms, 1, 6);
  const mult = PRICES.type[type] ?? 1;
  const discountRate = PRICES.frequency[frequency] ?? 0;
  const home = (PRICES.base + Math.max(0, beds - 1) * PRICES.perBedroom + (baths - 1) * PRICES.perBathroom) * mult;
  const addOns = [...new Set(extras)].filter((e) => e in PRICES.extras).reduce((s, e) => s + PRICES.extras[e], 0);
  const subtotal = Math.max(PRICES.minimum, Math.round(home + addOns));
  const discount = Math.round(subtotal * discountRate);
  const hours = Math.max(2, Math.round(((home / 45) + addOns / 40) * 2) / 2);  // rough crew time, half-hour steps
  return { home: Math.round(home), addOns, subtotal, discount, total: subtotal - discount, hours, beds, baths };
}
