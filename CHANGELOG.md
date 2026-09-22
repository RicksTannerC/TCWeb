# Change log

The running record of what changed in The T-Shirt Shop, why, and how it was
checked. Newest first. One entry per change (or tight group of changes), each
pointing at the commit(s) that carry it.

> **Format note.** The layout below is a working format. It will be brought in
> line with the FDR / SDR process once that guide is added to the repo; until
> then, entries record: **What** changed, **Why**, **Files**, **Verified** (how it
> was tested), and **Follow-ups** (anything left open).

---

## 2026-09-21 — Printful can now fetch private artwork; checkout is a safe placeholder

### Signed, expiring links for Printful

- **What:** `Design.print_file_url` now returns a real, working URL (was
  always `None`) — a signed, expiring link (`shop/printful_delivery.py`,
  `PRINTFUL_ARTWORK_LINK_MAX_AGE`, default 30 min) at
  `/printful/artwork/<id>/<token>/`, unauthenticated by design since Printful
  can't sign in. The token is bound to the design's id *and* its current
  file name, so it dies the instant the artwork is replaced or the design is
  deleted, on top of expiring. `sync_listing()` (send-to-Printful) and order
  fulfillment lines both use it automatically; the earlier guard that
  refused real Printful calls ("print file is private...") is now moot and
  removed, since there's a real link to hand over.
- **Why:** requested, to let the live Printful key be exercised for real
  instead of only against the mock.
- **Files:** `shop/printful_delivery.py` (new), `shop/models.py`
  (`Design.print_file_url`), `shop/printful.py` (`sync_listing`, guard
  removed), `shop/views.py` (`printful_artwork`), `shop/urls.py`,
  `config/settings.py`, `.env.example`.
- **Verified:** 15 new tests (expiry, tampering, wrong design, stale link
  after artwork replaced, deleted design, missing file, unauthenticated,
  console-host vs public-host) plus 5 updated Printful tests confirming
  `sync_listing`/fulfillment lines carry a working link; full suite green
  (111). Manually confirmed against the real Printful key: catalog reads
  succeed and authenticate correctly (no product was created — that's a
  real, visible action in the live Printful account and was left for the
  curator to trigger from the console when ready).
- **Follow-ups:** none blocking; a real "send to Printful" will now create a
  real product in the connected Printful store.

### Checkout is a safe placeholder until Stripe is set up

- **What:** with no Stripe keys configured (Stripe account creation hit a
  snag), the cart page shows a disabled "Checkout" button with a short note
  instead of a live one, and the checkout endpoint itself refuses before
  creating anything — no `Order` row, no charge, nothing queued — showing an
  on-brand message instead. Previously, every checkout attempt (even now, in
  production with no Stripe key) silently created an abandoned
  `pending_payment` Order row that would never resolve; that's fixed too.
  Local dev is unaffected: with `DEBUG=True` the existing simulated checkout
  still works for testing the full order pipeline without Stripe.
- **Why:** requested, so the storefront reads as intentional rather than
  broken while Stripe is pending, without risking a real (or fake) order
  being taken.
- **Files:** `shop/views.py` (`checkout_open`, `checkout`),
  `shop/context_processors.py`, `shop/templates/shop/_cart_body.html`,
  `_cart_drawer_body.html`.
- **Verified:** 8 new tests (no order created in production without Stripe,
  no orphan rows across repeated attempts, cart keeps its contents, empty
  cart's own message still wins, dev simulated checkout still works, correct
  button shown with/without Stripe keys); full suite green (111).
- **Follow-ups:** none; remove once real Stripe keys are in place (the
  button reappears automatically).

---

## 2026-09-21 — Run waitress as a module, not the .exe shim

- **What:** README's run command changed from `waitress-serve ...` to
  `python -m waitress ...`.
- **Why:** on this Windows machine, Windows Smart App Control blocks
  `waitress-serve.exe` (an unsigned, auto-generated launcher) as unrecognized
  software, which silently kept the site's app server from (re)starting.
  `python.exe` itself isn't affected, so running waitress as a module sidesteps
  it entirely with no behavior change. No code change; documentation only.
