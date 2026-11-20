"""NovaCart fake data generator - an Apple-products store (MySQL + Faker).

Run from the project root:
    python database/seed_data.py

What it does
  * reads the MySQL login from .env (no passwords in the code)
  * creates the database / tables from schema.sql ONLY if they are missing
  * empties the tables first, so you can re-run it without duplicate rows
  * generates realistic data, and plants 4 "underperforming" products so the
    AI analyst has real causes to discover (names are printed at the end and
    saved to database/underperformers.txt)
"""
import os
import random
from datetime import datetime, timedelta
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv
from faker import Faker

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

random.seed(42)          # same data every run (remove both lines for random data)
Faker.seed(42)
fake = Faker("en_IN")

# =========================================================
# MYSQL CONNECTION
# =========================================================

DB_NAME = os.getenv("MYSQL_DATABASE", "novacart")

conn = mysql.connector.connect(
    host=os.getenv("MYSQL_HOST", "localhost"),
    port=int(os.getenv("MYSQL_PORT", "3306")),
    user=os.getenv("MYSQL_USER", "root"),
    password=os.getenv("MYSQL_PASSWORD", ""),
)

cursor = conn.cursor()

cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}`")
conn.database = DB_NAME

print("Connected to MySQL successfully!")

# =========================================================
# 0. CREATE TABLES (only if missing) + EMPTY THEM
# =========================================================

TABLES_IN_ORDER = [
    "categories", "products", "customers", "addresses",
    "orders", "order_items", "payments", "returns",
]

cursor.execute("SHOW TABLES")
existing_tables = {row[0].lower() for row in cursor.fetchall()}

if not set(TABLES_IN_ORDER) <= existing_tables:
    print("Some tables are missing - creating them from schema.sql")
    schema_sql = (Path(__file__).with_name("schema.sql")).read_text(encoding="utf-8")
    schema_sql = "\n".join(
        line for line in schema_sql.splitlines() if not line.strip().startswith("--")
    )
    for statement in schema_sql.split(";"):
        if statement.strip():
            cursor.execute(statement)
    conn.commit()

cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
for table in reversed(TABLES_IN_ORDER):
    cursor.execute(f"TRUNCATE TABLE `{table}`")
cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
conn.commit()

print("Tables are empty and ready.")

# =========================================================
# 1. CATEGORIES
# =========================================================

categories = [
    ("iPhone", "Mobile"),
    ("iPad", "Tablets"),
    ("Laptops", "Mac"),
    ("Desktops", "Mac"),
    ("AirPods", "Audio"),
    ("Apple Watch", "Wearables"),
    ("Home & TV", "Home Entertainment"),
    ("Accessories", "Accessories")
]

cursor.executemany(
    """
    INSERT INTO categories (category_name, department)
    VALUES (%s, %s)
    """,
    categories
)

conn.commit()

print("Categories inserted:", len(categories))

# =========================================================
# 2. PRODUCTS
# =========================================================

# Names and launch dates follow Apple's real line-up; prices are illustrative
# Indian rupee prices, not official ones. Add / remove rows freely.
# (product_name, selling_price in Rs, launch_date)
CATALOG = {
    "iPhone": [
        ("iPhone 16e 128GB", 59900, "2025-02-28"),
        ("iPhone 16 128GB", 79900, "2024-09-20"),
        ("iPhone 16 256GB", 89900, "2024-09-20"),
        ("iPhone 16 Plus 128GB", 89900, "2024-09-20"),
        ("iPhone 16 Pro 128GB", 119900, "2024-09-20"),
        ("iPhone 16 Pro 256GB", 129900, "2024-09-20"),
        ("iPhone 16 Pro Max 256GB", 144900, "2024-09-20"),
        ("iPhone 16 Pro Max 512GB", 164900, "2024-09-20"),
        ("iPhone 15 128GB", 69900, "2023-09-22"),
        ("iPhone 14 128GB", 59900, "2022-09-16"),
    ],
    "iPad": [
        ("iPad (A16) 128GB", 34900, "2025-03-12"),
        ("iPad mini (A17 Pro) 128GB", 49900, "2024-10-23"),
        ("iPad Air 11-inch (M3) 128GB", 59900, "2025-03-12"),
        ("iPad Air 13-inch (M3) 128GB", 79900, "2025-03-12"),
        ("iPad Pro 11-inch (M4) 256GB", 99900, "2024-05-15"),
        ("iPad Pro 13-inch (M4) 256GB", 129900, "2024-05-15"),
        ("iPad Pro 13-inch (M4) 1TB", 189900, "2024-05-15"),
    ],
    "Laptops": [
        ("MacBook Air 13-inch (M4) 16GB/256GB", 99900, "2025-03-12"),
        ("MacBook Air 13-inch (M4) 16GB/512GB", 119900, "2025-03-12"),
        ("MacBook Air 15-inch (M4) 16GB/256GB", 124900, "2025-03-12"),
        ("MacBook Pro 14-inch (M4) 16GB/512GB", 169900, "2024-11-08"),
        ("MacBook Pro 14-inch (M4 Pro) 24GB/512GB", 199900, "2024-11-08"),
        ("MacBook Pro 16-inch (M4 Pro) 24GB/512GB", 249900, "2024-11-08"),
        ("MacBook Pro 16-inch (M4 Max) 36GB/1TB", 349900, "2024-11-08"),
        ("MacBook Pro 14-inch (M5) 16GB/512GB", 169900, "2025-10-22"),
    ],
    "Desktops": [
        ("iMac 24-inch (M4) 16GB/256GB", 134900, "2024-11-08"),
        ("Mac mini (M4) 16GB/256GB", 59900, "2024-11-08"),
        ("Mac mini (M4 Pro) 24GB/512GB", 149900, "2024-11-08"),
        ("Mac Studio (M4 Max) 36GB/512GB", 209900, "2025-03-12"),
    ],
    "AirPods": [
        ("AirPods 4", 12900, "2024-09-20"),
        ("AirPods 4 with Active Noise Cancellation", 17900, "2024-09-20"),
        ("AirPods Pro (2nd generation) USB-C", 24900, "2023-09-22"),
        ("AirPods Max", 59900, "2024-09-20"),
    ],
    "Apple Watch": [
        ("Apple Watch SE (2nd generation) 40mm", 29900, "2022-09-16"),
        ("Apple Watch Series 10 42mm", 46900, "2024-09-20"),
        ("Apple Watch Series 10 46mm", 49900, "2024-09-20"),
        ("Apple Watch Ultra 2", 89900, "2023-09-22"),
    ],
    "Home & TV": [
        ("Apple TV 4K Wi-Fi 64GB", 14900, "2022-11-04"),
        ("Apple TV 4K Wi-Fi + Ethernet 128GB", 16900, "2022-11-04"),
        ("HomePod (2nd generation)", 32900, "2023-02-03"),
        ("HomePod mini", 10900, "2020-11-16"),
    ],
    "Accessories": [
        ("Apple Pencil Pro", 13900, "2024-05-15"),
        ("Apple Pencil (USB-C)", 7900, "2023-11-01"),
        ("Magic Mouse", 9500, "2021-10-18"),
        ("Magic Keyboard with Touch ID", 15500, "2024-11-08"),
        ("AirTag (1 Pack)", 3490, "2021-04-30"),
        ("MagSafe Charger (1 m)", 4500, "2020-10-13"),
        ("20W USB-C Power Adapter", 1900, "2020-10-13"),
    ],
}

# How popular each category is (relative), before each product's own randomness
CATEGORY_POPULARITY = {
    "iPhone": 1.6,
    "iPad": 0.9,
    "Laptops": 0.7,
    "Desktops": 0.35,
    "AirPods": 1.3,
    "Apple Watch": 1.0,
    "Home & TV": 0.5,
    "Accessories": 1.1,
}

# Hidden stories: four products with a specific reason for weak sales.
#   declining   - demand falls ~22% every month (an older model being replaced)
#   overpriced  - priced ~3x the other AirPods, so very few people buy it
#   quality     - lots of returns (Damaged / Not as Expected)
#   late_launch - launched in Oct 2025, so it only had ~2 months on sale
STORIES = {
    "iPhone 14 128GB": "declining",
    "AirPods Max": "overpriced",
    "MagSafe Charger (1 m)": "quality",
    "MacBook Pro 14-inch (M5) 16GB/512GB": "late_launch",
}
STORY_TEXT = {
    "declining": "monthly demand shrinks ~22% each month through 2025",
    "overpriced": "priced ~3x the other AirPods, so very few sales",
    "quality": "about 25% of delivered items are returned, mostly Damaged / Not as Expected",
    "late_launch": "launched 2025-10-22, so it had only ~2 months on sale in 2025",
}

# Get category IDs
cursor.execute("SELECT category_id, category_name FROM categories")
category_map = {
    name: category_id
    for category_id, name in cursor.fetchall()
}

products = []
category_of_name = {}

for category, items in CATALOG.items():

    for product_name, selling_price, launch in items:

        cost_price = round(
            selling_price * random.uniform(0.60, 0.80),
            2
        )

        products.append(
            (
                category_map[category],
                product_name,
                "Apple",
                cost_price,
                selling_price,
                datetime.strptime(launch, "%Y-%m-%d").date(),
                True
            )
        )
        category_of_name[product_name] = category

story_by_name = dict(STORIES)

cursor.executemany(
    """
    INSERT INTO products
    (
        category_id,
        product_name,
        brand,
        cost_price,
        selling_price,
        launch_date,
        is_active
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    """,
    products
)

conn.commit()

print("Products inserted:", len(products))

# =========================================================
# 3. CUSTOMERS
# =========================================================

customers = []

acquisition_channels = [
    "Organic Search",
    "Paid Ads",
    "Email",
    "Social Media",
    "Referral",
    "Direct"
]

segments = [
    "New",
    "Regular",
    "VIP",
    "Inactive"
]

for i in range(500):

    first_name = fake.first_name()
    last_name = fake.last_name()

    email = f"{first_name.lower()}.{last_name.lower()}{i}@example.com"

    gender = random.choice([
        "Male",
        "Female",
        "Other"
    ])

    dob = fake.date_of_birth(
        minimum_age=18,
        maximum_age=65
    )

    signup_date = fake.date_between(
        start_date="-3y",
        end_date=datetime(2025, 12, 1).date()
    )

    segment = random.choices(
        segments,
        weights=[25, 50, 15, 10]
    )[0]

    channel = random.choice(acquisition_channels)

    customers.append(
        (
            first_name,
            last_name,
            email,
            gender,
            dob,
            signup_date,
            segment,
            channel
        )
    )

cursor.executemany(
    """
    INSERT INTO customers
    (
        first_name,
        last_name,
        email,
        gender,
        date_of_birth,
        signup_date,
        customer_segment,
        acquisition_channel
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """,
    customers
)

conn.commit()

print("Customers inserted:", len(customers))

# =========================================================
# 4. ADDRESSES
# =========================================================

cursor.execute("SELECT customer_id FROM customers")
customer_ids = [row[0] for row in cursor.fetchall()]

addresses = []

for customer_id in customer_ids:

    number_of_addresses = random.choices(
        [1, 2],
        weights=[80, 20]
    )[0]

    for i in range(number_of_addresses):

        address_type = "Shipping" if i == 0 else "Billing"

        addresses.append(
            (
                customer_id,
                fake.city(),
                fake.state(),
                "India",
                fake.postcode(),
                address_type
            )
        )

cursor.executemany(
    """
    INSERT INTO addresses
    (
        customer_id,
        city,
        state,
        country,
        postal_code,
        address_type
    )
    VALUES (%s, %s, %s, %s, %s, %s)
    """,
    addresses
)

conn.commit()

print("Addresses inserted:", len(addresses))

# =========================================================
# 5. GET PRODUCT IDs + SALES POPULARITY
# =========================================================

cursor.execute(
    """
    SELECT product_id, product_name, selling_price, launch_date
    FROM products
    """
)

product_data = cursor.fetchall()

product_ids = [row[0] for row in product_data]

product_prices = {
    row[0]: float(row[2])
    for row in product_data
}

product_launch = {
    row[0]: row[3]
    for row in product_data
}

story_by_pid = {
    row[0]: story_by_name[row[1]]
    for row in product_data
    if row[1] in story_by_name
}

# Every product gets its category's popularity with some natural variation
popularity = {
    row[0]: CATEGORY_POPULARITY[category_of_name[row[1]]] * random.uniform(0.7, 1.3)
    for row in product_data
}

for pid, story in story_by_pid.items():
    if story == "overpriced":
        popularity[pid] = 0.12
    elif story == "quality":
        popularity[pid] = 0.35


def product_weight(pid, order_date):
    """How likely this product is to be picked for an order placed on order_date."""

    # A product cannot be sold before it launches
    if order_date.date() < product_launch[pid]:
        return 0.0

    weight = popularity[pid]

    if story_by_pid.get(pid) == "declining":
        weight *= 0.78 ** (order_date.month - 1)

    return weight


def pick_quantity(price):
    """Expensive devices are usually bought one at a time."""
    if price >= 100000:
        return 1
    if price >= 40000:
        return random.choices([1, 2], weights=[90, 10])[0]
    return random.choices([1, 2, 3, 4], weights=[60, 25, 10, 5])[0]


# =========================================================
# 6. ORDERS
# =========================================================

orders = []

start_date = datetime(2025, 1, 1)
end_date = datetime(2025, 12, 31)

for i in range(5000):

    customer_id = random.choice(customer_ids)

    random_days = random.randint(
        0,
        (end_date - start_date).days
    )

    order_date = start_date + timedelta(
        days=random_days,
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59)
    )

    # Make cancelled orders less common
    order_status = random.choices(
        [
            "Pending",
            "Processing",
            "Shipped",
            "Delivered",
            "Cancelled"
        ],
        weights=[5, 8, 12, 68, 7]
    )[0]

    shipping_city = fake.city()
    shipping_state = fake.state()

    discount = round(
        random.choice([0, 0, 0, 100, 200, 300, 500]),
        2
    )

    shipping_fee = random.choice(
        [0, 0, 0, 50, 80, 100, 150]
    )

    orders.append(
        (
            customer_id,
            order_date,
            order_status,
            shipping_city,
            shipping_state,
            "India",
            discount,
            shipping_fee
        )
    )

cursor.executemany(
    """
    INSERT INTO orders
    (
        customer_id,
        order_date,
        order_status,
        shipping_city,
        shipping_state,
        shipping_country,
        discount_amount,
        shipping_fee
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """,
    orders
)

conn.commit()

print("Orders inserted:", len(orders))

# =========================================================
# 7. ORDER ITEMS
# =========================================================

cursor.execute("SELECT order_id, order_date FROM orders")
order_rows = cursor.fetchall()

order_items = []

for order_id, order_date in order_rows:

    # Most orders have 1–3 products
    number_of_items = random.choices(
        [1, 2, 3, 4, 5],
        weights=[35, 35, 20, 8, 2]
    )[0]

    # Popular (and already launched) products are picked more often; no product twice in one order
    weights = [product_weight(pid, order_date) for pid in product_ids]

    selected_products = []
    while len(selected_products) < number_of_items:
        pid = random.choices(product_ids, weights=weights)[0]
        if pid not in selected_products:
            selected_products.append(pid)

    for product_id in selected_products:

        unit_price = product_prices[product_id]

        quantity = pick_quantity(unit_price)

        # discount is a small % of the price (0 most of the time)
        item_discount = round(
            unit_price * random.choice([0, 0, 0, 0.02, 0.05, 0.08]),
            2
        )

        order_items.append(
            (
                order_id,
                product_id,
                quantity,
                unit_price,
                item_discount
            )
        )

cursor.executemany(
    """
    INSERT INTO order_items
    (
        order_id,
        product_id,
        quantity,
        unit_price,
        item_discount
    )
    VALUES (%s, %s, %s, %s, %s)
    """,
    order_items
)

conn.commit()

print("Order items inserted:", len(order_items))

# =========================================================
# 8. PAYMENTS
# =========================================================

payments = []

payment_methods = [
    "Credit Card",
    "Debit Card",
    "UPI",
    "PayPal",
    "Bank Transfer",
    "Cash on Delivery"
]

# One query gives every order with the total of its items
cursor.execute(
    """
    SELECT
        o.order_id,
        o.order_date,
        o.order_status,
        o.discount_amount,
        o.shipping_fee,
        COALESCE(SUM(oi.quantity * oi.unit_price - oi.item_discount), 0)
    FROM orders o
    LEFT JOIN order_items oi
        ON oi.order_id = o.order_id
    GROUP BY
        o.order_id,
        o.order_date,
        o.order_status,
        o.discount_amount,
        o.shipping_fee
    """
)

for order_id, order_date, order_status, order_discount, order_fee, item_total in cursor.fetchall():

    amount = max(
        float(item_total) - float(order_discount) + float(order_fee),
        0
    )

    if order_status == "Cancelled":
        payment_status = random.choice(
            ["Failed", "Refunded"]
        )
    else:
        payment_status = random.choices(
            ["Paid", "Pending", "Failed"],
            weights=[90, 7, 3]
        )[0]

    payment_date = order_date + timedelta(
        hours=random.randint(0, 48)
    )

    payments.append(
        (
            order_id,
            payment_date,
            random.choice(payment_methods),
            payment_status,
            amount
        )
    )

cursor.executemany(
    """
    INSERT INTO payments
    (
        order_id,
        payment_date,
        payment_method,
        payment_status,
        amount
    )
    VALUES (%s, %s, %s, %s, %s)
    """,
    payments
)

conn.commit()

print("Payments inserted:", len(payments))

# =========================================================
# 9. RETURNS
# =========================================================

# Only some delivered items are returned
returns = []

cursor.execute(
    """
    SELECT
        oi.order_item_id,
        o.order_date,
        oi.quantity,
        oi.unit_price,
        oi.product_id
    FROM order_items oi
    JOIN orders o
        ON oi.order_id = o.order_id
    WHERE o.order_status = 'Delivered'
    """
)

delivered_items = cursor.fetchall()

for item in delivered_items:

    is_quality_problem = story_by_pid.get(item[4]) == "quality"

    # Approximately 5% chance of return (25% for the "quality" product)
    if random.random() < (0.25 if is_quality_problem else 0.05):

        order_item_id = item[0]
        order_date = item[1]
        quantity = item[2]
        unit_price = item[3]

        return_date = order_date.date() + timedelta(
            days=random.randint(3, 30)
        )

        if is_quality_problem:
            return_reason = random.choices(
                ["Damaged", "Not as Expected", "Changed Mind"],
                weights=[55, 35, 10]
            )[0]
        else:
            return_reason = random.choice([
                "Damaged",
                "Wrong Product",
                "Not as Expected",
                "Changed Mind",
                "Late Delivery",
                "Size Issue"
            ])

        return_status = random.choice([
            "Approved",
            "Completed",
            "Processing"
        ])

        refund_amount = round(
            float(unit_price) * random.randint(
                1,
                quantity
            ),
            2
        )

        returns.append(
            (
                order_item_id,
                return_date,
                return_reason,
                return_status,
                refund_amount
            )
        )

cursor.executemany(
    """
    INSERT INTO returns
    (
        order_item_id,
        return_date,
        return_reason,
        return_status,
        refund_amount
    )
    VALUES (%s, %s, %s, %s, %s)
    """,
    returns
)

conn.commit()

print("Returns inserted:", len(returns))

# =========================================================
# FINISH
# =========================================================

cursor.close()
conn.close()

story_lines = [
    f"{name}|{story}|{STORY_TEXT[story]}"
    for name, story in story_by_name.items()
]
Path(__file__).with_name("underperformers.txt").write_text(
    "\n".join(story_lines), encoding="utf-8"
)

print("\n===================================")
print("DATA GENERATION COMPLETED!")
print("===================================")
print("\nProducts with a hidden reason for weak sales (try asking about them):")
for line in story_lines:
    name, story, text = line.split("|")
    print(f"  - {name}: {text}")