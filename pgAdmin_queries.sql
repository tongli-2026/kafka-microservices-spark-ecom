################################################################################
# pgAdmin Query Library
#
# A collection of useful SQL queries for monitoring the Kafka e-commerce system
# Usage: Copy and paste queries into pgAdmin Query Tool
#
################################################################################

-- ============================================================================
-- 1. DATABASE OVERVIEW
-- ============================================================================

-- View database size and connections
SELECT 
  datname as database,
  pg_size_pretty(pg_database_size(datname)) as size,
  numbackends as active_connections
FROM pg_stat_database 
WHERE datname = 'kafka_ecom';


-- ============================================================================
-- 2. TABLE STATISTICS
-- ============================================================================

-- View all tables with row counts and sizes
SELECT 
  schemaname,
  tablename,
  n_live_tup as row_count,
  n_dead_tup as dead_rows,
  pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as total_size,
  last_vacuum,
  last_autovacuum
FROM pg_stat_user_tables
ORDER BY n_live_tup DESC;


-- ============================================================================
-- 3. ORDERS ANALYSIS
-- ============================================================================

-- View recent orders
SELECT 
  id,
  user_id,
  total_amount,
  status,
  created_at,
  updated_at
FROM orders
ORDER BY created_at DESC
LIMIT 20;

-- Orders by status
SELECT 
  status,
  COUNT(*) as count,
  SUM(total_amount) as total_revenue,
  AVG(total_amount) as avg_amount
FROM orders
GROUP BY status
ORDER BY count DESC;

-- Orders by hour (for trending)
SELECT 
  DATE_TRUNC('hour', created_at) as hour,
  COUNT(*) as order_count,
  SUM(total_amount) as revenue,
  AVG(total_amount) as avg_order_value
FROM orders
GROUP BY DATE_TRUNC('hour', created_at)
ORDER BY hour DESC
LIMIT 24;


-- ============================================================================
-- 4. PAYMENTS ANALYSIS
-- ============================================================================

-- View recent payments
SELECT 
  id,
  order_id,
  amount,
  payment_method,
  status,
  created_at
FROM payments
ORDER BY created_at DESC
LIMIT 20;

-- Payment status distribution
SELECT 
  status,
  COUNT(*) as count,
  SUM(amount) as total_amount,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) as percentage
FROM payments
GROUP BY status
ORDER BY count DESC;

-- Failed payments (for debugging)
SELECT 
  id,
  order_id,
  amount,
  payment_method,
  status,
  created_at
FROM payments
WHERE status = 'failed'
ORDER BY created_at DESC
LIMIT 20;


-- ============================================================================
-- 5. REVENUE METRICS (Analytics)
-- ============================================================================

-- View recent revenue metrics
SELECT 
  window_start,
  window_end,
  total_orders,
  total_revenue,
  avg_order_value,
  created_at
FROM revenue_metrics
ORDER BY window_start DESC
LIMIT 10;

-- Revenue trend (hourly)
SELECT 
  window_start,
  total_orders,
  total_revenue,
  avg_order_value
FROM revenue_metrics
ORDER BY window_start DESC;


-- ============================================================================
-- 6. FRAUD ALERTS
-- ============================================================================

-- View recent fraud alerts
SELECT 
  id,
  order_id,
  risk_score,
  reason,
  status,
  created_at
FROM fraud_alerts
ORDER BY created_at DESC
LIMIT 20;

-- Fraud alerts by reason
SELECT 
  reason,
  COUNT(*) as count,
  AVG(risk_score) as avg_risk_score,
  MAX(risk_score) as max_risk_score
FROM fraud_alerts
GROUP BY reason
ORDER BY count DESC;

-- High-risk fraud alerts (risk_score > 0.8)
SELECT 
  id,
  order_id,
  risk_score,
  reason,
  created_at
FROM fraud_alerts
WHERE risk_score > 0.8
ORDER BY risk_score DESC
LIMIT 20;


-- ============================================================================
-- 7. CART ABANDONMENT
-- ============================================================================

-- View recent abandoned carts
SELECT 
  id,
  user_id,
  cart_value,
  items_count,
  abandoned_at,
  created_at
FROM cart_abandonment
ORDER BY abandoned_at DESC
LIMIT 20;

-- Cart abandonment statistics
SELECT 
  COUNT(*) as total_abandoned,
  SUM(cart_value) as total_value,
  AVG(cart_value) as avg_cart_value,
  AVG(items_count) as avg_items,
  MAX(cart_value) as max_cart_value
FROM cart_abandonment;

-- Abandonment by time of day
SELECT 
  EXTRACT(HOUR FROM abandoned_at) as hour_of_day,
  COUNT(*) as count,
  SUM(cart_value) as total_value,
  AVG(cart_value) as avg_value
FROM cart_abandonment
GROUP BY EXTRACT(HOUR FROM abandoned_at)
ORDER BY hour_of_day;


-- ============================================================================
-- 8. INVENTORY VELOCITY
-- ============================================================================

-- View recent inventory velocity
SELECT 
  product_id,
  window_start,
  window_end,
  units_sold,
  rank,
  created_at
FROM inventory_velocity
ORDER BY window_end DESC
LIMIT 20;

-- Top selling products
SELECT 
  product_id,
  SUM(units_sold) as total_units,
  COUNT(*) as time_windows,
  AVG(units_sold) as avg_units_per_window
FROM inventory_velocity
GROUP BY product_id
ORDER BY total_units DESC
LIMIT 20;


-- ============================================================================
-- 9. PRODUCTS
-- ============================================================================

-- View all products
SELECT 
  id,
  name,
  price,
  stock_quantity,
  created_at
FROM products
ORDER BY created_at DESC;

-- Low stock alert
SELECT 
  id,
  name,
  price,
  stock_quantity
FROM products
WHERE stock_quantity < 10
ORDER BY stock_quantity ASC;


-- ============================================================================
-- 10. EVENT PROCESSING
-- ============================================================================

-- Processed events count
SELECT 
  COUNT(*) as total_processed,
  event_type,
  COUNT(*) as count
FROM processed_events
GROUP BY event_type
ORDER BY count DESC;

-- Recent events
SELECT 
  id,
  event_type,
  user_id,
  created_at
FROM processed_events
ORDER BY created_at DESC
LIMIT 20;

-- Outbox events (pending delivery)
SELECT 
  COUNT(*) as pending_events
FROM outbox_events
WHERE is_processed = false;


-- ============================================================================
-- 11. DATABASE MAINTENANCE
-- ============================================================================

-- View table sizes (for optimization)
SELECT 
  schemaname,
  tablename,
  pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_tables
JOIN pg_class ON pg_class.relname = pg_tables.tablename
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- Check for missing indexes
SELECT 
  schemaname,
  tablename,
  attname,
  n_distinct,
  correlation
FROM pg_stats
WHERE schemaname = 'public'
ORDER BY ABS(correlation) DESC;


-- ============================================================================
-- 12. PERFORMANCE MONITORING
-- ============================================================================

-- Slow queries (if pg_stat_statements is enabled)
SELECT 
  query,
  calls,
  total_time,
  mean_time,
  max_time
FROM pg_stat_statements
ORDER BY total_time DESC
LIMIT 10;

-- Lock information
SELECT 
  pid,
  usename,
  query,
  wait_event_type,
  state
FROM pg_stat_activity
WHERE state != 'idle'
ORDER BY query_start DESC;

