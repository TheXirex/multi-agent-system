import argparse
from datetime import datetime, timedelta
import logging
import os
import random
from typing import Optional

from sqlalchemy import Engine, create_engine, text

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("data_generator")

FIRST_NAMES = [
    "Alex", "Jordan", "Taylor", "Morgan", "Sam", "Chris", "Pat", "Robin", "William", "Emma",
    "John", "Jane", "James", "Michael", "Emily", "Daniel", "Sophia", "David", "Olivia", "Lucas",
    "Liam", "Noah", "Oliver", "Elijah", "Ava", "Isabella", "Mia", "Harper", "Evelyn", "Benjamin",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Wilson", "Anderson",
    "Taylor", "Thomas", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson", "White", "Harris",
    "Clark", "Lewis", "Robinson", "Walker", "Young", "Allen", "King", "Wright", "Scott", "Torres",
]

COUNTRIES = [
    "USA", "UK", "Canada", "Germany", "France", "Australia", "Japan", "Ukraine", "Poland", "Italy",
]

CATEGORIES = [
    "Electronics",
    "Books",
    "Clothing",
    "Home & Kitchen",
    "Sports & Outdoors",
    "Beauty & Health",
]

PRODUCTS = [
    # Electronics (category_id 1)
    ("Wireless Headphones", 1, 99.99, 150),
    ("Mechanical Keyboard", 1, 149.50, 80),
    ("Ultra-wide Monitor", 1, 399.00, 45),
    ("USB-C Docking Station", 1, 79.99, 120),
    ("Wireless Gaming Mouse", 1, 59.99, 200),
    ("Noise Cancelling Earbuds", 1, 129.00, 90),
    # Books (category_id 2)
    ("Clean Code Book", 2, 35.00, 300),
    ("Designing Data-Intensive Applications", 2, 45.00, 250),
    ("Python Crash Course", 2, 29.99, 180),
    ("Hands-On Machine Learning", 2, 55.00, 140),
    ("Refactoring Book", 2, 42.50, 110),
    # Clothing (category_id 3)
    ("Cotton T-Shirt", 3, 20.00, 500),
    ("Slim-Fit Jeans", 3, 49.99, 320),
    ("Hooded Sweatshirt", 3, 39.99, 240),
    ("Running Shoes", 3, 89.99, 175),
    ("Wool Winter Coat", 3, 129.99, 85),
    # Home & Kitchen (category_id 4)
    ("Espresso Coffee Machine", 4, 199.99, 60),
    ("Cast Iron Skillet", 4, 34.99, 190),
    ("Smart LED Desk Lamp", 4, 45.00, 140),
    ("Stainless Steel Water Bottle", 4, 19.99, 400),
    # Sports & Outdoors (category_id 5)
    ("Yoga Mat", 5, 25.00, 220),
    ("Adjustable Dumbbells Set", 5, 119.99, 70),
    ("Camping Backpack", 5, 79.99, 95),
    ("Fitness Smartwatch", 5, 159.00, 110),
    # Beauty & Health (category_id 6)
    ("Vitamin C Serum", 6, 28.00, 310),
    ("Hydrating Face Cream", 6, 22.50, 280),
]


def get_default_database_url() -> str:
    """
    Constructs database URL from environment variables with defaults.
    """
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "app_db")
    user = os.getenv("DB_USER", "postgres")
    password = os.getenv("DB_PASSWORD", "postgres")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db_name}"


