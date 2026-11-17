"""The contract every `Supplier` must keep. One set of checks, run against every implementation:
the in-memory supplier, Printful over its canned mock, and Printful over real HTTP with the network
replaced by a local stand-in. A new supplier is ready to plug in when it passes this class too.

Nothing here makes a real network call or needs a credential."""

import json
from decimal import Decimal

import httpx
from django.test import SimpleTestCase

from tshirtbrand.adapters.suppliers.memory.supplier import MemorySupplier
from tshirtbrand.adapters.suppliers.printful.client import MockPrintful, RealPrintful
from tshirtbrand.adapters.suppliers.printful.supplier import PrintfulSupplier
from tshirtbrand.core.fulfilment.api import (
    CatalogProduct, ColorOption, OrderLine, OrderRequest, PrintArea, PrintFile, ProductRecord, ProductSpec,
    Recipient, SizeMatch, SubmittedOrder, SupplierError, SupplierEvent, VariantSpec,
)


def fake_printful_transport():
    """Answers Printful's HTTP calls from MockPrintful's canned data, wrapped the way Printful wraps replies."""
    mock = MockPrintful()

    def handler(request):
        path, method = request.url.path, request.method
        body = json.loads(request.content) if request.content else {}
        if method == "GET" and path == "/products":
            result = mock.list_catalog()
        elif method == "GET" and path.startswith("/products/"):
            result = mock.catalog_variants(int(path.rsplit("/", 1)[1]))
        elif method == "GET" and path.startswith("/mockup-generator/printfiles/"):
            result = mock.print_files(int(path.rsplit("/", 1)[1]))
        elif method == "POST" and path == "/store/products":
            result = mock.create_sync_product(body)
        elif method == "GET" and path.startswith("/store/products/"):
            result = mock.get_sync_product(path.rsplit("/", 1)[1])
        elif method == "POST" and path == "/orders":
            result = mock.create_order(body, confirm=True)
        elif method == "DELETE" and path.startswith("/orders/"):
            result = mock.cancel_order(path.rsplit("/", 1)[1])
        elif method == "POST" and path == "/webhooks":
            result = mock.set_webhook(body["url"], body["types"])
        else:
            return httpx.Response(404, json={"code": 404, "error": {"message": f"no route {method} {path}"}})
        return httpx.Response(200, json={"code": 200, "result": result})

    return httpx.MockTransport(handler)


