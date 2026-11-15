// hm-v1.12.1: spending report totals, sort, inclusive dates, pie paths. Pure Node, no browser.
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
  "savingsAndLeftover", "weeklyLedger", "monthStartYMD", "isYMD",
  "monthEndYMD", "previousMonthStartYMD", "pieSlicePath", "normalizeOmitIds", "spendingReport", "reportPresetRange"
];
const ctx = {};
vm.createContext(ctx);
vm.runInContext(names.map(grab).join("\n") + "\nvar REPORT_COLORS = ['#0f6b4c','#8d2f28','#e6b325','#1f6f8b','#6b4c9a','#c45c26','#2e7d4f','#5c6b7a','#b5477a','#3d5a80'];\n", ctx);
function J(v) { return JSON.parse(JSON.stringify(v)); }

const rows = [
  { id: "a", type: "spending", date: "2026-10-31", category: "Gas", amountCents: 4000, note: "Exxon" },
  { id: "b", type: "spending", date: "2026-11-01", category: "Groceries", amountCents: 8000, note: "Food Lion" },
  { id: "c", type: "spending", date: "2026-11-10", category: "Eating Out", amountCents: 5500, note: "Dragon Place" },
  { id: "d", type: "spending", date: "2026-11-15", category: "Groceries", amountCents: 2000, note: "ALDI" },
  { id: "e", type: "income", date: "2026-11-11", who: "Mitch", amountCents: 84258 },
  { id: "f", type: "savings", date: "2026-11-06", who: "Mitch", amountCents: 3500 },
  { id: "g", type: "spending", date: "2026-11-16", category: "Gas", amountCents: 1000, note: "Shell" }
];

const r = ctx.spendingReport(rows, "2026-11-01", "2026-11-15");
assert.strictEqual(r.ok, true);
assert.strictEqual(r.total, 8000 + 5500 + 2000); // groceries 10000 + eating 5500; gas 10/31 and 11/16 excluded
assert.deepStrictEqual(J(r.categories.map(c => [c.name, c.amountCents, c.count])), [
  ["Groceries", 10000, 2],
  ["Eating Out", 5500, 1]
]);
assert(r.categories[0].amountCents >= r.categories[1].amountCents);
assert.strictEqual(r.categories[0].percent, 64.5); // 10000/15500 = 64.516... -> 64.5
assert.strictEqual(r.categories[1].percent, 35.5);
assert.deepStrictEqual(J(r.entries.map(e => e.id)), ["b", "c", "d"]);
assert.deepStrictEqual(J((r.omitted || []).map(e => e.id)), []);

// Omit one entry: totals and sort recalculate; source rows are unchanged
const one = ctx.spendingReport(rows, "2026-11-01", "2026-11-15", ["c"]);
assert.strictEqual(one.total, 10000);
assert.deepStrictEqual(J(one.categories.map(c => [c.name, c.amountCents, c.count, c.percent])), [
  ["Groceries", 10000, 2, 100]
]);
assert.deepStrictEqual(J(one.entries.map(e => e.id)), ["b", "d"]);
assert.deepStrictEqual(J(one.omitted.map(e => e.id)), ["c"]);
assert.strictEqual(rows.find(e => e.id === "c").amountCents, 5500);

// Omit a whole category (both grocery entries)
const cat = ctx.spendingReport(rows, "2026-11-01", "2026-11-15", ["b", "d"]);
assert.strictEqual(cat.total, 5500);
assert.deepStrictEqual(J(cat.categories.map(c => [c.name, c.amountCents, c.count])), [["Eating Out", 5500, 1]]);
assert.deepStrictEqual(J(cat.omitted.map(e => e.id)), ["b", "d"]);

// Restore one grocery item (only "b" still omitted)
const rest = ctx.spendingReport(rows, "2026-11-01", "2026-11-15", ["b"]);
assert.strictEqual(rest.total, 7500);
assert.deepStrictEqual(J(rest.categories.map(c => [c.name, c.amountCents])), [["Eating Out", 5500], ["Groceries", 2000]]);
assert.deepStrictEqual(J(rest.omitted.map(e => e.id)), ["b"]);

// Restore all
const allBack = ctx.spendingReport(rows, "2026-11-01", "2026-11-15", []);
assert.strictEqual(allBack.total, 15500);
assert.strictEqual(allBack.omitted.length, 0);

// Inclusive ends and income/savings excluded
const justEnds = ctx.spendingReport(rows, "2026-10-31", "2026-10-31");
assert.strictEqual(justEnds.total, 4000);
const none = ctx.spendingReport(rows, "2026-11-02", "2026-11-09");
assert.strictEqual(none.total, 0);
assert.strictEqual(none.categories.length, 0);
const bad = ctx.spendingReport(rows, "2026-11-15", "2026-11-01");
assert.strictEqual(bad.ok, false);

// Weekly/monthly still count the same spending (report does not remove it)
const month = ctx.summarize(rows, "2026-11-01", "2026-11-15");
assert.strictEqual(month.moneyOut, 15500);
assert.strictEqual(month.moneyIn, 84258);

// Presets
assert.strictEqual(ctx.monthEndYMD("2026-11-01"), "2026-11-30");
assert.strictEqual(ctx.previousMonthStartYMD(new Date(2026, 10, 15)), "2026-10-01"); // Nov 15
assert.strictEqual(ctx.previousMonthStartYMD(new Date(2026, 0, 5)), "2025-12-01");
const last = ctx.reportPresetRange("last-month", new Date(2026, 10, 15));
assert.deepStrictEqual(J(last), { start: "2026-10-01", end: "2026-10-31" });
const week = ctx.reportPresetRange("week", new Date(2026, 10, 11)); // Wed Nov 11, 2026
assert.deepStrictEqual(J(week), { start: "2026-11-09", end: "2026-11-15" });
const mon = ctx.reportPresetRange("month", new Date(2026, 10, 15));
assert.deepStrictEqual(J(mon), { start: "2026-11-01", end: "2026-11-30" });

// Pie geometry: a half slice starts at the top and ends on the right
const half = ctx.pieSlicePath(100, 100, 90, 0, Math.PI);
assert(half.startsWith("M 100 100 L 100.000 10.000 A 90 90 0 0 1 100.000 190.000 Z") || half.indexOf("A 90 90 0 0 1") !== -1, half);
assert.strictEqual((half.match(/A 90 90 0 0 1/) || []).length, 1);
const most = ctx.pieSlicePath(100, 100, 90, 0, Math.PI * 1.5);
assert(most.indexOf("A 90 90 0 1 1") !== -1, most);

for (const id of ["view-report", "report-start", "report-end", "report-presets", "report-pie", "report-total", "report-print", "report-entries-wrap"]) {
  assert(html.includes('id="' + id + '"'), id);
}
assert(html.includes('href="#/report"'));
assert(html.includes("Save / Print PDF"));
assert(html.includes("@media print"));
assert(html.includes(".no-print"));
assert(html.includes("report-omitted"));
assert(html.includes("report-omit-line"));
assert(html.includes('id="report-entries-wrap" open') || html.includes("details.open = true"));
assert(html.includes("@media print") && html.includes(".report-omitted"));
const sw = fs.readFileSync(__dirname + "/../sw.js", "utf8");
assert(sw.includes('VERSION = "hm-v1.12.1"') && html.includes("App version hm-v1.12.1"));
console.log("report tests: OK");
