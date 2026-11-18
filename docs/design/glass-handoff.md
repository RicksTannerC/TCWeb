# The TCR-FileOS "glass" look: a design hand-off

**What this file is.** A complete, self-contained description of the look of three finished pages (the Home dashboard, the Drive file manager and the Design app's style guide), written so another Claude chat can redesign a different page to match, with no access to the original project. Everything needed is in this file: the description, the rules, and (in the appendices) the full stylesheet, both color modes, the page skeleton and the menu script. The only thing it cannot contain is the background photo; see section 2.

**How to use it.** Paste this whole file into the other chat and say something like:
> Here is my site's design system. Redesign the page below to match it exactly. Use the classes and rules in this file, do not invent new colors or effects, and tell me about anything this file does not cover. [then describe or paste the page]

---

## 1. The look in one paragraph

A still photo of mountains sits behind every page. Sections do not sit on a flat page; each one floats on a frosted-glass "bubble" (a rounded, blurred, slightly tinted panel with a thin bright edge, brightest along the top, and a faint gloss). The photo stays pinned while the page scrolls, so the bubbles slide over it like looking out of a window. A slim floating glass side bar on the left holds the navigation as icons, and an arrow at its top opens it into icons with titles. The palette is quiet olive green, warm cream and dark moss. There is a full light mode and a full dark mode, and both follow the device. Controls respond the same way everywhere: they tint toward olive and grow slightly under the pointer, and shrink slightly when pressed. It is calm, modern and soft, with large corners, generous touch targets and no clutter.

The site is used mostly on an iPhone, so **phone first** (Safari on iPhone is the hardest browser for it) and desktop second.

## 2. The photo (the one thing not in this file)

Two copies of one mountain photograph: a large one (about 1672 by 941, around 217 KB) for screens wider than 700 px and a small one (about 900 by 507, around 67 KB) for phones. The page loads them through two CSS variables (`--scene_image`, `--scene_image_phone`, see appendix B). Attach the photo to the chat (it is a separate file; I will send it with this one), or substitute any landscape photo that is mid-toned with some detail; the rules below were measured against this specific photo, so with a different one, re-check text contrast over its brightest and darkest areas.

## 3. Colors (design tokens)

Always write `var(--name)`. Never hard-code a hex value in a page. Dark mode uses the **same token names** with different values, so a page needs no dark-mode rules of its own.

| Token | Light | Dark | Meaning |
|---|---|---|---|
| `--bg` | #F7F5EF | #12150F | Solid page and form-field background |
| `--ink` | #2B2A22 | #F3EEDD | Primary text and icons |
| `--accent` | #6B7A45 | #A9BB78 | Olive: the one "interactive and important" color (primary buttons, current item, focus ring, link underline) |
| `--warm` | #D69E5A | #E3B070 | Amber: a second, friendlier accent; "open" or "waiting" states |
| `--good` | #4F7942 | #A8D492 | Success |
| `--bad` | #B3261E | #FF9A90 | Errors and destructive actions |
| `--soft` | #EEF0E4 | #2C3224 | Quiet fill for tags and hovered rows |
| `--line` | #E1DED1 | #4A5040 | Borders and rules |
| `--muted` | #80806B | #C9C9B1 | Secondary text on a solid background (not on glass) |
| `--glass_muted` | #3A3A2A | #D2D2BC | **Secondary text on glass** |
| `--on_accent` | #FFFFFF | #14170F | Text on an olive button |
| `--glass_tint` | #FFFFFF | #12150F | The bubble's tint color |
| `--glass_opacity` | 0.60 | 0.50 | Bubble tint strength |
| `--glass_dense_opacity` | 0.82 | 0.78 | Dense bubble tint strength (tables, forms) |
| `--glass_edge` | rgba(255,255,255,.80) | rgba(255,255,255,.30) | The thin bright edge |
| `--glass_gloss` | rgba(255,255,255,.30) | rgba(255,255,255,.08) | Gloss across the top |
| `--glass_shadow` | rgba(40,46,28,.20) | rgba(0,0,0,.45) | Shadow |
| `--glass_blur` | 14 | 14 | Blur radius (unitless; the CSS multiplies by 1px) |
| `--glass_wash` | rgba(244,242,234,.08) | rgba(8,10,6,.55) | A light or dark veil over the photo |
| `--glass_radius` | 24 | 24 | Bubble corner radius (unitless) |
| `--glass_saturate` | 1.2 | 1.2 | Color boost behind the glass |
| `--page_edge` | #7C7C79 | #373835 | One solid color behind everything (see section 8) |
| `--cream` | #F3EEDD | | Text on the photo itself (the end-of-page bar) |
| `--dark_bg` | #11140F | | Fallback behind the photo |

Brand feel: olive means "brand" and also "good", so **never use green alone to carry a meaning** (for money, pass/fail and so on, add a word or an icon). Status in a list is shown by a colored edge **and** words.

## 4. Type and spacing

- **System font only**: `-apple-system, "Segoe UI", sans-serif`. No web fonts, no icon fonts, no libraries, nothing loaded from another host.
- Body 16 px (`--base_font_size`), line height 1.45. Page titles about 1.4 to 1.5rem, weight 600 to 700. Section headings in lists are small caps-style: .8rem, uppercase, letter-spacing .06em, weight 600, in `--glass_muted`. Small text is .85em, muted.
- Spacing is in `rem` (.25, .4, .6, .75, 1, 1.25). Bubble padding 1rem by 1.25rem. Gaps between bubbles 1rem. Main content is at most 1100 px wide, centered; a 5.5rem left gutter keeps clear of the side bar.
- Corners: bubbles 24 px; things inside a bubble use fractions of that (buttons .5, wells and tiles .6, inputs .4); tags and the side bar's ends are fully round (pill/capsule). **One radius family**; do not invent other radii.
- Tone of voice (for any text you write): plain words, short sentences, US spelling (color, organize, center, gray), sentence case for titles, no jargon.

## 5. The page skeleton (copy this exactly)

Order matters. In order, inside `<body class="g-page">`:
1. `<div class="g-edgefade">`: a soft fade at the very top that blends the photo into the phone's status bar.
2. A "skip to content" link (`.g-skip`).
3. The side bar's three **sibling** elements: `input#g-side-open` (a hidden checkbox), `label.g-side-scrim` (tap-outside layer), `nav#g-side.g-bubble.g-rail.g-side`. **No wrapper between them**; the open/closed state works through the CSS `~` sibling selector.
4. `div.g-shell` containing: `div.g-scene` (the pinned photo), `main.g-main.g-side-pad` (the content, as bubbles), and `footer.g-footbar` (a fade into the page color with a pill "Back to top" button).
5. The menu script (appendix D).

A complete minimal page is in appendix E. The side bar needs **no script to open and close** (the arrow is a label of a checkbox); the small script only adds Esc, closing on a link tap, resetting after Back/Forward, and screen-reader state.

## 6. Components (all classes are prefixed `g-`)

| Class | What it is |
|---|---|
| `.g-bubble` | The main glass panel. Blurred, tinted, bright top edge, gloss, soft shadow. Use for sections and cards. |
| `.g-dense` | A more opaque bubble for **tables, forms and long lists**, so small text stays readable over a busy photo. |
| `.g-well` | A flat panel **inside** a bubble (no blur of its own). Use this instead of nesting a bubble. |
| `.g-cols` | A responsive grid of bubbles: one column on a phone, more as the width allows (min 16rem each). |
| `.g-row` | A wrapping flex row with .6rem gaps, for buttons and tags. |
| `.g-btn` + `-primary` / `-secondary` / `-danger` | Buttons, 44 px (2.75rem) minimum height. Primary is solid olive; secondary is glass with an olive outline; danger is tinted red and turns solid red on hover. |
| `.g-field` + `.g-input` | A label above an opaque input (always solid `--bg`, so the text never sits on the photo). Selects use `.g-input` too. `aria-invalid="true"` shows a red border. |
| `.g-tag` (+ `.is-done` green tint, `.is-open` amber tint) | A small pill chip. |
| `.g-banner` (+ `.is-ok`, `.is-warn`) | A notice on a solid tinted fill with a colored border; red by default. |
| `.g-table` inside `.g-table-wrap` | A table: uppercase small headers, hairline rules, row hover tint. Put it in **one** `.g-dense` bubble; the wrapper scrolls sideways on a phone (give it `tabindex="0" role="region" aria-label`). |
| `.g-figure` | One big key number (2.5rem, bold) with an olive-to-green text gradient. Only for the single number that matters. |
| `.g-muted`, `.g-small` | Secondary text color; .85em. |
| `.g-rail`, `.g-rail-item`, `.g-rail-rule`, `.g-side-spacer` | The side bar's parts. An item is a 44 px square icon button (24 px stroke icon), with a `.g-rail-label` title that fades in when the bar opens. |
| `.g-side-pad` | On `<main>`: keeps content clear of the slim bar. |
| `.g-sr-only`, `.g-skip` | Screen-reader-only text; the skip link. |
| `.g-footbar` | End of page. |

Patterns built on top of these, in the Drive and Home pages (full CSS in appendix F): a **tile** (a big glass card with a 4:3 preview on top, a bold two-line name, small dates; the name's link is stretched over the whole card so the card is one button); a **Tiles | List switch** (two toggle buttons in one pill; the one that is on is filled **and** outlined); **list rows** inside one dense bubble; a **disclosure menu** (a native `<details>` that unfolds in place, no script); and Home's **app card** (a well that is one big button showing a name, counts and short lines).

## 7. Behavior: the one response every control shares

- **Hover or keyboard focus**: tint toward olive (`color-mix(in srgb, var(--accent) 26%, ...)`) and grow (`scale(1.04)`; icons in the slim bar `1.16`).
- **Pressed**: shrink (`scale(.97)`; icons `.94`) with a stronger olive tint (44%), which fades back slowly on a finger lift.
- **Timing**: a springy ease, `cubic-bezier(.34, 1.56, .64, 1)`, about .25 to .3 s; the side bar widening is `.45s cubic-bezier(.4, 0, .2, 1)`.
- **Focus ring**: 2px ink outline plus a soft olive halo (`box-shadow: 0 0 0 5px`), never removed.
- **Only on devices that can hover** (`@media (hover: hover)`) does hover growth apply, so a phone does not get stuck "hovered" after a tap.
- **Reduced motion** (`prefers-reduced-motion: reduce`): no growth or transitions, tint only.
- **Current page** in the side bar is solid olive **and** has a 2px ink outline (never color alone).

## 8. Hard rules (each one came from a real failure; keep them)

**Layout and glass**
1. **Never nest a bubble inside a bubble.** Use `.g-well` inside a bubble.
2. **Blur costs a layer per bubble**, most of all on a phone. Keep it to two or three blurred bubbles per screen (the side bar counts as one). Tables, forms and long lists go inside **one** `.g-dense` bubble.
3. One scene per page. The photo is a **pinned layer inside the page** (`position: sticky`, taller than the screen), not `background-attachment: fixed` (iPhone Safari ignores it) and not `position: fixed` (iPhone Safari clips it between its bars and leaves a bare band).
4. The `<body>` paints nothing (`background: none`). The `<html>` element paints the solid `--page_edge` color, because iPhone Safari paints its status strip and toolbar from the page color, and it needs **one solid color**, not a gradient.
5. Add `viewport-fit=cover` to the viewport meta so the scene reaches under the phone's bars.
6. No dark or colored fixed layer may touch the top or bottom screen edge (iOS tints its bars from it). The menu's tap-outside layer has no color and stops 12 px short of the edges for the same reason.
7. Modals and toasts need a `z-index` above 20 (menu 20, its tap layer 19, edge fade -1, scene -2).
8. Where the browser cannot blur, or the device asks for less transparency, bubbles become solid (already in the CSS).

**Text and contrast**
9. **Text on a bubble is `--ink` or `--glass_muted` only.** Never put `--accent`, `--good` or `--bad` as text color on glass. Links are `--ink` with a 2px olive underline.
10. Small text must reach WCAG 4.5:1 in both modes over the brightest and darkest parts of the photo; do not lower a bubble opacity to make it prettier. Inputs, tags and notices use **solid fills** so they read the same over any part of the photo.
11. Touch targets are at least 44 px (2.75rem). Never use color alone to carry a status or "current" state.

**iPhone Safari lessons**
12. A layer that is a sibling of a separately composited sticky layer can fail to repaint after a long scroll. The top edge fade therefore has its own compositing layer (`transform: translateZ(0); backface-visibility: hidden`). If something "vanishes until you scroll a little", do this first.
13. Safari shows `:active` states only on a page that has a touch handler. Where inline attributes are allowed, `<body ontouchstart="">` does it. Where the page's security policy forbids inline script, add a one-line file instead (`document.addEventListener('touchstart', function(){}, {passive:true})`).
14. A `<details>` or popover menu inside a tile must unfold **in place**, not float as a popover (it would clip or leave a small screen).
15. Long names: always `overflow-wrap: anywhere`; in tiles clamp to two lines (`-webkit-line-clamp: 2`).
16. A flex search form: `.g-input` is `width: 100%`, so inside a narrow row set `flex: 1 1 0; width: auto; min-width: 0` or the button is pushed off the screen.

**Delivery**
17. Every class starts with `g-`, so this stylesheet can sit beside an older page's styles while a page is converted.
18. No external fonts, libraries, icon fonts or requests to other hosts. Icons are **inline SVG** on a 24x24 viewBox: `fill: none; stroke: currentColor; stroke-width: 1.8 (2 for the arrow); stroke-linecap: round; stroke-linejoin: round`. Minimal outline style; the logo (if the site has one) keeps its own fixed colors and is never recolored.
19. If a page's security policy forbids inline `<style>` or inline script, serve the CSS and the one script as separate files from the same address (appendices are written as separate files for this reason).
20. Keep any script free of the three-character openers of template syntax if the file will be included through a template engine.

## 9. Side bar content conventions

- Order: the arrow; the app's own places; a spacer; a rule; the light/dark/device switch; "Home" last.
- Same icons and labels on every page of the app. `aria-current="page"` marks **the page you are on and nothing else**; a place that contains the current page is not marked when a deeper item is.
- A **Back** item goes right after the arrow (arrow-left icon), hidden at the top level.
- A folder or sub-place trail may follow the app's own places, after a rule; each item is a plain `.g-rail-item` with an ellipsized label.
- More than about 8 items scrolls inside the bar with no visible scrollbar.
- Open, the bar lies over the page (it does not push it), up to 15rem wide.

## 10. Known gaps (things this look does not yet have; do not invent them without asking)

Not yet in the shared stylesheet, so each page has re-invented them in its own CSS: a tile utility, a segmented switch, list rows, a disclosure menu, extra status chips (failed, waiting), a picture frame, a small copyable text line, a modal, a toast, empty and loading states. The 'key figure' green gradient and some small look tweaks (glass visibility in dark mode, narrower side margins on a phone) are undecided. Contrast was measured only for the default values above. The menu script was tested in a desktop browser; behavior on a real iPhone is unconfirmed.

---

# Appendices (copy these into the new site as files)

The files are meant to be used together as in appendix E. Names below are suggestions.

## Appendix A: `glass-tokens.css` (all colors and glass values, light and dark)

Light is the default; dark applies when the device is set to dark; `data-theme="light|dark"` on `<html>` forces one.

```css
/* Generated by `manage.py export_theme` from the Design app's current theme record. Do not hand-edit:
 * re-run the export instead. Theme name: 'default'. */
:root {
  /* Brand */
  --accent: #6B7A45;
  --warm: #D69E5A;
  /* Surface */
  --bg: #F7F5EF;
  --ink: #2B2A22;
  --line: #E1DED1;
  --muted: #80806B;
  --soft: #EEF0E4;
  /* Status */
  --good: #4F7942;
  --bad: #B3261E;
  /* Arrival surface (the photo) */
  --dark_bg: #11140F;
  --cream: #F3EEDD;
  --glass_panel: rgba(255,255,255,0.08);
  --glass_accent: rgba(138,154,90,0.35);
  --glass_accent_hover: rgba(138,154,90,0.55);
  /* Scale */
  --radius: 8px;
  --base_font_size: 16px;
  /* Glass, both modes */
  --glass_radius: 24;
  --glass_saturate: 1.2;
  /* The light look (the default) */
  /* Colors */
  --bg: #F7F5EF;
  --ink: #2B2A22;
  --accent: #6B7A45;
  --warm: #D69E5A;
  --line: #E1DED1;
  --muted: #80806B;
  --soft: #EEF0E4;
  --good: #4F7942;
  --bad: #B3261E;
  /* Text on glass and on buttons */
  --glass_muted: #3A3A2A;
  --on_accent: #FFFFFF;
  /* The bubble */
  --glass_tint: #FFFFFF;
  --glass_opacity: 0.6;
  --glass_dense_opacity: 0.82;
  --glass_edge: rgba(255,255,255,0.80);
  --glass_gloss: rgba(255,255,255,0.30);
  --glass_shadow: rgba(40,46,28,0.20);
  --glass_blur: 14;
  --glass_wash: rgba(244,242,234,0.08);
  color-scheme: light;
}

/* The dark look, for a device set to dark (unless light was chosen on the page). */
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    /* Colors */
    --bg: #12150F;
    --ink: #F3EEDD;
    --accent: #A9BB78;
    --warm: #E3B070;
    --line: #4A5040;
    --muted: #C9C9B1;
    --soft: #2C3224;
    --good: #A8D492;
    --bad: #FF9A90;
    /* Text on glass and on buttons */
    --glass_muted: #D2D2BC;
    --on_accent: #14170F;
    /* The bubble */
    --glass_tint: #12150F;
    --glass_opacity: 0.5;
    --glass_dense_opacity: 0.78;
    --glass_edge: rgba(255,255,255,0.30);
    --glass_gloss: rgba(255,255,255,0.08);
    --glass_shadow: rgba(0,0,0,0.45);
    --glass_blur: 14;
    --glass_wash: rgba(8,10,6,0.55);
    color-scheme: dark;
  }
}

/* Forced by the light / dark / device switch. */
:root[data-theme="dark"] {
  /* Colors */
  --bg: #12150F;
  --ink: #F3EEDD;
  --accent: #A9BB78;
  --warm: #E3B070;
  --line: #4A5040;
  --muted: #C9C9B1;
  --soft: #2C3224;
  --good: #A8D492;
  --bad: #FF9A90;
  /* Text on glass and on buttons */
  --glass_muted: #D2D2BC;
  --on_accent: #14170F;
  /* The bubble */
  --glass_tint: #12150F;
  --glass_opacity: 0.5;
  --glass_dense_opacity: 0.78;
  --glass_edge: rgba(255,255,255,0.30);
  --glass_gloss: rgba(255,255,255,0.08);
  --glass_shadow: rgba(0,0,0,0.45);
  --glass_blur: 14;
  --glass_wash: rgba(8,10,6,0.55);
  color-scheme: dark;
}
:root[data-theme="light"] {
  /* Colors */
  --bg: #F7F5EF;
  --ink: #2B2A22;
  --accent: #6B7A45;
  --warm: #D69E5A;
  --line: #E1DED1;
  --muted: #80806B;
  --soft: #EEF0E4;
  --good: #4F7942;
  --bad: #B3261E;
  /* Text on glass and on buttons */
  --glass_muted: #3A3A2A;
  --on_accent: #FFFFFF;
  /* The bubble */
  --glass_tint: #FFFFFF;
  --glass_opacity: 0.6;
  --glass_dense_opacity: 0.82;
  --glass_edge: rgba(255,255,255,0.80);
  --glass_gloss: rgba(255,255,255,0.30);
  --glass_shadow: rgba(40,46,28,0.20);
  --glass_blur: 14;
  --glass_wash: rgba(244,242,234,0.08);
  color-scheme: light;
}
```

## Appendix B: `page.css` (page-level values every page must set)

Change the two photo paths to wherever the photo is served from (use absolute paths; a relative `url()` inside a custom property resolves differently by browser).

```css
/* The page-level values the shared glass.css asks every page to set (see the top of glass.css). Drive serves this as its own file
 * because its page policy allows no inline <style>: this is what the Design app's style guide and Home carry inline.
 *  - the two scene photos (Drive serves its own copies, byte for byte the Design app's two scene photos);
 *  - --page_edge, the one SOLID colour behind everything, the tone of the photo's top edge after the wash (light #7C7C79, dark #373835);
 *    iPhone Safari reads its status strip and toolbar colour from the page colour, so it must not be a gradient;
 *  - the border-box reset glass.css assumes.
 * Absolute paths on purpose: a url() inside a custom property is resolved by the browser in different places, a path from the root is not. */
:root {
  --scene_image: url("/static/mountains.jpg");
  --scene_image_phone: url("/static/mountains-phone.jpg");
}
html { --page_edge: #7C7C79; background: var(--page_edge); scroll-behavior: smooth; }
@media (prefers-color-scheme: dark) { html:not([data-theme="light"]) { --page_edge: #373835; } }
html[data-theme="dark"] { --page_edge: #373835; }
@media (prefers-reduced-motion: reduce) { html { scroll-behavior: auto; } }
* { box-sizing: border-box; }
```

## Appendix C: `glass.css` (the shared stylesheet, complete)

```css
/* glass.css -- the shared glass stylesheet. Plain CSS, no script, no outside request.
 *
 * It needs the tokens from `manage.py export_theme` (the full export: light default, dark for devices set to dark, forced
 * overrides) and two image addresses the PAGE sets, because each app serves its own copy of the photo:
 *     :root { --scene_image: url("/scene/mountains.jpg"); --scene_image_phone: url("/scene/mountains-phone.jpg"); }
 * Page skeleton:   <body class="g-page"><div class="g-scene" aria-hidden="true"></div> ... </body>
 *
 * Rules this file keeps (docs/product/briefs/lane-design-glass-theme.md):
 *  - The scene is a pinned (position: sticky) LAYER inside the page, taller than the screen. Not background-attachment: fixed
 *    (Safari on iPhone ignores it) and not position: fixed (Safari on iPhone clips it between its bars, leaving a bare band).
 *  - Blur is modest and costs a layer per bubble: put at most two or three blurred bubbles on a screen, never nest one
 *    inside another (use .g-well for a panel inside a bubble), and keep long lists inside ONE .g-dense bubble.
 *  - Text on a bubble is --ink or --glass_muted only; links are --ink with an accent underline. The tests compute these against
 *    the real photo's brightest and darkest areas after blur. Do not put --accent, --good or --bad text straight on glass.
 *  - Every class is prefixed g- so this file can sit beside an older page's styles while an app moves over.
 *  - Glass numbers (--glass_blur, --glass_radius, --glass_opacity ...) are unitless; calc() turns them into pixels.
 */

/* ---- the page and the scene -------------------------------------------------------------------------------------- */
.g-page, .g-scope {
  color: var(--ink);
  font-family: -apple-system, "Segoe UI", sans-serif;
  font-size: var(--base_font_size);
  line-height: 1.45;
}
/* The body paints nothing, or it would cover the scene. The page sets   html { background: var(--bg); }   for the overscroll colour. */
.g-page { margin: 0; min-height: 100vh; background: none; }
/* On a phone the page asks (viewport-fit=cover) to draw under the status bar and the bottom toolbar, so the scene can reach
   the bottom edge. The content keeps clear of both areas, and the top area is a bar of the sign-in page's dark grey. */
.g-page { padding: 0; }
/* The page's box. The scene layer is taller than the screen and would hang below the end of the page and let you scroll past
   the last bar; clipping here ends the page exactly at the bar. (overflow: clip does not make a scroll container, so the scene
   still pins to the screen; a browser too old for it gets overflow: hidden, where the scene scrolls with the page instead.) */
.g-shell { position: relative; padding-top: env(safe-area-inset-top, 0px); overflow: hidden; overflow: clip; }
/* The end of the page: a grey fade (the page colour) with a Back to top button. Kept short (the owner asked for a shorter bar): the phone paints its toolbar below the page, so the button needs only a small cushion. The photo runs behind it. */
.g-footbar {
  /* The mirror of the strip at the top: the photo (the scene runs behind this bar) fades into the page colour, which is the colour the phone paints its toolbar with, so the page ends with no seam. */
  position: relative; margin-top: 1.5rem; text-align: center; background: var(--dark_bg); background: linear-gradient(to bottom, transparent 0%, color-mix(in srgb, var(--page_edge, var(--dark_bg)) 3%, transparent) 10%, color-mix(in srgb, var(--page_edge, var(--dark_bg)) 10%, transparent) 20%, color-mix(in srgb, var(--page_edge, var(--dark_bg)) 22%, transparent) 30%, color-mix(in srgb, var(--page_edge, var(--dark_bg)) 35%, transparent) 40%, color-mix(in srgb, var(--page_edge, var(--dark_bg)) 50%, transparent) 50%, color-mix(in srgb, var(--page_edge, var(--dark_bg)) 65%, transparent) 60%, color-mix(in srgb, var(--page_edge, var(--dark_bg)) 78%, transparent) 70%, color-mix(in srgb, var(--page_edge, var(--dark_bg)) 90%, transparent) 80%, color-mix(in srgb, var(--page_edge, var(--dark_bg)) 97%, transparent) 90%, var(--page_edge, var(--dark_bg)) calc(100% - 6px), var(--page_edge, var(--dark_bg)) 100%); color: var(--cream);
  padding: 1.1rem 1rem calc(2.5rem + env(safe-area-inset-bottom, 0px));
}
/* (owner, 2026-11-16: a thin line between the end bar and the bottom of the page) The bar's pixel edge and the shell's clip edge can differ by a row, and in that row the photo showed. This covers it with the page colour; the shell clips anything beyond its own end, so it adds no length. */
.g-footbar::after { content: ""; position: absolute; left: 0; right: 0; top: 100%; height: 4px; background: var(--page_edge, var(--dark_bg)); }
.g-page .g-footbar a {
  display: inline-block; min-width: 12rem; padding: .85rem 1.8rem; font-weight: 600; text-decoration: none;
  color: var(--cream); background: rgba(17,20,15,.6); border: 1px solid rgba(255,255,255,.28);
  border-radius: 999px; transition: background-color .2s ease, transform .25s cubic-bezier(.34, 1.56, .64, 1);
}
.g-page .g-footbar a:focus-visible { background: rgba(17,20,15,.78); transform: translateY(-1px); outline: 2px solid var(--cream); outline-offset: 2px; }
@media (hover: hover) { .g-page .g-footbar a:hover { background: rgba(17,20,15,.78); transform: translateY(-1px); } }
.g-page .g-footbar a:active { transform: scale(.97); }
/* The browser paints the strip over the clock in the page colour (the page sets --page_edge to the tone of the photo's top edge); this fades that colour into the picture so there is no seam.
   PART OF THE PAGE, NOT FIXED (owner, iPhone, 2026-11-16, in the end: the top gradient "should scroll away with the screen", i.e. belong to the top of the page, not stay in the window. Earlier words: "the gradient stays on the same spot of the screen rather than staying with the top of the page"). A fixed layer is
   laid out by the phone below its top safe area and above its bottom one, and when you scroll the phone's strip turns see-through, so a fixed fade started a
   clock's height down with bare photo above it. A sticky layer is painted like the page itself, under both bars (the photo, .g-scene, has been sticky for the
   same reason), so these pin to the real top and bottom of the screen. Each is a layer with no room of its own in the page (its negative bottom margin cancels its
   height) whose first part, as tall as the safe area, is solid page colour (the part under the phone's own strip or toolbar) and whose second part is the fade. */
.g-edgefade {
  /* z-index -1: between the photo (-2) and everything else. The fades blend the photo into the browser's bars, but the page's own
     content (bubbles, text, the menu) is never faded, because it paints above them. */
  --g_fade_h: 4.5rem;
  position: absolute; top: 0; left: 0; right: 0; z-index: -1; pointer-events: none;   /* part of the page: it scrolls away with the page's top */
  height: var(--g_fade_h);
  /* Its own compositing layer (owner, iPhone, 2026-11-17: scroll to the very bottom and back to the top and the top gradient vanished until the next small scroll down).
     The photo above is a sticky, separately composited layer; after a long scroll Safari did not re-create this fade's layer when the top came back, and only did on the next
     scroll. A forced layer of its own is the usual remedy for that repaint miss. It changes nothing visible. */
  transform: translateZ(0); -webkit-transform: translateZ(0); backface-visibility: hidden; -webkit-backface-visibility: hidden;
  background: linear-gradient(to bottom, var(--page_edge, #7C7C79) 0%, color-mix(in srgb, var(--page_edge, #7C7C79) 97%, transparent) 10%, color-mix(in srgb, var(--page_edge, #7C7C79) 90%, transparent) 20%, color-mix(in srgb, var(--page_edge, #7C7C79) 78%, transparent) 30%, color-mix(in srgb, var(--page_edge, #7C7C79) 65%, transparent) 40%, color-mix(in srgb, var(--page_edge, #7C7C79) 50%, transparent) 50%, color-mix(in srgb, var(--page_edge, #7C7C79) 35%, transparent) 60%, color-mix(in srgb, var(--page_edge, #7C7C79) 22%, transparent) 70%, color-mix(in srgb, var(--page_edge, #7C7C79) 10%, transparent) 80%, color-mix(in srgb, var(--page_edge, #7C7C79) 3%, transparent) 90%, transparent 100%) top / 100% 100% no-repeat;
}
/* The solid part of the top fade HANGS ABOVE the layer (owner, iPhone, 2026-11-16, second look: the fade still began a clock's height down). The phone lays a sticky or fixed layer out from the top of the area it gives the page, which is below the clock; the photo gets to the very top of the screen only because it reaches 300px above its layer. The cap does the same: 400px of solid page colour above the fade, painted over the clock area (nothing there but the phone's own strip), and off the screen above that. Nothing is scrollable above the top of a page, so it adds no length. */
.g-edgefade::before { content: ""; position: absolute; left: 0; right: 0; bottom: 100%; height: 400px; background: var(--page_edge, #7C7C79); }
/* No bottom fade layer (owner, 2026-11-16: it did the same as the top one, staying with the window). The end of the page is .g-footbar, which fades the photo into the page colour
   (the colour the phone paints its toolbar with) and is part of the page, so it comes up with the page's end and is not there in the middle of a long page. */

.g-scene {
  /* A pinned layer inside the page (position: sticky), not position: fixed. On an iPhone the browser clips a fixed layer to the
     area between its status bar and its bottom toolbar and leaves a bare band under the toolbar; a sticky layer is painted like
     the page's own content, which runs under both bars. It is 300px taller than the screen at each end (lvh = the tallest the
     screen gets), takes up no room in the page, and in the first 300px of scrolling it drifts up a little before it pins. */
  --g_scene_h: calc(100vh + 600px);
  --g_scene_h: calc(100lvh + 600px);
  position: sticky;
  top: -300px;
  height: var(--g_scene_h);
  margin: calc(-1 * env(safe-area-inset-top, 0px)) 0 calc(-1 * var(--g_scene_h));
  z-index: -2;   /* under the edge fades (-1), which are under all content */
  pointer-events: none;
  background-color: var(--bg);
  background-image: var(--scene_image);
  background-size: cover;
  background-position: center;
  background-repeat: no-repeat;
}
.g-scene::before { content: ""; position: absolute; inset: 0; background: var(--glass_wash); }
/* The same scene inside a box (the editor preview, the style guide's frames): the box must be position: relative. */
.g-scene-inline { position: absolute; z-index: 0; top: 0; bottom: 0; height: auto; margin: 0; }
@media (max-width: 700px) {
  .g-scene { background-image: var(--scene_image_phone, var(--scene_image)); }
}
@media print { .g-scene { display: none; } }

:where(.g-page, .g-scope) a {
  color: var(--ink);
  text-decoration: underline;
  text-decoration-color: var(--accent);
  text-decoration-thickness: 2px;
  text-underline-offset: 3px;
}
.g-page h1, .g-page h2, .g-page h3, .g-scope h3 { color: var(--ink); margin: 0 0 .4rem; }
.g-muted { color: var(--glass_muted); }
.g-small { font-size: .85em; }

/* ---- the bubble ----------------------------------------------------------------------------------------------------- */
.g-bubble, .g-dense {
  position: relative;
  isolation: isolate;
  color: var(--ink);
  padding: 1rem 1.25rem;
  border-radius: calc(var(--glass_radius) * 1px);
  -webkit-backdrop-filter: blur(calc(var(--glass_blur) * 1px)) saturate(var(--glass_saturate));
  backdrop-filter: blur(calc(var(--glass_blur) * 1px)) saturate(var(--glass_saturate));
  box-shadow: 0 14px 32px -10px var(--glass_shadow), 0 2px 8px var(--glass_shadow);
}
/* the tint, at its opacity (a layer of its own, so the opacity never fades the text) */
.g-bubble::before, .g-dense::before {
  content: ""; position: absolute; inset: 0; z-index: -2; border-radius: inherit;
  background: var(--glass_tint); opacity: var(--glass_opacity);
}
.g-dense::before { opacity: var(--glass_dense_opacity); }
/* the faint gloss across the top, and the thin bright edge: brightest along the top, a quieter line all around */
.g-bubble::after, .g-dense::after {
  content: ""; position: absolute; inset: 0; z-index: -1; border-radius: inherit; pointer-events: none;
  background: linear-gradient(180deg, var(--glass_gloss) 0, transparent 42%);
  box-shadow: inset 0 1px 0 0 var(--glass_edge), inset 0 0 0 1px color-mix(in srgb, var(--glass_edge) 30%, transparent);
}
/* A panel inside a bubble: flat, no blur of its own. The tint only moves the background toward better contrast. */
.g-well {
  background: color-mix(in srgb, var(--glass_tint) 45%, transparent);
  border-radius: calc(var(--glass_radius) * .6px);
  border: 1px solid color-mix(in srgb, var(--ink) 14%, transparent);
  padding: .75rem 1rem;
}

/* Where the browser cannot blur, or the device asks for less transparency: solid bubbles over the same scene. */
@supports not ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px))) {
  .g-bubble, .g-dense { -webkit-backdrop-filter: none; backdrop-filter: none; }
  .g-bubble::before, .g-dense::before { background: var(--bg); opacity: 1; }
}
@media (prefers-reduced-transparency: reduce) {
  .g-bubble, .g-dense { -webkit-backdrop-filter: none; backdrop-filter: none; }
  .g-bubble::before, .g-dense::before { background: var(--bg); opacity: 1; }
}

/* ---- key figure: the green gradient ------------------------------------------------------------------------------ */
.g-figure {
  --fig_from: color-mix(in srgb, var(--accent) 22%, var(--ink));
  --fig_to: color-mix(in srgb, var(--good) 22%, var(--ink));
  font-size: 2.5rem; font-weight: 700; line-height: 1.1; letter-spacing: -.02em;
  background: linear-gradient(135deg, var(--fig_from), var(--fig_to));
  -webkit-background-clip: text; background-clip: text;
  -webkit-text-fill-color: transparent; color: transparent;
}

/* ---- buttons ------------------------------------------------------------------------------------------------------------ */
.g-btn {
  font: inherit; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; min-height: 2.75rem; text-align: center; text-decoration: none;
  padding: .5rem 1.15rem; border: 1px solid transparent;
  border-radius: calc(var(--glass_radius) * .5px);
  transition: transform .25s cubic-bezier(.34, 1.56, .64, 1), background-color .2s ease;
}
/* The same response as the side bar items: under the pointer or keyboard focus a button tints toward the olive and grows a little; pressed, it shrinks a touch (the press rule must stay after these two). */
.g-btn:focus-visible { transform: scale(1.04); }
@media (hover: hover) { .g-btn:hover { transform: scale(1.04); } }
.g-btn:active { transform: scale(.97); }
.g-page .g-btn-primary, .g-scope .g-btn-primary { background: var(--accent); color: var(--on_accent); text-decoration: none; }
.g-btn-primary:focus-visible { background: color-mix(in srgb, var(--accent) 88%, var(--ink)); }
@media (hover: hover) { .g-btn-primary:hover { background: color-mix(in srgb, var(--accent) 88%, var(--ink)); } }
.g-page .g-btn-secondary, .g-scope .g-btn-secondary {
  background: color-mix(in srgb, var(--glass_tint) 35%, transparent); color: var(--ink);
  border-color: color-mix(in srgb, var(--accent) 75%, var(--ink)); text-decoration: none;
}
.g-btn-secondary:focus-visible { background: color-mix(in srgb, var(--accent) 26%, color-mix(in srgb, var(--glass_tint) 50%, transparent)); }
@media (hover: hover) { .g-btn-secondary:hover { background: color-mix(in srgb, var(--accent) 26%, color-mix(in srgb, var(--glass_tint) 50%, transparent)); } }
.g-page .g-btn-danger, .g-scope .g-btn-danger {
  background: color-mix(in srgb, var(--bad) 12%, var(--glass_tint)); color: var(--ink); border-color: var(--bad); text-decoration: none;
}
.g-btn-danger:focus-visible { background: var(--bad); color: var(--on_accent); }
@media (hover: hover) { .g-btn-danger:hover { background: var(--bad); color: var(--on_accent); } }
.g-btn:focus-visible, .g-input:focus-visible, .g-rail-item:focus-visible, .g-page a:focus-visible {
  outline: 2px solid var(--ink); outline-offset: 2px;
  box-shadow: 0 0 0 5px color-mix(in srgb, var(--accent) 60%, transparent);
}

/* ---- form controls: opaque, so the text is always on --bg ------------------------------------------------------------ */
.g-field { display: flex; flex-direction: column; gap: .25rem; margin-bottom: .7rem; }
.g-field label { font-size: .85em; color: var(--glass_muted); }
.g-input {
  font: inherit; width: 100%; min-height: 2.75rem; padding: .5rem .65rem; color: var(--ink); background: var(--bg);
  border: 1.5px solid color-mix(in srgb, var(--ink) 55%, transparent); border-radius: calc(var(--glass_radius) * .4px);
}
.g-input::placeholder { color: var(--glass_muted); opacity: 1; }
.g-input:disabled, .g-btn:disabled, .g-btn[aria-disabled="true"] { opacity: .55; cursor: not-allowed; }
.g-input[aria-invalid="true"] { border-color: var(--bad); box-shadow: 0 0 0 1px var(--bad); }
.g-page input[type="checkbox"], .g-page input[type="radio"], .g-scope input[type="checkbox"], .g-scope input[type="radio"] { accent-color: var(--accent); }

/* ---- tag ----------------------------------------------------------------------------------------------------------------- */
.g-tag {
  display: inline-block; padding: .12rem .7rem; font-size: .8em; color: var(--ink); background: var(--soft);
  border: 1px solid color-mix(in srgb, var(--ink) 16%, transparent);
  border-radius: 999px;
}

.g-tag.is-done { background: color-mix(in srgb, var(--good) 24%, var(--soft)); }
.g-tag.is-open { background: color-mix(in srgb, var(--warm) 30%, var(--soft)); }

/* ---- notice -------------------------------------------------------------------------------------------------------------- */
.g-banner {
  padding: .6rem .9rem; color: var(--ink); background: color-mix(in srgb, var(--bad) 12%, var(--bg));
  border: 1px solid var(--bad); border-radius: calc(var(--glass_radius) * .5px);
}

.g-banner.is-ok { border-color: var(--good); background: color-mix(in srgb, var(--good) 12%, var(--bg)); }
.g-banner.is-warn { border-color: var(--warm); background: color-mix(in srgb, var(--warm) 16%, var(--bg)); }

/* ---- table: inside ONE .g-dense bubble ---------------------------------------------------------------------------------- */
.g-table { width: 100%; border-collapse: collapse; }
.g-table th {
  text-align: left; font-size: .8em; font-weight: 600; text-transform: uppercase; letter-spacing: .04em;
  color: var(--glass_muted); padding: .5rem .6rem; border-bottom: 1px solid color-mix(in srgb, var(--ink) 22%, transparent);
}
.g-table td { padding: .6rem; color: var(--ink); border-bottom: 1px solid color-mix(in srgb, var(--ink) 12%, transparent); }
@media (hover: hover) { .g-table tr:hover td { background: color-mix(in srgb, var(--soft) 70%, transparent); } }
.g-table-wrap { overflow-x: auto; }
.g-nowrap { white-space: nowrap; }

/* ---- the sidebar's pieces ----------------------------------------------------------------------------------------------- */
.g-rail { display: flex; flex-direction: column; align-items: center; gap: .35rem; padding: .75rem .5rem; width: 4.25rem; }
.g-rail-item {
  display: grid; place-items: center; width: 2.75rem; height: 2.75rem; color: var(--ink); text-decoration: none;
  border-radius: calc(var(--glass_radius) * .6px);
  transition: transform .3s cubic-bezier(.34, 1.56, .64, 1), background-color var(--rail_fade, .22s) ease;       /* a soft, slightly springy growth */
}
.g-rail-item svg { width: 1.4rem; height: 1.4rem; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
/* grows slightly under the pointer and on keyboard focus: a transform, so nothing around it moves */
.g-rail-item:hover, .g-rail-item:focus-visible { transform: scale(1.16); background: color-mix(in srgb, var(--accent) 26%, color-mix(in srgb, var(--glass_tint) 50%, transparent)); }
.g-page .g-rail-item[aria-current="page"], .g-scope .g-rail-item[aria-current="page"] { background: var(--accent); color: var(--on_accent); }
.g-rail-item, .g-side-arrow { -webkit-tap-highlight-color: transparent; }   /* no grey iOS flash behind our own press fill */
.g-rail-item:active { transform: scale(.94); background: color-mix(in srgb, var(--accent) 44%, color-mix(in srgb, var(--glass_tint) 50%, transparent)); transition: transform .3s cubic-bezier(.34, 1.56, .64, 1), background-color .12s ease; }                 /* touch (and click): a small press instead of the growth */
@media (hover: none) {
  .g-rail-item:hover:not(:focus-visible) { transform: none; background: transparent; }
  .g-rail-item[aria-current="page"]:hover:not(:focus-visible) { background: var(--accent); }
  .g-side-arrow:hover:not(:focus-visible) { transform: none; background: color-mix(in srgb, var(--glass_tint) 45%, transparent); }
  .g-side-toggle:checked ~ .g-side .g-rail-item:hover:not(:focus-visible), .g-side-toggle:checked ~ .g-side .g-side-arrow:hover:not(:focus-visible) { transform: none; background: transparent; }
  /* a finger down is a press, not a hover: it keeps the stronger olive fill (these beat the resets above) */
  .g-rail-item:hover:active:not(:focus-visible), .g-side-arrow:hover:active:not(:focus-visible),
  .g-side-toggle:checked ~ .g-side .g-rail-item:hover:active:not(:focus-visible), .g-side-toggle:checked ~ .g-side .g-side-arrow:hover:active:not(:focus-visible) { background: color-mix(in srgb, var(--accent) 44%, color-mix(in srgb, var(--glass_tint) 50%, transparent)); }
  .g-rail-item:not(:focus-visible), .g-side-arrow:not(:focus-visible) { --rail_fade: .6s; }          /* a finger lifts slowly: the olive press fill fades out over longer than a mouse hover (the press itself still comes on at once) */
}
.g-rail-rule { width: 1.75rem; height: 1px; margin: .25rem 0; background: color-mix(in srgb, var(--ink) 20%, transparent); }
.g-sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }

/* ---- the sidebar: floats on the left at all times; an arrow opens it from icons to icons with titles ------------------------
 * Markup (no script: the arrow is the label of a checkbox, and the checkbox is the open / closed switch):
 *   <input type="checkbox" id="g-side-open" class="g-side-toggle" aria-label="Show the menu titles" aria-controls="g-side">
 *   <nav id="g-side" class="g-bubble g-rail g-side" aria-label="Main menu">
 *     <label class="g-side-arrow" for="g-side-open"><span class="g-sr-only">Expand or collapse the menu</span><svg>...</svg></label>
 *     <a class="g-rail-item" href="/page"><svg>...</svg><span class="g-rail-label">Title</span></a> ...
 *   </nav>
 * The checkbox and the nav are siblings, outside .g-shell. Put class g-side-pad on <main> so the page keeps clear of the slim bar.
 * Open, the bar lies over the page (it does not push it). The open / closed choice is not remembered between pages: that needs
 * a script, which is a later, per-app decision.
 */
.g-side-scrim {
  /* The tap-outside layer. It has no colour and no opacity of its own: an opacity would make it a backdrop root (a blur inside it would see nothing of the page), and a visible colour touching the bottom or top edge made iOS tint its bars from it (the toolbar went opaque black while the menu was open). The dim and the blur are the two pseudo-elements below. */
  position: fixed; inset: 12px 0; z-index: 19;   /* not quite to the edges: a fixed layer touching the top or bottom edge makes iOS paint its bars opaque */
  visibility: hidden; pointer-events: none; transition: visibility 0s linear .3s; -webkit-tap-highlight-color: transparent;
}
.g-side-toggle:checked ~ .g-side-scrim { visibility: visible; pointer-events: auto; transition-delay: 0s; }
/* No dim and no blur while the menu is open (owner, 2026-11-16: "strange gray gradient bar near the top when the side bar is open"). The shade eased in from the top
   edge and the graded blur faded out nine rem down, and together they drew a band under the clock; they were the only layers with an edge. The open bar is glass on its own;
   the scrim stays as the invisible tap-outside layer. */
.g-side-toggle { position: fixed; top: 0; left: 0; width: 1px; height: 1px; opacity: 0; pointer-events: none; }
.g-side {
  position: fixed; z-index: 20;
  left: calc(env(safe-area-inset-left, 0px) + .75rem);
  top: .75rem;       /* pinned to the top; on an iPhone a fixed layer already starts below the status bar */
  align-items: stretch; gap: .35rem;
  /* Fully rounded ends: half the slim bar's width, so closed it is a capsule with semicircle ends. Open, the same corner size
     keeps the arrow and the first and last buttons inside the curve (a half-circle that wide would cut them off). */
  border-radius: 2.125rem; padding: .875rem .5rem;
  bottom: .75rem;       /* the whole height of the screen; on a short screen or in landscape the bar scrolls, so nothing is unreachable */
  overflow-y: auto; overflow-x: hidden; overscroll-behavior: contain; scrollbar-width: none;
  will-change: width;
  transition: width .45s cubic-bezier(.4, 0, .2, 1);       /* eased at both ends (a hard start looked like a jump on the phone) */
  /* A tight shadow that stays inside the .75rem gap above and below the bar (reach 10px, gap 12px). The bubble's own shadow reaches 36px below, and a phone paints a fixed layer only down to its toolbar, so that shadow was cut off in a hard line under the bar. */
  box-shadow: 0 0 14px -4px var(--glass_shadow), 0 1px 4px var(--glass_shadow);
}
.g-side::-webkit-scrollbar { display: none; }
.g-side-toggle:checked ~ .g-side { width: min(15rem, calc(100vw - 1.5rem - env(safe-area-inset-left, 0px))); }
.g-side .g-rail-item {
  display: flex; align-items: center; justify-content: flex-start; gap: .85rem; white-space: nowrap; overflow: hidden;
  /* the same rule closed and open: slim it comes to a 2.75rem square with the icon centred, open it fills the bar, and the icon
     never moves, so everything simply follows the bar as it grows (nothing jumps) */
  width: calc(100% - .5rem); align-self: center; padding: 0 .675rem;
}
.g-side .g-rail-item svg { flex: none; }
/* Open, an item nearly fills the bar (12px each side), so the full growth would push it past the bar's edge: grow less there, which
   leaves about 8px of glass on each side. Slim, the full growth still leaves about 8px. */
.g-side-toggle:checked ~ .g-side .g-rail-item:hover, .g-side-toggle:checked ~ .g-side .g-rail-item:focus-visible { transform: scale(1.04); }
.g-side-toggle:checked ~ .g-side .g-rail-item:active { transform: scale(.97); background: color-mix(in srgb, var(--accent) 44%, color-mix(in srgb, var(--glass_tint) 50%, transparent)); transition: transform .3s cubic-bezier(.34, 1.56, .64, 1), background-color .12s ease; }
.g-rail-label {
  max-width: 11rem; opacity: 0; overflow: hidden; text-overflow: ellipsis;
  transition: opacity .15s ease;                       /* closing: the titles go first (the bar clips them as it narrows; their width is never animated) */
}
.g-side-toggle:checked ~ .g-side .g-rail-label {
  opacity: 1;
  transition: opacity .3s ease .12s;                    /* opening: they fade in as the bar widens */
}
.g-side .g-rail-rule { align-self: center; width: calc(100% - 1rem); }
/* between the main buttons (top) and the pinned group (bottom): takes up the free height, so the bar can run the whole screen */
.g-side-spacer { flex: 1 1 auto; min-height: .5rem; }
.g-side > :not(.g-side-spacer) { flex: none; }      /* on a short screen the buttons keep their size and the bar scrolls, they are never squashed */
/* the arrow: a small round button when slim; when open it grows into a button the same size and shape as the rest (full width,
   2.75rem tall), with a title on the left and the arrow, now pointing left, at its right-hand end */
.g-side-arrow {
  position: relative; display: block; box-sizing: border-box; width: 2.75rem; height: 2.75rem; align-self: flex-start; margin-bottom: .15rem; cursor: pointer;
  margin-left: calc(50% - 1.375rem);                    /* closed: centred in the slim bar (a percentage is of the bar's width) */
  color: var(--ink); border-radius: 1.375rem; border: 1px solid color-mix(in srgb, var(--ink) 18%, transparent);
  background: color-mix(in srgb, var(--glass_tint) 45%, transparent);
  /* the same press / growth timing as the other buttons (see .g-rail-item), plus the glide into the open shape */
  transition: transform .3s cubic-bezier(.34, 1.56, .64, 1), background-color var(--rail_fade, .22s) ease, border-color .45s ease,
    width .45s cubic-bezier(.4, 0, .2, 1), height .45s cubic-bezier(.4, 0, .2, 1), margin-left .45s cubic-bezier(.4, 0, .2, 1), border-radius .45s cubic-bezier(.4, 0, .2, 1);
}
.g-side-toggle:checked ~ .g-side .g-side-arrow {
  width: calc(100% - .5rem); height: 2.75rem; margin-left: .25rem;      /* exactly an item's size, in the same place */
  border-radius: calc(var(--glass_radius) * .6px);
  border-color: transparent; background: transparent;                    /* open: no outline and no fill at rest, like the other buttons */
}
.g-side-arrow svg {
  position: absolute; top: 50%; margin-top: -.55rem; right: calc(50% - .55rem);                /* closed: centred */
  width: 1.1rem; height: 1.1rem; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round;
  transition: transform .45s cubic-bezier(.4, 0, .2, 1), right .45s cubic-bezier(.4, 0, .2, 1);
}
.g-side-toggle:checked ~ .g-side .g-side-arrow svg { right: calc(.675rem - 1px); transform: rotate(180deg); }   /* the same gap as an icon's, less the 1px border */
.g-side-arrow .g-rail-label { position: absolute; left: calc(2.925rem - 1px); top: 50%; transform: translateY(-50%); }   /* the same x as the other titles */
/* open, the arrow button nearly fills the bar like the others, so it grows less on hover (see the items above) */
.g-side-toggle:checked ~ .g-side .g-side-arrow:hover { transform: scale(1.04); background: color-mix(in srgb, var(--accent) 26%, color-mix(in srgb, var(--glass_tint) 50%, transparent)); }   /* the same hover fill as the other buttons */
.g-side-toggle:checked ~ .g-side .g-side-arrow:active { transform: scale(.97); background: color-mix(in srgb, var(--accent) 44%, color-mix(in srgb, var(--glass_tint) 50%, transparent)); transition: transform .3s cubic-bezier(.34, 1.56, .64, 1), background-color .12s ease; }
.g-side-arrow:hover { transform: scale(1.16); background: color-mix(in srgb, var(--accent) 26%, color-mix(in srgb, var(--glass_tint) 50%, transparent)); }       /* the same growth and fill as the other buttons */
.g-side-arrow:active { transform: scale(.94); background: color-mix(in srgb, var(--accent) 44%, color-mix(in srgb, var(--glass_tint) 50%, transparent)); transition: transform .3s cubic-bezier(.34, 1.56, .64, 1), background-color .12s ease; }
.g-side-toggle:focus-visible ~ .g-side .g-side-arrow { outline: 2px solid var(--ink); outline-offset: 2px; box-shadow: 0 0 0 5px color-mix(in srgb, var(--accent) 60%, transparent); }
.g-skip {
  position: fixed; left: .75rem; top: -5rem; z-index: 40; padding: .6rem 1.1rem; border-radius: 999px; font-weight: 600;
  background: var(--ink); color: var(--bg); text-decoration: none;
}
.g-page .g-skip { color: var(--bg); }
.g-skip:focus { top: calc(env(safe-area-inset-top, 0px) + .75rem); outline: 2px solid var(--accent); outline-offset: 2px; }
.g-page [id] { scroll-margin-top: calc(env(safe-area-inset-top, 0px) + 1rem); }
.g-main.g-side-pad { padding-left: calc(env(safe-area-inset-left, 0px) + 5.5rem); padding-right: calc(env(safe-area-inset-right, 0px) + .75rem); }

@media (prefers-reduced-motion: reduce) {
  .g-btn, .g-rail-item { transition: none; }
  .g-rail-item:hover, .g-rail-item:focus-visible { transform: none; }
  .g-btn:hover, .g-btn:focus-visible { transform: none; }
  .g-btn:active, .g-rail-item:active { transform: none; }
  .g-page .g-footbar a, .g-page .g-footbar a:hover, .g-page .g-footbar a:focus-visible, .g-page .g-footbar a:active { transition: none; transform: none; }
  .g-side, .g-rail-label, .g-side-arrow, .g-side-arrow svg { transition: none; }
  .g-side-arrow:hover, .g-side-arrow:active { transform: none; }
  .g-side-scrim, .g-side-scrim::before, .g-side-scrim::after { transition: none; }
  .g-side-toggle:checked ~ .g-side .g-rail-item:hover, .g-side-toggle:checked ~ .g-side .g-rail-item:focus-visible, .g-side-toggle:checked ~ .g-side .g-rail-item:active,
  .g-side-toggle:checked ~ .g-side .g-side-arrow:hover, .g-side-toggle:checked ~ .g-side .g-side-arrow:active { transform: none; }
}

/* the current page is also an outline (colour alone fails 3:1 on some parts of the photo) */
.g-page .g-rail-item[aria-current="page"], .g-scope .g-rail-item[aria-current="page"] { box-shadow: inset 0 0 0 2px var(--ink); }
@media (forced-colors: active) {
  .g-page .g-rail-item[aria-current="page"], .g-scope .g-rail-item[aria-current="page"] { outline: 2px solid Highlight; box-shadow: none; }
  .g-side { border: 1px solid CanvasText; }
}
@media (max-height: 520px) { .g-side { gap: .15rem; padding-block: .5rem; } }                    /* landscape: more of the menu fits before it has to scroll */

/* ---- layout helpers --------------------------------------------------------------------------------------------------------- */
.g-main { max-width: 1100px; margin: 0 auto; padding: 1rem; display: grid; grid-template-columns: minmax(0, 1fr); gap: 1rem; }
.g-main > * { min-width: 0; }
.g-row { display: flex; flex-wrap: wrap; gap: .6rem; align-items: center; }
.g-cols { display: grid; gap: 1rem; grid-template-columns: repeat(auto-fit, minmax(min(16rem, 100%), 1fr)); }
```

## Appendix D: `glass-menu.js` (the side menu's small helper)

Esc closes the menu (the search panel first if the page has one); a tap on a link in the menu closes it; Back/Forward bring the page back with the menu closed; a screen reader hears a button that is expanded or collapsed.

```js
/* The side menu's small helper. The menu works with no script at all (the arrow is the label of a checkbox);
   this only adds what a checkbox cannot do: Esc closes it, tapping a link in it closes it, it comes back closed after the browser's Back or Forward
   button, and a screen reader hears a button that is expanded or collapsed. Same text in the Design app, Home and Drive; keep it free of the
   three-character openers of template syntax, because Design and Home include it through the template engine. */
(function () {
  'use strict';
  var box = document.getElementById('g-side-open');
  if (!box) return;
  var search = document.getElementById('g-search-open');   // Home only: a panel that takes over the open menu

  function sync() {
    box.setAttribute('role', 'button');
    box.setAttribute('aria-expanded', box.checked ? 'true' : 'false');
  }
  function closeMenu() {
    if (search) search.checked = false;
    if (box.checked) box.checked = false;
    sync();
  }

  box.addEventListener('change', sync);

  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape' && e.key !== 'Esc') return;
    if (search && search.checked) { search.checked = false; return; }   // the panel first, then the menu on the next press
    if (box.checked) { closeMenu(); box.focus(); }
  });

  document.addEventListener('click', function (e) {
    var link = e.target && e.target.closest ? e.target.closest('#g-side a[href]') : null;
    if (link && box.checked) closeMenu();                // a link on the same page (or one that opens in a new tab) leaves the menu open otherwise
  });

  window.addEventListener('pageshow', function (e) {
    if (e.persisted) closeMenu();                        // Back and Forward restore the page as it was left: open
  });

  sync();
})();
```

## Appendix E: a complete minimal page

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="color-scheme" content="light dark">
  <title>My page</title>
  <link rel="preload" as="image" href="/static/mountains-phone.jpg" media="(max-width: 700px)">
  <link rel="preload" as="image" href="/static/mountains.jpg" media="(min-width: 701px)">
  <link rel="stylesheet" href="/static/glass-tokens.css">   <!-- appendix A -->
  <link rel="stylesheet" href="/static/page.css">           <!-- appendix B -->
  <link rel="stylesheet" href="/static/glass.css">          <!-- appendix C -->
  <link rel="stylesheet" href="/static/my-page.css">        <!-- only this page's own layout -->
</head>
<body id="top" class="g-page">
  <div class="g-edgefade" aria-hidden="true"></div>
  <a class="g-skip" href="#main">Skip to content</a>

  <!-- The side bar. The checkbox, the scrim and the nav must be SIBLINGS, in this order, with no wrapper between them. -->
  <input type="checkbox" id="g-side-open" class="g-side-toggle" aria-label="Show the menu titles" aria-controls="g-side" autocomplete="off">
  <label class="g-side-scrim" for="g-side-open" aria-hidden="true"></label>
  <nav id="g-side" class="g-bubble g-rail g-side" aria-label="Main menu">
    <label class="g-side-arrow" for="g-side-open">
      <span class="g-sr-only">Expand or collapse the menu</span><span class="g-rail-label" aria-hidden="true">Collapse menu</span>
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 6 6 6-6 6"/></svg>
    </label>
    <a class="g-rail-item" href="/" aria-current="page">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 11.5 12 4l9 7.5"/><path d="M5.5 10v9.5h13V10"/></svg><span class="g-rail-label">Overview</span></a>
    <a class="g-rail-item" href="/search">
      <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/></svg><span class="g-rail-label">Search</span></a>
    <div class="g-side-spacer"></div>
    <div class="g-rail-rule"></div>
    <a class="g-rail-item" href="?theme=dark">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/></svg><span class="g-rail-label">Theme</span></a>
  </nav>

  <div class="g-shell">
    <div class="g-scene" aria-hidden="true"></div>
    <main class="g-main g-side-pad" id="main">
      <header class="g-bubble">
        <h1>Page title</h1>
        <p class="g-muted">A line of secondary text.</p>
      </header>

      <div class="g-cols">                                   <!-- 1 column on a phone, more as the width allows -->
        <section class="g-bubble"><h2>A section</h2><p>Body text.</p><span class="g-tag is-open">open</span></section>
        <section class="g-bubble"><h2>A key figure</h2><div class="g-figure">7 of 12</div><div class="g-well">A flat panel inside the bubble.</div></section>
      </div>

      <section class="g-dense">                              <!-- tables and forms: ONE dense bubble -->
        <h2>Form</h2>
        <div class="g-field"><label for="n">Name</label><input class="g-input" id="n" type="text"></div>
        <div class="g-row"><button class="g-btn g-btn-primary" type="button">Save</button><button class="g-btn g-btn-secondary" type="button">Cancel</button></div>
      </section>
    </main>
    <footer class="g-footbar"><a href="#top">&uarr; Back to top</a></footer>
  </div>
  <script src="/static/glass-menu.js" defer></script>      <!-- appendix D -->
</body>
</html>
```

## Appendix F: patterns built on the shared look (from Drive and Home)

Take the pattern, rename the `dr-` prefix to suit; keep the behavior. These are Drive's tiles, Tiles | List switch, list rows, search-path line, disclosure menus and small forms.

```css
/* ---- the files bubble: a bar (where you are, the switch), then the tiles or the list ---- */
.dr-files { display: grid; gap: .9rem; align-content: start; }
.dr-files > * { min-width: 0; }
.dr-bar { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: .6rem 1rem; }
.dr-bar h1 { margin: 0; }
.dr-bar .crumbs { flex: 1 1 12rem; }
.dr-tools { display: flex; flex-wrap: wrap; align-items: center; gap: .6rem 1.2rem; }
.dr-tools > .dr-new[open] { flex: 1 1 100%; }
.dr-empty { margin: 0; }
.dr-empty p { margin: .2rem 0; }
.preview-toggle { margin: 0; font-size: .88rem; }
.preview-toggle label { display: inline-flex; align-items: center; gap: .5rem; cursor: pointer; min-height: 2rem; }
.dr-notice p { margin: .4rem 0; }
.dr-icon { width: 1.3rem; height: 1.3rem; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; flex: none; }

/* The Tiles | List switch: two toggle buttons in one capsule; the one that is on is filled and outlined (not colour alone) */
.dr-switch { display: inline-flex; gap: .2rem; padding: .2rem; margin: 0; border-radius: 999px;
             background: color-mix(in srgb, var(--glass_tint) 40%, transparent); border: 1px solid color-mix(in srgb, var(--ink) 16%, transparent); }
.g-btn.dr-seg { gap: .4rem; padding: 0 .95rem; background: transparent; color: var(--ink); border-radius: 999px; min-height: 2.5rem; }
.g-btn.dr-seg.is-on { background: var(--accent); color: var(--on_accent); box-shadow: inset 0 0 0 2px var(--ink); }
.dr-seg .dr-icon { width: 1.15rem; height: 1.15rem; }

/* ---- file tiles: one large glass button per file or folder (the Home app card's response: tint toward the olive and grow on hover or keyboard focus, shrink when
   pressed). The name's link is stretched over the whole tile; the Download link and the folder menu sit above it. ---- */
.dr-tiles, .dr-list { list-style: none; margin: 0; padding: 0; }
.dr-tiles { display: grid; gap: .7rem; grid-template-columns: repeat(2, minmax(0, 1fr)); }
@media (min-width: 480px) { .dr-tiles { grid-template-columns: repeat(auto-fill, minmax(9rem, 1fr)); } }
@media (min-width: 768px) { .dr-tiles { grid-template-columns: repeat(auto-fill, minmax(11rem, 1fr)); } }
.dr-item { min-width: 0; }
.dr-tile { position: relative; display: flex; flex-direction: column; gap: .45rem; height: 100%; padding: .55rem;
           border: 1px solid color-mix(in srgb, var(--ink) 14%, transparent);
           transition: transform .3s cubic-bezier(.34, 1.56, .64, 1), background-color .22s ease; }
.dr-tile:focus-within { transform: scale(1.04); z-index: 1; background: color-mix(in srgb, var(--accent) 26%, color-mix(in srgb, var(--glass_tint) 50%, transparent)); }
@media (hover: hover) { .dr-tile:hover { transform: scale(1.04); z-index: 1; background: color-mix(in srgb, var(--accent) 26%, color-mix(in srgb, var(--glass_tint) 50%, transparent)); } }
.dr-tile:active { transform: scale(.97); background: color-mix(in srgb, var(--accent) 44%, color-mix(in srgb, var(--glass_tint) 50%, transparent));
                  transition: transform .3s cubic-bezier(.34, 1.56, .64, 1), background-color .12s ease; }
.dr-tile:has(details[open]) { transform: none; }   /* a tile with its menu open does not move under the fingers filling in a form */
.dr-tile .name { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; overflow-wrap: anywhere; font-weight: 700; line-height: 1.3;
                 min-height: 2.6em; color: var(--ink); text-decoration: none; }
.g-page .dr-tile a.name { text-decoration: none; }
.dr-open::after { content: ""; position: absolute; inset: -1px; border-radius: calc(var(--glass_radius) * .6px); }
.g-page .dr-open:focus-visible { outline: none; box-shadow: none; }
.g-page .dr-open:focus-visible::after { outline: 2px solid var(--ink); outline-offset: 2px; box-shadow: 0 0 0 5px color-mix(in srgb, var(--accent) 60%, transparent); }
.dr-dates { margin: 0; font-size: .8rem; line-height: 1.3; }
.dr-date { display: block; }
.dr-tile-actions { position: relative; z-index: 1; display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: .3rem; margin-top: auto; }
.dr-size { font-size: .8rem; }
.g-page .dr-dl { display: grid; place-items: center; width: 2.75rem; height: 2.75rem; margin: -.3rem -.15rem -.3rem auto; text-decoration: none; color: var(--ink);
                 border-radius: calc(var(--glass_radius) * .6px); transition: transform .3s cubic-bezier(.34, 1.56, .64, 1), background-color .22s ease; }
@media (hover: hover) { .dr-dl:hover { transform: scale(1.1); background: color-mix(in srgb, var(--accent) 26%, color-mix(in srgb, var(--glass_tint) 50%, transparent)); } }
.dr-dl:active { transform: scale(.94); }
.dr-tile.trashed .name { opacity: .8; }

/* the large preview on top of a tile: a steady 4:3 box, so every tile has the same shape and the pictures line up */
.dr-prev { position: relative; display: block; flex: none; overflow: hidden; border-radius: calc(var(--glass_radius) * .4px); color: var(--ink);
           background: color-mix(in srgb, var(--bg) 60%, transparent); border: 1px solid color-mix(in srgb, var(--ink) 12%, transparent); }
.dr-tile .dr-prev { aspect-ratio: 4 / 3; }
.prev-folder { background: color-mix(in srgb, var(--accent) 20%, color-mix(in srgb, var(--bg) 60%, transparent)); }
.dr-prev .thumb { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; display: block; }
.dr-glyph, .dr-fallback { position: absolute; inset: 0; display: grid; place-items: center; }
.dr-fallback[hidden] { display: none; }
.dr-tile .dr-glyph .dr-icon, .dr-tile .dr-fallback .dr-icon { width: 38%; height: auto; max-width: 4.5rem; stroke-width: 1.5; }
.dr-ext { position: absolute; right: .35rem; bottom: .3rem; padding: .05rem .5rem; font-size: .65rem; font-weight: 700; letter-spacing: .03em; color: var(--ink);
          background: color-mix(in srgb, var(--bg) 85%, transparent); border: 1px solid color-mix(in srgb, var(--ink) 16%, transparent); border-radius: 999px; }
.dr-tile .snippet { position: absolute; inset: 0; margin: 0; padding: .45rem .5rem; overflow: hidden; overflow-wrap: anywhere; font-size: .8rem; line-height: 1.35;
                    text-align: left; color: var(--ink); }
body:not(.no-snippets) .snippet:not([hidden]) ~ .watch-snippet { display: none; }   /* the text replaces the icon once it has arrived (and stays out of the way when text previews are off) */
body.no-snippets .snippet { display: none !important; }

/* ---- the list: today's rows in the glass look (inside one dense bubble) ---- */
.dr-row { display: flex; flex-wrap: wrap; align-items: center; gap: .3rem .8rem; min-height: 3.5rem; padding: .3rem .25rem; border-top: 1px solid color-mix(in srgb, var(--ink) 14%, transparent); }
.dr-row:first-child { border-top: 0; }
@media (hover: hover) { .dr-row:hover { background: color-mix(in srgb, var(--soft) 70%, transparent); } }
.dr-namecol { flex: 1 1 10rem; min-width: 0; display: flex; flex-direction: column; padding-bottom: .3rem; }
.dr-row .dr-namecol .name { flex: none; padding: .35rem 0 0; }   /* (a column: the name keeps its own height, not the row's 10rem basis) */
.dr-row .name { flex: 1 1 10rem; min-width: 0; overflow-wrap: anywhere; padding: .5rem 0; color: var(--ink); text-decoration: none; }
.g-page .dr-row a.name { text-decoration: none; }
.g-page .dr-row a.name:hover { text-decoration: underline; text-decoration-color: var(--accent); }
.dr-row.folder .name { display: flex; align-items: center; gap: .7rem; }
.dr-rowicon { display: inline-grid; place-items: center; flex: none; }
.dr-rowicon .dr-icon { width: 1.6rem; height: 1.6rem; }
.meta { font-size: .85rem; white-space: nowrap; color: var(--glass_muted); }
.meta.wide { display: none; }
@media (min-width: 640px) { .meta.wide { display: inline; } }
.dl { padding: .6rem .5rem; font-size: .9rem; }
.dr-row.trashed .name { opacity: .8; }
.dr-row .dr-prev { width: 56px; height: 56px; }
.dr-row .dr-ext { display: none; }
.dr-row .dr-glyph .dr-icon, .dr-row .dr-fallback .dr-icon { width: 1.6rem; height: 1.6rem; }
.dr-row .snippet { flex-basis: 100%; order: 10; margin: 0; font-size: .85rem; color: var(--glass_muted); overflow-wrap: anywhere; }
.dr-list.versions .name { flex: 1 1 14rem; }

/* ---- a search result's folder: one small line, cut with an ellipsis, still all there as text to select and copy. In a tile it sits above the stretched link. ---- */
.dr-path { display: flex; align-items: center; gap: .3rem; min-width: 0; font-size: .8rem; line-height: 1.3; position: relative; z-index: 1; }
.dr-pathicon { width: .95rem; height: .95rem; stroke-width: 1.8; }
.dr-pathtext { min-width: 0; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; -webkit-user-select: all; user-select: all; }
.dr-tile .dr-path { margin-top: -.15rem; }

/* ---- the folder trail in the side bar: each item is a folder; a long name is cut, the full one is the tooltip ---- */
.g-side .dr-trail .g-rail-label { overflow: hidden; text-overflow: ellipsis; }

/* ---- menus and small forms: a native <details>, no script; open, it unfolds inside the tile or the row ---- */
.dr-menu { margin-left: auto; }
.dr-menu[open] { flex: 1 1 100%; margin-left: 0; }
.dr-menu > summary, .dr-new > summary { list-style: none; cursor: pointer; }
.dr-menu > summary::-webkit-details-marker, .dr-new > summary::-webkit-details-marker { display: none; }
.dr-menu > summary { min-width: 2.75rem; padding: 0 .6rem; }
.dr-menu[open] > summary { margin-left: auto; }
.dr-dots { width: 1.1rem; height: 1.1rem; fill: currentColor; }
.dr-menu-body { display: grid; gap: .5rem; margin-top: .5rem; padding: .6rem; color: var(--ink); background: var(--bg);
                border: 1px solid color-mix(in srgb, var(--ink) 18%, transparent); border-radius: calc(var(--glass_radius) * .4px); }
.dr-inline { display: flex; flex-wrap: wrap; gap: .5rem; align-items: center; margin: .3rem 0; }
.dr-inline .g-input { flex: 1 1 9rem; width: auto; min-width: 0; }
.dr-new[open] > summary { margin-bottom: .5rem; }
/* inside a tile the menu is narrow: its fields stack and fill the tile, and an open tile does not stretch its neighbours */
.dr-tiles { align-items: start; }
.dr-tile-actions, .dr-menu { min-width: 0; max-width: 100%; }
.dr-tile .dr-menu-body { padding: .45rem; min-width: 0; }
.dr-tile .dr-inline { flex-direction: column; align-items: stretch; }
.dr-tile .dr-inline .g-input { flex: none; width: 100%; }
.dr-tile .dr-menu-body .g-btn { width: 100%; }
.g-btn.dr-small { padding: .3rem .8rem; font-size: .9rem; }
.dr-check { display: flex; align-items: flex-start; gap: .5rem; margin: .6rem 0 0; font-size: .92rem; }
.dr-check input { margin-top: .25rem; }
```

Home's app card:

```css
/* Home's app card: a .g-well that is one whole button (the name's link is stretched over the card; small links inside sit above it). Same response as the tiles. */
.dh-app { position: relative; border: 1px solid color-mix(in srgb, var(--ink) 14%, transparent);
  transition: transform .3s cubic-bezier(.34, 1.56, .64, 1), background-color .22s ease; }
.dh-app h3 { font-size: 1em; margin: 0 0 .35rem; display: flex; flex-wrap: wrap; align-items: center; gap: .5rem; }
.g-page .dh-open { display: inline-flex; align-items: center; gap: .4rem; font-weight: 700; text-decoration: none; color: var(--ink); }
.dh-open::after { content: ""; position: absolute; inset: -1px; border-radius: calc(var(--glass_radius) * .6px); }   /* the stretched link */
.dh-arrow { width: .95em; height: .95em; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
.g-page .dh-open:focus-visible { outline: none; box-shadow: none; }
.g-page .dh-open:focus-visible::after { outline: 2px solid var(--ink); outline-offset: 2px; box-shadow: 0 0 0 5px color-mix(in srgb, var(--accent) 60%, transparent); }
.dh-app :is(.dh-counts, .dh-lines) a { position: relative; z-index: 1; }
.dh-app:focus-within { transform: scale(1.04); z-index: 1; background: color-mix(in srgb, var(--accent) 26%, color-mix(in srgb, var(--glass_tint) 50%, transparent)); }
@media (hover: hover) { .dh-app:hover { transform: scale(1.04); z-index: 1; background: color-mix(in srgb, var(--accent) 26%, color-mix(in srgb, var(--glass_tint) 50%, transparent)); } }
.dh-app:active { transform: scale(.97); background: color-mix(in srgb, var(--accent) 44%, color-mix(in srgb, var(--glass_tint) 50%, transparent));
  transition: transform .3s cubic-bezier(.34, 1.56, .64, 1), background-color .12s ease; }
.dh-counts { display: flex; flex-wrap: wrap; gap: .4rem 1rem; margin: 0 0 .35rem; padding: 0; list-style: none; }
.dh-counts b { display: block; font-size: 1.25em; }
.dh-counts span { font-size: .85em; color: var(--glass_muted); }
@media (prefers-reduced-motion: reduce) { .dh-app { transition: none; } .dh-app:hover, .dh-app:focus-within, .dh-app:active { transform: none; } }
```

Tile markup (Drive): `<li class="dr-item"><article class="g-well dr-tile"><a class="name dr-open" href="...">File name</a> ... </article></li>` inside `<ul class="dr-tiles">`. The tile preview is `<span class="dr-prev">` with an image or an inline SVG icon; the `dr-open::after` rule stretches the name's link over the whole tile, and anything that must stay clickable (Download, the menu) sits above it with `position: relative; z-index: 1`.
