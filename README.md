# TCR — pilot t-shirt shop (Django)

Same pilot as the earlier Node version — browse products, add to a
session cart, view the cart — rebuilt in Django, styled with the TCR
identity system (palette + crest). Placeholder brand, placeholder
products, no real checkout yet.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate      # .venv\Scripts\activate on Windows
pip install -r requirements.txt

python manage.py migrate
python manage.py createsuperuser   # for /admin/
python manage.py seed_products     # adds 3 placeholder shirts
python manage.py runserver
```

Then:
- Shop: http://127.0.0.1:8000/
- Admin: http://127.0.0.1:8000/admin/ — this is where you'd actually
  manage products day to day; the `seed_products` command is just a
  shortcut to skip typing them in by hand for this pilot.

## Structure

- `config/` — project-level settings, root URLs, WSGI/ASGI entry points
- `shop/` — the one app: `models.py` (Product), `views.py`,
  `urls.py`, `admin.py`, `cart.py` (session-based cart, same role as
  a typical Django tutorial's cart module), `templates/shop/`,
  `static/shop/css/style.css`
- `shop/management/commands/seed_products.py` — `manage.py
  seed_products` to populate placeholder data

## What's deliberately missing (pilot scope)

- No real checkout/payment integration
- No user accounts — cart is anonymous-session only
- SQLite, not Postgres — fine locally, swap the `DATABASES` setting
  before deploying anywhere with concurrent writes
- Product images aren't included — add them via the admin, or drop
  files in `media/products/` and point a product's `image` field at
  one

## Deploying

Same plan as before: push this to GitHub, connect it to Render or
Railway (both auto-detect Django via `requirements.txt` +
`manage.py`), and set `DEBUG=False`, a real `SECRET_KEY`, and
`ALLOWED_HOSTS` as environment variables on whichever platform you
pick. Swap SQLite for the platform's managed Postgres before
anything with real traffic — Render and Railway both offer it
built in.
