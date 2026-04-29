-- Companies (tenants)

CREATE TABLE companies (
    id         INT          PRIMARY KEY AUTO_INCREMENT,
    name       VARCHAR(255) NOT NULL,
    created_at TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);
 
 
-- Users  (belong to a company)

CREATE TABLE users (
    id         INT          PRIMARY KEY AUTO_INCREMENT,
    company_id INT          NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    email      VARCHAR(255) NOT NULL UNIQUE,
    role       VARCHAR(50)  NOT NULL DEFAULT 'member',   -- 'admin', 'member', …
    created_at TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);
 
 
-- Warehouses  (owned by a company)

CREATE TABLE warehouses (
    id         INT          PRIMARY KEY AUTO_INCREMENT,
    company_id INT          NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    name       VARCHAR(255) NOT NULL,
    address    TEXT,
    created_at TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_warehouses_company (company_id)
);
 
 
-- Suppliers  (can serve multiple companies; many-to-many via company_suppliers)

CREATE TABLE suppliers (
    id            INT          PRIMARY KEY AUTO_INCREMENT,
    name          VARCHAR(255) NOT NULL,
    contact_email VARCHAR(255),
    contact_phone VARCHAR(50),
    created_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);
 
CREATE TABLE company_suppliers (
    company_id  INT          NOT NULL REFERENCES companies(id)  ON DELETE CASCADE,
    supplier_id INT          NOT NULL REFERENCES suppliers(id)  ON DELETE CASCADE,
    account_ref VARCHAR(100),            -- company's account number with supplier
    PRIMARY KEY (company_id, supplier_id)
);
 
 
-- Products  (SKU is unique platform-wide)

CREATE TABLE products (
    id                  INT            PRIMARY KEY AUTO_INCREMENT,
    company_id          INT            NOT NULL REFERENCES companies(id),
    sku                 VARCHAR(100)   NOT NULL UNIQUE,
    name                VARCHAR(255)   NOT NULL,
    description         TEXT,
    price               DECIMAL(12, 4) NOT NULL,
    product_type        VARCHAR(50)    NOT NULL DEFAULT 'standard',
    low_stock_threshold INT            NOT NULL DEFAULT 10,
    is_active           BOOLEAN        NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP
                                       ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_products_company (company_id),
    INDEX idx_products_sku     (sku)
);
 
 
-- Product ↔ Supplier relationship

CREATE TABLE product_suppliers (
    product_id  INT            NOT NULL REFERENCES products(id)  ON DELETE CASCADE,
    supplier_id INT            NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
    unit_cost   DECIMAL(12, 4),
    lead_days   INT,                     -- typical lead time in days
    PRIMARY KEY (product_id, supplier_id)
);
 
 
-- Inventory  (quantity of a product in each warehouse)

CREATE TABLE inventory (
    id           INT       PRIMARY KEY AUTO_INCREMENT,
    product_id   INT       NOT NULL REFERENCES products(id)   ON DELETE CASCADE,
    warehouse_id INT       NOT NULL REFERENCES warehouses(id) ON DELETE CASCADE,
    quantity     INT       NOT NULL DEFAULT 0
                           CHECK (quantity >= 0),             -- never negative
    updated_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                           ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_inventory_product_warehouse (product_id, warehouse_id),
    INDEX idx_inventory_warehouse (warehouse_id)
);
 
 
-- Inventory movements  (append-only audit log of every quantity change)

CREATE TABLE inventory_movements (
    id           BIGINT       PRIMARY KEY AUTO_INCREMENT,
    inventory_id INT          NOT NULL REFERENCES inventory(id),
    delta        INT          NOT NULL,   -- positive = stock in, negative = stock out
    reason       VARCHAR(100) NOT NULL,   -- 'sale', 'purchase', 'adjustment', 'return'
    reference_id INT,                     -- e.g. order_id or purchase_order_id
    created_by   INT          REFERENCES users(id),
    created_at   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_movements_inventory (inventory_id),
    INDEX idx_movements_created   (created_at)
);
 
 
-- Product bundles  (parent product → component products, self-join)

CREATE TABLE product_bundles (
    bundle_product_id    INT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    component_product_id INT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    quantity             INT NOT NULL DEFAULT 1,
    PRIMARY KEY (bundle_product_id, component_product_id)
);
