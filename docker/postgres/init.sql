CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    country VARCHAR(50) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    category_id INTEGER REFERENCES categories(id),
    price NUMERIC(10, 2) NOT NULL,
    stock INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    status VARCHAR(20) NOT NULL DEFAULT 'status_1',
    total_amount NUMERIC(10, 2) NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS order_items (
    id SERIAL PRIMARY KEY,
    order_id INTEGER REFERENCES orders(id),
    product_id INTEGER REFERENCES products(id),
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(10, 2) NOT NULL
);

CREATE SCHEMA IF NOT EXISTS internal;

CREATE TABLE IF NOT EXISTS internal.generated_datasets (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL DEFAULT 'dataset',
    file_name VARCHAR(255) DEFAULT '',
    file_path TEXT DEFAULT '',
    query TEXT,
    row_count INTEGER DEFAULT 0,
    columns TEXT[] DEFAULT '{}',
    data JSONB NOT NULL DEFAULT '[]',
    session_id VARCHAR(36),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_generated_datasets_session_id ON internal.generated_datasets(session_id);

CREATE TABLE IF NOT EXISTS internal.generated_charts (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255),
    chart_type VARCHAR(50),
    spec JSONB NOT NULL,
    dataset_id INTEGER REFERENCES internal.generated_datasets(id) ON DELETE SET NULL,
    session_id VARCHAR(36),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_generated_charts_session_id ON internal.generated_charts(session_id);

CREATE TABLE IF NOT EXISTS internal.generated_scripts (
    id SERIAL PRIMARY KEY,
    script TEXT NOT NULL,
    language VARCHAR(50) DEFAULT 'python',
    task_description TEXT,
    dataset_id INTEGER REFERENCES internal.generated_datasets(id) ON DELETE SET NULL,
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

