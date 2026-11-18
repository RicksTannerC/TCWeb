# The console's design (the "glass" look)

The management console (`/manage/`, `manage.shopthetshirtbrand.com`) is being redesigned to the TCR-FileOS glass look, in
phases. This file records how it is built, what was added to the handoff, what is deliberately different, and the
naming convention for Printful products. The original handoff is kept unchanged in
[`docs/design/glass-handoff.md`](design/glass-handoff.md); its Drive/Home patterns (appendix F) are in
[`docs/design/glass-patterns-reference.css`](design/glass-patterns-reference.css) for the phases that need tiles.

## Where things live

| File | What it is |
|---|---|
| `shop/static/shop/console/glass-tokens.css` | The colors and glass values, light and dark. Appendix A of the handoff, verbatim. |
| `shop/static/shop/console/page.css` | Page-level values (appendix B), without the two photo paths. |
| `shop/static/shop/console/glass.css` | The shared stylesheet (appendix C), verbatim. Do not edit; add to `console.css`. |
| `shop/static/shop/console/glass-menu.js` | The side bar's helper (appendix D), verbatim. |
| `shop/static/shop/console/console.css` | **Our** additions: everything prefixed `c-`, plus a few clearly labeled gap fills. |
| `shop/static/shop/console/console.js` | The light / dark / device switch and the iPhone touch handler (rule 13). |
| `shop/static/shop/console/mountains.jpg`, `mountains-phone.jpg` | The scene photo (1672 px and 900 px wide). |
| `shop/templates/shop/manage/base.html` | The page skeleton from the handoff, with the side bar. |

The two photo addresses are set in an inline `<style>` in `base.html`, from `{% static %}`, because the site serves hashed
file names. There is no Content-Security-Policy on the site, so inline style and the small inline scripts are allowed.

## How a page is built

A redesigned page extends `base.html` and fills `{% block page %}` with bubbles (`g-bubble`, `g-dense`, `g-well`,
`g-cols`). Every console page is built this way now; there is no fallback wrapper. The pattern is one `g-bubble`
(a header, or a summary) and one `g-dense` (the form, table or list), with `g-well` panels inside, so a screen has two
blurred bubbles plus the side bar. Page-level helpers we added: `c-head` (title row), `c-stack` (vertical rhythm),
`c-cols` / `c-pair` (responsive columns), `c-label` (the small uppercase heading), `c-row` / `c-list` (list rows),
`c-fold` (a native `<details>` section), `c-stats` / `c-stat` (small figures), `c-switch` / `c-seg` (the Drive-style
segmented switch).

Rules carried over from the handoff, in the short form we check against: never nest a bubble in a bubble (use
`g-well`); two or three blurred bubbles per screen (the side bar counts); tables, forms and long lists inside **one**
`g-dense`; text on glass is `--ink` or `--glass_muted` only; touch targets at least 44 px; never color alone for a
status; no new colors, radii or effects.

## What we added or changed (and why)

Everything the handoff lists under "known gaps" is filled the smallest way that uses only existing tokens.

- **Side bar content:** Dashboard, Listings, Orders, Money, Content, Setup; then the theme switch, Shop (the storefront,
  where the handoff puts "Home"), and Log out. The handoff's theme item is a link (`?theme=dark`); ours is a button that
  cycles device → light → dark and stores the choice in the same `tts-theme` key the storefront uses.
- **Log out** is a `POST` form (Django requires it). `.g-side form { display: contents }` lets its button sit in the bar
  like the link items.
- **Notices:** Django's messages render as `.g-banner` (success `is-ok`, warning `is-warn`, error the red default). `info`
  had no variant, so `.g-banner.is-info` (neutral border, soft fill) was added.
- **Status chips:** `.g-tag.is-bad` and `.g-tag.is-wait` were added next to the handoff's `is-done` and `is-open`.
- **Dependencies:** the handoff says "no libraries". The console keeps htmx and Alpine (both self-hosted under
  `shop/static/shop/vendor/`, nothing from another host) because the color picker, the Printful search and the menus use them.
