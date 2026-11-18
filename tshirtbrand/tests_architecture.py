"""Boundary test for the ports-and-adapters layout (docs/ARCHITECTURE.md).

`violations(root)` reads every module under `<root>/tshirtbrand` and reports imports that break the rules.
It only reads source (no importing), so it runs fast and cannot be fooled by import side effects. The test
cases at the bottom prove the checker catches each rule on throwaway code, so a clean real tree means
something."""

import ast
import sys
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

ROOT_PKG = "tshirtbrand"
STDLIB = set(sys.stdlib_module_names)
REPO = Path(__file__).resolve().parent.parent
CONSOLE = sorted(p.relative_to(REPO).as_posix() for p in (REPO / "tshirtbrand/entrypoints/console").glob("*.py")
                 if p.name != "__init__.py")
STOREFRONT = sorted(p.relative_to(REPO).as_posix() for sub in ("storefront", "webhooks")
                    for p in (REPO / "tshirtbrand/entrypoints" / sub).glob("*.py") if p.name != "__init__.py")


def _module_parts(path, root):
    parts = list(path.relative_to(root).with_suffix("").parts)
    is_package = parts[-1] == "__init__"
    if is_package:
        parts = parts[:-1]
    return parts, is_package


def _targets(node, parts, is_package):
    """Dotted names a statement imports. `from a import b` yields `a.b` (b may be a module)."""
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    base = node.module or ""
    if node.level:
        pkg = parts if is_package else parts[:-1]
        keep = len(pkg) - (node.level - 1)
        base = ".".join([*pkg[: max(keep, 0)], *([base] if base else [])])
    if base == ROOT_PKG or base.startswith(ROOT_PKG + "."):
        return [f"{base}.{alias.name}" for alias in node.names if alias.name != "*"] or [base]
    return [base]


def _check(layer, context, parts, target):
    """Reason string if `parts` (in layer/context) may not import `target`, else None."""
    top = target.split(".")[0]
    inside = top == ROOT_PKG
    t = target.split(".")

    if parts == [ROOT_PKG, "bootstrap"]:
        return None  # the composition root may name anything

    if layer == "core":
        if not inside:
            if top in STDLIB:
                return None
            return f"core must be pure Python (imports {top!r})"
        if t[1:2] != ["core"]:
            return f"core may only import core (imports {target})"
        return _core_to_core(context, t, "core")

    if layer == "adapters":
        if top == "shop" and (len(parts) < 3 or parts[2] != "persistence"):
            return "only the persistence adapter may import the shop app (the tables)"
        if not inside:
            return None  # vendor SDKs, Django, PIL: that is what adapters are for
        if t[1:2] == ["core"]:
            return _core_to_core(None, t, "adapters")
        if t[1:3] == ["adapters", parts[2] if len(parts) > 2 else ""]:
            return None  # inside its own adapter family (suppliers/..., payments/...)
        return f"an adapter may not import {target}"

    if layer == "entrypoints":
        if not inside:
            if top in ("stripe", "requests", "PIL"):
                return f"entry points must not use vendor SDK {top!r}; call a use case"
            return None
        if t[1:2] == ["core"]:
            return _core_to_core(None, t, "entrypoints")
        if t[1:2] == ["entrypoints"] or t[1:2] == ["bootstrap"]:
            return None
        return f"an entry point may not import {target}"

    return None  # bootstrap itself, tests, and anything else at the package root


def _core_to_core(own_context, t, from_layer):
    ctx = t[2] if len(t) > 2 else ""
    sub = t[3] if len(t) > 3 else ""
    if ctx == "shared":
        return None
    if from_layer == "core" and ctx == own_context:
        return None
    allowed = {"core": ("api",), "adapters": ("api", "ports"), "entrypoints": ("api",)}[from_layer]
    if sub in allowed:
        return None
    where = "another context" if from_layer == "core" else "the core"
    return f"imports {'.'.join(t)}: {where} is reachable only through {' / '.join(allowed)}"


def violations(root):
    root = Path(root)
    pkg = root / ROOT_PKG
    found = []
    for path in sorted(pkg.rglob("*.py")):
        if path.name.startswith("tests_") or path.name == "tests.py":
            continue
        parts, is_package = _module_parts(path, root)
        layer = parts[1] if len(parts) > 1 else ""
        context = parts[2] if len(parts) > 2 else None
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            for target in _targets(node, parts, is_package):
                if not target:
                    continue
                reason = _check(layer, context, parts, target)
                if reason:
                    found.append(f"{'/'.join(parts)}:{node.lineno}: {reason}")
    return found


