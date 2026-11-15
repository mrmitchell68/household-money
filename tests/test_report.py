"""Spending report UI, pie chart, and print-media layout (hm-v1.12.1). System Chrome; Google is never contacted."""
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
URL = "http://127.0.0.1:8788/"
SHOT = Path("/workspace/hm-report-print-preview.png")

ENTRIES = [
    {"id": "a", "type": "spending", "date": "2026-10-31", "category": "Gas", "amountCents": 4000, "note": "Exxon", "createdAt": "2026-10-31T12:00:00.000Z"},
    {"id": "b", "type": "spending", "date": "2026-11-01", "category": "Groceries", "amountCents": 8000, "note": "Food Lion", "createdAt": "2026-11-01T12:00:00.000Z"},
    {"id": "c", "type": "spending", "date": "2026-11-10", "category": "Eating Out", "amountCents": 5500, "note": "Dragon Place", "createdAt": "2026-11-10T12:00:00.000Z"},
    {"id": "d", "type": "spending", "date": "2026-11-15", "category": "Groceries", "amountCents": 2000, "note": "ALDI", "createdAt": "2026-11-15T12:00:00.000Z"},
    {"id": "e", "type": "income", "date": "2026-11-11", "who": "Mitch", "amountCents": 84258, "note": "Paycheck", "createdAt": "2026-11-11T12:00:00.000Z"},
    {"id": "f", "type": "savings", "date": "2026-11-06", "who": "Mitch", "amountCents": 3500, "note": "Set aside", "createdAt": "2026-11-06T12:00:00.000Z"},
    {"id": "g", "type": "spending", "date": "2026-11-16", "category": "Gas", "amountCents": 1000, "note": "Shell", "createdAt": "2026-11-16T12:00:00.000Z"},
]


def text(page, sel):
    return page.locator(sel).inner_text().strip()