def seed_database(
    engine: Engine,
    reset: bool = False,
    num_users: int = 120,
    num_orders: int = 850,
) -> None:
    """
    Populates PostgreSQL database with realistic synthetic data.

    Args:
        engine (Engine): SQLAlchemy database engine.
        reset (bool): If True, truncates existing domain tables first.
        num_users (int): Number of synthetic users to generate.
        num_orders (int): Number of synthetic orders to generate.
    """
    logger.info("Connecting to database for data generation...")

    with engine.begin() as conn:
        if reset:
            logger.info("Reset requested. Truncating existing domain tables...")
            conn.execute(text("TRUNCATE order_items, orders, products, categories, users RESTART IDENTITY CASCADE;"))

        # Check existing count
        existing_users = conn.execute(text("SELECT COUNT(*) FROM users;")).scalar()
        if existing_users and existing_users > 0 and not reset:
            logger.info(f"Database already contains {existing_users} users. Skipping seeding (use --reset to overwrite).")
            return

        # 1. Categories
        logger.info(f"Seeding {len(CATEGORIES)} categories...")
        for cat_name in CATEGORIES:
            conn.execute(
                text("INSERT INTO categories (name) VALUES (:name) ON CONFLICT DO NOTHING;"),
                {"name": cat_name},
            )

        # 2. Products
        logger.info(f"Seeding {len(PRODUCTS)} products...")
        for p_name, p_cat, p_price, p_stock in PRODUCTS:
            conn.execute(
                text("""
                    INSERT INTO products (name, category_id, price, stock)
                    VALUES (:name, :category_id, :price, :stock)
                    ON CONFLICT DO NOTHING;
                """),
                {"name": p_name, "category_id": p_cat, "price": p_price, "stock": p_stock},
            )

        # Fetch product price mapping
        product_rows = conn.execute(text("SELECT id, price FROM products;")).fetchall()
        product_prices = {row[0]: float(row[1]) for row in product_rows}
        product_ids = list(product_prices.keys())

        # 3. Users
        logger.info(f"Generating {num_users} realistic users...")
        now = datetime.now()
        used_emails = set()
        user_ids = []

        for i in range(1, num_users + 1):
            first = random.choice(FIRST_NAMES)
            last = random.choice(LAST_NAMES)
            email_candidate = f"{first.lower()}.{last.lower()}{i}@example.com"
            if email_candidate in used_emails:
                email_candidate = f"{first.lower()}.{last.lower()}{i}_{random.randint(100, 999)}@example.com"
            used_emails.add(email_candidate)

            country = random.choice(COUNTRIES)
            created_at = now - timedelta(days=random.randint(30, 700), hours=random.randint(0, 23))

            res = conn.execute(
                text("""
                    INSERT INTO users (name, email, country, created_at)
                    VALUES (:name, :email, :country, :created_at)
                    RETURNING id;
                """),
                {
                    "name": f"{first} {last}",
                    "email": email_candidate,
                    "country": country,
                    "created_at": created_at,
                },
            )
            user_ids.append(res.scalar())

        # 4. Orders
        logger.info(f"Generating {num_orders} orders...")
        order_ids = []
        statuses = ["completed", "completed", "completed", "completed", "completed", "processing", "cancelled"]

        for _ in range(num_orders):
            u_id = random.choice(user_ids)
            status = random.choice(statuses)
            created_at = now - timedelta(days=random.randint(1, 280), hours=random.randint(0, 23), minutes=random.randint(0, 59))

            res = conn.execute(
                text("""
                    INSERT INTO orders (user_id, status, total_amount, created_at)
                    VALUES (:user_id, :status, 0, :created_at)
                    RETURNING id;
                """),
                {
                    "user_id": u_id,
                    "status": status,
                    "created_at": created_at,
                },
            )
            order_ids.append(res.scalar())

        # 5. Order Items
        logger.info("Generating order items across orders...")
        total_items = 0
        for o_id in order_ids:
            num_items = random.choices([1, 2, 3, 4], weights=[0.4, 0.35, 0.18, 0.07])[0]
            chosen_prods = random.sample(product_ids, k=min(num_items, len(product_ids)))

            for p_id in chosen_prods:
                qty = random.choices([1, 2, 3], weights=[0.75, 0.20, 0.05])[0]
                unit_price = product_prices[p_id]

                conn.execute(
                    text("""
                        INSERT INTO order_items (order_id, product_id, quantity, unit_price)
                        VALUES (:order_id, :product_id, :quantity, :unit_price);
                    """),
                    {
                        "order_id": o_id,
                        "product_id": p_id,
                        "quantity": qty,
                        "unit_price": unit_price,
                    },
                )
                total_items += 1

        # 6. Recalculate and update total_amount on orders
        logger.info("Updating orders total amounts from order items...")
        conn.execute(text("""
            UPDATE orders o
            SET total_amount = sub.sum_amt
            FROM (
                SELECT order_id, ROUND(SUM(quantity * unit_price), 2) AS sum_amt
                FROM order_items
                GROUP BY order_id
            ) sub
            WHERE o.id = sub.order_id;
        """))

    logger.info(f"Successfully seeded database: {num_users} users, {num_orders} orders, {total_items} items.")


def main() -> None:
    """
    CLI entry point for data generation.
    """
    parser = argparse.ArgumentParser(description="Synthetic Data Generator for Multi-Agent Database System")
    parser.add_argument("--reset", action="store_true", help="Truncate existing domain tables before generating")
    parser.add_argument("--users", type=int, default=120, help="Number of synthetic users (default: 120)")
    parser.add_argument("--orders", type=int, default=850, help="Number of synthetic orders (default: 850)")
    parser.add_argument("--url", type=str, default="", help="Custom PostgreSQL database URL")

    args = parser.parse_args()
    db_url = args.url or get_default_database_url()
    engine = create_engine(db_url, pool_pre_ping=True)

    seed_database(
        engine=engine,
        reset=args.reset,
        num_users=args.users,
        num_orders=args.orders,
    )


if __name__ == "__main__":
    main()
