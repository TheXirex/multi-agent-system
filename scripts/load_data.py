"""
Dataset Loader.
Downloads dataset via kagglehub,
loads the CSV strictly into memory without storing it locally,
cleans, normalizes, and sanitizes data into relational tables,
and seeds the baseline PostgreSQL public schema.
"""
import argparse
import io
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
import shutil
from typing import Any, Dict, List, Optional, Tuple

import kagglehub
import pandas as pd
from sqlalchemy import Engine, create_engine, text

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("data_loader")

DATASET_SLUG = "karkavelrajaj/amazon-sales-dataset"


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


def _sanitize_text(value: Any) -> str:
    """
    Strips brand mentions and sanitizes text strings without regex.
    """
    if pd.isna(value) or value is None:
        return ""
    text_val = str(value)
    replacements = [
        ("amazon's brand", "store brand"),
        ("amazon basics", "essential"),
        ("amazonbasics", "essential"),
        ("amazon's choice", "top choice"),
        ("amazon customer", "customer"),
        ("amazon", "store"),
    ]
    for target, repl in replacements:
        while True:
            idx = text_val.lower().find(target)
            if idx == -1:
                break
            orig = text_val[idx : idx + len(target)]
            actual_repl = repl.upper() if orig.isupper() else (repl.title() if orig[0].isupper() else repl)
            text_val = text_val[:idx] + actual_repl + text_val[idx + len(target):]
    return text_val.strip()


def _clean_price(value: Any) -> float:
    if pd.isna(value):
        return 0.0
    cleaned = str(value).replace("₹", "").replace(",", "").replace(" ", "").strip()
    try:
        return round(float(cleaned), 2)
    except (ValueError, TypeError):
        return 0.0


def _clean_discount_percentage(value: Any) -> float:
    if pd.isna(value):
        return 0.0
    cleaned = str(value).replace("%", "").replace(" ", "").strip()
    try:
        return round(float(cleaned), 2)
    except (ValueError, TypeError):
        return 0.0


def _clean_rating(value: Any, fallback: float = 4.1) -> float:
    if pd.isna(value):
        return fallback
    cleaned = str(value).strip()
    try:
        val = float(cleaned)
        return round(val, 2)
    except (ValueError, TypeError):
        return fallback


def _clean_count(value: Any) -> int:
    if pd.isna(value):
        return 0
    cleaned = str(value).replace(",", "").replace(" ", "").strip()
    try:
        return int(cleaned)
    except (ValueError, TypeError):
        return 0


def fetch_dataset_in_memory() -> pd.DataFrame:
    """
    Downloads the dataset via kagglehub, reads the CSV strictly into memory,
    and immediately deletes the downloaded files and cache from disk.
    """
    logger.info(f"Downloading dataset '{DATASET_SLUG}' via kagglehub...")
    download_dir = kagglehub.dataset_download(DATASET_SLUG)
    logger.info(f"Downloaded files located at temporary path: {download_dir}")

    csv_path: Optional[Path] = None
    target_dir = Path(download_dir)
    for p in target_dir.rglob("*.csv"):
        csv_path = p
        break

    if not csv_path or not csv_path.is_file():
        raise FileNotFoundError(f"No CSV file discovered inside downloaded path '{download_dir}'.")

    logger.info(f"Reading CSV '{csv_path.name}' directly into memory...")
    file_bytes = csv_path.read_bytes()

    # Clean up downloaded files from disk immediately
    try:
        shutil.rmtree(download_dir, ignore_errors=True)
        parent_cache = target_dir.parent
        if parent_cache.exists():
            shutil.rmtree(parent_cache, ignore_errors=True)
        logger.info("Local disk download files purged successfully. Processing in memory.")
    except Exception as cleanup_err:
        logger.warning(f"Could not purge temporary download dir: {cleanup_err}")

    raw_df = pd.read_csv(io.BytesIO(file_bytes))
    logger.info(f"Loaded CSV into memory: {raw_df.shape[0]} rows, {raw_df.shape[1]} columns.")
    return raw_df


