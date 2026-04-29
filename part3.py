from flask import jsonify, abort, g
from sqlalchemy import text
from datetime import datetime, timedelta


RECENT_SALES_WINDOW_DAYS = 30


@app.route('/api/companies/<int:company_id>/alerts/low-stock', methods=['GET'])
@require_auth
def low_stock_alerts(company_id):
    # ------------------------------------------------------------------ #
    # 1. Authorisation                                                     #
    # ------------------------------------------------------------------ #
    if g.current_user.company_id != company_id:
        abort(403, description="Access denied.")

    company = Company.query.get(company_id)
    if not company:
        abort(404, description="Company not found.")

    cutoff_date = datetime.utcnow() - timedelta(days=RECENT_SALES_WINDOW_DAYS)

    # ------------------------------------------------------------------ #
    # 2. Single query                                                      #
    #    - joins products → inventory → warehouses (scoped to company)    #
    #    - filters to rows where quantity < low_stock_threshold            #
    #    - checks at least one sale movement exists within the window      #
    #    - calculates avg daily sales and preferred supplier               #
    # ------------------------------------------------------------------ #
    sql = text("""
        SELECT
            p.id            AS product_id,
            p.name          AS product_name,
            p.sku           AS sku,
            w.id            AS warehouse_id,
            w.name          AS warehouse_name,
            inv.quantity    AS current_stock,
            p.low_stock_threshold AS threshold,

            -- Average daily outbound sales over the window
            COALESCE(
                ABS(SUM(CASE
                    WHEN im.reason = 'sale'
                     AND im.created_at >= :cutoff
                    THEN im.delta ELSE 0
                END)) / :window_days,
                0
            ) AS avg_daily_sales,

            -- First supplier found (production: add is_preferred flag)
            s.id            AS supplier_id,
            s.name          AS supplier_name,
            s.contact_email AS supplier_email

        FROM products p
        JOIN inventory inv
            ON inv.product_id = p.id
        JOIN warehouses w
            ON w.id            = inv.warehouse_id
           AND w.company_id    = :company_id
        LEFT JOIN inventory_movements im
            ON im.inventory_id = inv.id
        LEFT JOIN product_suppliers ps
            ON ps.product_id   = p.id
        LEFT JOIN suppliers s
            ON s.id            = ps.supplier_id

        WHERE p.company_id          = :company_id
          AND p.is_active           = TRUE
          AND inv.quantity          < p.low_stock_threshold

        GROUP BY
            p.id, p.name, p.sku,
            w.id, w.name,
            inv.quantity, p.low_stock_threshold,
            s.id, s.name, s.contact_email

        -- Only include if at least one sale occurred within the window
        HAVING SUM(CASE
                    WHEN im.reason = 'sale'
                     AND im.created_at >= :cutoff
                    THEN 1 ELSE 0
                   END) > 0

        ORDER BY (inv.quantity - p.low_stock_threshold) ASC   -- worst first
    """)

    rows = db.session.execute(sql, {
        'company_id':  company_id,
        'cutoff':      cutoff_date,
        'window_days': RECENT_SALES_WINDOW_DAYS,
    }).fetchall()

    # ------------------------------------------------------------------ #
    # 3. Build response                                                    #
    # ------------------------------------------------------------------ #
    alerts = []
    for row in rows:
        avg_daily = float(row.avg_daily_sales)

        # Avoid division by zero; return null when stock is not moving
        if avg_daily > 0:
            days_until_stockout = round(row.current_stock / avg_daily)
        else:
            days_until_stockout = None

        alert = {
            "product_id":          row.product_id,
            "product_name":        row.product_name,
            "sku":                 row.sku,
            "warehouse_id":        row.warehouse_id,
            "warehouse_name":      row.warehouse_name,
            "current_stock":       row.current_stock,
            "threshold":           row.threshold,
            "days_until_stockout": days_until_stockout,
            "supplier": {
                "id":            row.supplier_id,
                "name":          row.supplier_name,
                "contact_email": row.supplier_email,
            } if row.supplier_id else None,
        }
        alerts.append(alert)

    return jsonify({
        "alerts":       alerts,
        "total_alerts": len(alerts),
    }), 200
