# Change log

The running record of what changed in The T-Shirt Brand, why, and how it was
checked. Newest first. One entry per change (or tight group of changes), each
pointing at the commit(s) that carry it.

> **Format note.** The layout below is a working format. It will be brought in
> line with the FDR / SDR process once that guide is added to the repo; until
> then, entries record: **What** changed, **Why**, **Files**, **Verified** (how it
> was tested), and **Follow-ups** (anything left open).

---

## 2026-09-25 — First real payment never reached fulfilment (webhook crash)

- **What:** a customer paid through Stripe but the order never moved past
  `pending_payment`, so nothing reached Printful. Two bugs on the path:
  1. **Webhook crash.** `fulfill_from_session()` called `.get()` on the
     event's session object; the installed stripe library (15.x) returns a
     `StripeObject`, not a dict, so every `checkout.session.completed` raised
     `AttributeError` and returned 500. Now converts with `.to_dict()` first.
  2. **Wrong Printful variant.** `_line()` sent the listing's Printful
     *product* id as `sync_variant_id`. It now sends the ordered size's own
     variant (`sync_variant_id` if the listing is synced, else the catalog
     `variant_id` plus the artwork link) and raises a clear "match sizes"
     error when a size has none — recorded on the order instead of a crash.
- **Not a bug, by design:** a paid order lands in **Awaiting approval** and
  only goes to Printful when the curator approves it in the console.
- **Files:** `shop/payments.py`, `shop/fulfillment.py`,
  `shop/tests_paid_order_pipeline.py` (new), `shop/tests_private_artwork.py`.
- **Verified:** new tests post locally HMAC-signed events through the real
  `construct_event` path (no network); with the fix disabled they fail with
  the exact production error. Full suite green.
