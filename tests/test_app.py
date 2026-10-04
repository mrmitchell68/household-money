"""Household Money UI check. Uses a throwaway browser profile. Does not seed the app."""
import json
import re
import struct
import zlib
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
URL = "http://127.0.0.1:8788/"
PNG = Path("/tmp/hm-tiny-receipt.png")
BACKUP = Path("/tmp/hm-backup.json")
CATS = ["Tithes", "Mortgage", "Utilities", "Car Payment", "Groceries", "Phones", "Cards", "Medical", "Online"]


def tiny_png(path: Path) -> None:
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    # 2x2 RGB
    raw = b"".join(b"\x00" + b"\xff\x00\x00" * 2 for _ in range(2))
    ihdr = struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def text(page, sel):
    return page.locator(sel).inner_text().strip()


def main():
    html = (ROOT / "index.html").read_text()
    for cat in CATS:
        assert cat in html, cat
    for label in ("Add income", "Add spending", "Add savings", "Put aside", "Take out", "Saved this month", "Total saved", "Carried in from last month", "Left (rolls to next month)", "Shared Google Sheet", "Save photo", "eBay, Amazon, Facebook Marketplace, Walmart, and other online buys."):
        assert label in html, label
    assert "does not write to Google Sheets" not in html
    assert "Income, spending, and categories saved on either phone show up on the other phone when each app is opened online, because both read the shared sheet." in html
    assert "new income and spending are also added to the shared Google Sheet, under the category you picked" in html
    assert "the sheet stores the receipt file name" in html
    assert "sent when you open the app online again" in html
    assert "this phone remembers which category you used for that store" in html
    assert "hm-v1.7.3" in (ROOT / "sw.js").read_text()
    assert "Remind me each month" in html
    assert 'id="spend-remind"' in html
    assert "Save reminder" in html
    assert 'id="reminder-status"' in html
    assert "Day of the month has to be from 1 to 31." in html
    day_input = re.search(r'<input id="reminder-day"[^>]*>', html).group(0)
    time_input = re.search(r'<input id="reminder-time"[^>]*>', html).group(0)
    assert "required" not in day_input
    assert "required" not in time_input
    assert "Not this time" in html
    assert "Not saved until you tap Approve" in html
    tiny_png(PNG)

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        page = browser.new_page(viewport={"width": 412, "height": 915})
        page.route("**/*script.google.com/**", lambda route: route.abort())
        page.on("pageerror", lambda err: print("PAGEERROR", err))
        page.goto(URL, wait_until="domcontentloaded")
        page.wait_for_function("() => window.HM && document.querySelector('#week-in')")
        empty = {k: text(page, "#" + k) for k in ("week-in", "week-out", "week-left", "month-in", "month-out", "month-left")}
        print("EMPTY", empty)
        assert empty == {k: "$0.00" for k in empty}

        page.locator("#go-income").click()
        page.locator("#who-chips label.chip", has_text="Mitch").click()
        page.locator("#income-amount").fill("100")
        page.locator("#income-save").click()
        page.wait_for_function("() => location.hash === '#/' && document.querySelector('#week-in').textContent === '$100.00'")

        page.locator("#go-spend").click()
        page.locator("label.chip", has_text="Groceries").click()
        page.locator("#spend-amount").fill("25")
        page.locator("#spend-gallery").set_input_files(str(PNG))
        page.wait_for_selector("#photo-preview-wrap:not([hidden])")
        fname = text(page, "#photo-filename")
        print("RECEIPT_NAME", fname)
        assert fname.startswith("receipt-") and fname.endswith(".jpg")
        page.locator("#spend-save").click()
        page.wait_for_function("() => document.querySelector('#week-out').textContent === '$25.00'")

        totals = {k: text(page, "#" + k) for k in ("week-in", "week-out", "week-left", "month-in", "month-out", "month-left")}
        print("BEFORE_RELOAD", totals)
        assert totals["week-in"] == "$100.00"
        assert totals["week-out"] == "$25.00"
        assert totals["week-left"] == "$75.00"
        assert totals["month-in"] == "$100.00"
        assert totals["month-out"] == "$25.00"
        assert totals["month-left"] == "$75.00"
        roll_ui = {k: text(page, "#" + k) for k in ("saved-month", "saved-total", "carried-in", "left-rolls")}
        print("ROLL_UI", roll_ui)
        assert roll_ui["saved-month"] == "$0.00"
        assert roll_ui["saved-total"] == "$0.00"
        assert roll_ui["carried-in"] == "$0.00"
        assert roll_ui["left-rolls"] == "$75.00"
        assert "Mitch income" in page.locator("#recent").inner_text()
        assert "Groceries" in page.locator("#recent").inner_text()
        assert fname in page.locator("#recent").inner_text()

        page.reload(wait_until="domcontentloaded")
        page.wait_for_function("() => window.HM && document.querySelector('#week-left').textContent === '$75.00'")
        totals2 = {k: text(page, "#" + k) for k in ("week-in", "week-out", "week-left", "month-in", "month-out", "month-left")}
        print("AFTER_RELOAD", totals2)
        assert totals2 == totals
        stored = page.evaluate("""() => {
          const entries = JSON.parse(localStorage.getItem('householdMoney.entries.v1'));
          const spend = entries.find(e => e.type === 'spending');
          return new Promise((resolve, reject) => {
            const req = indexedDB.open('household-money');
            req.onerror = () => reject(req.error);
            req.onsuccess = () => {
              const db = req.result;
              const g = db.transaction('photos').objectStore('photos').get(spend.id);
              g.onsuccess = () => resolve({
                count: entries.length,
                receiptName: spend.receiptName,
                who: entries.find(e => e.type === 'income').who,
                income: entries.find(e => e.type === 'income').amountCents,
                spend: spend.amountCents,
                category: spend.category,
                photoBytes: g.result && g.result.blob ? g.result.blob.size : 0,
                photoType: g.result && g.result.blob ? g.result.blob.type : ''
              });
              g.onerror = () => reject(g.error);
            };
          });
        }""")
        print("STORED", stored)
        assert stored["count"] == 2
        assert stored["who"] == "Mitch"
        assert stored["income"] == 10000
        assert stored["spend"] == 2500
        assert stored["category"] == "Groceries"
        assert stored["photoBytes"] > 0
        assert stored["photoType"] == "image/jpeg"
        assert stored["receiptName"] == fname

        page.locator("a[href='#/settings']").click()
        with page.expect_download() as dl_info:
            page.locator("#export-backup").click()
        download = dl_info.value
        download.save_as(str(BACKUP))
        backup = json.loads(BACKUP.read_text())
        print("BACKUP", {"entries": len(backup["entries"]), "photosIncluded": backup["photosIncluded"], "photos": len(backup["photos"]), "note": backup["photoNote"]})
        assert backup["photosIncluded"] is True
        assert len(backup["entries"]) == 2
        assert len(backup["photos"]) == 1

        page.evaluate("() => localStorage.removeItem('householdMoney.entries.v1')")
        page.reload(wait_until="domcontentloaded")
        page.wait_for_function("() => document.querySelector('#week-in').textContent === '$0.00'")
        page.locator("a[href='#/settings']").click()
        page.locator("#import-file").set_input_files(str(BACKUP))
        page.wait_for_function("() => document.querySelector('#settings-status').textContent.includes('Added 2')")
        print("IMPORT1", text(page, "#settings-status"))
        page.locator("a.brand").click()
        page.wait_for_function("() => document.querySelector('#week-left').textContent === '$75.00'")
        page.locator("a[href='#/settings']").click()
        page.locator("#import-file").set_input_files(str(BACKUP))
        page.wait_for_function("() => document.querySelector('#settings-status').textContent.includes('Skipped 2')")
        print("IMPORT2", text(page, "#settings-status"))
        count = page.evaluate("() => JSON.parse(localStorage.getItem('householdMoney.entries.v1')).length")
        assert count == 2

        page.locator("a[href='#/categories']").click()
        page.once("dialog", lambda d: d.accept())
        page.locator("button[aria-label='Delete category Groceries']").click()
        page.locator("a.brand").click()
        page.wait_for_selector("#recent")
        recent = page.locator("#recent").inner_text()
        print("AFTER_CAT_DELETE_HAS_GROCERIES", "Groceries" in recent)
        assert "Groceries" in recent
        page.locator("#go-spend").click()
        assert page.locator("#cat-chips input[value='Groceries']").count() == 0
        page.locator("#spend-new-cat").fill("Pet care")
        page.locator("#spend-add-cat").click()
        assert page.locator("#cat-chips input[value='Pet care']").is_checked()

        logic = page.evaluate("""() => {
          const rows = [
            {type:'income', date:'2026-09-26', amountCents:5000},
            {type:'spending', date:'2026-10-03', amountCents:2500},
            {type:'income', date:'2026-10-01', amountCents:10000}
          ];
          const today = new Date(2026, 9, 3);
          const start = HM.weekStartYMD(today);
          const month = HM.monthStartYMD(today);
          return {
            weekStart: start,
            monthStart: month,
            week: HM.summarize(rows, start, '2026-10-03'),
            month: HM.summarize(rows, month, '2026-10-03'),
            zero: HM.formatUSD(0),
            bad: HM.parseCents('0'),
            ok: HM.parseCents('100.00')
          };
        }""")
        print("LOGIC", logic)
        assert logic["weekStart"] == "2026-09-28"
        assert logic["monthStart"] == "2026-10-01"
        assert logic["week"]["moneyIn"] == 10000
        assert logic["week"]["moneyOut"] == 2500
        assert logic["week"]["left"] == 7500
        assert logic["month"]["moneyIn"] == 10000
        assert logic["month"]["left"] == 7500
        assert logic["zero"] == "$0.00"
        assert logic["bad"] is None
        assert logic["ok"] == 10000

        guess = page.evaluate("""() => {
          const nl = String.fromCharCode(10);
          return {
            kind: typeof HM.guessCategory,
            walmart: HM.guessCategory('WALMART SUPERCENTER' + nl + 'TOTAL 12.34', HM.DEFAULT_CATEGORIES, {}),
            unknown: HM.guessCategory('mystery booth downtown', HM.DEFAULT_CATEGORIES, {}),
            learned: HM.guessCategory('WALMART', HM.DEFAULT_CATEGORIES, {walmart: 'Groceries'}),
            missing: HM.guessCategory('WALMART', ['Groceries'], {}),
            total: HM.extractAmount('SUBTOTAL 10.00' + nl + 'TAX 0.80' + nl + 'TOTAL 10.80'),
            due: HM.extractAmount('AMOUNT DUE $8.50'),
            balance: HM.extractAmount('SUBTOTAL 4.00' + nl + 'BALANCE 4.25')
          };
        }""")
        print("GUESS", guess)
        assert guess["kind"] == "function"
        assert guess["walmart"] == "Online"
        assert guess["unknown"] is None
        assert guess["learned"] == "Groceries"
        assert guess["missing"] is None
        assert guess["total"] == "10.80"
        assert guess["due"] == "8.50"
        assert guess["balance"] == "4.25"

        cats = page.evaluate("""() => {
          const a = HM.mergeCategoryLists(["Tithes", "Pets"], ["Tithes", "Amazon"], [], []);
          const b = HM.mergeCategoryLists(["Tithes", "Pets"], ["Tithes"], ["Tithes", "Pets"], []);
          const c = HM.mergeCategoryLists(["Tithes"], ["Tithes", "Pets"], ["Tithes"], ["Pets"]);
          return { a: a, b: b, c: c };
        }""")
        print("CATS", cats)
        assert cats["a"]["local"] == ["Tithes", "Pets", "Amazon"]
        assert cats["a"]["toAdd"] == ["Pets"]
        assert cats["b"]["local"] == ["Tithes"]
        assert "Pets" not in cats["b"]["toAdd"]
        assert cats["c"]["local"] == ["Tithes"]
        assert "Pets" in cats["c"]["toDeleteRetry"]

        roll = page.evaluate("""() => {
          const rows = [
            {type:'income', date:'2026-09-15', amountCents:10000},
            {type:'spending', date:'2026-09-20', amountCents:4000},
            {type:'savings', date:'2026-09-21', amountCents:1000},
            {type:'savings', date:'2026-08-01', amountCents:2000},
            {type:'income', date:'2026-10-01', amountCents:5000},
            {type:'spending', date:'2026-10-02', amountCents:2000},
            {type:'savings', date:'2026-10-03', amountCents:1500},
            {type:'savings', date:'2026-10-03', amountCents:-500},
            {type:'spending', date:'2026-10-03', amountCents:100, category:'Groceries'}
          ];
          const roll = HM.savingsAndLeftover(rows, '2026-10-01', '2026-10-03');
          const month = HM.summarize(rows, '2026-10-01', '2026-10-03');
          const neg = HM.savingsAndLeftover([
            {type:'spending', date:'2026-09-02', amountCents:5000},
            {type:'income', date:'2026-10-02', amountCents:1000},
            {type:'savings', date:'2026-10-02', amountCents:-200}
          ], '2026-10-01', '2026-10-03');
          return { roll: roll, monthOut: month.moneyOut, monthLeft: month.left, neg: neg };
        }""")
        print("ROLL", roll)
        assert roll["roll"]["savedThisMonth"] == 1000
        assert roll["roll"]["totalSaved"] == 4000
        assert roll["roll"]["carriedIn"] == 3000
        assert roll["roll"]["monthLeftover"] == 1900
        assert roll["roll"]["leftNow"] == 4900
        assert roll["monthOut"] == 2100
        assert roll["monthLeft"] == 2900
        assert roll["neg"]["carriedIn"] == -5000
        assert roll["neg"]["savedThisMonth"] == -200
        assert roll["neg"]["monthLeftover"] == 1200
        assert roll["neg"]["leftNow"] == -3800
        assert roll["neg"]["totalSaved"] == -200

        occ = page.evaluate("""() => {
          const now = new Date(2026, 9, 4, 15, 0, 0);
          const made = {
            id: 'r1', category: 'Mortgage', dayOfMonth: 1, daysBefore: 7, time: '09:00',
            active: true, createdYMD: '2026-10-04', handled: {}, amountCents: 10000
          };
          const old = HM.reminderOccurrences(Object.assign({}, made, { createdYMD: '' }), now);
          const fresh = HM.reminderOccurrences(made, now);
          const future = HM.reminderOccurrences(Object.assign({}, made, { dayOfMonth: 20, daysBefore: 7, time: '09:00' }), now);
          return {
            oldMonths: old.map(o => o.monthKey),
            freshMonths: fresh.map(o => o.monthKey),
            future: future.length,
            text: HM.ordinalDay(1)
          };
        }""")
        print("REMIND_LOGIC", occ)
        assert occ["text"] == "1st"
        assert "2026-09" in occ["oldMonths"]
        assert "2026-10" in occ["oldMonths"]
        assert occ["freshMonths"] == ["2026-10"]
        assert occ["future"] == 0

        page.evaluate("""() => {
          if (!window.Notification) return;
          try {
            Object.defineProperty(Notification, 'permission', { configurable: true, get: function () { return 'denied'; } });
          } catch (e) {}
          Notification.requestPermission = function () { return Promise.resolve('denied'); };
        }""")
        before_n = page.evaluate("() => JSON.parse(localStorage.getItem('householdMoney.entries.v1')).length")
        page.locator("a[href='#/reminders']").click()
        page.wait_for_selector("#reminder-form")
        page.locator("#rem-cat-chips label.chip", has_text="Mortgage").click()
        page.locator("#reminder-amount").fill("80")
        day = page.evaluate("() => String(new Date().getDate())")
        page.locator("#reminder-day").fill(day)
        page.locator("#reminder-days label.chip", has_text="7 days").click()
        page.locator("#reminder-time").fill("00:00")
        page.locator("#reminder-note").fill("bill reminder test")
        page.locator("#reminder-save").click()
        page.wait_for_function("() => document.querySelector('#reminder-list').innerText.includes('Mortgage')")
        assert text(page, "#reminder-status") == "Saved."
        kept = page.evaluate("""() => {
          const before = JSON.parse(localStorage.getItem('hm.reminders.v1'));
          const saved = before.find(r => r.category === 'Mortgage' && r.note === 'bill reminder test');
          if (!saved || saved.synced) return { ok: false, reason: 'not saved unsynced' };
          HM.mergePulledReminders([]);
          const afterEmpty = JSON.parse(localStorage.getItem('hm.reminders.v1'));
          const still = afterEmpty.find(r => r.id === saved.id);
          const ghost = {
            id: 'ghost-confirmed', category: 'Utilities', dayOfMonth: 2, daysBefore: 1,
            time: '09:00', active: true, amountCents: 100, note: 'confirmed ghost',
            who: '', handled: {}, createdYMD: '2026-10-01'
          };
          HM.mergePulledReminders([ghost]);
          const withGhost = JSON.parse(localStorage.getItem('hm.reminders.v1'));
          const ghostRow = withGhost.find(r => r.id === 'ghost-confirmed');
          HM.mergePulledReminders([]);
          const end = JSON.parse(localStorage.getItem('hm.reminders.v1'));
          return {
            still: !!still && still.synced === false,
            listHasMortgage: document.querySelector('#reminder-list').innerText.includes('Mortgage'),
            ghostSynced: !!(ghostRow && ghostRow.synced === true),
            ghostGone: !end.some(r => r.id === 'ghost-confirmed'),
            mortgageKept: end.some(r => r.id === saved.id && r.synced === false),
            listAfter: document.querySelector('#reminder-list').innerText.includes('Mortgage') && !document.querySelector('#reminder-list').innerText.includes('Utilities')
          };
        }""")
        print("REMINDER_EMPTY_PULL", kept)
        assert kept["still"] is True
        assert kept["listHasMortgage"] is True
        assert kept["ghostSynced"] is True
        assert kept["ghostGone"] is True
        assert kept["mortgageKept"] is True
        assert kept["listAfter"] is True
        page.locator("#reminder-note").fill("bill reminder test")
        page.locator("#reminder-note").fill("")
        assert text(page, "#reminder-status") == ""
        mid = page.evaluate("""() => {
          const entries = JSON.parse(localStorage.getItem('householdMoney.entries.v1'));
          const queue = JSON.parse(localStorage.getItem('hm.syncQueue') || '[]');
          return {
            count: entries.length,
            notes: entries.map(e => e.note || ''),
            queued: queue.some(item => item && (item.action === 'saveReminder' || item.kind === 'Spending'))
          };
        }""")
        print("BEFORE_APPROVE", mid)
        assert mid["count"] == before_n
        assert "bill reminder test" not in mid["notes"]
        assert mid["queued"] is False
        page.locator("a.brand").click()
        page.wait_for_selector("#due-list .due-card")
        assert "Mortgage" in page.locator("#due-list").inner_text()
        still = page.evaluate("() => JSON.parse(localStorage.getItem('householdMoney.entries.v1')).length")
        assert still == before_n
        page.locator("#due-list .due-card", has_text="Mortgage").locator("button", has_text="Approve").click()
        page.wait_for_selector("#approve-date")
        default_date = page.locator("#approve-date").input_value()
        print("DEFAULT_DUE", default_date)
        assert default_date.endswith("-" + day.zfill(2)) or default_date[8:10] == day.zfill(2)
        page.locator("#approve-date").fill("2026-10-20")
        page.locator("#approve-amount").fill("81.50")
        untouched = page.evaluate("""() => JSON.parse(localStorage.getItem('householdMoney.entries.v1')).filter(e => e.note === 'bill reminder test').length""")
        assert untouched == 0
        page.locator("#approve-save").click()
        page.wait_for_function("() => location.hash === '#/' && JSON.parse(localStorage.getItem('householdMoney.entries.v1')).some(e => e.note === 'bill reminder test')")
        approved = page.evaluate("""() => {
          const entries = JSON.parse(localStorage.getItem('householdMoney.entries.v1'));
          const hit = entries.find(e => e.note === 'bill reminder test');
          return { count: entries.length, hit: hit };
        }""")
        print("APPROVED", approved)
        assert approved["count"] == before_n + 1
        assert approved["hit"]["type"] == "spending"
        assert approved["hit"]["category"] == "Mortgage"
        assert approved["hit"]["date"] == "2026-10-20"
        assert approved["hit"]["amountCents"] == 8150

        page.locator("a[href='#/reminders']").click()
        page.wait_for_selector("#reminder-form")
        page.locator("#rem-cat-chips label.chip", has_text="Car Payment").click()
        page.locator("#reminder-amount").fill("40")
        page.locator("#reminder-day").fill(day)
        page.locator("#reminder-time").fill("00:00")
        page.locator("#reminder-note").fill("skip me")
        page.locator("#reminder-save").click()
        page.wait_for_function("() => document.querySelector('#reminder-list').innerText.includes('Car Payment')")
        page.locator("a.brand").click()
        page.locator("#due-list .due-card", has_text="Car Payment").locator("button", has_text="Not this time").click()
        page.wait_for_function("() => !document.querySelector('#due-list .due-card') || !document.querySelector('#due-list').innerText.includes('Car Payment')")
        skipped = page.evaluate("""() => {
          const entries = JSON.parse(localStorage.getItem('householdMoney.entries.v1'));
          const reminders = JSON.parse(localStorage.getItem('hm.reminders.v1'));
          const car = reminders.find(r => r.category === 'Car Payment');
          const month = new Date().getFullYear() + '-' + String(new Date().getMonth() + 1).padStart(2, '0');
          return {
            count: entries.length,
            skipNotes: entries.filter(e => e.note === 'skip me').length,
            handled: car && car.handled ? car.handled[month] : ''
          };
        }""")
        print("SKIPPED", skipped)
        assert skipped["count"] == before_n + 1
        assert skipped["skipNotes"] == 0
        assert skipped["handled"] == "skipped"

        posts = []
        page.on("request", lambda req: posts.append(req.url) if "script.google.com" in req.url or "google.com/macros" in req.url else None)
        page.locator("#go-spend").click()
        page.wait_for_selector("#spend-form")
        assert page.locator("#spend-remind-fields").is_hidden()
        page.locator("#spend-date").fill("2026-10-01")
        page.locator("#cat-chips label.chip", has_text="Mortgage").click()
        page.locator("#spend-amount").fill("1200")
        page.locator("#spend-note").fill("october mortgage")
        page.locator("#spend-remind").check()
        page.wait_for_selector("#spend-remind-fields:not([hidden])")
        assert page.locator('#spend-reminder-days input[value="7"]').is_checked()
        page.locator("#spend-remind-time").fill("")
        page.locator("#spend-save").click()
        page.wait_for_function("() => location.hash === '#/' && document.querySelector('#home-status').textContent.includes('Monthly reminder saved.')")
        kept_spend = page.evaluate("""() => {
          const entries = JSON.parse(localStorage.getItem('householdMoney.entries.v1'));
          const spend = entries.find(e => e.note === 'october mortgage');
          const before = JSON.parse(localStorage.getItem('hm.reminders.v1'));
          const saved = before.find(r => r.category === 'Mortgage' && r.dayOfMonth === 1 && r.note === 'october mortgage');
          if (!spend || !saved || saved.synced) return { ok: false, spend: !!spend, saved: saved || null };
          HM.mergePulledReminders([]);
          const afterEmpty = JSON.parse(localStorage.getItem('hm.reminders.v1'));
          const still = afterEmpty.find(r => r.id === saved.id);
          const queue = JSON.parse(localStorage.getItem('hm.syncQueue') || '[]');
          return {
            ok: true,
            spendDate: spend.date,
            spendCat: spend.category,
            spendCents: spend.amountCents,
            spendSynced: !!spend.synced,
            day: still && still.dayOfMonth,
            daysBefore: still && still.daysBefore,
            time: still && still.time,
            amount: still && still.amountCents,
            note: still && still.note,
            synced: still && still.synced,
            kept: !!still,
            queued: queue.some(item => item && (item.id === saved.id || item.id === spend.id || item.note === 'october mortgage'))
          };
        }""")
        print("SPEND_REMINDER", kept_spend, "POSTS", posts)
        assert posts == []
        assert kept_spend["ok"] is True
        assert kept_spend["spendDate"] == "2026-10-01"
        assert kept_spend["spendCat"] == "Mortgage"
        assert kept_spend["spendCents"] == 120000
        assert kept_spend["spendSynced"] is not True
        assert kept_spend["kept"] is True
        assert kept_spend["day"] == 1
        assert kept_spend["daysBefore"] == 7
        assert kept_spend["time"] == "09:00"
        assert kept_spend["amount"] == 120000
        assert kept_spend["note"] == "october mortgage"
        assert kept_spend["synced"] is False
        assert kept_spend["queued"] is False
        browser.close()
    print("PASS")


if __name__ == "__main__":
    main()
