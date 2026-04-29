# stockflow
# StockFlow — Inventory Management System

**Candidate:** Priya Sharma  
**Date:** April 29, 2026  
**Time spent:** ≈ 85 minutes

---

## Overview

This repository contains the solution to the StockFlow take-home assignment, split across three self-contained files. Each file targets one part of the brief and can be read independently.

| File | Part | Description |
|---|---|---|
| `part1_create_product.py` | Code Review & Debugging | Fixed `create_product` Flask endpoint |
| `part2_schema.sql` | Database Design | Full DDL for the StockFlow schema |
| `part3_low_stock_alerts.py` | Low-Stock Alert Endpoint | `GET /api/companies/<id>/alerts/low-stock` |

---

## Part 1 — Code Review & Debugging

### Bugs Fixed

**Issue 1 — Split transactions (critical)**  
The original code committed the `Product` row and the `Inventory` row in two separate transactions. A crash between the two commits would leave the database permanently inconsistent (a product with no matching inventory record).

**Fix:** `db.session.flush()` obtains the new `product.id` without committing, then a single `db.session.commit()` at the end covers both rows atomically.

---

**Issue 2 — No input validation / missing-key crashes (critical)**  
All fields were accessed with `data[key]`, which raises a raw `KeyError` (→ HTTP 500) when a field is missing.

**Fix:** All required fields are checked upfront. `price` is validated as a non-negative `Decimal`; `initial_quantity` as a non-negative `int`. Missing or invalid inputs return HTTP 400 with a human-readable message.

---

**Issue 3 — No SKU uniqueness check (business-logic bug)**  
The code did not check for duplicate SKUs. Without an application-level guard, an existing DB unique constraint throws an unhandled `IntegrityError`, and without the constraint, silent duplicates are created.

**Fix:** An explicit `Product.query.filter_by(sku=...)` check runs before the insert, returning HTTP 409 on conflict. The DB unique constraint is still recommended as a safety net.

---

**Issue 4 — `warehouse_id` stored on the `Product` model (design issue)**  
A product can exist in multiple warehouses. Attaching `warehouse_id` to `Product` locks it to a single warehouse at creation time.

**Fix:** `warehouse_id` is removed from `Product`; it lives exclusively in the `Inventory` join table.

---

**Issue 5 — No authentication / authorisation checks**  
Any caller could create products under any company.

**Fix:** A `@require_auth` decorator is assumed to populate `g.current_user`. The requested `warehouse_id` is verified to belong to the authenticated user's `company_id` before anything is written.

---

**Issue 6 — Wrong HTTP status codes**  
Successful creation returned an implicit `200 OK`. Errors returned `500`.

**Fix:** Success returns `201 Created`. Validation errors return `400`, conflicts return `409`, access failures return `403`/`404`.

---

**Issue 7 — `request.json` can be `None`**  
If the caller sends no body or the wrong `Content-Type`, `request.json` is `None` and the first dictionary access crashes with `TypeError`.

**Fix:** `request.get_json(silent=True)` is used instead; an explicit `None` check returns HTTP 400 before any field access.

---

## Part 2 — Database Design

### Tables

| Table | Purpose |
|---|---|
| `companies` | Top-level tenants |
| `users` | Belong to a company; have a `role` |
| `warehouses` | Owned by a company |
| `suppliers` | Platform-wide; linked to companies via `company_suppliers` |
| `products` | Platform-wide catalogue; SKU is globally unique |
| `product_suppliers` | Which suppliers provide which products (with cost & lead time) |
| `inventory` | Current stock level per (product, warehouse) pair |
| `inventory_movements` | Append-only audit log of every quantity change |
| `product_bundles` | Self-join for multi-component bundles |

### Key Design Decisions

- **`DECIMAL(12,4)` for money** — avoids floating-point rounding errors.
- **`inventory_movements` as an audit log** — `inventory.quantity` is the fast read path; the movements table provides full history without expensive replays.
- **`low_stock_threshold` on `products`** — the requirement states thresholds vary by product type; per-product storage is flexible without requiring a separate lookup table.
- **`CHECK (quantity >= 0)`** — prevents negative stock at the DB level.
- **Bundle self-join** — handles multi-level bundles cleanly without a separate entity.
- **Indexes on all FK columns** that appear in `WHERE` or `JOIN` clauses.

### Open Questions for the Product Team

1. **Stock reservation** — do we need a soft-lock pattern for in-flight orders? If so, a `reservations` table is required.
2. **Negative stock policy** — is going below zero allowed (backorder scenario)?
3. **Multi-currency** — is `price` always in one currency, or is a `currency_code` column needed?
4. **Bundle inventory** — is bundle stock computed from components on the fly, or tracked as its own SKU?
5. **Product ownership** — can a SKU be shared across companies, or does each company have its own catalogue?
6. **Soft delete** — should deleted products/warehouses be hidden or truly removed? This affects referential integrity choices.
7. **Orders data** — the low-stock alert relies on "recent sales activity"; where does the orders table live?

---

## Part 3 — Low-Stock Alert Endpoint

### Endpoint

```
GET /api/companies/<company_id>/alerts/low-stock
```

**Auth:** Bearer token (populates `g.current_user`)

### Response

```json
{
  "alerts": [
    {
      "product_id":          1,
      "product_name":        "Widget A",
      "sku":                 "WGT-001",
      "warehouse_id":        3,
      "warehouse_name":      "East Hub",
      "current_stock":       4,
      "threshold":           10,
      "days_until_stockout": 2,
      "supplier": {
        "id":            7,
        "name":          "Acme Supplies",
        "contact_email": "orders@acme.com"
      }
    }
  ],
  "total_alerts": 1
}
```

### Business Rules Applied

- "Recent sales activity" = at least one `inventory_movements` record with `reason = 'sale'` in the last **30 days**.
- `days_until_stockout` = `current_stock / avg_daily_sales` (averaged over 30 days). Set to `null` when there are no recent sales (no division by zero).
- Products where `is_active = FALSE` are excluded.
- One alert row is generated **per (product, warehouse)** pair.
- Results are ordered worst-first: `(current_stock - threshold) ASC`.

### Edge Cases Handled

| Scenario | Behaviour |
|---|---|
| No sales in window | Product excluded (HAVING clause) |
| Zero avg daily sales | `days_until_stockout` → `null` |
| No supplier linked | `supplier` field → `null` |
| Product in multiple warehouses | One alert row per warehouse |
| Inactive product | Excluded by `is_active = TRUE` filter |
| Wrong company | HTTP 403 |
| Company not found | HTTP 404 |

### Before Shipping

1. **Pagination** — large catalogues need `limit`/`offset` or cursor-based pagination.
2. **Preferred supplier flag** — add `is_preferred` to `product_suppliers` so supplier selection is deterministic.
3. **Caching** — low-stock reads are tolerant of slight staleness; a 5-minute Redis cache would significantly reduce DB load.
4. **Unit tests** — cover every edge case listed above.
5. **ORM migration** — replace raw SQL with ORM queries once the schema is finalised, for easier testing and maintenance.

---

## Assumptions Summary

| Area | Assumption |
|---|---|
| Auth | `@require_auth` decorator populates `g.current_user` with `company_id` |
| SKU scope | SKUs are unique platform-wide, not just per company |
| Recent sales | Last 30 days of `inventory_movements` with `reason = 'sale'` |
| Stockout estimate | Simple 30-day average; no seasonality modelling |
| Bundle stock | Bundles are independent SKUs; component-derived stock is out of scope |
| Currency | Single currency; no conversion needed |
| Supplier | First supplier in `product_suppliers` is used; no preferred flag yet |