- **Later same day:** first real Printful submit was rejected ("Sync variant not
  found") — the listing's stored size ids weren't real sync-variant ids.
  `sync_listing` now also reads Printful's nested `sync_product` reply shape.
  The listing's existing ids still need correcting from Printful (one
  read-only lookup, pending the curator's approval to run it).
- **Follow-ups:** the stuck order needs Stripe to re-send its event (below);
  the real Printful order submit is still untested against the live API.

---

## 2026-09-24 — Beta-launch cleanup; a real Stripe failure hardened

- **What:** three small pre-launch items, plus one real bug caught live:
  - Seeded the five launch content pages (About, Shipping & Returns,
    Privacy, Terms, Social) — previously 0 existed.
  - Deleted three stale `pending_payment` test orders with no email
    attached (harmless leftovers from checkout being clicked before it was
    gated, and from the incident below).
  - **A real production error, fixed:** the live site returned a raw 500 on
    `/checkout/` because `STRIPE_SECRET_KEY` had the *publishable* key
    pasted into it. Stripe correctly rejected the API call
    (`This API call cannot be made with a publishable API key`) — but the
    view had no handling for a configured-yet-failing Stripe, so the
    customer saw a crash page and an `Order` row was created and stranded
    (this is the same `pending_payment`-orphan shape the placeholder fix
    solved for "not configured", just reachable a different way: "configured
    but broken"). `checkout()` now catches any `stripe.StripeError`, deletes
    the order, clears the pending-order session key, and shows a plain
    "checkout hit a snag, your card was not charged" message instead.
- **Why:** found live, mid pre-launch setup, while wiring up the real keys.
- **Files:** `shop/views.py` (`checkout`), `shop/tests_checkout_placeholder.py`.
- **Verified:** 5 new tests (friendly message instead of a 500, no orphan
  order, session cleaned up, cart keeps its contents, a real success path is
  unaffected). Full suite green (198). The actual bad key is a `.env` value
  on `D:\TCData\` the curator fixes themselves — this entry only covers the
  code-side hardening.
- **Follow-ups:** the underlying key-swap in `.env` needs the curator to
  paste the real `sk_live_...` secret key over the current (incorrect)
  publishable-key value before checkout will actually work.

---

## 2026-09-23 — A code-level guarantee the test suite can't repeat the incident

- **What:** `settings.TESTING` (`"test" in sys.argv[:2]`, set once at settings
  load) is now checked first by both `shop.printful.configured()` and
  `shop.payments.stripe_ready()`. While it's true, neither ever reports a
  real key as usable, no matter what's actually in the environment — so
  `manage.py test` can no longer reach a real third-party API by accident,
  the way it did in the previous incident. This is a second, independent
  layer on top of no longer making `TCWEB_ENV_FILE` a permanent variable:
  even if the environment leaks again some other way, this closes the door
  at the code level instead of relying on shell hygiene alone.
- **Why:** asked for directly — turning the incident into a standing
  safeguard rather than just a one-time fix.
- **Files:** `config/settings.py` (`TESTING`), `shop/printful.py`
  (`configured`), `shop/payments.py` (`stripe_ready`); one existing test
  (`tests_checkout_placeholder.py`) updated to explicitly opt out of the
  guard (`TESTING=False`) for the one case that deliberately simulates
  "Stripe is configured."
- **Verified:** new `tests_testing_guard.py` proves the guard itself works —
  a real-looking key is refused while `TESTING` is on, and the same key
  would be accepted if the guard were the only thing changed (`TESTING=False`)
  — so this is locked in as a regression, not just asserted. Full suite green.

---

## 2026-09-23 — Print positioning, a real color dropdown, and a layout fix

- **What:**
  - **Placement** on the Templates page is now a dropdown of Printful's real
    placement keys (front, back, left chest, left/right sleeve) instead of
    free text.
  - **Print size and position** — new, simple per-listing controls (a size
    percentage and a Centered/Higher/Lower/Left/Right choice) let the
    curator adjust where the design sits within its placement area, without
    needing to know Printful's raw pixel coordinates. Both flow into the
    file entry `sync_listing()` and a real customer order send to Printful.
  - **Color** on the listing editor is now a dropdown of the linked
    Printful product's real colors (cached, shared with the size-matching
    lookup so it's one real fetch, not two) when a product is chosen;
    otherwise it's still the free-text field it was. An existing color that
    isn't one of the real options is kept, flagged, rather than silently
    dropped. A Printful hiccup falls back to the free-text field instead of
    breaking the page.
  - **The Catalogue setup page's tables** no longer stretch to the full
    width of a wide console window; `.table-wrap` is now capped and scrolls
    horizontally on narrow screens instead of overflowing.
- **An honest limit, flagged rather than glossed over:** the position sent
  to Printful (`area_width`/`area_height`/`width`/`height`/`top`/`left`) is
  a best-effort, self-consistent proportional shape — it has **not** been
  checked against a real Printful order or API response, since that would
  need a real API call (only made with the curator's own go-ahead from the
  console, or with the user's explicit yes, never on request from Claude
  alone). The always-safe case (100% scale, centered) needs no positioning
  fields at all and is unaffected. Confirming the exact payload against a
  real Printful response is a reasonable next step before relying on a
  non-default scale/position for a paying customer's order.
- **A separate bug found and flagged, not fixed here:** while wiring this
  up, `shop/fulfillment.py`'s `_line()` (real customer orders, not the
  "send to Printful" setup step) turned out to reference
  `listing.printful_product_id` (the whole product's id) as the Printful
  `sync_variant_id`, instead of the ordered size's own
  `ListingSize.printful_variant_id`. Flagged as its own task rather than
  folded in here, since it's a different code path (real order submission)
  that deserves its own focused fix and test.
- **Files:** `shop/models.py` (`PrintPlacement`, `PrintPosition`,
  `Listing.print_scale_pct` / `print_position` / `print_file_payload`,
  `ProductTemplate.print_placement` choices), migration `0008`,
  `shop/printful.py` (`catalog_colors`, cached `_cached_variants`),
  `shop/console_views.py`, `shop/templates/shop/manage/template_edit.html` /
  `listing_edit.html`, `shop/static/shop/css/style.css`.
- **Verified:** 25 new tests (payload construction and clamping for every
  position preset, the sync payload carries it, both console forms
  save/validate correctly, the color dropdown's real-options/fallback/error
  paths, and that the color and size lookups share one cached fetch). Full
  suite green (193).

---

## 2026-09-22 — Pick a real Printful blank and match its sizes, from the console

- **What:** the Templates editor now has a **search box** for Printful's real
  catalog (by name, model or brand — e.g. "Stanley Stella STTU169") instead
  of a bare numeric-ID field; picking a result fills in the product ID and
  a human-readable name (`ProductTemplate.printful_blueprint_name`, new,
  display-only). Once a template has a Printful product chosen, a listing
  using that template gets a **"Match sizes to Printful variants"** button
  on its editor: it looks up that product's real variants in the listing's
  color, and fills in the correct Printful variant id for every one of the
  listing's sizes automatically — the number `sync_listing()` actually needs
  to place a real order, which nothing in the console could set before this.
  A mismatch (unknown color, a size Printful doesn't have) reports exactly
  which sizes didn't match and lists the colors Printful really has for that
  product, rather than failing silently.
- **Why:** requested, after finding the ID fields on the Templates page were
  unused free-text placeholders with nowhere to get the real numbers from,
  and no way at all to set the per-size variant id `sync_listing()` needs.
- **A real, third-party API call, used deliberately:** the search box and
  the "Match sizes" button both make a real, read-only call to Printful's
  catalog using the account's live key — but only when the curator
  triggers it themselves, signed into their own console. Printful's full
  catalog (not searchable server-side) is cached for an hour so repeated
  searches don't refetch it.
- **Files:** `shop/printful.py` (`search_catalog`, `match_variants`,
  `list_catalog` on both the real and mock client), `shop/models.py`
  (`printful_blueprint_name`), migration `0007`, `shop/console_views.py`
  (`template_printful_search`, `listing_match_printful_sizes`),
  `shop/urls.py`, `shop/templates/shop/manage/template_edit.html` /
  `listing_edit.html` / `catalogue_setup.html` (shows the linked product) /
  `_printful_search_results.html` (new), `shop/static/shop/css/style.css`.
- **Verified:** 24 new tests, entirely against the local Printful mock
  (extended with a small real-shaped catalog and multi-color variants) —
  search matching/caching, color+size matching and its failure messages,
  both new views, and that a listing with no product chosen is told to set
  one rather than silently failing. Full suite green (163). A real,
  disclosed, one-off lookup against the live catalog (before this rule
  existed) confirmed Printful's actual data shape, including a `null`
  brand field on some products that the original search code didn't
  handle — fixed (`str(x or "")` throughout) before this shipped, so it
  won't crash the same way against the real catalog in use.
- **Follow-ups:** none blocking. `sync_listing()` itself is unchanged; it
  already sends whatever variant id is stored per size, so a real "Send to
  Printful" should now work end to end once a real order is actually
  placed against a matched listing (still untested against the real API,
  per the new rule below).

---

## 2026-09-22 — Incident: dev/test commands were silently reading the real environment

- **What happened:** `TCWEB_ENV_FILE` had been set as a *permanent* Windows
  environment variable so the real server always found its config. That was
  the mistake: a permanent env var is inherited by every shell, including
  the ones used for ordinary local development and to run the automated
  test suite. While it was set, `python manage.py test` and similar dev
  commands were silently reading the real `.env` — real `PRINTFUL_API_KEY`
  included — instead of the safe, mock-only local defaults. In practice this
  caused one batch of new, not-yet-reviewed tests to make about a dozen
  real, read-only GET requests to Printful's catalog API
  (`/products`, `/products/456`) during a test run, rather than hitting the
  local mock as intended. Nothing was created, changed, or ordered in the
  Printful account — every call involved was a read; no writes, no orders,
  no store changes — but it should never have reached the real API at all
  without being asked first, and is reported here in full rather than
  quietly fixed.
- **Fix:** removed `TCWEB_ENV_FILE` as a permanent environment variable.
  It's now set explicitly, only for the one command that needs it (starting
  the real server, or a one-off `migrate`/`collectstatic` against the real
  data) — see the updated **Deployment** section in `README.md`. Local
  development and the test suite now get the safe project-folder defaults
  (SQLite, the Printful mock) unless that one command explicitly opts in.
- **Files:** `README.md` (Deployment section rewritten); no application
  code changed by this entry.
- **Follow-ups:** the session's own shell history may still have the
  variable cached in an already-running process for its remaining
  lifetime; new shells no longer pick it up. Going forward, dev/test
  commands are run with an explicit empty override
  (`TCWEB_ENV_FILE=`) as a second layer of protection regardless.

---

## 2026-09-22 — Cursor tracking, and the console nav restructure

### Cursor shadow: true 1:1 tracking

- **What:** removed the trailing/easing entirely — the cursor shadow now sets
  its position directly from each `mousemove` event, with no smoothing loop.
  As real-time as the browser's own pointer events allow.
- **Files:** `shop/templates/shop/base.html`.
- **Verified:** full suite green (139, unaffected — JS-only).

### Console nav: 9 pages down to 5, with real merges (not just folders)

- **What:** per the design review discussion, the console's top nav is now
  **Dashboard · Catalogue ▾ · Orders · Money · Content** instead of nine
  flat links. "Catalogue" is the only actual dropdown (Listings, and a new
  **Setup** page); Money and Content are real merges, not just grouping:
  - **Setup** = Templates + Collections, one page, two sections.
  - **Money** = Pricing + Books, one page, two sections.
  - **Content** = Messages (inbox) + Pages, one page, two sections.

  Orders and Listings keep their own top-level slot — they're the two
  highest-traffic, most detailed pages and don't belong folded into
  anything. Every action that used to land back on one of the six old list
  pages (saving/deleting a template, publishing a collection, saving
  prices, logging an expense, etc.) now redirects straight to the right
  section of its merged page (e.g. `#pricing`, `#collections`) instead of
  the top. The six old bare URLs (`/manage/templates/`, `/collections/`,
  `/pricing/`, `/books/`, `/messages/`, `/pages/`) still work — they
  redirect to the right merged page/section — so nothing that already
  linked to them (including the intake page's "no templates yet" notice)
  had to change. The old, now-unused list templates were deleted; every
  create/edit/delete sub-page (template editor, collection editor, page
  editor, etc.) is untouched.
- **Why:** requested in the design review ("a simpler collapsible setup
  that connects related pages, cutting down on the amount of navigation
  needed"), refined in discussion to favor real page merges over just
  sorting the same nine pages into folders.
- **Files:** `shop/console_views.py` (`catalogue_setup`, `money`, `content`,
  and every redirect target updated), `shop/urls.py` (three new routes),
  `shop/templates/shop/manage/catalogue_setup.html` / `money.html` /
  `content.html` (new), `shop/templates/shop/manage/base.html` (the nav,
  now with one Alpine dropdown), `shop/static/shop/css/style.css` (dropdown
  + merged-section styling), six old list templates deleted.
- **Verified:** 13 new tests (each merged page shows both of its sections;
  every affected action's redirect lands on the right page and anchor; the
  old bare URLs still redirect correctly, including preserving `?show=` on
  the messages one; the nav shows exactly the five agreed destinations and
  correctly highlights the active one/group); updated 9 existing tests that
  asserted the old flat URLs/redirects (all in `tests_templates_intake.py`,
  `tests_landing_cards.py`, `tests_console_host.py`); full suite green
  (139). `collectstatic` run for the CSS.
- **Follow-ups:** none blocking. The merged pages are plain stacked
  sections for now (matching the "clean factory, still minimalist" brief);
  a further visual pass on density/layout is still open from the original
  review if wanted.

---

## 2026-09-22 — Follow-up from the design review: cursor lag, backdrop blur, swipe pacing

*Feedback on last round's work, not new review items.*

- **Cursor shadow felt delayed.** Not a latency artifact — the smoothing
  factor was too slow (~300ms to catch up to the real pointer). Tightened
  from a 0.18 to a 0.55 easing factor per frame; now reads as essentially
  real-time with just enough smoothing to avoid jitter.
- **The full-page blur behind the enlarged tile wasn't reading as blur.**
  Checked live: the backdrop genuinely did cover the whole viewport already
  (confirmed via its actual rendered size), but at 3px the blur was too weak
  to notice against mostly-flat dark backgrounds, so only the card's own
  stronger glass-panel blur was visible — which read as "a blurred box
  around the card, everything else normal." Strengthened to 10px, and the
  header now explicitly stacks above the overlay (it has its own solid
  background, so nothing to blur) so it stays sharp and usable — the "other
  than the nav bar" part of the request — while the rest of the page behind
  the card is now clearly blurred.
- **Slowed and smoothed the swipe-to-dismiss close animation** — 0.2s linear
  ease to 0.34s with a gentler ease-out curve, with the JS timing that hands
  off to the actual close action adjusted to match so it no longer cuts the
  animation off partway through.
- **Files:** `shop/static/shop/css/style.css`, `shop/templates/shop/base.html`,
  `shop/templates/shop/_overlay.html`.
- **Verified:** full suite green (123, unchanged — CSS/JS tuning only);
  `collectstatic` run and restarted; re-checked live.

---

## 2026-09-21 — Landing page shows collection cards, curator-controlled

- **What:** the landing page now shows a card per **live, curator-featured**
  collection — its centerpiece image is that collection's first live listing,
  and the card links to that collection's own section on `/shop/` (a real
  anchor, `#collection-<slug>`, now present on each collection's section
  there) rather than to an individual product. A new **"Show on landing" /
  "Remove from landing"** toggle on the console's Collections page controls
  which collections appear, in what order (`landing_sort_order`); a
  collection can be flagged while still hidden, with a warning that it won't
  actually show until published. If nothing is featured yet, the landing
  page falls back to today's small grid of individual live shirts, so it's
  never empty before any collection is set up.
- **Why:** requested in the design review, plus the follow-up request to let
  the curator choose which collections surface on landing rather than always
  showing all of them.
- **Files:** `shop/models.py` (`Collection.featured_on_landing`,
  `landing_sort_order`, `centerpiece_listing`, `landing_cards`), migration
  `0006`, `shop/views.py` (`landing`), `shop/console_views.py`
  (`collection_toggle_landing`), `shop/urls.py`,
  `shop/templates/shop/landing.html`, `_grid.html` (anchor id),
  `manage/collections.html`.
- **Verified:** 12 new tests (centerpiece selection, the live+featured+has-
  listings filter, ordering, the landing fallback, the anchor link, the
  toggle and its warning, auth); full suite green (123). Migrated and
  `collectstatic`'d the real database/static files.
- **Follow-ups:** right now there's one real collection ("Base Heros," not
  yet marked to show on landing) — toggle it on from the console's
  Collections page to see a real card live. Nothing else pending on this
  item.

---

## 2026-09-21 — First design review pass

*From the curator's live design review: renamed the site, separated the
enlarged tile's close control from the title, added a mobile swipe-to-dismiss
gesture, gave tiles/buttons a real hover shadow, and added a cursor shadow
effect. Two review items (the landing page's catalogue cards, and the
console's nav) need a decision before they're built, and the logo swap is
waiting on the file.*

- **Renamed the site** from "The T-Shirt Shop" to "The T-Shirt Brand" to
  match the domain, everywhere it's customer- or operator-facing: page
  titles, Open Graph tags, the header/footer wordmark, email sender name and
  CAN-SPAM postal line, the two-factor issuer name shown in authenticator
  apps, and the demo/seed content. Historical CHANGELOG entries and the
  external vision/build-plan documents are left as they were — they're a
  record of what was decided at the time, not live copy.
- **Separated the enlarged tile's close button from the title.** It was
  absolutely positioned over the info column with no reserved space, so it
  sat on top of the product name. It's now a distinct circular control with
  its own background, with the info column padded clear of it; unchanged on
  the stacked mobile layout, where it sits over the image instead.
- **Swipe down to dismiss, on mobile.** The enlarged tile now tracks a
  downward touch drag, following the finger 1:1, and either snaps back or
  slides fully off-screen (fading out) into the close action past a small
  threshold. A small handle bar at the top (mobile only) hints at the
  gesture. Scoped to the card itself, ignoring drags that start on the size
  dropdown, the buy buttons, or the thumbnail strip, so it doesn't fight
  those controls.
- **Real hover/press feedback.** Tiles now lift with a genuine drop shadow on
  hover (previously just a thin outline ring); buttons lift with a soft
  shadow on hover and settle back down on press. Kept subtle and consistent
  with the rest of the transition language (all of it already respects
  `prefers-reduced-motion`, which the base stylesheet turns into near-zero
  transition durations globally).
- **A soft cursor shadow, desktop only.** A blurred glow now follows the
  pointer with a slight trailing lag, reading as something hovering just
  above the page, and grows slightly over tiles and buttons. Only runs on
  devices reporting a real mouse (`hover: hover` and `pointer: fine`) and
  skips itself entirely under `prefers-reduced-motion: reduce`; the console
  doesn't get it, matching its own stated "lighter weight, less animation"
  design intent.
- **Dashboard: "Top designs" and "Where visits came from" are now their own
  cards**, matching the stat tiles above them, instead of two bare headings
  and lists sitting under the fold with no card treatment.
- **Files:** `shop/static/shop/css/style.css`, `shop/templates/shop/base.html`,
  `shop/templates/shop/_overlay.html`, `shop/templates/shop/manage/dashboard.html`,
  plus the rename across `config/settings.py`, `README.md`, `requirements.txt`,
  `shop/management/commands/seed_catalogue.py` / `seed_pages.py`, and every
  template title/meta tag.
- **Verified:** full test suite green (111, unchanged — this pass is
  template/CSS/JS, no behavior to newly cover); checked live afterwards
  against the real domain in both the desktop and a mobile viewport: the
  close button's separation, the mobile grab handle, the cursor shadow
  activating and growing over a tile (confirmed via its own DOM state, not
  just by eye), and the renamed title/meta tags.
- **A real gap this caught:** none of the CSS changes were actually visible
  live at first, because production (`DEBUG=False`) serves compiled,
  hashed static files from `staticfiles/`, and `collectstatic` hadn't been
  run since the edits — so the site was quietly still serving the old
  stylesheet. Running `python manage.py collectstatic` fixed it; **this is
  now a step to remember after every static-file (CSS/JS/image) change on
  this Windows/waitress setup**, the same way a Python change needs a
  restart.
- **Follow-ups / still open from the review:**
  - Logo swap — waiting on the file.
  - Landing page: show a few catalogue-type cards instead of individual
    shirts, linking through to the catalogue — needs a decision on what a
    "catalogue card" is before building it (see discussion).
  - Console nav: collapse the row of top-level tabs into a simpler, grouped
    structure — needs a decision on the grouping before building it (see
    discussion).
  - Dashboard cards are now correctly styled but not restyled beyond that;
    the deeper console visual pass is bundled with the nav item above.

---

## 2026-09-21 — Real data moved off the OneDrive-synced project folder

- **What:** `db.sqlite3`, `.env`, and `private_media/` (print-ready originals)
  now live at `D:\TCData\` — a plain local drive, not the OneDrive-synced
  `Desktop\TShirtBrand\` folder they'd been sitting in since the project
  started. `config/settings.py` reads `.env` from the OS environment variable
  `TCWEB_ENV_FILE` if it's set (`D:\TCData\.env` here), falling back to the
  project folder otherwise — so a plain checkout with no variable set still
  works for local dev, against its own separate, empty database, never the
  real one. `MEDIA_ROOT` (public product images) is now environment-driven
  too, the same way `PRIVATE_MEDIA_ROOT` already was, though it was left in
  the project folder for now since it holds nothing sensitive.
- **Why:** requested; the original reason for asking about this early on in
  this project's setup. Real customer and order data, and unreleased artwork,
  no longer sit in a folder that syncs to Microsoft's cloud.
- **Files:** `config/settings.py`, `.env.example`, `README.md`. Nothing on
  `D:\TCData\` is or was ever tracked by git.
- **Verified:** copied the live files (not left duplicated — confirmed the
  old copies were gone from the project folder after the move, sizes matched
  exactly on the new location); full test suite green (111) both before and
  after; confirmed live afterwards against the real domain: the shop, the
  console, and a design's signed Printful link all resolved correctly from
  the new location, and a clean shell with the environment variable unset
  correctly falls back to an empty local database rather than the real one.
- **Follow-ups:** OneDrive may still hold the old copies in its own online
  recycle bin / version history for a retention period even though they're
  gone locally; purging that, if wanted, is a OneDrive-side action on
  onedrive.com, outside what's changeable from this machine's filesystem.

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
