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

- `TCWEB_ENV_FILE` is **not** set as a permanent/ambient environment variable —
  deliberately. A persistent one gets inherited by every shell and every dev
  command (tests, `manage.py shell`, ...) without you noticing, which risks
  those ordinary commands silently reading real secrets and hitting real
  third-party APIs (Printful, Stripe) with the live key. Instead, set it
  explicitly only for the specific command that needs the real config:
  - PowerShell, before starting/restarting the real server:
    `$env:TCWEB_ENV_FILE = "D:\TCData\.env"` then run waitress in that same
    command.
  - A one-off command (migrate, `collectstatic`, a real shell check):
    prefix that single command, e.g. `TCWEB_ENV_FILE=D:/TCData/.env python manage.py migrate`.
  - Local dev and the test suite should almost always run with **no**
    `TCWEB_ENV_FILE` set, so they use the safe project-folder defaults
    (SQLite, the Printful mock) automatically.
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
- **The app auto-restarts after a reboot, sleep, or crash.** `deploy/run_server.ps1`
  is a small supervisor loop (sets `TCWEB_ENV_FILE`, starts waitress, and just
  restarts it 5 seconds after it ever exits, forever); it never starts a second
  copy if port 8000 is already in use. A Windows Scheduled Task named
  `TShirtBrandWebsite` runs that script at startup, so the site comes back on
  its own even if no one is around to restart it by hand. Cloudflared is
  already a Windows service and needs nothing here.
  - **One-time setup** (run this once, in your own terminal — it prompts for
    your Windows account password directly, never through anything else):
    ```
    schtasks /create /tn "TShirtBrandWebsite" /tr "powershell -ExecutionPolicy Bypass -WindowStyle Hidden -File \"C:\Users\trick\OneDrive\Desktop\TShirtBrand\TCWeb\deploy\run_server.ps1\"" /sc onstart /ru trick /rp * /rl highest /f
    ```
    (`/rp *` is what makes it prompt for the password interactively instead of
    taking it as a plain argument; `/ru trick` runs it as your own account,
    which matters because the repo lives inside OneDrive.)
  - **To restart the app by hand** during development, stop the task first so
    the supervisor and a manual run don't both grab port 8000:
    `Stop-ScheduledTask -TaskName "TShirtBrandWebsite"`, then start it again
    when done: `Start-ScheduledTask -TaskName "TShirtBrandWebsite"`.
  - Logs: `waitress.supervisor.log` (start/restart events),
    `waitress.log`/`waitress.err.log` (the app itself, as before).
  - Verified: killed the waitress process out from under a running supervisor
    and confirmed it noticed and relaunched the app within 5 seconds, with no
    manual action. Not yet verified across an actual machine reboot.

### Backups

`deploy/backup.py` (Python standard library only) takes a real, verified backup
of the shop's data. Run it from the project folder:

```
python deploy/backup.py                      # D:\TCData  ->  D:\TCData\backups
python deploy/backup.py --source D:\TCData --dest E:\TCBackups --keep 14
```

- **What is backed up**, into `<dest>\<YYYY-MM-DD_HHMMSS>\`:
  `db.sqlite3` (orders, customers' emails and addresses, listings), copied with
  SQLite's *online* backup API so it is consistent while the app is running
  (a plain file copy of a live database can be torn or miss recent writes);
  `private_media\` (the print-ready artwork originals); `media\` (public
  product images, if the folder exists); and `manifest.json` (row counts, file
  counts, sizes and checksums).
- **What is NOT backed up: `.env`.** It holds the Stripe/Printful/email keys and
  `SECRET_KEY`; the script never reads it, and logs and other files in the data
  folder are skipped too. Keep `.env` in a password manager, separately.
- **Safety.** The copied database must pass `PRAGMA integrity_check` before a
  backup is kept; a backup is built in a hidden staging folder and only renamed
  into place on success, so a failed run leaves no half backup and deletes
  nothing. The exit status is non-zero on any failure, and each run appends to
  `<dest>\backup.log`.
- **Retention.** The newest 14 are kept (`--keep N`); older timestamped folders
  inside `--dest` are deleted after a successful run. Nothing else in `--dest`
  is touched.
- **Verify (do this now and then).** `python deploy/backup.py --verify` restores
  the newest backup (or `--verify <backup folder>`) into a temporary folder,
  runs `integrity_check`, compares every table's row count and every file's
  size/checksum with the manifest, prints `PASS`/`FAIL`, and cleans up. It
  never writes to live data.
- **Restore.** Stop the app (`Stop-ScheduledTask -TaskName "TShirtBrandWebsite"`),
  move the damaged `db.sqlite3` / `private_media` out of the way, then
  `python deploy/backup.py --restore-to C:\Restore --from <backup folder>`
  (the target must be new or empty; it refuses to overwrite an existing
  database), copy the restored files into `D:\TCData`, put `.env` back from
  your password manager, and start the app again.
- **A backup on the same disk is not a safe backup.** The default destination
  (`D:\TCData\backups`) protects against a bad migration, a deleted listing or
  a corrupted database, but not against disk failure, theft, fire or ransomware.
  Point `--dest` at a second drive, or at a folder that is synced somewhere
  else. Note that the backup holds customer emails and addresses, so putting it
  in OneDrive (or any cloud folder) uploads that personal data to the cloud --
  that is the owner's call.
- **Schedule it daily.** The script does not schedule itself. Run this once
  yourself, in an administrator PowerShell; it prompts for your Windows account
  password (`/rp *`), which is never part of the command:
  ```
  schtasks /create /tn "TShirtBrandBackup" /tr "C:\Users\trick\AppData\Local\Programs\Python\Python314\python.exe C:\Users\trick\OneDrive\Desktop\TShirtBrand\TCWeb\deploy\backup.py" /sc daily /st 03:00 /ru "MicrosoftAccount\tricks496@gmail.com" /rp * /rl limited /f
  ```
  (The full path to `python.exe` is used because a scheduled task does not
  reliably get your shell's `PATH`; to change the destination, append
  `--dest <folder>` inside the `/tr` string. If Windows rejects the account name,
  use `/ru trick` as the `TShirtBrandWebsite` task does.) The task only runs
  while the PC is on and awake at 03:00; in Task Scheduler's task Settings tab,
  tick "Run task as soon as possible after a scheduled start is missed" so a
  sleeping PC catches up. Check `<dest>\backup.log` after the first night.

Still to do for launch (Milestone 6): a VPS, Postgres (add a driver such as
`psycopg` to `requirements.txt`), Cloudflare R2 for media, live Stripe and
Printful keys, an email provider, and a second-location copy of the
backups (see [Backups](#backups)).

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
- **Fonts are self-hosted**, so visitors' browsers never contact Google. The
  latin-subset `woff2` files live in `shop/static/shop/fonts/`: Oswald 400, 500,
  600, 700; IBM Plex Sans 400, 500, 600; IBM Plex Mono 400, 500. They come from
  the `@fontsource` packages and are under the SIL Open Font License; the
  licence texts (`OFL-*.txt`) sit beside them and must stay with the fonts.
  Each file has an `@font-face` rule at the top of `shop/static/shop/css/style.css`
  (relative `url()`, so the static manifest fingerprints it), and `base.html`
  preloads the Oswald 600 face. To add a weight, drop the matching
  `<family>-latin-<weight>-normal.woff2` into that folder, add its `@font-face`
  rule, and run `shop.tests_fonts` (it fails if the CSS uses a weight with no
  rule, or names a file that is missing). After any font or CSS change run
  `collectstatic` and restart the app, since WhiteNoise only reads the
  collected files at startup.