class RealTreeTests(SimpleTestCase):
    def test_the_real_tree_obeys_the_boundaries(self):
        self.assertEqual(violations(REPO), [])

    def test_skeleton_present(self):
        for sub in ("core", "core/shared", "adapters", "entrypoints"):
            self.assertTrue((REPO / ROOT_PKG / sub / "__init__.py").exists(), sub)


class CheckerCatchesEachRule(SimpleTestCase):
    """The rules are only worth something if the checker really trips on them."""

    def run_tree(self, files):
        with tempfile.TemporaryDirectory() as tmp:
            for rel, text in files.items():
                p = Path(tmp) / ROOT_PKG / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(text, encoding="utf-8")
            return violations(tmp)

    def test_clean_layout_passes(self):
        self.assertEqual(
            self.run_tree(
                {
                    "core/catalogue/model.py": "import dataclasses\nfrom decimal import Decimal\n",
                    "core/catalogue/api.py": "from . import model\nfrom tshirtbrand.core.shared import money\n",
                    "core/ordering/usecases.py": "from tshirtbrand.core.catalogue import api\n",
                    "adapters/suppliers/printful/client.py": "import requests\nfrom tshirtbrand.core.fulfilment import ports\n",
                    "entrypoints/console/views.py": "import django\nfrom tshirtbrand.core.ordering import api\n",
                    "bootstrap.py": "from tshirtbrand.adapters.suppliers.printful import client\n",
                }
            ),
            [],
        )

    def test_core_must_not_import_frameworks_or_vendors(self):
        for line in ("import django", "from django.db import models", "import stripe", "import requests", "from PIL import Image"):
            self.assertEqual(len(self.run_tree({"core/catalogue/model.py": line + "\n"})), 1, line)

    def test_core_must_not_import_shop_adapters_or_entrypoints(self):
        for line in ("import shop.models", "from tshirtbrand.adapters import x", "from tshirtbrand.entrypoints import x"):
            self.assertEqual(len(self.run_tree({"core/catalogue/model.py": line + "\n"})), 1, line)

    def test_context_may_only_use_another_through_api(self):
        bad = self.run_tree({"core/ordering/usecases.py": "from tshirtbrand.core.catalogue.model import Listing\n"})
        self.assertEqual(len(bad), 1)
        bad = self.run_tree({"core/ordering/usecases.py": "from tshirtbrand.core.catalogue import usecases\n"})
        self.assertEqual(len(bad), 1)
        ok = self.run_tree({"core/ordering/usecases.py": "from tshirtbrand.core.catalogue.api import find\n"})
        self.assertEqual(ok, [])

    def test_a_context_may_use_its_own_internals_relatively(self):
        self.assertEqual(self.run_tree({"core/catalogue/usecases.py": "from .model import X\nfrom . import ports\n"}), [])
        self.assertEqual(len(self.run_tree({"core/catalogue/usecases.py": "from ..ordering import model\n"})), 1)

    def test_adapters_see_the_core_only_through_ports_and_api(self):
        bad = self.run_tree({"adapters/payments/stripe/gateway.py": "from tshirtbrand.core.payments.model import X\n"})
        self.assertEqual(len(bad), 1)
        ok = self.run_tree({"adapters/payments/stripe/gateway.py": "from tshirtbrand.core.payments.ports import Gateway\n"})
        self.assertEqual(ok, [])

    def test_only_persistence_may_import_the_shop_app(self):
        bad = self.run_tree({"adapters/suppliers/printful/a.py": "from shop import models\n"})
        self.assertEqual(len(bad), 1)
        ok = self.run_tree({"adapters/persistence/django_orm/a.py": "from shop import models\nimport shop.orders\n"})
        self.assertEqual(ok, [])

    def test_adapters_do_not_use_each_other_or_entrypoints(self):
        files = {"adapters/suppliers/printful/a.py": "from tshirtbrand.adapters.payments.stripe import gateway\n"}
        self.assertEqual(len(self.run_tree(files)), 1)
        files = {"adapters/suppliers/printful/a.py": "from tshirtbrand.entrypoints.console import views\n"}
        self.assertEqual(len(self.run_tree(files)), 1)
        files = {"adapters/suppliers/printful/a.py": "from tshirtbrand.adapters.suppliers.printful import b\n"}
        self.assertEqual(self.run_tree(files), [])

    def test_entrypoints_use_api_only_and_never_adapters_or_vendor_sdks(self):
        for line in (
            "from tshirtbrand.adapters.suppliers.printful import client",
            "from tshirtbrand.core.ordering.usecases import place",
            "from tshirtbrand.core.ordering.model import Order",
            "import stripe",
        ):
            self.assertEqual(len(self.run_tree({"entrypoints/console/v.py": line + "\n"})), 1, line)

    def test_function_level_imports_are_checked_too(self):
        text = "def f():\n    import stripe\n"
        self.assertEqual(len(self.run_tree({"core/payments/model.py": text})), 1)

    def test_bootstrap_may_wire_anything(self):
        text = "from tshirtbrand.adapters.suppliers.mock import m\nfrom tshirtbrand.core.fulfilment import usecases\nimport django\n"
        self.assertEqual(self.run_tree({"bootstrap.py": text}), [])


