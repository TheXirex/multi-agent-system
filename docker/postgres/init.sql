-- Relational Domain Schema

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

-- Internal schema and persistent application storage
CREATE SCHEMA IF NOT EXISTS internal;

CREATE TABLE IF NOT EXISTS internal.generated_charts (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255),
    chart_type VARCHAR(50),
    spec JSONB NOT NULL,
    table_name VARCHAR(255),
    dataset_id INTEGER,
    session_id VARCHAR(36),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_generated_charts_session_id ON internal.generated_charts(session_id);

CREATE TABLE IF NOT EXISTS internal.generated_scripts (
    id SERIAL PRIMARY KEY,
    script TEXT NOT NULL,
    language VARCHAR(50) DEFAULT 'python',
    task_description TEXT,
    table_name VARCHAR(255),
    dataset_id INTEGER,
    session_id VARCHAR(36),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_generated_scripts_session_id ON internal.generated_scripts(session_id);

CREATE TABLE IF NOT EXISTS internal.chat_sessions (
    id VARCHAR(36) PRIMARY KEY,
    title VARCHAR(255) NOT NULL DEFAULT 'New Chat',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS internal.chat_messages (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(36) REFERENCES internal.chat_sessions(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS internal.change_history (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(36) NOT NULL,
    action_type VARCHAR(50) NOT NULL,
    table_name VARCHAR(255) NOT NULL,
    description TEXT,
    executed_sql TEXT NOT NULL,
    rollback_sql TEXT,
    before_state JSONB DEFAULT '[]',
    after_state JSONB DEFAULT '[]',
    is_reverted BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_change_history_session_id ON internal.change_history(session_id);
