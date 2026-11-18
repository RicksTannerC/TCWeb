# Architecture: ports and adapters

Status: **plan, adopted 2026-11-17**. Only the skeleton and the boundary test exist so far. The migration
order at the bottom says how the rest arrives, one slice at a time, with the shop live throughout.

## Why

The shop is one Django app (`shop/`, ~11,000 lines). Business rules, HTTP handling, the ORM and the vendor
APIs (Printful, Stripe) are mixed together: `console_views.py` is 1,300 lines of all four, `models.py` carries
print-layout maths, and `printful.py` reaches into `Listing`. A change to one thing can break another, and
adding a second printer, a second product line or a second server means touching everything.

The goal is **plug and play**: each part of the project has a fixed set of inputs and outputs, so someone can
work inside one part, or replace one part, without reading or breaking the rest.

## The shape

```
tshirtbrand/
  core/                  the business. Pure Python: no Django, no vendor SDKs, no I/O.
    <context>/
      model.py             entities and rules (plain dataclasses and functions)
      ports.py             interfaces the context NEEDS from the outside (a supplier, a payment gateway, ...)
      usecases.py          the things the business can do ("publish a listing", "refund an order")
      api.py               the ONLY file other parts may import: use cases + the data they take and return
    shared/                small value types used everywhere (Money, errors, ids)
  adapters/              implementations of ports. All the dirty work lives here.
    suppliers/printful/ , suppliers/mock/
    payments/stripe/ , payments/mock/
    persistence/django_orm/
    storage/ , mail/ , imaging/ , cache/
  entrypoints/           how the outside world drives the core. Thin: parse input, call a use case, render.
    storefront/ , console/ , webhooks/ , cli/
  bootstrap.py           the composition root: reads settings, picks the adapters, hands them to the core.
shop/                    the existing Django app. Shrinks as slices move out; becomes the ORM adapter's
                         home for the tables (models keep their app label and table names: no migrations).
```

Contexts (each is a replaceable unit): `catalogue` (products, templates, listings, sizes), `artwork` (designs,
print placement and the print file), `ordering` (cart, checkout, orders), `fulfilment` (sending to a supplier,
tracking, reprints, refunds), `payments`, `customers` (subscribers, contact messages), `content` (pages),
`insights` (visits, overhead, money reports). Login throttling and 2FA are Django-bound platform code and stay
with the console entry point.

## The rules (enforced by `tshirtbrand/tests_architecture.py`)

1. **Core is pure.** A core module imports only the standard library and other core modules. No `django`, `stripe`,
   `requests`, `PIL`, no ORM, no settings, no clock or network calls except through a port.
2. **Contexts talk through `api.py`.** A context may import another context only via its `api` module (or
   `shared`). Nothing reaches into another context's `model`, `usecases` or `ports`.
3. **Adapters implement ports.** An adapter imports the core only through `ports`, `api` and `shared`. It never
   imports an entry point, `bootstrap`, or another adapter. Only `persistence` may import `shop` (the tables).
4. **Entry points call use cases.** An entry point imports the core only through `api` and `shared`, and never
   imports an adapter or a vendor SDK. It gets its collaborators from `bootstrap`.
5. **Only `bootstrap` knows both sides.** It is the one place that names a concrete adapter.
6. **Data crossing a boundary is plain.** Frozen dataclasses, `Decimal`, strings, numbers, lists. Never an ORM
   instance, a request, or a vendor's raw JSON.

## What "swap it" looks like

- **Another printer:** write `adapters/suppliers/<name>/` that satisfies `fulfilment.ports.Supplier`, pass the
  shared **contract test** (the same test suite runs against the mock and every real adapter's stubbed
  transport), change one line in `bootstrap`. Core, console and storefront don't change.
- **Another product line:** add a product kind in `catalogue` (what sizes, what print areas, what costs mean);
  suppliers declare which kinds they can make. No Printful or Stripe code mentions "shirt".
- **Another payment gateway, another mail provider, S3 instead of disk:** same move, different port.
- **A redesigned console:** replace `entrypoints/console/`; the use cases it calls are unchanged.
- **More than one server:** anything that must be shared goes behind a port from the start: file storage,
  cache, sessions, background work, the clock, the database (SQLite -> Postgres via `DATABASE_URL`). Nothing in
  the core may assume a local disk, a single process or in-memory state.