- **Verified:** restarted the live server with the new command; site, console
  and media all reachable through Cloudflare afterwards.
- **Follow-ups:** Windows-only quirk; moot once Milestone 6 moves the app to a
  Linux VPS under gunicorn.

---

## 2026-09-19 — Storefront images now load (public media served)

- **What:** the public media folder (mockups, lifestyle shots, collection art) is now
  served on both hosts at `/media/...`, in production as well as debug. Only plain
  raster images are served (`png jpg jpeg webp gif avif`); SVG, HTML and anything
  else return 404, and path traversal is refused. Responses carry `nosniff` and a
  one-day public cache header. Print-ready originals are unaffected: they live in
  private storage and are still reachable only in the console.
- **Why:** a live listing showed a broken image. Its mockup was requested from
  `/media/listings/...` and returned 404, because uploaded files were only served
  with `DEBUG=True`.
- **Files:** `shop/public_media.py` (new), `config/urls.py`, `config/urls_console.py`.
- **Verified:** 7 new tests (served with safe headers, non-images refused, originals
  and traversal unreachable, both hosts, a live listing's page and image load);
  full suite green (89).
- **Follow-ups:** images are served from this machine; Cloudflare will cache them, but
  Cloudflare R2 remains the launch plan. Duplicate design 1 (no listings) is still
  in the database, and the "Basic T" tee prices at $53, over the $40 tee ceiling.

---

## 2026-09-19 — Print-ready originals are private (console-only)

- **What:** Design originals (SVG or PNG) are now stored in `private_media/`
  (`PRIVATE_MEDIA_ROOT`), outside public media, with no public URL. They are shown
  only through a staff-only view on the console host (`/designs/<id>/artwork/`),
  behind sign-in and two-factor, with a locked-down policy so an SVG is displayed
  as an image and can never run script. SVG uploads are now accepted (scripts and
  entity tricks rejected). Removed the raw admin's artwork upload. The existing
  original was moved into private storage and the two duplicate files were deleted.
- **Why:** the original is the print-ready file and shouldn't be downloadable;
  product images were also returning 404 on the live site.
- **Files:** `shop/storage.py` (new), `shop/models.py` + migration `0005`,
  `shop/console_views.py`, `shop/urls.py`, `shop/printful.py`, `shop/fulfillment.py`,
  `shop/admin.py`, `config/settings.py`, `.gitignore`, `.env.example`.
- **Verified:** 17 new tests (private storage, headers, auth + 2FA, console-host only,
  unsafe SVGs); full suite green (82). Real DB backed up before the migration.
- **Follow-ups:** sending a design to Printful is now refused with a clear message
  (Printful can't reach a private file); it needs a signed, expiring link. Storefront
  images (downsized PNG/WebP copies and mockups) are still not served publicly.

---

## 2026-09-19 — Upload fixes and the product-template dashboard

*One commit: "Fix duplicate-name uploads; add a product-template dashboard" (see `git log` for the hash).*

### Uploading the same artwork twice no longer crashes

- **What:** Dropping a file whose name matches an existing design used to return the
  "Something went wrong" page. Design slugs are now made unique (`pillars`,
  `pillars-2`, ...); product-template slugs get the same protection. Each uploaded
  file is now all-or-nothing: a failure keeps nothing for that file (no half-made
  design, no stray file left on disk) and the other files in the batch still go
  through. Files that aren't readable images (including SVG, for now) are skipped
  with a clear message instead of an error page. Duplicate titles are allowed and
  flagged with a note.
- **Why:** Diagnosed from the server log: `UNIQUE constraint failed: shop_design.slug`
  on `/listings/intake/`. `Design.save()` slugified the title without checking it was
  free, and the file was written to disk before the database insert failed, leaving
  orphan copies in `media/designs/`.
- **Files:** `shop/models.py` (`unique_slug`, `Design.save`, `ProductTemplate.save`),
  `shop/console_views.py` (`listings_intake`).
- **Verified:** automated tests for repeat uploads, batches, non-images, a mid-batch
  failure (rollback and no orphan file), and slug edge cases; full suite green.
- **Follow-ups:** two orphan copies from the earlier failed uploads still sit in
  `media/designs/` (`..._XorIFu8.png`, `..._gSULDqD.png`) and were left untouched
  pending sign-off to delete.

### Product templates: a console page, and uploads that explain themselves

- **What:** New **Templates** page in the console (`/templates/` on the console host,
  `/manage/templates/` locally) to create, edit and delete product templates: name,
  product type, base cost, absorbed shipping, default sizes (one per line as
  `label, width, height`) and the optional Printful mapping. Shows each template's
  landed cost, the suggested price from the pricing rule `(base + ship) x 2.5`,
  how many listings use it, and warnings (zero costs, tee over the $40 ceiling, no
  sizes). Editing a template affects new uploads only. A template in use by listings
  can't be deleted. The Listings page now says when no templates exist, and an
  upload with no templates is refused with a pointer to the Templates page instead
  of silently creating a design with no listings.
- **Why:** Uploads build a tee and sticker listing from templates, and none existed
  because they were only created by the demo-data command. The first upload therefore
  produced a design with 0 listings and no explanation.
- **Files:** `shop/console_views.py` (`product_templates`, `product_template_edit`,
  `product_template_delete`, `parse_sizes`), `shop/urls.py`,
  `shop/templates/shop/manage/templates.html`, `template_edit.html`, `base.html`
  (nav link), `listings.html` (notice), `shop/models.py` (`ProductTemplate.landed_cost`,
  `suggested_price`).
- **Verified:** automated tests for create/edit/delete, validation messages,
  duplicate names, size parsing, the in-use guard, auth, and that existing listings
  are unaffected by template edits.
- **Follow-ups:** the actual tee and sticker costs and sizes are yours to enter on the
  new page; nothing was invented. One design (id 1) already exists with no listings
  from the earlier upload.
- **Not done yet (next):** serving images. Uploaded files still return 404 on the live
  site (media is only served with `DEBUG=True`), and the print-ready original is
  stored in the same folder. Plan: keep originals private and serve them only on the
  console host, and publish downsized PNG/WebP copies for the storefront.

---

## Earlier history (from git, most recent first)

| Date | Commit | Change |
| --- | --- | --- |
| 2026-09-19 | `98e6827` | README brought up to date; `waitress` added for Windows. |
| 2026-09-19 | `1e1fe55` | Console served at the root of a private `CONSOLE_HOST` (`manage.` host); other hosts stop serving `/manage/` and `/admin/`. |
| 2026-09-19 | `1c00ac2` | Two-factor (authenticator app / backup codes) required for the console and admin; enroll with `manage.py otp_setup`. |
| 2026-09-18 | `b53ce1b` | Trust Cloudflare Tunnel's `X-Forwarded-Proto` so Django sees HTTPS. |
| 2026-09-18 | `abbe5c2` | Ignore the `get-pip.py` installer download. |
| 2026-09-18 | `b26f6bc` | `ALLOWED_HOSTS` defaults to `localhost,127.0.0.1` when unset. |
| 2026-09-18 | `f0b4072` | Fix the broken `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` parsing (syntax error). |
| 2026-09-13 | `d75f24c` | Identity: real crest wired in, palette retuned to match. |
| 2026-09-06 | `4ae2bc4` | Review pass: five storefront adjustments. |
| 2026-09-05 | `168bc41` | Milestone 5: content, legal and the front door. |
| 2026-09-05 | `da822d7` | Milestone 4: the curator's console. |
| 2026-09-05 | `f2120c8` | Milestone 3: Printful integration and the order pipeline. |

Milestones 0-2 (foundations, catalogue, cart and checkout) predate this log; see
`git log` and the build plan.
