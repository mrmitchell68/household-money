// hm-v1.11.6: trip date-range rule, explicit No trip, totals, weekly/monthly unchanged. Pure Node, no browser.
const fs = require("fs"), vm = require("vm"), assert = require("assert");
const html = fs.readFileSync(__dirname + "/../index.html", "utf8");
function grab(name) {
  const i = html.indexOf("function " + name + "(");
  assert(i >= 0, "missing " + name);
  let d = 0, j = html.indexOf("{", i);
  for (let k = j; k < html.length; k++) { if (html[k] === "{") d++; else if (html[k] === "}" && --d === 0) return html.slice(i, k + 1); }
}
const names = [
  "pad", "todayYMD", "ymdToDate", "addDaysYMD", "weekStartYMD", "summarize",
  "savingsAndLeftover", "weeklyLedger", "monthStartYMD", "isYMD", "sanitizeTrip",
  "findTrip", "tripsCoveringDate", "defaultTripForDate", "normalizeTripOverride",
  "entryTripId", "entryBelongsToTrip", "tripSpending", "chosenTripOverride"
];
const ctx = {};
vm.createContext(ctx);
vm.runInContext(names.map(grab).join("\n") + "\nvar trips = [];\n", ctx);
function J(v) { return JSON.parse(JSON.stringify(v)); }

const trip = ctx.sanitizeTrip({ id: "trip-2026-11-10-15", name: "Trip Nov 10–15, 2026", start: "2026-11-10", end: "2026-11-15" });
assert.strictEqual(trip.id, "trip-2026-11-10-15");
assert.strictEqual(trip.name, "Trip Nov 10–15, 2026");
assert.strictEqual(ctx.sanitizeTrip({ id: "x", name: "Bad", start: "2026-11-15", end: "2026-11-10" }), null);
assert.strictEqual(ctx.sanitizeTrip({ id: "x", name: "  ", start: "2026-11-10", end: "2026-11-15" }), null);

const list = [trip];
const later = ctx.sanitizeTrip({ id: "t2", name: "Later", start: "2026-11-14", end: "2026-11-20" });
const two = [trip, later];

// Inclusive start and end, exclusive outside
assert.strictEqual(ctx.defaultTripForDate(list, "2026-11-10").id, trip.id);
assert.strictEqual(ctx.defaultTripForDate(list, "2026-11-15").id, trip.id);
assert.strictEqual(ctx.defaultTripForDate(list, "2026-11-09"), null);
assert.strictEqual(ctx.defaultTripForDate(list, "2026-11-16"), null);
// Overlap: later start wins
assert.strictEqual(ctx.defaultTripForDate(two, "2026-11-14").id, "t2");
assert.strictEqual(ctx.defaultTripForDate(two, "2026-11-13").id, trip.id);

const gas = { id: "1", type: "spending", date: "2026-11-10", category: "Gas", amountCents: 4000 };
const food = { id: "2", type: "spending", date: "2026-11-12", category: "Eating Out", amountCents: 5500 };
const after = { id: "3", type: "spending", date: "2026-11-16", category: "Gas", amountCents: 1000 };
const before = { id: "4", type: "spending", date: "2026-11-09", category: "Groceries", amountCents: 2000 };
const income = { id: "5", type: "income", date: "2026-11-11", who: "Mitch", amountCents: 99999 };
const savings = { id: "6", type: "savings", date: "2026-11-11", who: "Mitch", amountCents: 3500 };
const none = { id: "7", type: "spending", date: "2026-11-11", category: "Cards", amountCents: 30000, tripOverride: "none" };
const taggedOut = { id: "8", type: "spending", date: "2026-11-20", category: "Gas", amountCents: 800, tripOverride: trip.id };

assert.strictEqual(ctx.entryBelongsToTrip(gas, trip, list), true);
assert.strictEqual(ctx.entryBelongsToTrip(food, trip, list), true);
assert.strictEqual(ctx.entryBelongsToTrip(after, trip, list), false);
assert.strictEqual(ctx.entryBelongsToTrip(before, trip, list), false);
assert.strictEqual(ctx.entryBelongsToTrip(income, trip, list), false);
assert.strictEqual(ctx.entryBelongsToTrip(savings, trip, list), false);
assert.strictEqual(ctx.entryBelongsToTrip(none, trip, list), false);
assert.strictEqual(ctx.entryTripId(none, list), "none");
assert.strictEqual(ctx.entryBelongsToTrip(taggedOut, trip, list), true);

const items = [gas, food, after, before, income, savings, none, taggedOut];
const sum = ctx.tripSpending(list, items, trip);
assert.strictEqual(sum.total, 4000 + 5500 + 800); // gas + food + explicit outside, not Cards (No trip)
assert.deepStrictEqual(J(sum.byCategory.map(c => [c.name, c.amountCents])), [["Eating Out", 5500], ["Gas", 4800]]);
assert.deepStrictEqual(J(sum.entries.map(e => e.id)), ["1", "2", "8"]);

// chosenTripOverride: default trip left unset; No trip is explicit only when a trip covers the date
assert.strictEqual(ctx.chosenTripOverride(trip.id, "2026-11-11", list), "");
assert.strictEqual(ctx.chosenTripOverride("none", "2026-11-11", list), "none");
assert.strictEqual(ctx.chosenTripOverride("none", "2026-11-20", list), "");
assert.strictEqual(ctx.chosenTripOverride("t2", "2026-11-11", two), "t2");

// Weekly and monthly still include trip spending (no double-count, not removed)
const week = ctx.weeklyLedger(items, "2026-11-15");
const thisWeek = week.filter(w => w.start === "2026-11-09")[0];
// Mon 11/9 through Sun 11/15: before 2000, gas 4000, food 5500, none 30000; income ignored in moneyOut; taggedOut is 11/20
assert.strictEqual(thisWeek.moneyOut, 2000 + 4000 + 5500 + 30000);
assert.strictEqual(thisWeek.moneyIn, 99999);
const month = ctx.summarize(items, "2026-11-01", "2026-11-30");
assert.strictEqual(month.moneyOut, 2000 + 4000 + 5500 + 1000 + 30000 + 800);
assert.strictEqual(month.moneyIn, 99999);
const roll = ctx.savingsAndLeftover(items, "2026-11-01", "2026-11-30");
assert.strictEqual(roll.savedThisMonth, 3500);

// UI wiring and version
for (const id of ["view-trips", "view-trip", "view-trip-form", "spend-trip", "home-trip", "trip-total", "trip-cats", "trip-entries"]) {
  assert(html.includes('id="' + id + '"'), id);
}
assert(html.includes("Trip Nov 10–15, 2026"));
assert(html.includes("trip-2026-11-10-15"));
assert(html.includes('href="#/trips"'));
assert(html.includes("function loadTrips"));
assert(!/entrySyncPayload[\s\S]{0,400}tripOverride/.test(html), "sync payload must not send tripOverride");
const sw = fs.readFileSync(__dirname + "/../sw.js", "utf8");
assert(sw.includes('VERSION = "hm-v1.11.6"') && html.includes("App version hm-v1.11.6"));
console.log("trip tests: OK");
