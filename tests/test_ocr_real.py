"""Real Tesseract OCR on phone-size receipt photos (hm-v1.11.3). No OCR stub. Google is never contacted.
Includes Allen's two real receipts (tests/fixtures) with the results they must give.
Run a static server on 127.0.0.1:8788 first."""
import json
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8788/"
FIX = Path(__file__).resolve().parent / "fixtures"
CATS = ["Tithes", "Mortgage", "Utilities", "Car Payment", "Groceries", "Phones", "Cards", "Medical", "Online", "Eating Out"]
# Real phone photos on a marble counter. amount: allowed values; hint: words the note must contain.
REAL = {
    "receipt-food-lion-2626.jpg": {"amount": ["9.43"], "note": "Food Lion", "date": "2026-10-18", "cat": "Groceries"},
    # Dot-matrix card slip; the 55.04 total (tip) is handwritten. Printed Amount + a tip note is the fallback.
    "receipt-dragon-place.jpg": {"amount": ["55.04", "47.04"], "date": "2026-10-18", "cat": "Eating Out", "hint": "tip"},
}
OUT = Path("/tmp/hm-ocr"); OUT.mkdir(exist_ok=True)
LINES = ["FOOD LION #1234", "4110 N MAIN ST", "KERNERSVILLE NC 27284", "10/17/26  09:22 AM",
         "MILK GAL           3.49", "BREAD WHEAT        2.79", "EGGS 18CT          4.99",
         "BANANAS            1.62", "SUBTOTAL          12.89", "TAX                0.26",
         "TOTAL             13.15", "VISA TEND         13.15", "THANK YOU FOR SHOPPING"]
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"

def receipt(w, h, fg=0, bg=255, table=(120, 90, 60)):
    img = Image.new("RGB", (w, h), table)
    d = ImageDraw.Draw(img)
    pw, ph = int(w * 0.5), int(h * 0.85)
    x0, y0 = (w - pw) // 2, (h - ph) // 2
    d.rectangle([x0, y0, x0 + pw, y0 + ph], fill=(bg, bg, bg - 5))
    size = int(pw / 26)
    f = ImageFont.truetype(FONT, size)
    y = y0 + size
    for ln in LINES:
        d.text((x0 + size, y), ln, font=f, fill=(fg, fg, fg)); y += int(size * 1.6)
    return img

def make():
    cases = {}
    receipt(4000, 3000).rotate(0).save(OUT / "12mp.jpg", quality=88); cases["12mp"] = OUT / "12mp.jpg"
    big = receipt(8160, 6120); big.save(OUT / "50mp.jpg", quality=85); cases["50mp"] = OUT / "50mp.jpg"
    # Portrait phone photo stored sideways with EXIF orientation 6 (how Samsung saves it).
    side = receipt(3000, 4000).transpose(Image.ROTATE_90)
    ex = Image.Exif(); ex[0x0112] = 6
    side.save(OUT / "exif6.jpg", quality=88, exif=ex.tobytes()); cases["exif6"] = OUT / "exif6.jpg"
    # Faded thermal paper in dim light.
    lc = receipt(4000, 3000, fg=140, bg=190, table=(90, 80, 70)).filter(ImageFilter.GaussianBlur(1.5))
    lc.save(OUT / "lowcontrast.jpg", quality=80); cases["lowcontrast"] = OUT / "lowcontrast.jpg"
    # Sideways photo with no EXIF at all.
    receipt(3000, 4000).transpose(Image.ROTATE_270).save(OUT / "sideways.jpg", quality=88); cases["sideways"] = OUT / "sideways.jpg"
    return cases

def main():
    extra = [Path(p) for p in sys.argv[1:]]
    cases = make()
    for name in REAL: cases[name] = FIX / name
    for p in extra: cases[p.name] = p
    fails = []
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True)
        ctx = b.new_context(viewport={"width": 412, "height": 915})
        ctx.route("**/*script.google.com/**", lambda r: r.abort())
        ctx.add_init_script("localStorage.setItem('householdMoney.categories.v1', JSON.stringify(%s));" % json.dumps(CATS))
        page = ctx.new_page()
        # The real receipts are dated Oct 18, 2026; pin the clock so the date check never ages out.
        page.clock.set_fixed_time("2026-10-18T22:30:00")
        errs = []; page.on("pageerror", lambda e: errs.append(str(e)))
        page.goto(URL); page.wait_for_function("() => window.HM")
        for name, path in cases.items():
            page.evaluate("() => { location.hash = '#/'; }")
            page.locator("#go-spend").click(); page.wait_for_selector("#view-spend:not([hidden])")
            page.evaluate("() => { document.querySelector('#spend-amount').value=''; document.querySelector('#spend-note').value=''; document.querySelector('#spend-date').value=''; document.querySelectorAll('#cat-chips input:checked').forEach(i => i.checked = false); }")
            page.locator("#spend-gallery").set_input_files(str(path))
            page.wait_for_function("() => { const h=document.querySelector('#receipt-hint'); return h && !h.hidden && !/Reading/.test(h.textContent); }", timeout=120000)
            r = page.evaluate("() => ({a: document.querySelector('#spend-amount').value, d: document.querySelector('#spend-date').value, n: document.querySelector('#spend-note').value, c: (document.querySelector('#cat-chips input[name=category]:checked') || {}).value || '', h: document.querySelector('#receipt-hint').textContent})")
            print(name, r)
            if name in ("12mp", "50mp", "exif6", "lowcontrast", "sideways") and r["a"] != "13.15": fails.append(name)
            want = REAL.get(name)
            if want:
                bad = []
                if r["a"] not in want["amount"]: bad.append("amount")
                if r["d"] != want["date"]: bad.append("date")
                if r["c"] != want["cat"]: bad.append("category")
                if "note" in want and r["n"] != want["note"]: bad.append("note")
                if "hint" in want and r["a"] != "55.04" and want["hint"] not in r["h"].lower(): bad.append("hint")
                if bad: fails.append(name + ":" + "/".join(bad))
        print("page errors:", errs)
        b.close()
    print("FAILS", fails); sys.exit(1 if fails or errs else 0)

if __name__ == "__main__":
    main()