def transform_data(raw_df: pd.DataFrame) -> Tuple[
    List[Dict[str, Any]],
    List[Dict[str, Any]],
    List[Dict[str, Any]],
    List[Dict[str, Any]],
    List[Dict[str, Any]],
]:
    """
    Parses, cleans, sanitizes, and normalizes the in-memory raw dataframe
    into 5 relational table datasets:
    1. categories
    2. products
    3. users
    4. orders
    5. product_reviews
    """
    logger.info("Transforming and normalizing dataset in memory...")

    # 1. Categories
    unique_categories = raw_df["category"].dropna().unique()
    category_map: Dict[str, int] = {}
    categories_data: List[Dict[str, Any]] = []

    for cat_id, cat_str in enumerate(unique_categories, start=1):
        clean_cat = _sanitize_text(cat_str)
        parts = [p.strip() for p in clean_cat.split("|") if p.strip()]
        main_cat = parts[0] if parts else "General"
        sub_cat = parts[1] if len(parts) > 1 else main_cat
        category_map[str(cat_str)] = cat_id
        categories_data.append({
            "id": cat_id,
            "name": clean_cat[:255],
            "main_category": main_cat[:100],
            "sub_category": sub_cat[:100],
        })

    # 2. Products (deduplicate by product_id)
    products_data: List[Dict[str, Any]] = []
    seen_products = set()

    for _, row in raw_df.iterrows():
        pid = str(row["product_id"]).strip()
        if not pid or pid in seen_products:
            continue
        seen_products.add(pid)

        cat_id = category_map.get(str(row.get("category", "")))
        p_name = _sanitize_text(row.get("product_name", "")) or "Product"
        d_price = _clean_price(row.get("discounted_price"))
        a_price = _clean_price(row.get("actual_price"))
        if a_price < d_price:
            a_price = d_price

        pct = _clean_discount_percentage(row.get("discount_percentage"))
        rating_val = _clean_rating(row.get("rating"))
        rating_cnt = _clean_count(row.get("rating_count"))
        about_prod = _sanitize_text(row.get("about_product", ""))

        products_data.append({
            "id": pid[:50],
            "name": p_name,
            "category_id": cat_id,
            "discounted_price": d_price,
            "actual_price": a_price,
            "discount_percentage": pct,
            "rating": rating_val,
            "rating_count": rating_cnt,
            "about_product": about_prod,
        })

    # 3. Users, Reviews, and Orders
    users_dict: Dict[str, str] = {}
    reviews_data: List[Dict[str, Any]] = []
    orders_data: List[Dict[str, Any]] = []
    seen_reviews = set()

    for _, row in raw_df.iterrows():
        pid = str(row.get("product_id", "")).strip()
        if pid not in seen_products:
            continue

        p_rating = _clean_rating(row.get("rating"))
        p_price = _clean_price(row.get("discounted_price"))

        u_ids = [u.strip() for u in str(row.get("user_id", "")).split(",") if u.strip()]
        u_names = [n.strip() for n in str(row.get("user_name", "")).split(",") if n.strip()]
        r_ids = [r.strip() for r in str(row.get("review_id", "")).split(",") if r.strip()]
        r_titles = [t.strip() for t in str(row.get("review_title", "")).split(",") if t.strip()]
        r_contents = [c.strip() for c in str(row.get("review_content", "")).split(",") if c.strip()]

        for i, uid in enumerate(u_ids):
            raw_uname = u_names[i] if i < len(u_names) else "Customer"
            uname = _sanitize_text(raw_uname) or "Customer"
            safe_uid = uid[:100]
            if safe_uid not in users_dict:
                users_dict[safe_uid] = uname[:255]

        for i, rid in enumerate(r_ids):
            safe_rid = rid[:100]
            if safe_rid in seen_reviews:
                continue
            seen_reviews.add(safe_rid)

            assigned_uid = u_ids[i][:100] if i < len(u_ids) else (u_ids[0][:100] if u_ids else None)
            if not assigned_uid or assigned_uid not in users_dict:
                continue

            title = _sanitize_text(r_titles[i]) if i < len(r_titles) else ""
            content = _sanitize_text(r_contents[i]) if i < len(r_contents) else ""

            reviews_data.append({
                "id": safe_rid,
                "product_id": pid[:50],
                "user_id": assigned_uid,
                "rating": p_rating,
                "review_title": title,
                "review_content": content,
            })

            order_idx = len(orders_data)
            base_date = datetime(2024, 11, 1)
            offset_days = (order_idx * 724) // 10000
            order_dt = base_date + timedelta(days=offset_days, hours=(order_idx % 24), minutes=(order_idx % 60))

            status_mod = order_idx % 100
            if status_mod < 75:
                order_status = "Delivered"
            elif status_mod < 87:
                order_status = "Shipped"
            elif status_mod < 94:
                order_status = "Processing"
            elif status_mod < 98:
                order_status = "Cancelled"
            else:
                order_status = "Returned"

            orders_data.append({
                "order_id": f"ORD-{safe_rid}"[:100],
                "user_id": assigned_uid,
                "product_id": pid[:50],
                "unit_price": p_price,
                "quantity": 1,
                "total_amount": p_price,
                "status": order_status,
                "order_date": order_dt,
            })

    users_data = [{"id": uid, "name": uname} for uid, uname in users_dict.items()]

    logger.info(
        f"Transformation complete: {len(categories_data)} categories, "
        f"{len(products_data)} products, {len(users_data)} users, "
        f"{len(orders_data)} orders, {len(reviews_data)} reviews."
    )
    return categories_data, products_data, users_data, orders_data, reviews_data


