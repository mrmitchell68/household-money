"""Weekly tracker (Mon-Sun, rollover) check. System Chrome; Google is never contacted."""
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8788/"


def main():
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True)
        ctx = b.new_context()
        ctx.route("**/*script.google.com/**", lambda route: route.abort())
        page = ctx.new_page()
        page.goto(URL)
        page.wait_for_function("() => window.HM && HM.weeklyLedger")
        r = page.evaluate("""() => {
          const rows = [
            {type:'income', date:'2026-09-30', amountCents:10000},   // week Sep 28
            {type:'spending', date:'2026-10-04', amountCents:30000}, // Sunday, same week -> -200
            {type:'spending', date:'2026-10-05', amountCents:5000},  // Monday, next week
            {type:'income', date:'2026-10-11', amountCents:50000},   // Sunday
            {type:'savings', date:'2026-10-06', amountCents:9999},   // not counted
            {type:'spending', date:'2026-10-12', amountCents:1000}   // Monday week 3
          ];
          return {
            sunNight: HM.weekStartYMD(new Date(2026, 9, 4, 23, 59)),
            monMorning: HM.weekStartYMD(new Date(2026, 9, 5, 0, 1)),
            ledger: HM.weeklyLedger(rows, '2026-10-14'),
            empty: HM.weeklyLedger([], '2026-10-14'),
            month: HM.summarize(rows, '2026-10-01', '2026-10-31')
          };
        }""")
        print(r)
        assert r["sunNight"] == "2026-09-28" and r["monMorning"] == "2026-10-05"
        L = r["ledger"]
        assert [w["start"] for w in L] == ["2026-09-28", "2026-10-05", "2026-10-12"]
        assert L[0]["end"] == "2026-10-04"
        assert (L[0]["startBalance"], L[0]["moneyIn"], L[0]["moneyOut"], L[0]["endBalance"]) == (0, 10000, 30000, -20000)
        assert (L[1]["startBalance"], L[1]["moneyIn"], L[1]["moneyOut"], L[1]["endBalance"]) == (-20000, 50000, 5000, 25000)
        assert (L[2]["startBalance"], L[2]["moneyIn"], L[2]["moneyOut"], L[2]["endBalance"]) == (25000, 0, 1000, 24000)
        assert len(r["empty"]) == 1 and r["empty"][0]["startBalance"] == 0
        assert r["month"] == {"moneyIn": 50000, "moneyOut": 36000, "left": 14000}

        # UI with seeded entries and a fixed clock (Wed Oct 14 2026)
        page2 = ctx.new_page()
        page2.clock.set_fixed_time("2026-10-14T12:00:00")
        page2.add_init_script("""localStorage.setItem('__seed','1')""")
        page2.goto(URL)
        page2.wait_for_function("() => window.HM")
        key = "householdMoney.entries.v1"
        assert key, "entries key"
        import json
        seed = [
            {"id": "a", "type": "income", "who": "Mitch", "date": "2026-09-30", "amountCents": 10000, "createdAt": "2026-09-30T10:00:00Z"},
            {"id": "b", "type": "spending", "category": "Groceries", "date": "2026-10-04", "amountCents": 30000, "createdAt": "2026-10-04T10:00:00Z"},
            {"id": "c", "type": "spending", "category": "Groceries", "date": "2026-10-05", "amountCents": 5000, "createdAt": "2026-10-05T10:00:00Z"},
            {"id": "d", "type": "income", "who": "Tonya", "date": "2026-10-11", "amountCents": 50000, "createdAt": "2026-10-11T10:00:00Z"},
            {"id": "e", "type": "spending", "category": "Groceries", "date": "2026-10-12", "amountCents": 1000, "createdAt": "2026-10-12T10:00:00Z"},
        ]
        page2.evaluate("([k, v]) => localStorage.setItem(k, v)", [key, json.dumps(seed)])
        page2.reload()
        page2.wait_for_function("() => document.querySelector('#week-end').textContent === '$240.00'")
        t = lambda s: page2.locator(s).inner_text().strip()
        assert t("#week-start") == "$250.00" and t("#week-in") == "$0.00" and t("#week-out") == "$10.00"
        assert "Mon, Oct 12" in t("#week-range") and "Sun, Oct 18" in t("#week-range"), t("#week-range")
        assert page2.locator("#week-next").is_disabled()
        month_before = (t("#month-in"), t("#month-out"), t("#month-left"))
        page2.locator("#week-prev").click()
        page2.locator("#week-prev").click()
        assert t("#week-start") == "$0.00" and t("#week-end") == "-$200.00"
        assert "neg" in page2.locator("#week-end").get_attribute("class")
        assert page2.locator("#week-prev").is_disabled()
        page2.locator("#week-next").click()
        assert t("#week-start") == "-$200.00" and t("#week-end") == "$250.00"
        assert (t("#month-in"), t("#month-out"), t("#month-left")) == month_before == ("$500.00", "$360.00", "$140.00"), month_before
        assert page2.locator("#week-past .week-row").count() == 4
        page2.set_viewport_size({"width": 390, "height": 844})
        page2.screenshot(path="/tmp/hm-week.png", full_page=False)
        b.close()
        print("WEEK OK")


if __name__ == "__main__":
    main()
