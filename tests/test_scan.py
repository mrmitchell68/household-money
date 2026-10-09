"""Receipt scan checks for hm-v1.10.0: date parsing, category guessing, and the scan flow.
Runs against http://127.0.0.1:8788/ with system Chrome. Google is never contacted."""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
URL = "http://127.0.0.1:8788/"
PNG = Path("/tmp/hm-scan-receipt.png")
DEFAULT = ["Tithes", "Mortgage", "Utilities", "Car Payment", "Groceries", "Phones", "Cards", "Medical", "Online"]
FAILS = []


def check(name, got, want):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + name + ": got " + json.dumps(got) + (" " if ok else " want " + json.dumps(want)))
    if not ok:
        FAILS.append(name)


# Realistic OCR output (including OCR noise) from common receipts and bills.
WALMART = """Walmart >|<
Save money. Live better.
( 336 ) 555 - 0142
MANAGER JOHN SMITH
1234 S MAIN ST
KERNERSVILLE NC 27284
ST# 01234 OP# 009012 TE# 12 TR# 04567
GV 2% MILK 007874235187 3.12 N
EGGS LG 18CT 007874213301 4.27 N
GREAT VALUE BREAD 007874237003 1.42 N
BANANAS 000000004011KF 1.38 N
SUBTOTAL 10.19
TAX 1 2.000 % 0.20
TOTAL 10.39
DEBIT TEND 10.39
CHANGE DUE 0.00
# ITEMS SOLD 4
TC# 1234 5678 9012 3456 7890
10/07/26 14:32:11
***CUSTOMER COPY***"""

SHELL = """SHELL
3401 N PATTERSON AVE
WINSTON SALEM NC 27105
DATE: 10/05/2026 TIME: 08:15
INVOICE 004512
PUMP # 04
UNLEADED
GALLONS 10.123
PRICE/GAL $3.099
FUEL TOTAL $31.37
VISA XXXXXXXXXXXX1234
EXP **/**
APPROVED AUTH 012345"""

HOME_DEPOT = """THE HOME DEPOT
1800 PEACHTREE RD
(336)555-0199
6234 00045 12345 09/02/26 10:12 AM
SALE SELF CHECKOUT
012345678901 CLOSET FLANGE <A> 8.97
049793034427 PVC CEMENT <A> 6.48
SUBTOTAL 15.45
SALES TAX 1.08
TOTAL $16.53
XXXXXXXXXXXX4321 VISA
RETURN POLICY DEFINITIONS
POLICY ID DAYS POLICY EXPIRES ON
A 1 30 10/02/2026"""

CVS = """CVS pharmacy
Store 7123
RX#1234567 PATIENT: HENDERSON
COPAY 10.00
TOTAL 10.00
Oct 3, 2026 4:51 PM
Returns with receipt by 11/02/2026"""

AMAZON = """amazon.com
Order Placed: October 1, 2026
Order# 112-1234567-1234567
Shipped to: Allen Henderson
Order Total: $42.18"""

DUKE = """DUKE ENERGY
Statement Date Sep 15, 2026
Service address 12 OAK ST
Electric service 1,024 kWh
Amount Due $142.36
Due Date Oct 5, 2026"""

VERIZON = """verizon
Bill date 08OCT26
Account number 123456789-00001
Wireless line access 4 lines
Total amount due $186.40"""

KROGER = """KROGER
Your cashier was SELF
KRO HOMESTYLE MILK 3.29
GROUND BEEF 6.99
APPLES 2.49
TOTAL 12.77
TRANS DATE 1O/O4/2026"""

SPEEDWAY = """SPEEDWAY 0043712
9-30-26 07:02
PUMP 2 REGULAR UNL
GALLONS 9.500
TOTAL $29.40"""

NO_DATE = """MYSTERY BOOTH
THANK YOU
TOTAL 5.00"""

DOLLAR_GENERAL = """DOLLAR GENERAL #04512
BLEACH 64OZ 3.50
PAPER TOWELS 6PK 7.95
TOTAL 11.45
10/06/2026 18:22"""

SHEETZ_OCR = """SHEETZ #0412
1200 S STRATFORD RD
Date 10/06/2026 Time 17:45
Pump 6 Unleaded
Gallons 11.502
Price/Gal $3.149
Total $38.12
Approved"""


def tiny_png(path: Path) -> None:
    import struct
    import zlib

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + b"\xff\xff\xff" * 2 for _ in range(2))
    ihdr = struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


