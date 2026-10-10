"""Self-hosted fonts: no Google Fonts anywhere, and every face the CSS needs is
bundled, valid, and served from our own static URL."""

import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.templatetags.static import static
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .management.commands.seed_pages import PAGES

BASE = Path(settings.BASE_DIR)
STATIC_SHOP = BASE / "shop" / "static" / "shop"
CSS_FILE = STATIC_SHOP / "css" / "style.css"
FONT_DIR = STATIC_SHOP / "fonts"
TEMPLATE_ROOTS = (BASE / "shop" / "templates", BASE / "templates")
EXTERNAL_FONT_HOSTS = ("googleapis", "gstatic")
FAMILIES = {"Oswald", "IBM Plex Sans", "IBM Plex Mono"}

COMMENT = re.compile(r"/\*.*?\*/", re.S)
BLOCK = re.compile(r"([^{}]+)\{([^{}]*)\}")


def css_text():
    return COMMENT.sub("", CSS_FILE.read_text(encoding="utf-8"))


def declared(block, prop):
    m = re.search(rf"(?<![-\w]){re.escape(prop)}\s*:\s*([^;]+)", block)
    return m.group(1).strip() if m else None


def first_family(value):
    return value.split(",")[0].strip().strip("\"'")


def font_faces():
    """[(family, weight, [file names])] from every @font-face rule."""
    faces = []
    for selector, body in BLOCK.findall(css_text()):
        if not selector.strip().startswith("@font-face"):
            continue
        family = first_family(declared(body, "font-family"))
        weight = int(declared(body, "font-weight"))
        files = re.findall(r"url\(\s*[\"']?([^)\"']+)[\"']?\s*\)", declared(body, "src"))
        faces.append((family, weight, files))
    return faces


def used_weights():
    """[(family or None, weight)] for numeric font-weights the stylesheet sets."""
    css = css_text()
    tokens = {name: first_family(value)
              for name, value in re.findall(r"(--font-[\w-]+)\s*:\s*([^;]+);", css)}
    used = []
    for selector, body in BLOCK.findall(css):
        if selector.strip().startswith("@"):
            continue
        weight = declared(body, "font-weight")
        if weight is None:
            continue
        weight = {"normal": "400"}.get(weight, weight)
        if not weight.isdigit():
            continue  # bold/bolder/lighter/inherit: resolved by the browser
        family = declared(body, "font-family")
        if family:
            var = re.match(r"var\(\s*(--[\w-]+)\s*\)", family)
            family = tokens[var.group(1)] if var else first_family(family)
        used.append((family, int(weight)))
    return used


class NoExternalFontHostTests(TestCase):
    def test_no_template_or_stylesheet_names_a_font_host(self):
        files = [CSS_FILE]
        for root in TEMPLATE_ROOTS:
            files += [p for p in root.rglob("*") if p.is_file()]
        self.assertGreater(len(files), 10)  # the scan is really looking at something
        for path in files:
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
            for host in EXTERNAL_FONT_HOSTS:
                self.assertNotIn(host, text, f"{path.relative_to(BASE)} mentions {host}")

    def test_seeded_privacy_text_no_longer_mentions_google_fonts(self):
        privacy = next(p for p in PAGES if p["slug"] == "privacy")
        body = privacy["body"].lower()
        self.assertNotIn("google", body)
        self.assertNotIn("fonts", body)
        # the rest of the service list is untouched
        for name in ("Stripe", "Printful", "Cloudflare", "Our email provider"):
            self.assertIn(f"**{name}**", privacy["body"])


