# Household Money

A phone page for Mitch and Tonya. It tracks money in, money out, and what's left this week (Monday through today) and this month. Receipt photos stay on the phone. There is no app store and no account.

Entries live on the phone that saved them. The [shared Google Sheet](https://docs.google.com/spreadsheets/d/15Yk4zozMPdaJEURppm4JmCXb--HyCgOPW8-31RTd_8g/edit) is a separate log. This app does not write to that sheet.

## Put it on GitHub Pages and install it on your phone

1. Create a repo and commit the contents of this folder. `tests/` is optional.
2. Go to Settings → Pages and choose Deploy from branch → `main` / root.
3. Open `https://<user>.github.io/<repo>/` on the phone.
4. Android, in Chrome: tap ⋮ → **Install app** (or **Add to Home screen**). It opens full-screen as "Money".
5. iPhone, in Safari: tap the Share button → **Add to Home Screen** → **Add**. It opens as "Money".

After the first online open, the page works offline. Income, spending, categories, and receipt photos are saved on that phone.

**Shipping an update:** edit `index.html`, then bump `VERSION` in `sw.js`. The next time the phone opens the app, it picks up the new version.

## What it does

- This week and this month: Money in, Money out, and Left (in minus out).
- Add income for Mitch or Tonya. Add spending in a category. Add your own categories.
- Take a receipt photo or pick one from the gallery. It is stored on the phone. Tap it to view it, then **Save photo** to put a copy in your files.
- A receipt photo fills in the amount, store, and date. The category guess uses this phone's per-store memory first, then a small learner trained on all synced entries (both phones), the words read from past receipts on this phone, and corrections, then common store names. It only picks categories in your list and asks when unsure.
- Delete one entry at a time. Deleting a category does not delete old entries.
- Settings → **Export backup** / **Import backup**. Import matches entries by id and does not duplicate them.

## Tests

```bash
python3 -m http.server 8788 --bind 127.0.0.1
# from this folder, in another terminal:
/workspace/.venv-tjl/bin/python tests/test_app.py
/workspace/.venv-tjl/bin/python tests/test_scan.py   # receipt date + category + scan flow
```

The test uses a temporary browser profile. It does not put sample entries in the app.