class SupplierContract:
    """Mixin: subclasses supply `make_supplier()` and a few sample values."""

    catalog_query = "tee"     # matches something in the supplier's catalogue
    catalog_id = "71"         # a product id the supplier knows
    color = "Black"
    sample_event = None       # a webhook body this supplier would send for a shipment, or None

    def make_supplier(self):
        raise NotImplementedError

    def setUp(self):
        self.supplier = self.make_supplier()

    # --- identity
    def test_has_a_name_and_a_simulated_flag(self):
        self.assertTrue(self.supplier.name)
        self.assertIsInstance(self.supplier.simulated, bool)

    # --- catalogue
    def test_search_needs_two_characters(self):
        self.assertEqual(self.supplier.search_catalog(""), [])
        self.assertEqual(self.supplier.search_catalog(" a "), [])

    def test_search_returns_catalog_products_and_a_miss_is_empty(self):
        hits = self.supplier.search_catalog(self.catalog_query)
        self.assertTrue(hits)
        self.assertLessEqual(len(hits), 25)
        self.assertTrue(all(isinstance(h, CatalogProduct) and h.id and isinstance(h.id, str) for h in hits))
        self.assertEqual(self.supplier.search_catalog("zzzz no such thing"), [])

    def test_colors_are_named_and_sorted(self):
        colors = self.supplier.colors(self.catalog_id)
        self.assertTrue(colors)
        self.assertTrue(all(isinstance(c, ColorOption) and c.name for c in colors))
        names = [c.name for c in colors]
        self.assertEqual(names, sorted(names, key=str.lower))
        self.assertEqual(self.supplier.colors(""), [])

    def test_match_sizes_accounts_for_every_label_exactly_once(self):
        wanted = ["S", "M", "XL", "7XL"]
        m = self.supplier.match_sizes(self.catalog_id, self.color, wanted)
        self.assertIsInstance(m, SizeMatch)
        self.assertEqual(set(m.matches) | set(m.unmatched), set(wanted))
        self.assertFalse(set(m.matches) & set(m.unmatched))
        self.assertIn("7XL", m.unmatched)
        self.assertTrue(all(isinstance(v, str) and v for v in m.matches.values()))
        self.assertIn(self.color, m.available_colors)

    def test_match_sizes_in_an_unknown_colour_matches_nothing_but_lists_colours(self):
        m = self.supplier.match_sizes(self.catalog_id, "Mauve", ["S"])
        self.assertEqual(m.matches, {})
        self.assertEqual(m.unmatched, ("S",))
        self.assertTrue(m.available_colors)

    def test_print_area_is_a_real_size_or_none(self):
        area = self.supplier.print_area(self.catalog_id, "front")
        self.assertTrue(area is None or (isinstance(area, PrintArea) and area.width > 0 and area.height > 0))
        self.assertIsNone(self.supplier.print_area("", "front"))
        self.assertIsNone(self.supplier.print_area(self.catalog_id, "no_such_placement"))

    def test_made_in_us_is_a_yes_no_or_unknown(self):
        self.assertIn(self.supplier.made_in_us(self.catalog_id), (True, False, None))
        self.assertIsNone(self.supplier.made_in_us(""))

    def test_dashboard_url_is_a_link_or_empty(self):
        url = self.supplier.dashboard_url("Bella + Canvas 3001", "tee")
        self.assertTrue(url == "" or url.startswith("https://"))
        self.assertEqual(self.supplier.dashboard_url("", "tee"), "")
        self.assertEqual(self.supplier.dashboard_url("Anything", "mug"), "")

    # --- products
    def spec(self):
        files = (PrintFile("front", "https://art.example.test/a.png"),)
        return ProductSpec("Test tee", "test-tee", tuple(
            VariantSpec(f"test-tee::{s}", "", Decimal("25.00"), files) for s in ("S", "M")))

    def test_create_then_read_a_product(self):
        made = self.supplier.create_product(self.spec(), self.color)
        self.assertIsInstance(made, ProductRecord)
        self.assertTrue(made.product_id and isinstance(made.product_id, str))
        read = self.supplier.get_product(made.product_id, self.color)
        self.assertEqual(read.product_id, made.product_id)
        for v in read.variants:
            self.assertTrue(isinstance(v.id, str) and v.id)
            self.assertIsInstance(v.size, str)
        self.assertLessEqual(len(read.previews), 6)
        self.assertTrue(all(p.url.startswith("https://") for p in read.previews))

    # --- orders
    def order(self, ref="TTS-1-1"):
        return OrderRequest(ref, Recipient("Sam Buyer", "sam@example.test", "1 Main St", "", "Afton", "WY", "US", "83110"),
                            (OrderLine(1, "Test tee (M)", Decimal("25.00"), catalog_variant_id="4011",
                                       files=(PrintFile("front", "https://art.example.test/a.png"),)),))

    def test_submit_returns_an_id_and_typed_costs(self):
        sub = self.supplier.submit_order(self.order())
        self.assertIsInstance(sub, SubmittedOrder)
        self.assertTrue(sub.supplier_order_id and isinstance(sub.supplier_order_id, str))
        self.assertTrue(sub.cost_total is None or (isinstance(sub.cost_total, Decimal) and sub.cost_total > 0))
        self.assertIsInstance(sub.cost_tax, Decimal)

    def test_different_references_get_different_supplier_ids(self):
        a = self.supplier.submit_order(self.order("TTS-9-1"))
        b = self.supplier.submit_order(self.order("TTS-9-2"))
        self.assertNotEqual(a.supplier_order_id, b.supplier_order_id)

    def test_a_submitted_order_can_be_cancelled(self):
        sub = self.supplier.submit_order(self.order())
        self.assertIsNone(self.supplier.cancel_order(sub.supplier_order_id))

    # --- events
    def test_register_events_lists_what_it_subscribed_to(self):
        names = self.supplier.register_events("https://shop.example.test/hook/x/")
        self.assertTrue(names and all(isinstance(n, str) for n in names))

    def test_garbage_is_not_an_event_and_never_raises(self):
        for junk in (None, [], "x", 5, {}, {"type": 5}, {"type": "package_shipped", "data": 3}, {"event": None}):
            self.assertIsNone(self.supplier.parse_event(junk), repr(junk))

    def test_a_shipment_event_is_understood(self):
        if self.sample_event is None:
            self.skipTest("no sample")
        ev = self.supplier.parse_event(self.sample_event)
        self.assertIsInstance(ev, SupplierEvent)
        self.assertEqual(ev.kind.value, "shipped")
        self.assertEqual(ev.tracking_number, "TRK1")