class FontFilesTests(TestCase):
    def test_every_font_file_the_css_names_exists_and_is_woff2(self):
        faces = font_faces()
        self.assertTrue(faces)
        for family, weight, files in faces:
            self.assertEqual(len(files), 1, (family, weight))
            for name in files:
                path = (CSS_FILE.parent / name).resolve()
                self.assertTrue(path.is_file(), f"{name} missing")
                self.assertEqual(path.parent, FONT_DIR.resolve())
                with open(path, "rb") as fh:
                    self.assertEqual(fh.read(4), b"wOF2", name)

    def test_every_bundled_family_ships_its_licence(self):
        for stem in ("oswald", "ibm-plex-sans", "ibm-plex-mono"):
            text = (FONT_DIR / f"OFL-{stem}.txt").read_text(encoding="utf-8")
            self.assertIn("SIL Open Font License", text)

    def test_font_faces_are_swap_and_latin_ranged(self):
        blocks = [b for s, b in BLOCK.findall(css_text()) if s.strip().startswith("@font-face")]
        self.assertEqual(len(blocks), len(font_faces()))
        for body in blocks:
            self.assertEqual(declared(body, "font-display"), "swap")
            self.assertEqual(declared(body, "font-style"), "normal")
            self.assertIn("U+0000-00FF", declared(body, "unicode-range"))
            self.assertIn("woff2", declared(body, "src"))

    def test_every_weight_the_css_uses_has_a_font_face(self):
        faces = {}
        for family, weight, _files in font_faces():
            faces.setdefault(family, set()).add(weight)
        self.assertEqual(set(faces), FAMILIES)
        used = used_weights()
        self.assertTrue(used)
        all_weights = set().union(*faces.values())
        for family, weight in used:
            if family is None:
                # weight set on an element that inherits its family
                self.assertIn(weight, all_weights, f"font-weight {weight} has no @font-face")
            else:
                self.assertIn(family, faces, f"{family} is not self-hosted")
                self.assertIn(weight, faces[family], f"{family} {weight} has no @font-face")

    def test_the_families_the_css_names_are_all_self_hosted(self):
        css = css_text()
        tokens = {first_family(v) for v in re.findall(r"--font-[\w-]+\s*:\s*([^;]+);", css)}
        self.assertEqual(tokens, FAMILIES)


@override_settings(STAFF_2FA_REQUIRED=False)
class PagesUseOwnFontsTests(TestCase):
    PRELOAD = "oswald-latin-600-normal"

    def assert_no_external_font_host(self, html):
        low = html.lower()
        for host in EXTERNAL_FONT_HOSTS:
            self.assertNotIn(host, low)
        # nothing in <head> that preconnects/preloads/styles from another origin
        for tag in re.findall(r"<link\b[^>]*>", html, re.I):
            if re.search(r'rel="(stylesheet|preconnect|preload|dns-prefetch)"', tag, re.I):
                self.assertIsNone(re.search(r'href="(https?:)?//', tag, re.I), tag)

    def test_public_home_page_renders_with_own_fonts_only(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assert_no_external_font_host(html)
        self.assertRegex(
            html,
            r'<link rel="preload" as="font" type="font/woff2" crossorigin href="[^"]*'
            + self.PRELOAD + r'[^"]*\.woff2"',
        )
        self.assertIn(static("shop/fonts/oswald-latin-600-normal.woff2"), html)

    def test_console_page_renders_with_own_fonts_only(self):
        staff = get_user_model().objects.create_user(
            "curator", password="pw-12345-xyz", is_staff=True, is_superuser=True)
        c = Client()
        c.force_login(staff)
        r = c.get(reverse("shop:manage_dashboard"))
        self.assertEqual(r.status_code, 200)
        self.assert_no_external_font_host(r.content.decode())

    def test_error_pages_do_not_name_a_font_host(self):
        from django.template.loader import render_to_string

        for name in ("404.html", "500.html"):
            self.assert_no_external_font_host(render_to_string(name))


class FontServingTests(TestCase):
    def test_a_font_is_served_from_the_static_url_cached_for_long(self):
        url = static("shop/fonts/oswald-latin-600-normal.woff2")
        self.assertTrue(url.startswith("/"), url)
        r = Client().get(url)
        self.assertEqual(r.status_code, 200)
        body = b"".join(r.streaming_content)
        r.close()
        self.assertEqual(body[:4], b"wOF2")
        self.assertIn(r["Content-Type"], ("font/woff2", "application/font-woff2"))
        if getattr(settings, "WHITENOISE_MAX_AGE", None) == 0:
            return  # DEBUG dev mode deliberately disables static caching
        match = re.search(r"max-age=(\d+)", r["Cache-Control"])
        self.assertIsNotNone(match, r["Cache-Control"])
        self.assertGreaterEqual(int(match.group(1)), 86400)