STUB_OCR = """
window.__ocrText = '';
window.Tesseract = { createWorker: function () { return Promise.resolve({ recognize: function () {
  return Promise.resolve({ data: { text: window.__ocrText } }); } }); } };
"""


def unit_tests(page):
    dates = page.evaluate("""(s) => {
      const now = new Date(2026, 9, 8, 12, 0, 0);
      const out = {};
      for (const k of Object.keys(s)) out[k] = HM.extractDate(s[k], now);
      return out;
    }""", {
        "walmart": WALMART, "shell": SHELL, "homeDepot": HOME_DEPOT, "cvs": CVS, "amazon": AMAZON,
        "duke": DUKE, "verizon": VERIZON, "kroger": KROGER, "speedway": SPEEDWAY, "none": NO_DATE,
        "iso": "Order Date: 2026-10-06", "slashIso": "2026/09/14 SALE",
        "named": "Oct 8, 2026", "namedNoYear": "Sale Sep 30 4:10 PM",
        "dmy": "08OCT26", "dmyDash": "TRANS 07-OCT-2026",
        "cardExp": "EXP 09/30/2026\nSale 10/02/26",
        "future": "Date 12/25/2026", "tooOld": "01/02/2024",
        "phoneOnly": "TEL 336-555-1234\nTOTAL 4.99",
        "market": "FARMERS MARKET 12\nTOTAL 3.00",
        "dayFirst": "Date 25/09/2026",
    })
    want = {
        "walmart": "2026-10-07", "shell": "2026-10-05", "homeDepot": "2026-09-02", "cvs": "2026-10-03",
        "amazon": "2026-10-01", "duke": "2026-09-15", "verizon": "2026-10-08", "kroger": "2026-10-04",
        "speedway": "2026-09-30", "none": "", "iso": "2026-10-06", "slashIso": "2026-09-14",
        "named": "2026-10-08", "namedNoYear": "2026-09-30", "dmy": "2026-10-08", "dmyDash": "2026-10-07",
        "cardExp": "2026-10-02", "future": "", "tooOld": "", "phoneOnly": "", "market": "", "dayFirst": "2026-09-25",
    }
    for k in want:
        check("date " + k, dates[k], want[k])

    cats_gas = DEFAULT + ["Gas"]
    cats_fuel = DEFAULT + ["Fuel"]
    cats_build = DEFAULT + ["Building Material"]
    cases = page.evaluate("""(a) => {
      const s = (t, cats, learned) => HM.suggestCategory(t, cats, { learned: learned || {} });
      const g = (t, cats, learned) => { const r = s(t, cats, learned); return r ? r.category : null; };
      const T = a.t;
      return {
        shellDefault: s(T.shell, a.d),
        shellGas: g(T.shell, a.gas),
        shellFuel: g(T.shell, a.fuel),
        speedwayGas: g(T.speedway, a.gas),
        exxon: g('EXXONMOBIL' + String.fromCharCode(10) + 'GALLONS 8.2' + String.fromCharCode(10) + 'TOTAL 25.10', a.gas),
        wawa: g('WAWA 8123' + String.fromCharCode(10) + 'FUEL PUMP 3' + String.fromCharCode(10) + 'TOTAL 40.00', a.gas),
        bp: g('BP' + String.fromCharCode(10) + 'UNLEADED' + String.fromCharCode(10) + 'TOTAL 20.00', a.gas),
        circleK: g('CIRCLE K 2741' + String.fromCharCode(10) + 'TOTAL 30.00', a.gas),
        walmartItems: g(T.walmart, a.d),
        walmartPlain: g('WALMART SUPERCENTER' + String.fromCharCode(10) + 'TOTAL 12.34', a.d),
        walmartCom: g('walmart.com' + String.fromCharCode(10) + 'Order total 22.10', a.d),
        kroger: g(T.kroger, a.d),
        aldi: g('ALDI' + String.fromCharCode(10) + 'TOTAL 54.20', a.d),
        foodLion: g('FOOD LION #1234' + String.fromCharCode(10) + 'TOTAL 54.20', a.d),
        lowesFoods: g('LOWES FOODS' + String.fromCharCode(10) + 'TOTAL 54.20', a.build),
        homeDepotDefault: s(T.homeDepot, a.d),
        homeDepotBuild: g(T.homeDepot, a.build),
        lowes: g("LOWE'S HOME CENTERS" + String.fromCharCode(10) + 'TOTAL 18.00', a.build),
        cvs: g(T.cvs, a.d),
        walgreens: g('Walgreens #0312' + String.fromCharCode(10) + 'TOTAL 8.20', a.d),
        amazon: g(T.amazon, a.d),
        ebay: g('eBay order confirmation' + String.fromCharCode(10) + 'Total 15.00', a.d),
        fb: g('Facebook Marketplace' + String.fromCharCode(10) + 'Paid 40.00', a.d),
        verizon: g(T.verizon, a.d),
        duke: g(T.duke, a.d),
        groceryWater: g(T.kroger + String.fromCharCode(10) + 'DASANI WATER 4.99', a.d),
        unknown: s(T.none, a.d),
        memoryWins: g(T.kroger, a.d, { 'kroger': 'Online' }),
        memoryMissingCat: g(T.kroger, a.d, { 'kroger': 'Gone Category' }),
        onlyExisting: g(T.shell, ['Groceries', 'Online']),
      };
    }""", {"t": {"shell": SHELL, "speedway": SPEEDWAY, "walmart": WALMART, "kroger": KROGER, "homeDepot": HOME_DEPOT,
                 "cvs": CVS, "amazon": AMAZON, "verizon": VERIZON, "duke": DUKE, "none": NO_DATE},
           "d": DEFAULT, "gas": cats_gas, "fuel": cats_fuel, "build": cats_build})
    check("cat shell without Gas category asks", [cases["shellDefault"]["category"], cases["shellDefault"]["concept"]], [None, "gas"])
    check("cat shell -> Gas", cases["shellGas"], "Gas")
    check("cat shell -> Fuel", cases["shellFuel"], "Fuel")
    check("cat speedway", cases["speedwayGas"], "Gas")
    check("cat exxon", cases["exxon"], "Gas")
    check("cat wawa", cases["wawa"], "Gas")
    check("cat bp", cases["bp"], "Gas")
    check("cat circle k", cases["circleK"], "Gas")
    check("cat walmart grocery items", cases["walmartItems"], "Groceries")
    check("cat walmart plain (old behavior)", cases["walmartPlain"], "Online")
    check("cat walmart.com", cases["walmartCom"], "Online")
    check("cat kroger", cases["kroger"], "Groceries")
    check("cat aldi", cases["aldi"], "Groceries")
    check("cat food lion", cases["foodLion"], "Groceries")
    check("cat lowes foods is groceries", cases["lowesFoods"], "Groceries")
    check("cat home depot without hardware category asks", [cases["homeDepotDefault"]["category"], cases["homeDepotDefault"]["concept"]], [None, "hardware"])
    check("cat home depot -> Building Material", cases["homeDepotBuild"], "Building Material")
    check("cat lowe's -> Building Material", cases["lowes"], "Building Material")
    check("cat cvs", cases["cvs"], "Medical")
    check("cat walgreens", cases["walgreens"], "Medical")
    check("cat amazon", cases["amazon"], "Online")
    check("cat ebay", cases["ebay"], "Online")
    check("cat facebook marketplace", cases["fb"], "Online")
    check("cat verizon", cases["verizon"], "Phones")
    check("cat duke energy", cases["duke"], "Utilities")
    check("cat grocery receipt with water stays groceries", cases["groceryWater"], "Groceries")
    check("cat unknown store", cases["unknown"], None)
    check("cat per-store memory first", cases["memoryWins"], "Online")
    check("cat memory to deleted category ignored", cases["memoryMissingCat"], "Groceries")
    check("cat only existing categories", cases["onlyExisting"], None)

    # Learner trained from synced entries (shape returned by hmPull), as on the other phone.
    learn = page.evaluate("""(a) => {
      const cats = a.d.concat(['Household', 'Pets']);
      const pulled = [
        {id:'p1', type:'spending', date:'2026-09-01', who:'Tonya', category:'Household', amountCents:1145, note:'Dollar General', receiptName:'', hasPhoto:false},
        {id:'p2', type:'spending', date:'2026-09-09', who:'Mitch', category:'Household', amountCents:2210, note:'Dollar General #0451', receiptName:'', hasPhoto:false},
        {id:'p3', type:'spending', date:'2026-09-12', who:'Tonya', category:'Pets', amountCents:3899, note:'Pet Supermarket dog food', receiptName:'', hasPhoto:false},
        {id:'p4', type:'spending', date:'2026-09-20', who:'Tonya', category:'Pets', amountCents:4200, note:'Pet Supermarket', receiptName:'', hasPhoto:false},
        {id:'p5', type:'spending', date:'2026-09-21', who:'Mitch', category:'Groceries', amountCents:8800, note:'Food Lion', receiptName:'', hasPhoto:false},
        {id:'p6', type:'income', date:'2026-09-21', who:'Mitch', category:'', amountCents:100000, note:'Dollar General paycheck', receiptName:'', hasPhoto:false},
        {id:'p7', type:'spending', date:'2026-09-22', who:'Mitch', category:'Deleted Cat', amountCents:500, note:'Pet Supermarket', receiptName:'', hasPhoto:false}
      ];
      const model = HM.trainLearner(pulled, cats, {});
      const nl = String.fromCharCode(10);
      const s = (t) => HM.suggestCategory(t, cats, { learned: {}, model: model });
      const dg = s(a.dg);
      const pets = s('PET SUPERMARKET 0112' + nl + 'BLUE BUFFALO 30LB 54.99' + nl + 'TOTAL 58.84');
      const unseen = s('JOES TACKLE SHOP' + nl + 'TOTAL 19.00');
      const scanned = HM.trainLearner([{id:'x1', type:'spending', category:'Pets', amountCents:2000, note:'Tractor Supply'}], cats, { scanTokens: { x1: 'kibble|dog treats|kibble dog' } });
      const items = HM.suggestCategory('FARM STORE 22' + nl + 'KIBBLE DOG 40LB 39.99' + nl + 'TOTAL 39.99', cats, { learned: {}, model: scanned });
      const fixed = HM.trainLearner([], cats, { fixes: [{ t: 'family dollar|family|dollar', c: 'Household', from: 'Groceries' }] });
      const fix = HM.suggestCategory('FAMILY DOLLAR #9' + nl + 'TOTAL 7.00', cats, { learned: {}, model: fixed });
      const noModel = HM.suggestCategory(a.dg, cats, { learned: {} });
      return { dg: dg && dg.category, dgSource: dg && dg.source, pets: pets && pets.category, unseen: unseen ? unseen.category : null,
               items: items && items.category, fix: fix && fix.category, noModel: noModel ? noModel.category : null,
               ignoredDeleted: !Object.keys(model.cats).includes('Deleted Cat') };
    }""", {"d": DEFAULT, "dg": DOLLAR_GENERAL})
    check("learner dollar general -> Household", [learn["dg"], learn["dgSource"]], ["Household", "learned"])
    check("learner pet supermarket -> Pets", learn["pets"], "Pets")
    check("learner unseen store stays unsure", learn["unseen"], None)
    check("learner uses receipt item words", learn["items"], "Pets")
    check("learner uses corrections", learn["fix"], "Household")
    check("without learner dollar general unsure", learn["noModel"], None)
    check("learner ignores categories not in list", learn["ignoredDeleted"], True)