class MemorySupplierContract(SupplierContract, SimpleTestCase):
    catalog_query = "tee"
    catalog_id = "1"
    sample_event = {"event": "shipped", "order": "5", "tracking_number": "TRK1"}

    def make_supplier(self):
        return MemorySupplier()


SHIPPED = {"type": "package_shipped", "data": {"order": {"id": 5, "external_id": "TTS-1-1"},
                                               "shipment": {"tracking_number": "TRK1", "carrier": "UPS"}}}


class PrintfulOverMockContract(SupplierContract, SimpleTestCase):
    catalog_query = "bella"
    sample_event = SHIPPED

    def make_supplier(self):
        return PrintfulSupplier(MockPrintful())


class PrintfulOverHttpContract(SupplierContract, SimpleTestCase):
    """The real HTTP client, the real wire shapes, a fake network."""
    catalog_query = "bella"
    sample_event = SHIPPED

    def make_supplier(self):
        return PrintfulSupplier(RealPrintful("test-key", transport=fake_printful_transport()))

    def test_it_reports_itself_as_not_simulated(self):
        self.assertFalse(self.supplier.simulated)

    def test_a_refusal_becomes_a_supplier_error_with_the_suppliers_message(self):
        def refuse(request):
            return httpx.Response(400, json={"code": 400, "error": {"message": "Variant not available"}})

        supplier = PrintfulSupplier(RealPrintful("k", transport=httpx.MockTransport(refuse)))
        with self.assertRaisesMessage(SupplierError, "Variant not available"):
            supplier.submit_order(self.order())

    def test_the_api_key_is_sent_as_a_bearer_token_and_nothing_else_leaks(self):
        seen = []

        def spy(request):
            seen.append(request)
            return httpx.Response(200, json={"code": 200, "result": MockPrintful().create_order({"external_id": "x"})})

        PrintfulSupplier(RealPrintful("secret-123", transport=httpx.MockTransport(spy))).submit_order(self.order())
        req = seen[0]
        self.assertEqual(req.headers["authorization"], "Bearer secret-123")
        self.assertNotIn(b"secret-123", req.content)
        self.assertEqual(str(req.url), "https://api.printful.com/orders?confirm=1")