class SliceStaysClean(SimpleTestCase):
    """Slices already moved behind a port must not slide back. Each step of the migration adds its
    modules here (docs/ARCHITECTURE.md, "How a slice is moved", step 5)."""

    # step 1, the print supplier: these talk to the supplier only through tshirtbrand.core.fulfilment
    SUPPLIER_CLEAN = [
        "shop/fulfillment.py", "shop/listing_sync.py", "shop/supplier_bridge.py", *CONSOLE,
        "shop/admin.py", "shop/orders.py", "shop/cart.py", "shop/emails.py",
    ]
    FORBIDDEN = ("shop.printful", "RealPrintful", "MockPrintful", "adapters.suppliers", "httpx")

    def imports_of(self, rel):
        tree = ast.parse((REPO / rel).read_text(encoding="utf-8"))
        names = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names += [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = ("." * node.level) + (node.module or "")
                names += [base] + [f"{base}.{a.name}".lstrip(".") for a in node.names]
        return names

    def test_the_supplier_slice_does_not_reach_the_vendor(self):
        for rel in self.SUPPLIER_CLEAN:
            for name in self.imports_of(rel):
                bare = name.lstrip(".")
                self.assertFalse(
                    bare == "printful" or bare.startswith(("printful.", "shop.printful", "httpx"))
                    or "adapters.suppliers" in bare,
                    f"{rel} imports {name}: go through tshirtbrand.bootstrap.get_supplier() instead")

    def test_the_supplier_slice_has_no_vendor_wire_names(self):
        for rel in self.SUPPLIER_CLEAN:
            text = (REPO / rel).read_text(encoding="utf-8")
            for word in ("sync_variant_id", "sync_product", "create_sync_product", "get_sync_product", "state_code"):
                self.assertFalse(word in text, f"{rel} mentions the vendor wire name {word!r}")


class PaymentsSliceStaysClean(SimpleTestCase):
    """Step 3, payments: the shop talks to its payment provider only through tshirtbrand.core.payments."""

    CLEAN = ["shop/payments.py", *STOREFRONT, *CONSOLE, "shop/fulfillment.py",
             "shop/orders.py", "shop/cart.py", "shop/emails.py", "shop/admin.py"]

    def test_no_stripe_sdk_or_adapter_in_the_shop(self):
        imports_of = SliceStaysClean.imports_of
        for rel in self.CLEAN:
            for name in imports_of(self, rel):
                bare = name.lstrip(".")
                self.assertFalse(bare.split(".")[0] == "stripe" or "adapters.payments" in bare,
                                 f"{rel} imports {name}: go through tshirtbrand.bootstrap.get_gateway()")

    def test_no_stripe_wire_names(self):
        for rel in self.CLEAN:
            text = (REPO / rel).read_text(encoding="utf-8")
            for word in ("stripe.checkout", "stripe.Refund", "stripe.Webhook", "construct_event", "StripeError",
                         "fulfill_from_session", "stripe_ready"):
                self.assertFalse(word in text, f"{rel} mentions the Stripe wire name {word!r}")


class PersistenceSliceStaysClean(SimpleTestCase):
    """Step 6, persistence: the use cases keep their data behind repository ports; the modules that front them
    for the views no longer write the tables themselves."""

    def test_the_wrappers_do_not_write_the_tables(self):
        forbidden = {
            "shop/listing_sync.py": (".save(", ".update(", ".objects.", "printful_variant_id", "printful_preview"),
            "shop/payments.py": (".objects.create", ".save(", "OrderItem", "order.status", "order.grand_total"),
            "shop/fulfillment.py": (".save(", ".update(", ".create("),
        }
        for rel, words in forbidden.items():
            text = (REPO / rel).read_text(encoding="utf-8")
            for word in words:
                self.assertFalse(word in text, f"{rel} mentions {word!r}: that belongs in the persistence adapter")


class OrderingSliceStaysClean(SimpleTestCase):
    """Step 5, ordering and fulfilment use cases: sequencing and status rules live in tshirtbrand.core.ordering;
    shop/fulfillment.py only hands Django objects to the order desk and back."""

    def test_the_fulfillment_module_holds_no_rules_or_collaborators(self):
        imports = SliceStaysClean.imports_of(self, "shop/fulfillment.py")
        for name in imports:
            bare = name.lstrip(".")
            self.assertFalse(
                bare.endswith(("get_supplier", "get_gateway", "supplier_bridge", "payments", "emails"))
                or bare.startswith("tshirtbrand.core.fulfilment"),
                f"shop/fulfillment.py imports {name}: the use cases get these from bootstrap.get_order_desk()")
        text = (REPO / "shop/fulfillment.py").read_text(encoding="utf-8")
        for word in ("_rollup", "SupplierError", "EventKind", "OrderRequest", "status =", ".save("):
            self.assertFalse(word in text, f"shop/fulfillment.py mentions {word!r}")

    def test_the_status_rules_are_not_restated_elsewhere_in_the_shop(self):
        for rel in (*CONSOLE, *STOREFRONT):
            text = (REPO / rel).read_text(encoding="utf-8")
            for word in ("_address_looks_complete", "def _rollup", "should_hold"):
                self.assertFalse(word in text, f"{rel} restates {word!r}")


class CatalogueSliceStaysClean(SimpleTestCase):
    """Step 4, catalogue and pricing: the pricing rule and per-kind facts live in tshirtbrand.core.catalogue."""

    def test_the_old_pricing_constants_and_ceiling_are_gone_from_the_django_app(self):
        for rel in ("shop/models.py", *CONSOLE, *STOREFRONT):
            text = (REPO / rel).read_text(encoding="utf-8")
            for word in ("PRICING_MULTIPLIER", "PRICING_GUARDRAIL", "TEE_CEILING"):
                self.assertFalse(word in text, f"{rel} still mentions {word!r}")

    def test_the_stored_product_types_match_the_core_kinds(self):
        from shop.models import ProductType
        from tshirtbrand.core.catalogue.api import KINDS

        self.assertEqual(sorted(ProductType.values), sorted(KINDS))
        self.assertEqual({v: label for v, label in ProductType.choices}, {k.code: k.label for k in KINDS.values()})


class ArtworkSliceStaysClean(SimpleTestCase):
    """Step 2, artwork and print layout: layout maths and image handling live in tshirtbrand.core.artwork and
    the imaging adapter, so the Django app neither does the maths nor touches an image library."""

    NO_IMAGE_LIBRARY = ["shop/models.py", *STOREFRONT, "shop/supplier_bridge.py", "shop/listing_sync.py",
                        "shop/printful_delivery.py"]
    OLD_NAMES = ("placement_payload", "print_file_payload", "print_file_entries", "POSITION_OFFSETS = ")

    def test_no_image_library_in_the_models_views_or_bridge(self):
        imports_of = SliceStaysClean.imports_of
        for rel in self.NO_IMAGE_LIBRARY:
            for name in imports_of(self, rel):
                bare = name.lstrip(".")
                self.assertFalse(bare.split(".")[0] == "PIL" or bare.endswith("print_files"),
                                 f"{rel} imports {name}: use tshirtbrand.bootstrap.get_image_tool()")

    def test_the_old_layout_names_are_gone(self):
        for rel in self.NO_IMAGE_LIBRARY + CONSOLE:
            text = (REPO / rel).read_text(encoding="utf-8")
            for word in self.OLD_NAMES:
                self.assertFalse(word in text, f"{rel} still mentions {word!r}")
