from flask import request, jsonify, abort, g
from sqlalchemy.exc import IntegrityError
from decimal import Decimal, InvalidOperation


@app.route('/api/products', methods=['POST'])
@require_auth  # assumed decorator that populates g.current_user
def create_product():   
    # 1. Parse body                                                     
    data = request.get_json(silent=True)
    if not data:
        abort(400, description="Request body must be valid JSON.")

    # 2. Validate required fields                                         
    required = ['name', 'sku', 'warehouse_id', 'price', 'initial_quantity']
    missing = [f for f in required if f not in data]
    if missing:
        abort(400, description=f"Missing required fields: {', '.join(missing)}")

    # 3. Validate types / ranges                                          
    try:
        price = Decimal(str(data['price']))
        if price < 0:
            raise ValueError
    except (InvalidOperation, ValueError):
        abort(400, description="'price' must be a non-negative number.")

    try:
        quantity = int(data['initial_quantity'])
        if quantity < 0:
            raise ValueError
    except (ValueError, TypeError):
        abort(400, description="'initial_quantity' must be a non-negative integer.")

    # 4. Authorise warehouse access                                       
    warehouse_id = data['warehouse_id']
    warehouse = Warehouse.query.filter_by(
        id=warehouse_id,
        company_id=g.current_user.company_id
    ).first()
    if not warehouse:
        abort(404, description="Warehouse not found or access denied.")

    # 5. Check SKU uniqueness (application layer; DB constraint is backup)
    if Product.query.filter_by(sku=data['sku']).first():
        abort(409, description=f"SKU '{data['sku']}' already exists.")

    # 6. Write both rows in a single atomic transaction                 
    try:
        product = Product(
            name=data['name'],
            sku=data['sku'],
            price=price,
            # warehouse_id intentionally omitted: the relationship lives in Inventory
        )
        db.session.add(product)
        db.session.flush()   # obtain product.id without committing yet

        inventory = Inventory(
            product_id=product.id,
            warehouse_id=warehouse_id,
            quantity=quantity,
        )
        db.session.add(inventory)
        db.session.commit()  # one commit covers both rows

    except IntegrityError:
        db.session.rollback()
        abort(409, description="A database conflict occurred. Please try again.")
    except Exception:
        db.session.rollback()
        raise

    return jsonify({
        "message": "Product created successfully.",
        "product_id": product.id,
    }), 201