class PrintfulWireFormat(SimpleTestCase):
    """What Printful specifically expects: the part of the contract only this adapter owns."""

    def submit(self, order):
        sent = []

        class Spy(MockPrintful):
            def create_order(self, payload, confirm=False):
                sent.append((payload, confirm))
                return {"id": 9, "costs": {"total": "12.50", "tax": "1.00", "vat": "0.25"}}

        return PrintfulSupplier(Spy()).submit_order(order), sent[0]

    def test_a_synced_line_goes_by_sync_variant_and_a_blank_line_by_catalog_variant_with_art(self):
        order = OrderRequest("R-1", Recipient("A B", "a@b.test", "1 St", "Apt 2", "Afton", "WY", "US", "83110"), (
            OrderLine(2, "Shirt", Decimal("30"), product_variant_id="8001"),
            OrderLine(1, "Other", Decimal("30"), catalog_variant_id="4011",
                      files=(PrintFile("front", "https://a.test/x.png"),)),
        ))
        result, (payload, confirm) = self.submit(order)
        self.assertTrue(confirm)
        self.assertEqual(payload["recipient"], {"name": "A B", "email": "a@b.test", "address1": "1 St", "address2": "Apt 2",
                                                "city": "Afton", "state_code": "WY", "country_code": "US", "zip": "83110"})
        synced, blank = payload["items"]
        self.assertEqual(synced, {"quantity": 2, "name": "Shirt", "retail_price": "30", "sync_variant_id": 8001})
        self.assertEqual(blank["variant_id"], 4011)
        self.assertEqual(blank["files"], [{"url": "https://a.test/x.png", "type": "front"}])
        self.assertEqual((result.supplier_order_id, result.cost_total, result.cost_tax), ("9", Decimal("12.50"), Decimal("1.25")))

    def test_a_box_becomes_printfuls_position_object(self):
        from tshirtbrand.core.fulfilment.api import PrintBox

        order = OrderRequest("R-2", Recipient("A"), (OrderLine(
            1, "S", Decimal("1"), catalog_variant_id="1",
            files=(PrintFile("front", "https://a.test/x.svg", PrintBox(1800, 2400, 100, 50, 900, 700)),)),))
        _, (payload, _c) = self.submit(order)
        self.assertEqual(payload["items"][0]["files"][0]["position"],
                         {"area_width": 1800, "area_height": 2400, "width": 900, "height": 700, "top": 50, "left": 100})

    def test_a_zero_or_missing_cost_is_no_cost(self):
        class Free(MockPrintful):
            pass

        sub = PrintfulSupplier(Free()).submit_order(OrderRequest("R-3", Recipient("A"), (
            OrderLine(1, "S", Decimal("1"), catalog_variant_id="1"),)))
        self.assertIsNone(sub.cost_total)

    def test_every_event_name_maps_to_a_kind(self):
        s = PrintfulSupplier(MockPrintful())
        order = {"id": 5, "external_id": "TTS-1-1"}
        cases = [
            ("order_updated", {"order": {**order, "status": "inprocess"}}, "in_production"),
            ("package_returned", {"order": order}, "returned"),
            ("order_failed", {"order": order, "reason": "bad file"}, "failed"),
            ("order_put_hold", {"order": order}, "on_hold"),
            ("order_canceled", {"order": order}, "canceled"),
        ]
        for etype, data, kind in cases:
            ev = s.parse_event({"type": etype, "data": data})
            self.assertEqual((ev.kind.value, ev.supplier_order_id, ev.external_id), (kind, "5", "TTS-1-1"), etype)
        self.assertEqual(s.parse_event({"type": "order_failed", "data": {"order": order, "reason": "bad file"}}).reason, "bad file")
        self.assertIsNone(s.parse_event({"type": "order_updated", "data": {"order": {**order, "status": "draft"}}}))
        self.assertIsNone(s.parse_event({"type": "something_else", "data": {}}))

    def test_previews_use_the_wanted_colour_and_drop_non_images(self):
        class Rich(MockPrintful):
            def get_sync_product(self, product_id):
                return {"sync_product": {"id": 7, "thumbnail_url": "https://files.cdn.printful.com/"},
                        "sync_variants": [
                            {"id": 1, "name": "T - Black / M", "files": [{"type": "preview", "preview_url": "https://i.test/black.png"}]},
                            {"id": 2, "name": "T - White / M", "files": [{"type": "preview", "preview_url": "https://i.test/white.png"}]},
                        ]}

        rec = PrintfulSupplier(Rich()).get_product("7", "White")
        self.assertEqual([(p.label, p.url) for p in rec.previews], [("White", "https://i.test/white.png")])
        self.assertEqual([(v.id, v.size, v.color) for v in rec.variants], [("1", "M", "Black"), ("2", "M", "White")])

    def test_catalogue_calls_are_cached(self):
        calls = []

        class Counting(MockPrintful):
            def list_catalog(self):
                calls.append(1)
                return super().list_catalog()

        s = PrintfulSupplier(Counting())
        s.search_catalog("stanley")
        s.search_catalog("gildan")
        self.assertEqual(len(calls), 1)