def e2e(browser):
    ctx = browser.new_context(viewport={"width": 412, "height": 915})
    google = []
    ctx.route("**/*script.google.com/**", lambda route: route.abort())
    ctx.on("request", lambda req: google.append(req.url) if "google.com" in req.url else None)
    ctx.add_init_script(STUB_OCR)
    ctx.add_init_script("""
      if (!localStorage.getItem('hm.scan.seeded')) {
        localStorage.setItem('hm.scan.seeded', '1');
        localStorage.setItem('householdMoney.categories.v1', JSON.stringify(%s));
      }
    """ % json.dumps(DEFAULT + ["Gas", "Household"]))
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(URL, wait_until="domcontentloaded")
    page.wait_for_function("() => window.HM && document.querySelector('#week-in')")
    today = page.evaluate("() => HM.todayYMD()")

    def scan(text):
        page.evaluate("(t) => { window.__ocrText = t; }", text)
        page.locator("#go-spend").click()
        page.wait_for_selector("#view-spend:not([hidden])")
        page.locator("#spend-gallery").set_input_files(str(PNG))
        page.wait_for_function("() => { const h = document.querySelector('#receipt-hint'); return h && !h.hidden && !/Reading/.test(h.textContent); }")
        return page.evaluate("""() => {
          const c = document.querySelector('#cat-chips input[name=category]:checked');
          return { amount: document.querySelector('#spend-amount').value, date: document.querySelector('#spend-date').value,
                   note: document.querySelector('#spend-note').value, cat: c ? c.value : null,
                   hint: document.querySelector('#receipt-hint').textContent };
        }""")

    def save():
        page.locator("#spend-save").click()
        page.wait_for_function("() => location.hash === '#/' || location.hash === ''")

    # 1. Gas receipt fills amount, store, date, and the Gas category.
    r = scan(SHEETZ_OCR)
    print("SCAN1", r)
    check("e2e gas amount", r["amount"], "38.12")
    check("e2e gas date", r["date"], "2026-10-06")
    check("e2e gas note", r["note"], "SHEETZ #0412")
    check("e2e gas category", r["cat"], "Gas")
    check("e2e gas hint", ("Date from the receipt" in r["hint"], "This looks like Gas" in r["hint"]), (True, True))
    save()
    e = page.evaluate("() => JSON.parse(localStorage.getItem('householdMoney.entries.v1')).find(x => x.note === 'SHEETZ #0412')")
    check("e2e gas saved", [e["date"], e["category"], e["amountCents"]], ["2026-10-06", "Gas", 3812])
    tok = page.evaluate("(id) => (JSON.parse(localStorage.getItem('hm.scanTokens.v1') || '{}')[id] || '')", e["id"])
    check("e2e scan words kept for learning", "unleaded" in tok, True)

    # 2. Unknown store: no date, asks for category; user picks Household.
    r = scan("DOLLAR GENERAL #04512\nBLEACH 64OZ 3.50\nPAPER TOWELS 6PK 7.95\nTOTAL 11.45")
    print("SCAN2", r)
    check("e2e unknown asks", r["cat"], None)
    check("e2e no date -> today", r["date"], today)
    check("e2e no date hint", "No date found" in r["hint"] and "Which category is this?" in r["hint"], True)
    page.locator("#cat-chips label.chip", has_text="Household").click()
    save()

    # 3. Same store again, with this phone's store memory wiped (like the other phone): learner picks Household.
    page.evaluate("() => localStorage.setItem('hm.learned.v1', '{}')")
    r = scan(DOLLAR_GENERAL)
    print("SCAN3", r)
    check("e2e learner from entries", r["cat"], "Household")
    check("e2e learner date", r["date"], "2026-10-06")
    page.evaluate("() => { location.hash = '#/'; }")
    page.wait_for_function("() => location.hash === '#/' || location.hash === ''")

    # 4. Correction: guess Groceries for a Walmart grocery receipt, user changes to Online.
    r = scan(WALMART)
    print("SCAN4", r)
    check("e2e walmart guess", r["cat"], "Groceries")
    check("e2e walmart date", r["date"], "2026-10-07")
    page.locator("#cat-chips label.chip", has_text="Online").click()
    save()
    fixes = page.evaluate("() => JSON.parse(localStorage.getItem('hm.catFixes.v1') || '[]')")
    learned = page.evaluate("() => JSON.parse(localStorage.getItem('hm.learned.v1') || '{}')")
    check("e2e correction recorded", [fixes[-1]["from"], fixes[-1]["c"]] if fixes else None, ["Groceries", "Online"])
    check("e2e correction in store memory", learned.get("walmart"), "Online")
    r = scan(WALMART)
    check("e2e corrected store now guessed Online", r["cat"], "Online")

    # 5. A date the user typed is not overwritten.
    page.evaluate("() => { location.hash = '#/'; }")
    page.wait_for_function("() => location.hash === '#/'")
    page.locator("#go-spend").click()
    page.wait_for_selector("#view-spend:not([hidden])")
    page.locator("#spend-date").fill("2026-09-01")
    page.evaluate("(t) => { window.__ocrText = t; }", SHELL)
    page.locator("#spend-gallery").set_input_files(str(PNG))
    page.wait_for_function("() => { const h = document.querySelector('#receipt-hint'); return h && !h.hidden && !/Reading/.test(h.textContent); }")
    check("e2e typed date kept", page.locator("#spend-date").input_value(), "2026-09-01")

    check("e2e no page errors", errors, [])
    check("e2e Google never contacted", google, [])
    ctx.close()


def main():
    tiny_png(PNG)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        ctx = browser.new_context()
        ctx.route("**/*script.google.com/**", lambda route: route.abort())
        page = ctx.new_page()
        page.goto(URL, wait_until="domcontentloaded")
        page.wait_for_function("() => window.HM && HM.extractDate")
        unit_tests(page)
        ctx.close()
        e2e(browser)
        browser.close()
    print("FAILED: " + ", ".join(FAILS) if FAILS else "PASS")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
