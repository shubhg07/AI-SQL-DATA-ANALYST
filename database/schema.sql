-- NovaCart schema (MySQL 8).
-- Inferred from the INSERT statements in seed_data.py.
-- seed_data.py only runs this file if the tables do not exist yet,
-- so if you already have your own schema, yours is kept.

CREATE TABLE IF NOT EXISTS categories (
    category_id   INT AUTO_INCREMENT PRIMARY KEY,
    category_name VARCHAR(100) NOT NULL,
    department    VARCHAR(100) NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
    product_id    INT AUTO_INCREMENT PRIMARY KEY,
    category_id   INT NOT NULL,
    product_name  VARCHAR(150) NOT NULL,
    brand         VARCHAR(100),
    cost_price    DECIMAL(10,2) NOT NULL,
    selling_price DECIMAL(10,2) NOT NULL,
    launch_date   DATE,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    FOREIGN KEY (category_id) REFERENCES categories(category_id)
);

CREATE TABLE IF NOT EXISTS customers (
    customer_id         INT AUTO_INCREMENT PRIMARY KEY,
    first_name          VARCHAR(80) NOT NULL,
    last_name           VARCHAR(80) NOT NULL,
    email               VARCHAR(150) NOT NULL UNIQUE,
    gender              VARCHAR(20),
    date_of_birth       DATE,
    signup_date         DATE NOT NULL,
    customer_segment    VARCHAR(30),
    acquisition_channel VARCHAR(50)
);

CREATE TABLE IF NOT EXISTS addresses (
    address_id   INT AUTO_INCREMENT PRIMARY KEY,
    customer_id  INT NOT NULL,
    city         VARCHAR(100),
    state        VARCHAR(100),
    country      VARCHAR(50),
    postal_code  VARCHAR(20),
    address_type VARCHAR(20),
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

CREATE TABLE IF NOT EXISTS orders (
    order_id         INT AUTO_INCREMENT PRIMARY KEY,
    customer_id      INT NOT NULL,
    order_date       DATETIME NOT NULL,
    order_status     VARCHAR(20) NOT NULL,
    shipping_city    VARCHAR(100),
    shipping_state   VARCHAR(100),
    shipping_country VARCHAR(50),
    discount_amount  DECIMAL(10,2) NOT NULL DEFAULT 0,
    shipping_fee     DECIMAL(10,2) NOT NULL DEFAULT 0,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
    INDEX idx_orders_date (order_date)
);

CREATE TABLE IF NOT EXISTS order_items (
    order_item_id INT AUTO_INCREMENT PRIMARY KEY,
    order_id      INT NOT NULL,
    product_id    INT NOT NULL,
    quantity      INT NOT NULL,
    unit_price    DECIMAL(10,2) NOT NULL,
    item_discount DECIMAL(10,2) NOT NULL DEFAULT 0,
    FOREIGN KEY (order_id) REFERENCES orders(order_id),
    FOREIGN KEY (product_id) REFERENCES products(product_id)
);

CREATE TABLE IF NOT EXISTS payments (
    payment_id     INT AUTO_INCREMENT PRIMARY KEY,
    order_id       INT NOT NULL,
    payment_date   DATETIME NOT NULL,
    payment_method VARCHAR(30),
    payment_status VARCHAR(20),
    amount         DECIMAL(12,2) NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders(order_id)
);

CREATE TABLE IF NOT EXISTS returns (
    return_id     INT AUTO_INCREMENT PRIMARY KEY,
    order_item_id INT NOT NULL,
    return_date   DATE NOT NULL,
    return_reason VARCHAR(50),
    return_status VARCHAR(30),
    refund_amount DECIMAL(10,2) NOT NULL,
    FOREIGN KEY (order_item_id) REFERENCES order_items(order_item_id)
);