def main():
    html = (ROOT / "index.html").read_text()
    sw = (ROOT / "sw.js").read_text()
    assert "hm-v1.12.1" in sw
    assert 'VERSION = "hm-v1.12.1"' in sw
    assert "Save / Print PDF" in html
    assert 'href="#/report"' in html
    assert "@media print" in html

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        page = browser.new_page(viewport={"width": 412, "height": 915})
        page.route("**/*script.google.com/**", lambda route: route.abort())
        google_hits = []
        page.on("request", lambda req: google_hits.append(req.url) if "script.google.com" in req.url or "google.com/macros" in req.url else None)
        page.goto(URL, wait_until="domcontentloaded")
        page.wait_for_function("() => window.HM && window.HM.spendingReport")
        page.evaluate(
            """(entries) => {
              localStorage.setItem("householdMoney.entries.v1", JSON.stringify(entries));
            }""",
            ENTRIES,
        )
        page.goto(URL + "#/report", wait_until="domcontentloaded")
        page.reload(wait_until="domcontentloaded")
        page.wait_for_function("() => window.HM && document.querySelector('#view-report') && !document.querySelector('#view-report').hidden")
        page.locator("#report-start").fill("2026-11-01")
        page.locator("#report-end").fill("2026-11-15")
        page.wait_for_function("() => document.querySelector('#report-total') && document.querySelector('#report-total').textContent.indexOf('155.00') !== -1")
        assert text(page, "#report-total") == "$155.00"
        range_label = text(page, "#report-range-label")
        assert "2026" in range_label or "Nov" in range_label
        rows = page.locator("#report-cats tbody tr")
        assert rows.count() == 2
        assert "Groceries" in rows.nth(0).inner_text() and "$100.00" in rows.nth(0).inner_text() and "64.5%" in rows.nth(0).inner_text()
        assert "Eating Out" in rows.nth(1).inner_text() and "$55.00" in rows.nth(1).inner_text()
        pie_parts = page.locator("#report-pie path, #report-pie circle")
        assert pie_parts.count() >= 2
        legend = text(page, "#report-legend")
        assert "Groceries" in legend and "Eating Out" in legend
        presets = text(page, "#report-presets")
        assert "This week" in presets and "This month" in presets and "Last month" in presets
        assert "Trip Nov 10" in presets
        assert page.locator("#report-entries-wrap").evaluate("el => el.open") is True
        entries = page.locator("#report-entries tbody tr")
        assert entries.count() == 3
        assert "Food Lion" in entries.nth(0).inner_text()
        assert "Paycheck" not in page.locator("#report-entries").inner_text()

        page.locator('#report-entries tr[data-id="b"] button').click()
        assert text(page, "#report-total") == "$75.00"
        assert "1 item removed" in text(page, "#report-omit-line")
        assert "Restore all" in text(page, "#report-omit-line")
        cats = page.locator("#report-cats tbody tr")
        assert cats.count() == 2
        assert "Eating Out" in cats.nth(0).inner_text() and "$55.00" in cats.nth(0).inner_text()
        assert "Groceries" in cats.nth(1).inner_text() and "$20.00" in cats.nth(1).inner_text()
        assert "report-omitted" in (page.locator('#report-entries tr[data-id="b"]').get_attribute("class") or "")
        stored = page.evaluate("() => JSON.parse(localStorage.getItem('householdMoney.entries.v1'))")
        assert len(stored) == 7
        assert any(e["id"] == "b" and e["amountCents"] == 8000 for e in stored)
        month_out = page.evaluate("() => window.HM.summarize(JSON.parse(localStorage.getItem('householdMoney.entries.v1')), '2026-11-01', '2026-11-15').moneyOut")
        assert month_out == 15500

        page.locator("#report-cats tbody tr", has_text="Groceries").locator("button").click()
        assert text(page, "#report-total") == "$55.00"
        assert page.locator("#report-cats tbody tr").count() == 1
        assert "Eating Out" in text(page, "#report-cats")
        assert "2 items removed" in text(page, "#report-omit-line")
        assert page.locator("#report-pie circle").count() == 1
        assert "report-omitted" in (page.locator('#report-entries tr[data-id="d"]').get_attribute("class") or "")

        page.locator('#report-entries tr[data-id="d"] button').click()
        assert text(page, "#report-total") == "$75.00"
        assert "1 item removed" in text(page, "#report-omit-line")

        page.locator("#report-restore-all").click()
        assert text(page, "#report-total") == "$155.00"
        assert page.locator("#report-omit-line").evaluate("el => el.hidden") is True
        assert page.locator("#report-cats tbody tr").count() == 2

        page.locator('#report-entries tr[data-id="b"] button').click()
        assert text(page, "#report-total") == "$75.00"
        page.locator("#report-end").fill("2026-11-16")
        page.wait_for_function("() => document.querySelector('#report-total') && document.querySelector('#report-total').textContent.indexOf('165.00') !== -1")
        assert page.locator("#report-omit-line").evaluate("el => el.hidden") is True
        page.locator("#report-end").fill("2026-11-15")
        page.wait_for_function("() => document.querySelector('#report-total') && document.querySelector('#report-total').textContent.indexOf('155.00') !== -1")
        page.locator('#report-entries tr[data-id="b"] button').click()
        assert text(page, "#report-total") == "$75.00"

        printed = page.evaluate(
            """() => {
              window.__printed = false;
              window.print = function () { window.__printed = true; };
              document.getElementById("report-print").click();
              return window.__printed;
            }"""
        )
        assert printed is True

        page.emulate_media(media="print")
        assert page.locator("header.appbar").evaluate("el => getComputedStyle(el).display") == "none"
        assert page.locator("#report-print").evaluate("el => getComputedStyle(el).display") == "none"
        assert page.locator("#report-form").evaluate("el => getComputedStyle(el).display") == "none"
        assert page.locator("#report-omit-line").evaluate("el => getComputedStyle(el).display") == "none"
        assert page.locator('#report-entries tr[data-id="b"]').evaluate("el => getComputedStyle(el).display") == "none"
        assert page.locator(".report-omit-btn").first.evaluate("el => getComputedStyle(el).display") == "none"
        assert page.locator("#report-pie").evaluate("el => getComputedStyle(el).display") != "none"
        assert page.locator("#report-pie path, #report-pie circle").count() >= 1
        assert text(page, "#report-total") == "$75.00"
        assert page.locator("#report-total").is_visible()
        omit_shot = Path("/workspace/hm-report-omit-print-preview.png")
        omit_shot.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(omit_shot), full_page=True)
        print("SHOT", omit_shot, "bytes", omit_shot.stat().st_size)
        page.emulate_media(media="screen")
        print("GOOGLE", google_hits)
        assert google_hits == []
        browser.close()
    print("PASS")


if __name__ == "__main__":
    main()
