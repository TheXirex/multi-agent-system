import argparse
from datetime import datetime, timedelta
import logging
import os
from typing import Optional

from sqlalchemy import Engine, create_engine, text

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("data_generator")


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
    num_users: int = 150,
    num_orders: int = 900,
    num_categories: int = 8,
    num_products: int = 40,
) -> None:
    """
    Populates PostgreSQL database with synthetic data using rules and increments
    for categorical and text fields.

    Args:
        engine (Engine): SQLAlchemy database engine.
        reset (bool): If True, truncates existing domain tables first.
        num_users (int): Number of synthetic users to generate.
        num_orders (int): Number of synthetic orders to generate.
        num_categories (int): Number of synthetic categories to generate.
        num_products (int): Number of synthetic products to generate.
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
        logger.info(f"Generating {num_categories} categories...")
        for c in range(1, num_categories + 1):
            conn.execute(
                text("INSERT INTO categories (name) VALUES (:name) ON CONFLICT DO NOTHING;"),
                {"name": f"category_{c}"},
            )

        # 2. Products
        logger.info(f"Generating {num_products} products...")
        product_prices = {}
        for p in range(1, num_products + 1):
            cat_id = ((p - 1) % num_categories) + 1
            price = round(12.50 + ((p * 17.3) % 230.0), 2)
            stock = 20 + ((p * 31) % 350)
            conn.execute(
                text("""
                    INSERT INTO products (name, category_id, price, stock)
                    VALUES (:name, :category_id, :price, :stock)
                    ON CONFLICT DO NOTHING;
                """),
                {"name": f"product_{p}", "category_id": cat_id, "price": price, "stock": stock},
            )
            product_prices[p] = price

        product_ids = list(product_prices.keys())

        # 3. Users
        logger.info(f"Generating {num_users} users...")
        now = datetime.now()
        user_ids = []
        for i in range(1, num_users + 1):
            domain_idx = ((i - 1) % 5) + 1
            country_idx = ((i - 1) % 10) + 1
            days_ago = (i * 7) % 650
            hours_ago = (i * 3) % 24
            created_at = now - timedelta(days=days_ago, hours=hours_ago)

            res = conn.execute(
                text("""
                    INSERT INTO users (name, email, country, created_at)
                    VALUES (:name, :email, :country, :created_at)
                    RETURNING id;
                """),
                {
                    "name": f"user_{i}",
                    "email": f"user_{i}@domain_{domain_idx}.net",
                    "country": f"country_{country_idx}",
                    "created_at": created_at,
                },
            )
            user_ids.append(res.scalar())

        # 4. Orders
        logger.info(f"Generating {num_orders} orders...")
        order_ids = []
        for o in range(1, num_orders + 1):
            u_id = user_ids[(o * 13) % len(user_ids)]
            status = f"status_{(o % 3) + 1}"
            days_ago = (o * 3) % 360
            hours_ago = (o * 7) % 24
            minutes_ago = (o * 19) % 60
            created_at = now - timedelta(days=days_ago, hours=hours_ago, minutes=minutes_ago)

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

        # 5. Order items
        logger.info("Generating order items across orders...")
        total_items = 0
        for o_idx, o_id in enumerate(order_ids, start=1):
            num_items = 1 + ((o_idx * 3) % 4)
            for k in range(num_items):
                p_idx = ((o_idx * 11 + k * 7) % len(product_ids))
                p_id = product_ids[p_idx]
                qty = 1 + ((o_idx * 5 + k * 3) % 5)
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
    parser.add_argument("--users", type=int, default=150, help="Number of synthetic users (default: 150)")
    parser.add_argument("--orders", type=int, default=900, help="Number of synthetic orders (default: 900)")
    parser.add_argument("--categories", type=int, default=8, help="Number of synthetic categories (default: 8)")
    parser.add_argument("--products", type=int, default=40, help="Number of synthetic products (default: 40)")
    parser.add_argument("--url", type=str, default="", help="Custom PostgreSQL database URL")

    args = parser.parse_args()
    db_url = args.url or get_default_database_url()
    engine = create_engine(db_url, pool_pre_ping=True)

    seed_database(
        engine=engine,
        reset=args.reset,
        num_users=args.users,
        num_orders=args.orders,
        num_categories=args.categories,
        num_products=args.products,
    )


if __name__ == "__main__":
    main()
