-- ============================================================================
-- Database Initialization Script for Spark Analytics Jobs
--
-- This script creates all the necessary PostgreSQL tables for the Spark
-- streaming analytics jobs (cart_abandonment, revenue_streaming, fraud_detection,
-- inventory_velocity, operational_metrics).
--
-- Run manually:
--   docker-compose exec postgres psql -U postgres -d kafka_ecom -f /db-init.sql
-- ============================================================================

-- ============================================================================
-- 1. CART ABANDONMENT TABLE
-- ============================================================================
-- Tracks shopping carts where users added items but didn't complete checkout
CREATE TABLE IF NOT EXISTS cart_abandonment (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    product_id VARCHAR(255) NOT NULL,
    item_added_time TIMESTAMP NOT NULL,
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for faster queries by user_id
CREATE INDEX IF NOT EXISTS idx_cart_abandonment_user_id ON cart_abandonment(user_id);
-- Index for faster queries by detected_at
CREATE INDEX IF NOT EXISTS idx_cart_abandonment_detected_at ON cart_abandonment(detected_at);

GRANT ALL PRIVILEGES ON cart_abandonment TO postgres;
GRANT ALL PRIVILEGES ON cart_abandonment_id_seq TO postgres;

-- ============================================================================
-- 2. REVENUE METRICS TABLE
-- ============================================================================
-- Real-time revenue aggregations by time window
CREATE TABLE IF NOT EXISTS revenue_metrics (
    id SERIAL PRIMARY KEY,
    window_start TIMESTAMP NOT NULL,
    window_end TIMESTAMP NOT NULL,
    total_revenue DECIMAL(12, 2),
    order_count INTEGER,
    avg_order_value DECIMAL(12, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for time-range queries
CREATE INDEX IF NOT EXISTS idx_revenue_metrics_window_start ON revenue_metrics(window_start);
-- Index for trending queries
CREATE INDEX IF NOT EXISTS idx_revenue_metrics_created_at ON revenue_metrics(created_at);

GRANT ALL PRIVILEGES ON revenue_metrics TO postgres;
GRANT ALL PRIVILEGES ON revenue_metrics_id_seq TO postgres;

-- ============================================================================
-- 3. FRAUD ALERTS TABLE
-- ============================================================================
-- Detects and tracks suspicious payment patterns
CREATE TABLE IF NOT EXISTS fraud_alerts (
    id SERIAL PRIMARY KEY,
    alert_id VARCHAR(255) UNIQUE,
    alert_timestamp TIMESTAMP NOT NULL,
    user_id VARCHAR(255) NOT NULL,
    order_id VARCHAR(255),
    alert_type VARCHAR(50),
    severity VARCHAR(20),
    details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for user-based fraud queries
CREATE INDEX IF NOT EXISTS idx_fraud_alerts_user_id ON fraud_alerts(user_id);
-- Index for severity filtering
CREATE INDEX IF NOT EXISTS idx_fraud_alerts_severity ON fraud_alerts(severity);
-- Index for timestamp queries
CREATE INDEX IF NOT EXISTS idx_fraud_alerts_alert_timestamp ON fraud_alerts(alert_timestamp);

GRANT ALL PRIVILEGES ON fraud_alerts TO postgres;
GRANT ALL PRIVILEGES ON fraud_alerts_id_seq TO postgres;

-- ============================================================================
-- 4. INVENTORY VELOCITY TABLE
-- ============================================================================
-- Product sales velocity and ranking for inventory optimization
CREATE TABLE IF NOT EXISTS inventory_velocity (
    id SERIAL PRIMARY KEY,
    window_start TIMESTAMP NOT NULL,
    window_end TIMESTAMP NOT NULL,
    product_id VARCHAR(255) NOT NULL,
    units_sold INTEGER,
    revenue DECIMAL(12, 2),
    velocity_rank INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for product queries
CREATE INDEX IF NOT EXISTS idx_inventory_velocity_product_id ON inventory_velocity(product_id);
-- Index for time-range queries
CREATE INDEX IF NOT EXISTS idx_inventory_velocity_window_start ON inventory_velocity(window_start);
-- Index for ranking queries
CREATE INDEX IF NOT EXISTS idx_inventory_velocity_rank ON inventory_velocity(velocity_rank);

GRANT ALL PRIVILEGES ON inventory_velocity TO postgres;
GRANT ALL PRIVILEGES ON inventory_velocity_id_seq TO postgres;

-- ============================================================================
-- 5. OPERATIONAL METRICS TABLE
-- ============================================================================
-- System health monitoring and alerting
CREATE TABLE IF NOT EXISTS operational_metrics (
    id SERIAL PRIMARY KEY,
    window_start TIMESTAMP NOT NULL,
    window_end TIMESTAMP NOT NULL,
    metric_name VARCHAR(255),
    metric_value DECIMAL(12, 2),
    threshold DECIMAL(12, 2),
    status VARCHAR(20),
    services_checked JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for status queries
CREATE INDEX IF NOT EXISTS idx_operational_metrics_status ON operational_metrics(status);
-- Index for time-range queries
CREATE INDEX IF NOT EXISTS idx_operational_metrics_window_start ON operational_metrics(window_start);

GRANT ALL PRIVILEGES ON operational_metrics TO postgres;
GRANT ALL PRIVILEGES ON operational_metrics_id_seq TO postgres;

-- ============================================================================
-- SUMMARY
-- ============================================================================
-- Tables created:
-- ✓ cart_abandonment - Cart abandonment detection results
-- ✓ revenue_metrics - Revenue analytics by time window
-- ✓ fraud_alerts - Fraud detection alerts
-- ✓ inventory_velocity - Product sales velocity rankings
-- ✓ operational_metrics - System health and monitoring
--
-- All tables include indexes for common query patterns and proper timestamps.
-- Permissions granted to postgres user for Spark job writes.
-- ============================================================================
