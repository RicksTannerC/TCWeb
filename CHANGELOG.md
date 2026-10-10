# Change log

The running record of what changed in The T-Shirt Brand, why, and how it was
checked. Newest first. One entry per change (or tight group of changes), each
pointing at the commit(s) that carry it.

> **Format note.** The layout below is a working format. It will be brought in
> line with the FDR / SDR process once that guide is added to the repo; until
> then, entries record: **What** changed, **Why**, **Files**, **Verified** (how it
> was tested), and **Follow-ups** (anything left open).

---

## 2026-10-11 — www.<domain> redirects to the bare domain

- **What:** `www.shopthetshirtbrand.com` had no route, so it simply failed. `HostRoutingMiddleware`
  now answers a `www.` host with a permanent redirect (301; 308 for non-GET so a POST keeps its
  method) to the same path and query on the bare domain. It runs before host validation, so `www`
  does not need adding to ALLOWED_HOSTS, and it only ever redirects to an exact ALLOWED_HOSTS entry
  (a crafted Host header can't pick the destination). The private console host is never redirected.
- **Still needs the owner:** in Cloudflare, add `www.shopthetshirtbrand.com` as a public hostname on
  the same tunnel (service `http://127.0.0.1:8000`), which also creates its DNS record.
- **Files:** `shop/middleware.py`, `shop/tests_www_redirect.py` (10 tests).

---

## 2026-10-11 — Rights notes per design; TTS-00009's real cost recorded

- **Rights record (private).** Each design now has: where the artwork came from (original /
  commissioned / licensed / public domain / AI / other / not recorded), the date a conflict search was
  done, and free-text notes (source files, licence terms, receipts, what was searched). Edited in the
  listing editor's Design panel; never shown on the public shop (a test checks the notes can't leak).
  A live listing without a recorded origin *and* a dated search gets a quiet nudge, and the Listings
  list marks it "rights not recorded". This is the evidence behind the Terms' ownership promise.
  Migration 0016. Existing designs start as "not recorded".
- **TTS-00009's real Printful cost recorded** (one approved read-only lookup of order 179489366):
  subtotal $21.55 + shipping $4.95 + tax $1.60 = **$28.10**. The order sold for $27.00, so it lost
  $1.10 before Stripe's card fee. Jack-o's cost inputs ($21.55 base, $6.00 shipping est.) were already
  accurate; the listing now sells at $30.00, which leaves roughly $1.90 before Stripe's fee and is
  flagged below the 2.0× guardrail. Pricing is the owner's decision; nothing was changed.
- The same lookup showed the order "in process" at Printful with a shipment already created, while
  the console still said "submitted": Printful's status webhook is not reaching the site (or is not
  registered). Checking/registering it is a Printful read + write and needs the owner's approval.
- **Files:** `shop/models.py`, `shop/console_views.py`, `listing_edit.html`, `listings.html`,
  migration 0016, `shop/tests_design_rights.py` (11 tests).

---

## 2026-10-10 — Console login throttling and real backups (built by sub-agents, reviewed and merged)

- **Login throttling.** Repeated failed staff sign-ins are locked, at both the password step and the
  second-factor step. Defaults: 5 failures per username or 15 per client IP within 15 minutes; a lock
  ends 15 minutes after the last real failure, so the owner can never be locked out for good. A locked
  attempt is refused before the password is evaluated, and hammering a locked account can't extend
  it. Unknown usernames are counted and answered identically (no user enumeration). Failures live in
  the database (`FailedLogin`, migration 0014) so a lock survives a restart. Behind the Cloudflare
  Tunnel the real IP is read from `CF-Connecting-IP`, only when the connection itself is loopback.
  Owner escape hatch: `python manage.py clear_login_lockouts [--username NAME]`; off switch:
  `LOGIN_THROTTLE_ENABLED=false`. Known limit: an attacker who knows the username can nuisance-lock
  the owner out of *new* sign-ins (existing sessions are unaffected).