def create_schema_tables(conn: Any) -> None:
    """
    Creates normalized relational baseline tables in the public schema.
    """
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS categories (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) UNIQUE NOT NULL,
            main_category VARCHAR(100) NOT NULL,
            sub_category VARCHAR(100) NOT NULL
        );

        CREATE TABLE IF NOT EXISTS products (
            id VARCHAR(50) PRIMARY KEY,
            name TEXT NOT NULL,
            category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
            discounted_price NUMERIC(10, 2) NOT NULL,
            actual_price NUMERIC(10, 2) NOT NULL,
            discount_percentage NUMERIC(5, 2) NOT NULL,
            rating NUMERIC(3, 2) NOT NULL,
            rating_count INTEGER NOT NULL DEFAULT 0,
            about_product TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS users (
            id VARCHAR(100) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
            order_id VARCHAR(100) UNIQUE NOT NULL,
            user_id VARCHAR(100) REFERENCES users(id) ON DELETE CASCADE,
            product_id VARCHAR(50) REFERENCES products(id) ON DELETE CASCADE,
            unit_price NUMERIC(10, 2) NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1,
            total_amount NUMERIC(10, 2) NOT NULL,
            status VARCHAR(50) NOT NULL DEFAULT 'Delivered',
            order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS product_reviews (
            id VARCHAR(100) PRIMARY KEY,
            product_id VARCHAR(50) REFERENCES products(id) ON DELETE CASCADE,
            user_id VARCHAR(100) REFERENCES users(id) ON DELETE CASCADE,
            rating NUMERIC(3, 2) NOT NULL,
            review_title TEXT,
            review_content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_products_category_id ON products(category_id);
        CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id);
        CREATE INDEX IF NOT EXISTS idx_orders_product_id ON orders(product_id);
        CREATE INDEX IF NOT EXISTS idx_product_reviews_product_id ON product_reviews(product_id);
        CREATE INDEX IF NOT EXISTS idx_product_reviews_user_id ON product_reviews(user_id);
    """))


def seed_database(engine: Engine, reset: bool = False) -> None:
    """
    Main entry point for populating the database with the relational dataset.
    If reset is False and the tables already contain products, seeding is skipped.
    """
    logger.info("Checking dataset status in database...")

    if reset:
        logger.info("Reset requested: wiping existing session schemas and domain tables...")
        with engine.begin() as conn:
            # 1. Drop existing session schemas
            session_schemas = [
                row[0]
                for row in conn.execute(
                    text("""
                        SELECT schema_name 
                        FROM information_schema.schemata 
                        WHERE schema_name LIKE 'session_%';
                    """)
                ).fetchall()
            ]
            for s in session_schemas:
                conn.execute(text(f'DROP SCHEMA IF EXISTS "{s}" CASCADE;'))

            # 2. Truncate internal application state
            conn.execute(text("""
                CREATE SCHEMA IF NOT EXISTS internal;
                TRUNCATE TABLE internal.chat_messages, internal.chat_sessions RESTART IDENTITY CASCADE;
                TRUNCATE TABLE internal.change_history RESTART IDENTITY CASCADE;
                TRUNCATE TABLE internal.generated_charts RESTART IDENTITY CASCADE;
                TRUNCATE TABLE internal.generated_scripts RESTART IDENTITY CASCADE;
            """))

            # 3. Drop existing public domain tables
            conn.execute(text("""
                DROP TABLE IF EXISTS marketing_campaigns CASCADE;
                DROP TABLE IF EXISTS web_sessions CASCADE;
                DROP TABLE IF EXISTS order_items CASCADE;
                DROP TABLE IF EXISTS product_reviews CASCADE;
                DROP TABLE IF EXISTS orders CASCADE;
                DROP TABLE IF EXISTS products CASCADE;
                DROP TABLE IF EXISTS users CASCADE;
                DROP TABLE IF EXISTS categories CASCADE;
            """))
            create_schema_tables(conn)
    else:
        with engine.begin() as conn:
            try:
                prod_count = conn.execute(text("SELECT COUNT(*) FROM products;")).scalar() or 0
                if prod_count > 0:
                    logger.info(f"Database already contains {prod_count} products. Skipping seeding.")
                    return
            except Exception:
                pass
            create_schema_tables(conn)

    # Fetch and transform dataset in memory
    raw_df = fetch_dataset_in_memory()
    categories_data, products_data, users_data, orders_data, reviews_data = transform_data(raw_df)

    # Insert into database in batched transactions
    chunk_size = 1000
    with engine.begin() as conn:
        logger.info(f"Inserting {len(categories_data)} categories...")
        conn.execute(
            text("""
                INSERT INTO categories (id, name, main_category, sub_category)
                VALUES (:id, :name, :main_category, :sub_category)
                ON CONFLICT (id) DO NOTHING;
            """),
            categories_data,
        )

        logger.info(f"Inserting {len(products_data)} products...")
        for i in range(0, len(products_data), chunk_size):
            chunk = products_data[i : i + chunk_size]
            conn.execute(
                text("""
                    INSERT INTO products (id, name, category_id, discounted_price, actual_price, discount_percentage, rating, rating_count, about_product)
                    VALUES (:id, :name, :category_id, :discounted_price, :actual_price, :discount_percentage, :rating, :rating_count, :about_product)
                    ON CONFLICT (id) DO NOTHING;
                """),
                chunk,
            )

        logger.info(f"Inserting {len(users_data)} users...")
        for i in range(0, len(users_data), chunk_size):
            chunk = users_data[i : i + chunk_size]
            conn.execute(
                text("""
                    INSERT INTO users (id, name)
                    VALUES (:id, :name)
                    ON CONFLICT (id) DO NOTHING;
                """),
                chunk,
            )

        logger.info(f"Inserting {len(orders_data)} orders...")
        for i in range(0, len(orders_data), chunk_size):
            chunk = orders_data[i : i + chunk_size]
            conn.execute(
                text("""
                    INSERT INTO orders (order_id, user_id, product_id, unit_price, quantity, total_amount, status, order_date)
                    VALUES (:order_id, :user_id, :product_id, :unit_price, :quantity, :total_amount, :status, :order_date)
                    ON CONFLICT (order_id) DO NOTHING;
                """),
                chunk,
            )

        logger.info(f"Inserting {len(reviews_data)} product reviews...")
        for i in range(0, len(reviews_data), chunk_size):
            chunk = reviews_data[i : i + chunk_size]
            conn.execute(
                text("""
                    INSERT INTO product_reviews (id, product_id, user_id, rating, review_title, review_content)
                    VALUES (:id, :product_id, :user_id, :rating, :review_title, :review_content)
                    ON CONFLICT (id) DO NOTHING;
                """),
                chunk,
            )

    logger.info("Dataset successfully seeded into PostgreSQL public schema!")


# Backward compatibility aliases
seed_dataset = seed_database
load_dataset = seed_database


def main() -> None:
    """
    CLI entry point for dataset loader.
    """
    parser = argparse.ArgumentParser(description="Dataset Loader from Kaggle")
    parser.add_argument("--reset", action="store_true", help="Wipe schemas and re-seed dataset from scratch")
    parser.add_argument("--url", type=str, default="", help="Custom PostgreSQL database URL")

    args = parser.parse_args()
    db_url = args.url or get_default_database_url()
    engine = create_engine(db_url, pool_pre_ping=True)

    seed_database(engine=engine, reset=args.reset)


if __name__ == "__main__":
    main()
