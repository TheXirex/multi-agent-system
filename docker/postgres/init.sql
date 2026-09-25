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
    status VARCHAR(20) NOT NULL DEFAULT 'completed',
    total_amount NUMERIC(10, 2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS order_items (
    id SERIAL PRIMARY KEY,
    order_id INTEGER REFERENCES orders(id),
    product_id INTEGER REFERENCES products(id),
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(10, 2) NOT NULL
);

-- Seed Data
INSERT INTO users (name, email, country) VALUES
('William Brown', 'william.brown@example.com', 'UK'),
('Emma Wilson', 'emma.wilson@example.com', 'USA'),
('John Doe', 'john.doe@example.com', 'USA'),
('Jane Smith', 'jane.smith@example.com', 'UK'),
('James Taylor', 'james.taylor@example.com', 'Canada');

INSERT INTO categories (name) VALUES
('Electronics'),
('Books'),
('Clothing');

INSERT INTO products (name, category_id, price, stock) VALUES
('Wireless Headphones', 1, 99.99, 50),
('Mechanical Keyboard', 1, 149.50, 30),
('Clean Code Book', 2, 35.00, 100),
('Designing Data-Intensive Applications', 2, 45.00, 80),
('Cotton T-Shirt', 3, 20.00, 200);

INSERT INTO orders (user_id, status, total_amount, created_at) VALUES
(1, 'completed', 184.99, '2026-08-10 14:30:00'),
(2, 'completed', 149.50, '2026-08-15 10:15:00'),
(1, 'completed', 35.00, '2026-09-01 11:00:00'),
(3, 'completed', 249.49, '2026-09-12 16:45:00'),
(4, 'completed', 45.00, '2026-09-20 09:30:00');

INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES
(1, 1, 1, 99.99),
(1, 4, 1, 45.00),
(1, 5, 2, 20.00),
(2, 2, 1, 149.50),
(3, 3, 1, 35.00),
(4, 1, 2, 99.99),
(4, 4, 1, 45.00),
(5, 4, 1, 45.00);
