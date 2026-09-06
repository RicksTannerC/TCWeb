# The T-Shirt Shop

A curated print-on-demand storefront (Django + htmx). Currently in **Phase 1**
— see the vision document and build plan for scope.

- Vision: <https://claude.ai/code/artifact/f516ae9b-f45e-4f9f-8d41-955fea59b61a>
- Build plan: <https://claude.ai/code/artifact/e13d6d80-b9d0-47ca-b884-4cb3f70293c9>

## Status

**Milestone 0 — foundations & shell.** Environment-driven settings, the
warm-industrial design system, the base layout shell (header / nav / footer /
theme toggle), vendored htmx + Alpine, custom 404/500. Catalogue, cart,
checkout, Printful and the console come in later milestones.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate            # source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt

cp .env.example .env              # optional in dev — defaults work without it
python manage.py migrate
python manage.py createsuperuser  # for /admin/
python manage.py seed_products    # 3 placeholder shirts (temporary, until Milestone 1)
python manage.py runserver
```

- Shop: <http://127.0.0.1:8000/>
- Admin: <http://127.0.0.1:8000/admin/>

## Configuration

All config is environment variables, read from `.env` (git-ignored) via
`django-environ`. Local development needs none of them — the defaults run a
working SQLite site. See [.env.example](.env.example) for the full list.

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS` | core Django |
| `DATABASE_URL` | unset → local SQLite; a `postgres://` URL in production (Milestone 6) |
| `EMAIL_URL` | unset → console backend; an SMTP URL for real mail (Milestone 2) |
| `STRIPE_*` | checkout (Milestone 2) |
| `PRINTFUL_API_KEY` | fulfilment (Milestone 3) |

## Structure

- `config/` — settings (env-driven), root URLs, WSGI/ASGI
- `shop/` — the app: `models.py`, `views.py`, `urls.py`, `cart.py` (session cart),
  `context_processors.py`, `templates/shop/`, `static/shop/`
- `shop/static/shop/css/style.css` — the design system (tokens, both themes,
  glass panel, layout)
- `shop/static/shop/vendor/` — vendored htmx + Alpine (no CDN dependency)
- `templates/` — project-level `404.html`, `500.html`
- `shop/management/commands/seed_products.py` — temporary placeholder data

## Stack notes

- **Django 6.1**, server-rendered, with **htmx** for partial updates and a light
  touch of **Alpine** (theme toggle now; enlarged-tile interactions in Milestone 1).
- **SQLite** locally, **Postgres** in production — the ORM is portable, so the
  switch is a `DATABASE_URL` change with no code impact.
- **WhiteNoise** serves static files; media is local disk for now, Cloudflare R2
  later (Milestone 6).
