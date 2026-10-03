"""Household Money UI check. Uses a throwaway browser profile. Does not seed the app."""
import json
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
    for label in ("Add income", "Add spending", "Shared Google Sheet", "Save photo", "eBay, Amazon, Facebook Marketplace, Walmart, and other online buys."):
        assert label in html, label
    assert "does not write to Google Sheets" not in html
    assert "new income and spending are also added to the shared Google Sheet, under the category you picked" in html
    assert "the sheet stores the receipt file name" in html
    assert "sent when you open the app online again" in html
    tiny_png(PNG)

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:
            print("PLAYWRIGHT_BROWSER", exc)
            browser = p.chromium.launch(channel="chrome")
        page = browser.new_page(viewport={"width": 412, "height": 915})
        page.on("pageerror", lambda err: print("PAGEERROR", err))
        page.goto(URL, wait_until="domcontentloaded")
        page.wait_for_function("() => window.HM && document.querySelector('#week-in')")
        empty = {k: text(page, "#" + k) for k in ("week-in", "week-out", "week-left", "month-in", "month-out", "month-left")}
        print("EMPTY", empty)
        assert empty == {k: "$0.00" for k in empty}

        page.locator("#go-income").click()
        page.locator("label.chip", has_text="Mitch").click()
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
        assert logic["weekStart"] == "2026-09-27"
        assert logic["monthStart"] == "2026-10-01"
        assert logic["week"]["moneyIn"] == 10000
        assert logic["week"]["moneyOut"] == 2500
        assert logic["week"]["left"] == 7500
        assert logic["month"]["moneyIn"] == 10000
        assert logic["month"]["left"] == 7500
        assert logic["zero"] == "$0.00"
        assert logic["bad"] is None
        assert logic["ok"] == 10000
        browser.close()
    print("PASS")


if __name__ == "__main__":
    main()
