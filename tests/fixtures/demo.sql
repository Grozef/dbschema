-- Schema de demonstration (invente) : librairie en ligne. Sert aux tests et a l'exemple du README.
-- Couvre : table tres referencee (users, 11 FK), auto-reference, 1:1, cle primaire composite, FK facultatives,
-- colonne referencee a la fois en 1 et en 0..1, FK vers une colonne UNIQUE qui n'est pas la PK.

CREATE TABLE users (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  email VARCHAR(190) NOT NULL UNIQUE,
  display_name VARCHAR(120) NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  is_staff TINYINT(1) NOT NULL DEFAULT 0,
  created_at TIMESTAMP NULL,
  updated_at TIMESTAMP NULL
) COMMENT 'Clients et personnel';

CREATE TABLE user_profiles (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT UNSIGNED NOT NULL UNIQUE,
  birth_date DATE NULL,
  newsletter TINYINT(1) NOT NULL DEFAULT 0,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) COMMENT '1:1 avec users';

CREATE TABLE countries (
  id INT AUTO_INCREMENT PRIMARY KEY,
  iso_code CHAR(2) NOT NULL UNIQUE,
  name VARCHAR(80) NOT NULL
);

CREATE TABLE addresses (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT UNSIGNED NOT NULL,
  label VARCHAR(50) NOT NULL,
  street VARCHAR(190) NOT NULL,
  city VARCHAR(100) NOT NULL,
  postal_code VARCHAR(20) NOT NULL,
  country_iso CHAR(2) NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY (country_iso) REFERENCES countries(iso_code)
);

CREATE TABLE categories (
  id INT AUTO_INCREMENT PRIMARY KEY,
  parent_id INT NULL,
  name VARCHAR(100) NOT NULL,
  slug VARCHAR(120) NOT NULL UNIQUE,
  FOREIGN KEY (parent_id) REFERENCES categories(id)
) COMMENT 'Arborescence (auto-reference)';

CREATE TABLE publishers (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(150) NOT NULL,
  website VARCHAR(190) NULL
);

CREATE TABLE authors (
  id INT AUTO_INCREMENT PRIMARY KEY,
  full_name VARCHAR(150) NOT NULL,
  birth_year SMALLINT NULL,
  biography TEXT NULL
);

CREATE TABLE books (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  isbn CHAR(13) NOT NULL UNIQUE,
  title VARCHAR(255) NOT NULL,
  category_id INT NOT NULL,
  publisher_id INT NULL,
  price DECIMAL(8,2) NOT NULL,
  published_on DATE NULL,
  created_by BIGINT UNSIGNED NOT NULL,
  created_at TIMESTAMP NULL,
  FOREIGN KEY (category_id) REFERENCES categories(id),
  FOREIGN KEY (publisher_id) REFERENCES publishers(id),
  FOREIGN KEY (created_by) REFERENCES users(id)
);

CREATE TABLE book_authors (
  book_id BIGINT UNSIGNED NOT NULL,
  author_id INT NOT NULL,
  position TINYINT NOT NULL DEFAULT 1,
  PRIMARY KEY (book_id, author_id),
  FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
  FOREIGN KEY (author_id) REFERENCES authors(id)
) COMMENT 'Table de liaison, PK composite';

CREATE TABLE warehouses (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  country_iso CHAR(2) NOT NULL,
  FOREIGN KEY (country_iso) REFERENCES countries(iso_code)
);

CREATE TABLE stock_levels (
  warehouse_id INT NOT NULL,
  book_id BIGINT UNSIGNED NOT NULL,
  quantity INT NOT NULL DEFAULT 0,
  updated_at TIMESTAMP NULL,
  PRIMARY KEY (warehouse_id, book_id),
  FOREIGN KEY (warehouse_id) REFERENCES warehouses(id),
  FOREIGN KEY (book_id) REFERENCES books(id)
);

CREATE TABLE coupons (
  id INT AUTO_INCREMENT PRIMARY KEY,
  code VARCHAR(40) NOT NULL UNIQUE,
  percent_off TINYINT NOT NULL,
  valid_until DATE NULL,
  created_by BIGINT UNSIGNED NOT NULL,
  FOREIGN KEY (created_by) REFERENCES users(id)
);

CREATE TABLE orders (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  number VARCHAR(30) NOT NULL UNIQUE,
  customer_id BIGINT UNSIGNED NOT NULL,
  shipping_address_id BIGINT UNSIGNED NOT NULL,
  billing_address_id BIGINT UNSIGNED NULL,
  coupon_id INT NULL,
  handled_by BIGINT UNSIGNED NULL,
  status VARCHAR(30) NOT NULL,
  total DECIMAL(10,2) NOT NULL,
  placed_at TIMESTAMP NULL,
  FOREIGN KEY (customer_id) REFERENCES users(id),
  FOREIGN KEY (shipping_address_id) REFERENCES addresses(id),
  FOREIGN KEY (billing_address_id) REFERENCES addresses(id),
  FOREIGN KEY (coupon_id) REFERENCES coupons(id),
  FOREIGN KEY (handled_by) REFERENCES users(id)
);

CREATE TABLE order_items (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  order_id BIGINT UNSIGNED NOT NULL,
  book_id BIGINT UNSIGNED NOT NULL,
  quantity SMALLINT NOT NULL,
  unit_price DECIMAL(8,2) NOT NULL,
  FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
  FOREIGN KEY (book_id) REFERENCES books(id)
);

CREATE TABLE payments (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  order_id BIGINT UNSIGNED NOT NULL,
  provider VARCHAR(40) NOT NULL,
  amount DECIMAL(10,2) NOT NULL,
  paid_at TIMESTAMP NULL,
  refunded_by BIGINT UNSIGNED NULL,
  FOREIGN KEY (order_id) REFERENCES orders(id),
  FOREIGN KEY (refunded_by) REFERENCES users(id)
);

CREATE TABLE shipments (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  order_id BIGINT UNSIGNED NOT NULL UNIQUE,
  warehouse_id INT NOT NULL,
  carrier VARCHAR(60) NOT NULL,
  tracking_number VARCHAR(80) NULL,
  prepared_by BIGINT UNSIGNED NULL,
  shipped_at TIMESTAMP NULL,
  FOREIGN KEY (order_id) REFERENCES orders(id),
  FOREIGN KEY (warehouse_id) REFERENCES warehouses(id),
  FOREIGN KEY (prepared_by) REFERENCES users(id)
) COMMENT '1:1 avec orders';

CREATE TABLE reviews (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  book_id BIGINT UNSIGNED NOT NULL,
  user_id BIGINT UNSIGNED NOT NULL,
  rating TINYINT NOT NULL,
  body TEXT NULL,
  moderated_by BIGINT UNSIGNED NULL,
  created_at TIMESTAMP NULL,
  UNIQUE (book_id, user_id),
  FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
  FOREIGN KEY (user_id) REFERENCES users(id),
  FOREIGN KEY (moderated_by) REFERENCES users(id)
);

CREATE TABLE wishlists (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT UNSIGNED NOT NULL,
  book_id BIGINT UNSIGNED NOT NULL,
  added_at TIMESTAMP NULL,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
);

CREATE TABLE audit_logs (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT UNSIGNED NULL,
  action VARCHAR(60) NOT NULL,
  entity VARCHAR(60) NOT NULL,
  entity_id BIGINT UNSIGNED NULL,
  payload JSON NULL,
  created_at TIMESTAMP NULL,
  FOREIGN KEY (user_id) REFERENCES users(id)
) COMMENT 'Journal (aucune FK entrante)';