- **Backups with a tested restore** (`deploy/backup.py`, README "Backups"). Online SQLite copy of the
  database plus `private_media`, integrity-checked, with a manifest of row counts and file checksums;
  keeps the newest 14; `--verify` restores to a temp folder and compares; `--restore-to` refuses to
  overwrite anything. `.env` and logs are never copied. A first real backup was taken to
  `D:\TCDataackups\` and independently re-verified (PASS). **Not yet scheduled** (needs the
  owner's password) and **a copy on the same disk is not disaster-proof**.
- Migration numbering: both branches added a 0014; the supplier-costs migration was renumbered to
  0015 and re-parented before anything was applied to the real database.
- **Verified:** 423 tests on the merged result; the backup re-verified by hand; the throttling code
  read in full before merging.

---

## 2026-10-10 — Books now use Printful's real charge, and show the sales tax it billed

- **What:** the owner pointed out that Printful charges *them* sales tax, and that the tax they
  collect from customers is a separate matter. "Supplier cost" was only an estimate (the listing's
  hand-typed base cost), so neither was visible.
  - Each fulfilment now stores what Printful actually billed (`supplier_cost_actual`) and the tax in
    it (`supplier_tax`, tax + VAT), read from the reply to "create order" — no extra Printful call.
    A zero or unparseable total is ignored rather than recorded.
  - `Order.supplier_cost` uses the recorded charges (a billed reprint counts again) and falls back to
    the estimate; margins and the Books page follow. The Books page shows how many orders are still
    estimated, a new "Sales tax Printful charged you" tile (already inside supplier cost), and
    relabels collected tax "owed to the state — not income, not in Net".
  - Listing editor: Base cost label now reminds you to include any tax Printful charges you.
- **Not done (needs the owner):** order TTS-00009 was submitted before this existed, so its real cost
  is not recorded (one read-only Printful lookup would fill it). Collecting tax from customers needs
  Stripe Tax set up and registrations in place first; `STRIPE_TAX_ENABLED` stays off until then.
- **Files:** `shop/orders.py`, `shop/fulfillment.py`, `shop/console_views.py`, `money.html`,
  `listing_edit.html`, migration 0014, `shop/tests_supplier_costs.py` (13 tests).

---

## 2026-10-10 — Exact legal name, and the Terms decisions the owner settled

- **Legal name set exactly as given:** "The Tshirt Brand LLC" (previously "L.L.C."). Changed in
  the `SHOP_LEGAL_NAME` default (footer, emails), the seed pages, the live Privacy and Terms pages,
  and the Terms draft. PO Box 1403 confirmed as the published mailing address.
- **Terms draft:** cancellation (only before production starts) and returns (30 days from delivery)
  accepted as written, so those markers are gone. Still open: sales tax (below), dispute venue,
  artwork ownership after IP clearance, a lawyer's review.
- `.claude/worktrees/` added to `.gitignore` (sub-agent working copies).

---

## 2026-10-10 — Terms of Service draft, a real delivery estimate, stale orders cleared

- **Terms of Service draft** (`docs/terms-of-service-draft.md`, also a DRAFT page in the
  console titled "Terms of Service (draft)": not live, not in the footer, 404 publicly).
  Fifteen sections written to match what the shop actually does (US-only shipping,
  every order held for approval, made to order, 30-day defect policy). Anything that is a
  business decision is marked `[CONFIRM]` rather than invented: cancellation policy,
  return-window start, entity/address, dispute venue, artwork ownership after IP clearance,
  and **sales tax**. The live "Terms" page is unchanged until a reviewed version replaces it.
- **Sales tax gap noted, not fixed:** `STRIPE_TAX_ENABLED` is off, so no tax is added, yet the
  live Shipping page says tax is calculated at checkout. Needs a business decision.
- **Delivery estimate:** the curator supplied a real figure (an order placed Oct 5, estimated
  delivery Oct 12–14 = 7–9 days). The Shipping & Returns page now says orders arrive "about
  7–9 days" (replacing "a few days") and the seed copy matches. Stripe's checkout estimate was
  hard-coded "3–8 business days" (earlier than reality); it now says 7–9 calendar days.
  This rests on one order; widen it if real deliveries run longer.
- **Cleanup:** stale unpaid test orders TTS-00005 and TTS-00006 deleted (checked: no email,
  no payment, no fulfilments; backup `D:\TCData\db-before-terms-draft.sqlite3`).
- **Files:** `docs/terms-of-service-draft.md`, `shop/payments.py`,
  `shop/management/commands/seed_pages.py`, `shop/tests_shipping_estimate.py`.

---

## 2026-10-05 — Second Jack-o order also failed: its sizes still had no ids

- **What:** a new paid order (TTS-00009) was approved but never reached Printful: the
  same "no Printful variant" failure. The previous day's fix only applies to listings
  sent *after* it; Jack-o had been sent before, and its sizes still had no Printful ids.
  - With the curator's go-ahead, one read-only request (GET sync product 477732182)
    showed Printful names Jack-o's variants exactly as the matching code expects
    (`<external_id>::M`, size and color fields present), with sync ids S 5539558975,
    M 5539558979, L 5539559080. These were written to the three sizes directly (after
    checking each against the stored catalogue id; backup
    `D:\TCData\db-before-jacko-ids.sqlite3`). TTS-00009's order line now builds
    (`sync_variant_id` 5539558979); the retry is the curator's to press.
  - **New warning:** a listing that is on Printful but has a size with no Printful id
    now shows "Orders for this listing will fail" at the top of its editor page (and
    suggests hiding it if it's live). Local check only. This was a silent trap: a live
    listing could take real payments it could not fulfil.
- **Files:** `shop/console_views.py`, `listing_edit.html`, `shop/tests_reprint_and_sync_ids.py`.
- **Verified:** 350 tests; order line for TTS-00009 built from the real database.
- **Known gap:** the warning only catches *blank* ids. The Wanderer still holds ids from
  its previous Printful product (non-blank, wrong) until "Refresh sizes from Printful" is
  pressed on it.

---

## 2026-10-04 — Reprint crashed: sent listings never got Printful's size ids

- **What:** the curator's reprint of order TTS-00008 (the new "Jack-o" shirt) kept
  landing on the error page. Three defects, two of them mine:
  1. **Sent listings had no size ids.** Printful's reply to "create product" is a
     short summary with no per-size ids, so `sync_listing` stored none. Orders need
     them (`_line` refuses to build a line without one), so the order failed at
     approval. Worse, on a *re-send* the sizes kept the **previous product's** ids,
     so an order would have been made from the old shirt (The Wanderer is in that
     state until its ids are refreshed). `sync_listing` now clears the old ids and
     reads the new product back (a read-only call on the product it just created)
     to store each size's id; if that read fails the sizes stay blank, never stale.
     Send / Re-send now warn when any size is left without an id.
  2. **Reprint crashed instead of reporting.** `reprint()` created the new
     fulfilment first and built the order lines after, outside its error handling.
     It now builds the lines first (nothing is created if that fails), the view
     shows the reason, and a reprint Printful itself refuses is reported as such
     rather than as "created". A successful retry of an order stuck at "approved"
     now moves it to "submitted".
  3. **Stray rows.** Each crashed reprint left a "pending" fulfilment. Fulfilments
     #4 and #5 on TTS-00008 were marked cancelled (backup:
     `D:\TCData\db-before-reprint-cleanup.sqlite3`); nothing had reached Printful.
- **Files:** `shop/printful.py`, `shop/fulfillment.py`, `shop/manage_views.py`,
  `shop/console_views.py`, `shop/tests_reprint_and_sync_ids.py` (16 tests).
- **Verified:** 346 tests. With the old code restored, 11 of the 16 new tests fail,
  including the exact crash and the stale-id case.
- **Follow-ups:** the existing listings still hold no (Jack-o) or stale (The Wanderer)
  size ids until the curator presses "Refresh sizes from Printful" on each; the live
  app needs a restart to pick up this fix.

---

## 2026-10-03 — Reorder a listing's images (and choose the cover)

- **What:** images could be added and deleted but never reordered. Each image in
  the editor's Imagery section now has ← / → buttons and a "make cover" link; the
  first image is labelled Cover. The order is exactly what shoppers see in the
  carousel, and the first image is also the picture on the shop tile, in the cart
  and on the landing card (`Listing.primary_image`). Plain buttons rather than
  drag-and-drop, since those work reliably on a phone.
  - The whole set is renumbered 0..n-1 on every move, which also heals duplicate
    sort values (the old mock button created rows that all had 0).
  - New uploads now go to the end of the current order (they used `count()`, which
    could collide after a delete or move; a first upload into an empty listing
    starts at 0). Several files in one upload each get their own place.
  - Moving, adding or deleting an image returns to the Imagery section.
- **Files:** `shop/console_views.py` (`image_move`, `listing_add_image`,
  `image_delete`), `shop/urls.py`, `listing_edit.html`, `style.css`,
  `shop/tests_image_order.py` (18 tests).
- **Verified:** 330 tests (including that the public carousel and the cover follow
  the new order); and a real click in a browser against a scratch instance.

---

## 2026-10-03 — Color picker with Printful's real swatches, photo and link

- **What:** the listing editor's color field is now a dropdown whose options each
  carry a circle in Printful's own color value (a split circle for two-tone
  colors). Picking a color shows Printful's photo of that color on the blank and a
  "See this color on Printful" link that opens the blank's Printful page with that
  color selected.
  - New `printful.catalog_color_options()`, built from the variants already
    fetched for the old color list (no extra Printful call). Hex values and image
    URLs from the API are validated (six hex digits; https only) before they reach
    a style attribute or `<img>`; tests cover hostile values.
  - The link is *constructed*, not looked up (`dashboard_product_url`): Printful's
    API doesn't publish page URLs, so it follows the pattern of a real dashboard
    link the curator pasted (`/dashboard/custom/mens/t-shirts/<title-slug>?color=`).
    Tees only. If a link ever 404s, the title-slug rule needs adjusting.
  - An existing color that isn't a real Printful color is kept and flagged, as
    before. The plain text field remains the fallback when Printful is unreachable.
- **Files:** `shop/printful.py`, `shop/console_views.py`, `listing_edit.html`,
  `style.css`, `shop/tests_color_swatches.py` (new), `tests_print_positioning.py`.
- **Verified:** 312 tests; and in a real browser against a scratch instance (own
  database, mock Printful): the menu opens with an exact-color circle per option,
  picking updates the hidden field, trigger swatch and link, and Save stores it.
  The same run added a front print area through the new print-areas panel.
- **Not verified:** against real Printful data. The code expects `color_code`,
  `color_code2` and `image` on each catalogue variant; if Printful names them
  differently, colors show without circles/photos (nothing breaks).

---

## 2026-10-03 — "Generate mockups" no longer touches the real Printful

- **What:** found in the server log: someone pressed Generate mockups and it sent
  the live Printful account a create-product request with no variants (the stub
  fell through to the real client). Printful refused it ("No product variants"),
  so nothing was created, but it was a real write and it crashed the page.
  Now, with the real client, the button is hidden and the endpoint refuses
  without contacting Printful; only the local mock can fabricate mockups. Also
  fixed an older dev-only crash where the mock's file-less image rows broke the
  listing page.
- **Also:** `deploy/run_server.ps1` now lets cmd.exe do the log redirection;
  PowerShell 5.1's own redirection wrote UTF-16 into the logs. Takes effect when
  the supervisor next starts (next boot, or stop/start the task).
- **Files:** `shop/console_views.py`, `listing_edit.html`, `deploy/run_server.ps1`,
  `shop/tests_paid_order_pipeline.py`.
- **Verified:** 295 tests; the new launch line was run on a spare port and served
  requests with a readable log.

---

## 2026-10-03 — Several print areas on one shirt (large back + small front)

- **What:** a listing could only ever have one print. It can now carry a main
  print plus additional print areas, each with its own artwork, size and
  position, e.g. a large back print and a small front design.
  - New `ListingPrint` model (migration 0013): placement (front/back), optional
    own `Design` (blank = same artwork as the main print), size, position. The
    extra artwork reuses the existing private-artwork system, so signed links,
    console-only viewing and upload validation work unchanged. The main print
    stays on the Listing fields as before.
  - Listing page: new "Additional print areas" panel (add with an upload or an
    existing design, edit size/position, remove). Removing a print deletes
    artwork that was uploaded just for it, never one a listing or another
    print still uses. Clashes (two prints on one side) are refused, and an
    extra that ends up on the main print's side is skipped when sending.
  - Both sync (Send / Re-send) and orders for unsent listings now send every
    print area. The listing records a fingerprint of the layout when sent, and
    the "Printful still has the old version" banner now also fires when a
    print area's side, size, position or artwork changes (before, only the
    main print's side was tracked).
  - New "Upper left" / "Upper right" position presets for chest-style prints
    (as you look at the shirt). Position boxes are now kept inside the print
    area; before, e.g. "Higher" at 100% could produce negative coordinates.
- **Files:** `shop/models.py`, `shop/printful.py`, `shop/fulfillment.py`,
  `shop/console_views.py`, `shop/urls.py`, `listing_edit.html`, migration 0013,
  `shop/tests_multi_print.py` (34 tests).
- **Verified:** 291 tests, all mocked; nothing was sent to Printful.
- **Not verified (flagged):** the position/size numbers use a normalized square
  rather than Printful's real print-area size, and the box is square whatever
  shape the artwork is, so a non-square design may come out stretched or
  offset. Check the product preview on Printful after Re-send before selling
  a non-default size/position. Reading Printful's real print-area sizes would
  fix this (one read-only call; needs the curator's OK). Printful also bills
  each print area, so base cost needs raising by hand.

---

## 2026-09-29 — The app now auto-restarts after a reboot, sleep or crash

- **What:** until now, only Cloudflared (already a Windows service) survived a
  reboot; waitress had to be started by hand every time, which meant the site
  stayed down until someone noticed and ran the PowerShell block. Added
  `deploy/run_server.ps1`, a supervisor loop that sets `TCWEB_ENV_FILE`, starts
  waitress, and restarts it 5 seconds after it exits, forever; it refuses to
  start a second copy if port 8000 is already bound. A Windows Scheduled Task
  (`TShirtBrandWebsite`, set up by the curator with the command in README.md)
  runs it at startup, as the curator's own account (not SYSTEM or Local
  System), since the repo lives inside OneDrive and needs that account's sync
  context to read the files reliably.
- **Files:** `deploy/run_server.ps1` (new), `README.md`.
- **Verified:** killed the waitress process under a running supervisor and
  confirmed it noticed and relaunched the app within 5 seconds. Registering
  the scheduled task itself needs the curator's Windows password typed
  directly into `schtasks`, so that one step, and a real reboot test, are
  theirs to do and confirm.

---

## 2026-09-27 — Re-send button now looks inactive until sizes are matched

- **What:** the curator clicked Re-send to Printful with unmatched sizes; the
  server correctly refused, but from the button alone it looked like nothing
  happened. The button is now visibly muted (same look as a real `:disabled`
  button) whenever a size has no matched catalogue id, and clicking it in
  that state shows a small popup naming the unmatched sizes instead of
  submitting. The server-side refusal is unchanged — this is on top of it,
  not instead of it.
- **Files:** `shop/console_views.py` (context), `listing_edit.html`,
  `style.css` (`.btn--needs-match`, `.btn-popup`).
- **Verified:** 257 tests.

---

## 2026-09-25 — Changing a listing's shirt/color now reaches Printful

- **What:** the curator changed a template's shirt and a listing's color in the
  console and Printful didn't change. The console only edits the local copy;
  the Printful product is built once, at "Send to Printful", and nothing ever
  updated it. Also found: "Match sizes" and "Send" wrote into the same id
  field, so matching a listing already on Printful silently replaced the sync
  ids orders depend on (the same class of bug as the first failed order).
  - **Two id fields now.** `ListingSize.printful_variant_id` = the sync id
    Printful gave after sending (what orders use); new
    `printful_catalog_variant_id` = what Match sizes finds (what building a
    product uses). Matching no longer touches the sync ids. Migration 0012
    moves ids on never-sent listings to the catalogue field.
  - **Re-send to Printful** (connected listings): builds a *new* product from
    the listing as it is now and switches to it, with fresh external ids. The
    old product is deliberately not deleted; the console says to remove it by
    hand. Refuses until sizes are matched; a Printful failure leaves the
    listing on its old product.
  - **Out-of-date warning:** the listing records what it was sent as (shirt,
    color, placement); the page says "Printful still has the old version"
    when it has since changed. Listings sent before this get a gentle note.
- **Files:** `shop/models.py`, `shop/printful.py`, `shop/fulfillment.py`,
  `shop/console_views.py`, `shop/urls.py`, `listing_edit.html`, migrations
  0011–0012, tests (`tests_paid_order_pipeline.py` + updated older ones).
- **Verified:** 254 tests, all mocked; nothing was sent to Printful. The new
  external-id scheme for a second product is unverified against real Printful.
- **Follow-ups:** old Printful product(s) must be deleted by hand after a
  re-send. Orders already placed against an old product keep the old ids.

---

## 2026-09-25 — Legal-page corrections from an outside compliance read

- **What:** an outside review of the live site flagged wording that was wrong
  or looked unfinished. Fixed the clearly-wrong parts now (live pages + the
  `seed_pages` defaults); the rest is waiting on decisions (see follow-ups).
  - **Privacy:** "we do not log IP addresses ... or use third-party trackers"
    was not accurate: the *shop* stores no IPs (its visit log holds only
    referrer + campaign tag), but Cloudflare processes visitor IPs and every
    page loads fonts from Google Fonts. Reworded to say exactly that and added
    a "Services that handle data" list (Stripe, Printful, Cloudflare, email
    provider, Google Fonts). Replaced "last updated when published" with a date.
  - **Terms:** removed the public "have these reviewed before relying on them"
    line; added a last-updated date.
  - **Social:** the page listed placeholder handles; set to draft and hidden
    from the footer until real accounts exist (dropped from the seed too).
  - **Operating entity named** (curator supplied the name: The Tshirt Brand
    L.L.C.): footer, Privacy ("operated by ..."), a new "Who we are" section
    at the top of Terms, and every email footer (sender identity ahead of the
    postal address, per CAN-SPAM). New `SHOP_LEGAL_NAME` setting (env
    override; defaults to that name).
- **Files:** `shop/management/commands/seed_pages.py`; live `Page` rows
  (backup: `D:\TCData\db-before-legal-text.sqlite3`).
- **Verified:** live rows re-read after the update; seed file parses.
- **Follow-ups (need the curator's input, not guessed):** the operating
  entity's exact name/status for Terms, Privacy and footer; real production
  and shipping times for the shipping page (FTC mail-order rule); a fuller
  Terms of Service; textile-label check on the chosen blank; trademark/IP
  clearance for "I ski and I know things" and the brand name; self-hosting the
  fonts (removes the Google dependency); state sales-tax registration.

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
- **Added (same day):**
  - **"Refresh sizes from Printful"** button on a connected listing: re-reads
    the product from Printful (read-only, curator-clicked) and stores each
    size's real sync-variant id, matching by our external id, size/color
    fields, or the variant name; never guesses when a size matches more than
    one variant. Fixes listings whose stored ids aren't real sync variants.
  - **Front/back per listing** (`Listing.print_placement`, migration 0009):
    overrides the template's placement; blank keeps the template's.
  - Console order page: a note on a healthy fulfilment (e.g. "Reprint of #1")
    now shows green (new `--good` token) instead of red; red is kept for
    fulfilments actually in `problem`.
  - **Refund now also cancels the Printful order.** Found by the curator:
    refunding only reversed the Stripe payment and left the print order
    live at Printful (which would print, ship and bill for it). Refund goes
    first (if Stripe refuses, nothing changes and a message is shown instead
    of a crash), then every unshipped fulfilment is cancelled at Printful. If
    Printful won't cancel (e.g. already in production) the refund stands and
    the console says to cancel it by hand. Refunding twice is a no-op.
  - **"Cancel on Printful" button** on each unshipped fulfilment, without
    touching the payment (for orders already refunded). New `cancelled`
    fulfilment status (migration 0010); Printful's own "order canceled"
    notice no longer flips a fulfilment we cancelled into a Problem.
  - **Customer tracking page no longer shows internal notes.** Supplier
    errors and reprint reasons (`Fulfillment.problem_note`) were visible to
    anyone with the order link; they are now console-only, and a fulfilment
    in `problem` reads "We're looking into it" instead of "Problem — needs
    attention".
  - **"Not made in the US" warning** on the listing page when Printful's
    variant data shows a product available outside the US only (the
    Stanley/Stella STTU169 blank was EU/UK-only, so a US order was routed to
    Europe). Reads data already fetched for the color dropdown (no extra
    call) and stays silent when Printful gives no availability info.
    Written against an assumed reply shape (list or mapping of regions);
    unverified against a real product with US availability.
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