## How a slice is moved (the same recipe every time)

1. Write down the slice's inputs and outputs as dataclasses and a port, in `core/<context>/`.
2. Add a **contract test** for the port and run it against the existing mock first.
3. Move the logic into `usecases.py`, fed only by those inputs; wrap the existing code as the first adapter.
4. Point the old call sites at the new `api`; delete the old path.
5. Add the slice to the boundary test's "must be clean" list so it cannot regress.
6. Whole suite green (555 at the time of writing), CHANGELOG entry, own commit. The site runs the whole way.

## Migration order

0. **Guardrails (done in this step):** skeleton, this document, the boundary test.
1. **Fulfilment supplier port: DONE 2026-11-17.** `core/fulfilment` (neutral types + `Supplier` port),
   `adapters/suppliers/printful` (raw client, canned mock, `PrintfulSupplier`), `adapters/suppliers/memory`
   (a second implementation), one contract test run against all of them, `bootstrap.get_supplier()`.
   `shop/fulfillment.py`, `shop/listing_sync.py` and the console/admin now speak only neutral types; the
   boundary test keeps them that way. To add a printer: write an adapter, pass the contract, change
   `bootstrap.get_supplier()`.
   *Left for later steps:* the webhook URL/token and the `printful_webhook` command still use
   `shop/printful.py` directly (they move with the webhook entry point, step 8); `Listing.print_file_entries()`
   still builds Printful-shaped dicts that `supplier_bridge` converts (moves with step 2); model fields are still
   named `printful_*` (renamed with the persistence adapter, step 6); `get_supplier()` always picks Printful
   (a settings switch arrives with the first second real printer).
2. **Artwork / print layout: DONE 2026-11-17.** `core/artwork` (`plan_layout`, `Layout`, `print_signature`,
   `aspect_of`, `ImageTool` port), `adapters/imaging/pillow` (visible-design measuring and the composed print
   file), `bootstrap.get_image_tool()`. `Listing` exposes `main_layout()`, `layout_for()` and `print_jobs()`;
   `supplier_bridge.print_files_for` builds the neutral files. The boundary test keeps the models, views and
   bridge free of Pillow and of the old Printful-shaped names.
   *Left for later steps:* the signed artwork-link code is still `shop/printful_delivery.py` (moves with the
   storage/webhook entry points, steps 8-9); `Design.artwork` is still a Django file field (persistence, step 6);
   `PrintPlacement`/`PrintPosition` remain Django choices classes whose values the core treats as plain strings.
3. **Payments port: DONE 2026-11-18.** `core/payments` (`PaymentGateway` port, `CheckoutRequest`, `PaymentEvent`,
   checkout-line rules), `adapters/payments/stripe` and `adapters/payments/memory`, one contract test over both,
   `bootstrap.get_gateway()` (simulated when keyless or under test). `shop/payments.py` is order bookkeeping only.
   *Left for later steps:* `Order.stripe_*` field names (persistence, step 6); fulfilling an order from a payment
   event still reads and writes the ORM directly (step 5).
4. **Catalogue and pricing** (templates, listings, margins), including the product-kind abstraction.
5. **Ordering and fulfilment use cases** out of `console_views.py` / `manage_views.py` / `orders.py`.
6. **Persistence adapter.** Repositories behind ports; ORM models become an implementation detail.
7. **Split the console** into entry points per context. This is where the new console design drops in.
8. **Storefront entry point.**
9. **Multi-server readiness:** storage, cache, sessions, jobs behind ports; idempotent webhooks.

Each step is its own set of commits, deployable on its own. If a step turns out to be wrong, it is reverted
without touching the others.

## Constraints that do not change

- No migrations for the sake of moving code: models keep `app_label = "shop"` and their table names.
- The live database and `D:\TCData` are never touched by a refactor step; back up before any real migration.
- Credentials stay behind the owner's rule: nothing calls Printful, Stripe or any other credentialed service
  without a fresh yes. Contract tests use stubbed transports, never live calls.