- **Fonts:** the console now uses the system font stack from the handoff. The storefront keeps its own fonts.
- **Dialogs:** browser `confirm()` stays for now; the handoff has no modal.
- **`g-` vs `c-`:** `g-` classes come from the handoff and are never redefined here; `c-` classes are ours.

## Phases

1. **Shell, side bar, dashboard** (done): base template, assets, theme switch, dashboard.
2. **Listings and the listing editor** (done): one Printful strip with one action (Send / Update), folded sections, the
   status dropdown restyled, the quick-create drop (front and back designs), product versions (below).
3. **Orders** (done): the queue, and the order page with the approval first and the rest folded.
4. **Money, Content, Setup** (done): pricing table and books, messages and pages, templates, collections.
5. **Sign-in step and cleanup** (done): the second-factor page is a glass page; `console-legacy.css` is deleted; the
   console-only rules were removed from the storefront's `style.css` (`.row-2` and `.field` stay, the storefront uses them).

Not done, on purpose: the old Printful routes (`match-printful-sizes`, `resend-to-printful`, `refresh-printful-sizes`,
`refresh-preview`) still exist and have tests, but nothing links to them. Remove them together with their tests when
you are sure you will not want separate buttons back.

## Deploying a phase

Templates and static files change together, so after pulling a phase on the machine that serves the site:

```
python manage.py collectstatic --noinput
```

then restart the site. A page that names a new static file before `collectstatic` has run fails to render (WhiteNoise's
manifest has no entry for it); the test suite has the same dependency on this machine.

## Printful product names and versions

**Why versions.** Printful's v1 API has `PUT /store/products/{id}` (modify a sync product) and it accepts partial
updates, but the public documentation does not say whether a `files` array on a variant replaces or merges, and a
`sync_variants` array deletes any variant left out of it. v2 has no product management at all. Nothing has been
verified against a real product, so the console does **not** use it: an update builds a **new** product, as the
re-send always did, and leaves the old one in the Printful store to be deleted by hand. To make the old one easy to
find, every product carries a version in its name.

**The name.** `<title> <whole>.<front>.<back>`, for example `Relativity 1.1.0`. The same text is shown in the console.

| Number | Counts changes to | Examples |
|---|---|---|
| first (whole) | the listing as a whole | shirt, color, or a rebuild with nothing else to show for it; also a change to a product sent before sides were recorded |
| second (front) | the front print | its artwork, size or position |
| third (back) | the back print (every print that is not the front) | its artwork, size or position, or adding or removing it |

A whole-listing change starts the front and back counts again (`2.0.0`). A front-only change is `1.1.0`, back-only
`1.0.1`, both `1.1.1`. The first send of a listing is `1.0.0`. The version moves only when a new product is actually
created, never when a send is refused. A product sent before versions existed is named just `<title>`; the message
after its first update says so, and its next version is `2.0.0`.

**Where it lives.** `Listing.version_whole/front/back`, plus `printful_sent_front` / `printful_sent_back` (the print
fingerprints split by side, recorded on every send). The rules are in `tshirtbrand/core/catalogue` (`Version`,
`next_version`, `product_name`); the persistence adapter works out which side changed.

**Trying an in-place update later.** It needs a supervised test on one throwaway product (you approve the call): send
a `PUT` with all variant ids and changed files, read the product back, and compare. Only then should the console offer
"update in place".

## The one Printful action

The listing editor has one button for Printful. It sends the listing if it is not on Printful, otherwise builds the new
version, and matches sizes first when any size has no Printful variant yet. It replaces Match sizes, Send, Re-send and
Refresh sizes (their URLs still exist). After an update the page asks Printful for the preview by itself, every 20
seconds, up to five times (read-only calls made because you pressed Update); opening the page alone never calls
Printful.
