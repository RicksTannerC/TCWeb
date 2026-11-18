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
| `shop/static/shop/console/console-legacy.css` | **Temporary** styling for pages not yet redesigned. Deleted at the end of the last phase. |
| `shop/static/shop/console/mountains.jpg`, `mountains-phone.jpg` | The scene photo (1672 px and 900 px wide). |
| `shop/templates/shop/manage/base.html` | The page skeleton from the handoff, with the side bar. |

The two photo addresses are set in an inline `<style>` in `base.html`, from `{% static %}`, because the site serves hashed
file names. There is no Content-Security-Policy on the site, so inline style and the small inline scripts are allowed.

## How a page is built

A redesigned page extends `base.html` and fills `{% block page %}` with bubbles (`g-bubble`, `g-dense`, `g-well`,
`g-cols`). A page not yet redesigned still fills `{% block console %}`, and `base.html` wraps it in one dense bubble.
That is the whole migration path: change `console` to `page`, replace the old classes, and delete the rules in
`console-legacy.css` that nothing uses any more.

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

1. **Shell, side bar, dashboard** (done): base template, assets, theme switch, dashboard. Other pages keep their content
   inside one legacy bubble.
2. **Listings and the listing editor:** one status strip and one Printful action, folded sections, dropdown status
   restyled, the new quick-create drop system (front and back designs).
3. **Orders** (queue and order page).
4. **Money, Content, Setup** (templates, collections, pages, messages).
5. **Sign-in step (`two_factor.html`), cleanup:** delete `console-legacy.css`, remove the console-only rules left in
   the storefront's `style.css` once nothing uses them.

## Deploying a phase

Templates and static files change together, so after pulling a phase on the machine that serves the site:

```
python manage.py collectstatic --noinput
```

then restart the site. A page that names a new static file before `collectstatic` has run fails to render (WhiteNoise's
manifest has no entry for it); the test suite has the same dependency on this machine.

## Printful product names (decided in phase 2)

Recorded here when phase 2 settles it. The scheme you asked for, if the product cannot be updated in place: a version
in the title, `1.0.0`, where the first number is a change to the whole listing, the second is the front print, and the
third is the back print, shown on the console and on Printful so the product to delete is obvious.
