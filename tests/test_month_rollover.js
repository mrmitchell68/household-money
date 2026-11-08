// hm-v1.11.5: monthly rollover math + This month panel wiring. Pure Node, no browser.
const fs = require("fs"), vm = require("vm"), assert = require("assert");
const html = fs.readFileSync(__dirname + "/../index.html", "utf8");
function grab(name) {
  const i = html.indexOf("function " + name + "(");
  assert(i >= 0, name);
  let d = 0, j = html.indexOf("{", i);
  for (let k = j; k < html.length; k++) { if (html[k] === "{") d++; else if (html[k] === "}" && --d === 0) return html.slice(i, k + 1); }
}
const names = ["pad", "todayYMD", "ymdToDate", "addDaysYMD", "weekStartYMD", "summarize", "savingsAndLeftover", "weeklyLedger", "monthStartYMD"];
const ctx = {}; vm.createContext(ctx);
vm.runInContext(names.map(grab).join("\n"), ctx);
const S = (l, a, b) => ctx.savingsAndLeftover(l, a, b);
// positive rollover with savings
let r = S([{type:"income",date:"2026-10-02",amountCents:500000},{type:"spending",date:"2026-10-31",amountCents:100000},{type:"savings",date:"2026-10-15",amountCents:20000},
  {type:"income",date:"2026-11-01",amountCents:10000},{type:"spending",date:"2026-11-05",amountCents:30000},{type:"savings",date:"2026-11-06",amountCents:5000}],"2026-11-01","2026-11-07");
assert.deepStrictEqual([r.carriedIn,r.savedThisMonth,r.leftNow],[380000,5000,355000]);
// negative rollover; savings taken out (negative) adds back
r = S([{type:"spending",date:"2026-10-31",amountCents:70000},{type:"income",date:"2026-11-01",amountCents:20000},{type:"savings",date:"2026-11-02",amountCents:-10000}],"2026-11-01","2026-11-30");
assert.deepStrictEqual([r.carriedIn,r.savedThisMonth,r.leftNow],[-70000,-10000,-40000]);
// month boundary: 10/31 counts as prior, 11/01 as this month; future dates excluded
r = S([{type:"income",date:"2026-10-31",amountCents:100},{type:"income",date:"2026-11-01",amountCents:7},{type:"income",date:"2026-11-08",amountCents:999}],"2026-11-01","2026-11-07");
assert.deepStrictEqual([r.carriedIn,r.leftNow],[100,107]);
// Oct ending = Nov starting
const rows=[{type:"income",date:"2026-10-05",amountCents:1112112},{type:"spending",date:"2026-10-20",amountCents:788538},{type:"savings",date:"2026-10-21",amountCents:21000}];
assert.strictEqual(S(rows,"2026-10-01","2026-10-31").leftNow, S(rows,"2026-11-01","2026-11-07").carriedIn);
assert.strictEqual(S(rows,"2026-11-01","2026-11-07").carriedIn, 302574);
// weekly unchanged (savings ignored, Mon-Sun)
const L = ctx.weeklyLedger([{type:"income",date:"2026-09-30",amountCents:10000},{type:"spending",date:"2026-10-04",amountCents:30000},{type:"spending",date:"2026-10-05",amountCents:5000},{type:"savings",date:"2026-10-06",amountCents:9999}],"2026-10-07");
assert.deepStrictEqual(JSON.parse(JSON.stringify(L.map(w=>[w.start,w.startBalance,w.endBalance]))),[["2026-09-28",0,-20000],["2026-10-05",-20000,-25000]]);
// panel wiring
for (const id of ["month-start","month-in","month-out","month-saved","month-left","carried-in","left-rolls","week-start"]) assert(html.includes('id="'+id+'"'), id);
for (const s of ['setSigned("month-start", roll.carriedIn)','setSigned("month-saved", roll.savedThisMonth)','setSigned("month-left", roll.leftNow)']) assert(html.includes(s), s);
assert(html.indexOf('setSigned("month-left"') > html.indexOf('setMoney("month"'));
assert(fs.readFileSync(__dirname+"/../sw.js","utf8").includes('VERSION = "hm-v1.11.5"') && html.includes("App version hm-v1.11.5"));
console.log("month rollover tests: OK");
