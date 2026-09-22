# The T-Shirt Brand

A curated print-on-demand storefront (Django + htmx). Currently in **Phase 1**
— see the vision document and build plan for scope.

- Vision: <https://claude.ai/code/artifact/f516ae9b-f45e-4f9f-8d41-955fea59b61a>
- Build plan: <https://claude.ai/code/artifact/e13d6d80-b9d0-47ca-b884-4cb3f70293c9>

## Status

**Milestones 0–5 are built**: the design system and shell, the catalogue and
enlarged-tile browse experience, cart and Stripe checkout, the Printful order
pipeline, the curator's console, and the content/legal pages. The shop is
intentionally empty until real designs are added through the console.

**Milestone 6 (deploy) is in progress.** The site is currently served from a
Windows machine through a Cloudflare Tunnel; a VPS with Postgres, live payment
keys and backups come later (see [Deployment](#deployment)).

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate            # source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt

cp .env.example .env              # optional in dev — defaults work without it
python manage.py migrate
python manage.py createsuperuser  # a staff account for the console + /admin/
python manage.py otp_setup <username>   # two-factor for that account (see below)
python manage.py runserver
```

- Shop: <http://127.0.0.1:8000/>
- Console: <http://127.0.0.1:8000/manage/> (Django admin: `/admin/`)

Optional placeholder data for local development only:
`python manage.py seed_catalogue` (7 demo designs) and `python manage.py seed_pages`
(About / Shipping & Returns / Privacy / Terms / Social starting copy — the legal
pages are drafts and need review before launch).

Run the tests with `python manage.py test shop`.

## Configuration

All config is environment variables, read from `.env` (git-ignored) via
`django-environ`. Local development needs none of them — the defaults run a
working SQLite site. See [.env.example](.env.example) for the full list.

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY`, `DEBUG` | core Django (use a long random `SECRET_KEY` in production) |
| `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` | comma-separated; origins need a scheme and no trailing slash. `ALLOWED_HOSTS` defaults to `localhost,127.0.0.1` |
| `SITE_BASE_URL` | public URL, used for links in emails and "view live" links |
| `CONSOLE_HOST` | private console hostname — see [Console access](#console-access-and-two-factor) |
| `STAFF_2FA_REQUIRED`, `STAFF_2FA_MAX_AGE` | second factor for staff (default on; re-verify every 12 h) |
| `SECURE_SSL_REDIRECT` | `True` makes Django enforce HTTPS itself (default off; Cloudflare redirects at the edge) |
| `DATABASE_URL` | unset → local SQLite in the project folder; a `postgres://` URL in production (Milestone 6) |
| `MEDIA_ROOT`, `PRIVATE_MEDIA_ROOT` | unset → served from the project folder; point elsewhere to keep uploads off a synced drive too |
| `EMAIL_URL` | unset → console backend; an SMTP URL for real mail |
| `STRIPE_*` | checkout |
| `PRINTFUL_API_KEY`, `PRINTFUL_ARTWORK_LINK_MAX_AGE` | fulfilment; the latter is how long a signed print-file link stays valid (default 30 min) |

Keep `.env`, the database and `private_media/` out of git (all git-ignored) and
out of any cloud-synced folder — they hold customer data, private artwork and
live keys. **This project's real data lives on `D:\TCData\`**, not in this
folder: `db.sqlite3`, `.env` (with `DATABASE_URL` / `PRIVATE_MEDIA_ROOT` set to
point back into that same folder) and `private_media/`. Django is told where
to find that `.env` by the OS environment variable `TCWEB_ENV_FILE`
(`D:\TCData\.env`), set for the Windows user account that runs the app; with
that variable unset, Django falls back to `.env` in this project folder — a
separate, empty local-dev setup, never the real data. See `.env.example` for
how to point a fresh checkout at data of its own.

## Console access and two-factor

The curator's console (dashboard, listings, collections, pricing, product templates,
orders, books, messages, pages) and the Django admin require a **password plus an authenticator
code** (TOTP) or a one-time backup code.

- **Enroll** on the machine that runs the shop: `python manage.py otp_setup <username>`.
  It prints a QR code and 8 backup codes once. There is deliberately no web
  enrollment, so a stolen password can't be used to add an attacker's device.
  Lost your phone: `python manage.py otp_setup <username> --reset`.
- Staff without an enrolled device are locked out of the console (they are told
  to run the command), not let through.
- Repeated wrong codes are throttled; verification lasts `STAFF_2FA_MAX_AGE`
  seconds (12 h by default), and a code can't be reused.
- Set `STAFF_2FA_REQUIRED=False` only for throwaway local development.

**Private console host.** With `CONSOLE_HOST=manage.yourdomain.com` the console is
served at the *root* of that host — `/` is the dashboard, `/orders/`, `/listings/`,
… with no `/manage/` prefix — and nothing else is served there. Other public hosts
then return 404 for `/manage/` and `/admin/`; `localhost` keeps the single-host
layout (`/manage/`), and with `CONSOLE_HOST` unset nothing changes. Add the host to
`ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` as well.

## Deployment

Current setup (interim, from a Windows machine):

- `TCWEB_ENV_FILE` is set as a permanent environment variable for the Windows
  user account that runs the app (`D:\TCData\.env`), so any shell that user
  opens finds the real config without it being passed explicitly.
- The app runs under **waitress** (`gunicorn` doesn't run on Windows):
  `python -m waitress --listen=127.0.0.1:8000 config.wsgi:application` — bound
  to localhost only, so it is reachable solely through the tunnel. Run it as a
  `python -m` module rather than the `waitress-serve.exe` shim: Windows **Smart
  App Control**, if enabled, blocks that shim as an unrecognized unsigned
  binary (`python.exe` itself isn't affected). This is a Windows quirk, not a
  code issue, and stops mattering once this moves to a Linux VPS.
- A **Cloudflare Tunnel** publishes the shop (`yourdomain.com`) and the private
  console host (`manage.yourdomain.com`) to `http://127.0.0.1:8000`. Leave the
  route's *Path* field empty, and use `127.0.0.1` rather than `localhost`.
- HTTPS ends at Cloudflare. Django trusts the tunnel's `X-Forwarded-Proto`
  header (`SECURE_PROXY_SSL_HEADER`) so `request.is_secure()`, CSRF checks and
  absolute URLs use `https`. This is only safe while the origin isn't reachable
  except through the tunnel.
- Static files are served by WhiteNoise (run `collectstatic` after changing them);
  media is served from local disk only in `DEBUG` for now.

Still to do for launch (Milestone 6): a VPS, Postgres (add a driver such as
`psycopg` to `requirements.txt`), Cloudflare R2 for media, live Stripe and
Printful keys, an email provider, and nightly backups with a tested restore.

## Structure

- `config/` — settings (env-driven), root URLs, `urls_console.py` (the private
  console host's URL layout), WSGI/ASGI
- `shop/` — the app: `models.py`, `views.py`, `urls.py` (public + console
  patterns), `cart.py` (session cart), `payments.py` (Stripe), `printful.py` +
  `fulfillment.py` + `orders.py` (order pipeline), `console*.py` /
  `manage_views.py` (the console), `two_factor.py` (second-factor check),
  `middleware.py` (host routing, 2FA gate, visit capture), `emails.py`,
  `templates/shop/`, `static/shop/`
- `shop/static/shop/css/style.css` — the design system (tokens, both themes,
  glass panel, layout)
- `shop/static/shop/vendor/` — vendored htmx + Alpine (no CDN dependency)
- `templates/` — project-level `404.html`, `500.html`
- `shop/management/commands/` — `otp_setup` (enroll two-factor), plus
  `seed_catalogue` / `seed_pages` (demo content)

## Stack notes

- **Django 6.1**, server-rendered, with **htmx** for partial updates and a light
  touch of **Alpine** (theme toggle, cart drawer, enlarged-tile interactions).
- **SQLite** locally, **Postgres** in production — the ORM is portable, so the
  switch is a `DATABASE_URL` change with no code impact.
- **django-otp** for the staff second factor; **WhiteNoise** for static files.
- Media is local disk for now, Cloudflare R2 later (Milestone 6).
