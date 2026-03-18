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
  relname as table_name,
  n_live_tup as row_count,
  n_dead_tup as dead_rows,
  pg_size_pretty(pg_total_relation_size(schemaname||'.'||relname)) as total_size,
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
  method,
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
  method,
  status,
  created_at
FROM payments
WHERE status = 'FAILED'
ORDER BY created_at DESC
LIMIT 20;


-- ============================================================================
-- 5. REVENUE METRICS (Analytics)
-- ============================================================================

-- View recent revenue metrics
SELECT 
  window_start,
  window_end,
  order_count,
  total_revenue,
  avg_order_value
FROM revenue_metrics
ORDER BY window_start DESC
LIMIT 10;

-- Revenue trend (hourly)
SELECT 
  window_start,
  order_count,
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
  alert_id,
  alert_timestamp,
  user_id,
  order_id,
  alert_type,
  severity,
  details,
  created_at
FROM fraud_alerts
ORDER BY alert_timestamp DESC
LIMIT 20;

-- Fraud alerts by type
SELECT 
  alert_type,
  COUNT(*) as count,
  AVG(CASE WHEN severity = 'HIGH' THEN 1 ELSE 0 END) as high_severity_ratio
FROM fraud_alerts
GROUP BY alert_type
ORDER BY count DESC;

-- High-risk fraud alerts (severity HIGH)
SELECT 
  id,
  alert_id,
  alert_timestamp,
  user_id,
  order_id,
  alert_type,
  severity,
  details
FROM fraud_alerts
WHERE severity = 'HIGH'
ORDER BY alert_timestamp DESC
LIMIT 20;


-- ============================================================================
-- 7. CART ABANDONMENT
-- ============================================================================

-- View recent cart abandonments with product details
SELECT 
  ca.user_id,
  ca.product_id,
  ca.item_added_time,
  p.name as product_name,
  p.price,
  (EXTRACT(EPOCH FROM (NOW() - ca.item_added_time)) / 3600)::INT as hours_since_added
FROM cart_abandonment ca
JOIN products p ON ca.product_id = p.product_id
ORDER BY ca.item_added_time DESC
LIMIT 20;

-- Cart abandonment products (most frequently abandoned)
SELECT 
  ca.product_id,
  p.name as product_name,
  COUNT(*) as times_abandoned,
  AVG(p.price) as avg_product_price,
  COUNT(DISTINCT ca.user_id) as unique_users
FROM cart_abandonment ca
JOIN products p ON ca.product_id = p.product_id
GROUP BY ca.product_id, p.name
ORDER BY times_abandoned DESC
LIMIT 20;

-- Users with most abandoned items
SELECT 
  ca.user_id,
  COUNT(*) as total_abandoned_items,
  COUNT(DISTINCT ca.product_id) as unique_products,
  MAX(ca.item_added_time) as last_abandoned
FROM cart_abandonment ca
GROUP BY ca.user_id
ORDER BY total_abandoned_items DESC
LIMIT 20;


-- ============================================================================
-- 8. INVENTORY VELOCITY
-- ============================================================================

-- View recent inventory velocity
SELECT 
  product_id,
  window_start,
  window_end,
  units_sold,
  revenue,
  velocity_rank
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
  stock,
  created_at
FROM products
ORDER BY created_at DESC;

-- Low stock alert
SELECT 
  id,
  name,
  price,
  stock
FROM products
WHERE stock < 10
ORDER BY stock ASC;


-- ============================================================================
-- 10. EVENT PROCESSING
-- ============================================================================

-- Processed events count
SELECT 
  event_type,
  COUNT(*) as count
FROM processed_events
GROUP BY event_type
ORDER BY count DESC;

-- Event processing analysis
SELECT 
  'Total processed events' as metric,
  COUNT(*) as count
FROM processed_events

UNION ALL

SELECT 
  CONCAT('Events - ', event_type) as metric,
  COUNT(*) as count
FROM processed_events
GROUP BY event_type;

-- Recent events
SELECT 
  id,
  event_id,
  event_type,
  processed_at
FROM processed_events
ORDER BY processed_at DESC
LIMIT 20;

-- Outbox events (pending delivery)
SELECT 
  COUNT(*) as pending_events
FROM outbox_events
WHERE published = 'N';


-- ============================================================================
-- 11. STOCK RESERVATIONS
-- ============================================================================

-- View recent stock reservations
SELECT 
  id,
  order_id,
  product_id,
  quantity,
  created_at
FROM stock_reservations
ORDER BY created_at DESC
LIMIT 20;

-- Stock reservation statistics
SELECT 
  product_id,
  COUNT(*) as total_reservations,
  SUM(quantity) as total_reserved,
  AVG(quantity) as avg_reserved
FROM stock_reservations
GROUP BY product_id
ORDER BY total_reserved DESC;

-- Pending reservations by product
SELECT 
  product_id,
  COUNT(*) as count,
  SUM(quantity) as total_quantity
FROM stock_reservations
GROUP BY product_id
ORDER BY count DESC;


-- ============================================================================
-- 12. OPERATIONAL METRICS (Spark Analytics)
-- ============================================================================

-- View recent operational metrics
SELECT 
  metric_name,
  metric_value,
  status,
  window_start
FROM operational_metrics
ORDER BY window_start DESC
LIMIT 20;

-- Operational metrics by status
SELECT 
  status,
  metric_name,
  AVG(metric_value) as avg_value,
  MAX(metric_value) as max_value,
  MIN(metric_value) as min_value,
  COUNT(*) as measurements
FROM operational_metrics
GROUP BY status, metric_name
ORDER BY status, metric_name;

-- Operational metrics trend
SELECT 
  DATE_TRUNC('hour', window_start) as hour,
  metric_name,
  AVG(metric_value) as avg_value,
  MAX(metric_value) as max_value
FROM operational_metrics
GROUP BY DATE_TRUNC('hour', window_start), metric_name
ORDER BY hour DESC
LIMIT 24;


-- ============================================================================
-- 13. SPARK ANALYTICS DATA FRESHNESS
-- ============================================================================

-- Check how recent each analytics table's data is
SELECT 
  'revenue_metrics' as table_name,
  MAX(window_end) as last_update,
  NOW() - MAX(window_end) as age
FROM revenue_metrics

UNION ALL

SELECT 
  'fraud_alerts' as table_name,
  MAX(alert_timestamp) as last_update,
  NOW() - MAX(alert_timestamp) as age
FROM fraud_alerts

UNION ALL

SELECT 
  'cart_abandonment' as table_name,
  MAX(detected_at) as last_update,
  NOW() - MAX(detected_at) as age
FROM cart_abandonment

UNION ALL

SELECT 
  'inventory_velocity' as table_name,
  MAX(window_end) as last_update,
  NOW() - MAX(window_end) as age
FROM inventory_velocity

UNION ALL

SELECT 
  'operational_metrics' as table_name,
  MAX(window_start) as last_update,
  NOW() - MAX(window_start) as age
FROM operational_metrics

ORDER BY age DESC;


-- ============================================================================
-- 14. DATABASE MAINTENANCE
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
-- 15. PERFORMANCE MONITORING
-- ============================================================================

-- Active database connections
SELECT 
  datname as database,
  COUNT(*) as active_connections,
  MAX(EXTRACT(EPOCH FROM (NOW() - query_start))) as longest_query_seconds
FROM pg_stat_activity
WHERE datname = 'kafka_ecom'
GROUP BY datname;

-- Long-running queries
SELECT 
  pid,
  usename,
  application_name,
  query_start,
  EXTRACT(EPOCH FROM (NOW() - query_start)) as duration_seconds,
  query
FROM pg_stat_activity
WHERE datname = 'kafka_ecom'
AND state != 'idle'
ORDER BY query_start ASC
LIMIT 10;
SELECT 
  pid,
  usename,
  query,
  wait_event_type,
  state
FROM pg_stat_activity
WHERE state != 'idle'
ORDER BY query_start DESC;


-- ============================================================================
-- 16. DATA CONSISTENCY DIAGNOSTICS
-- ============================================================================

-- Complete order status breakdown
SELECT 
  'Total orders' as metric,
  COUNT(*) as count
FROM orders

UNION ALL

SELECT 
  CONCAT('Orders - ', status) as metric,
  COUNT(*) as count
FROM orders
GROUP BY status

UNION ALL

SELECT 
  'Total payments' as metric,
  COUNT(*) as count
FROM payments

UNION ALL

SELECT 
  CONCAT('Payments - ', status) as metric,
  COUNT(*) as count
FROM payments
GROUP BY status;

-- Orders vs Payments mismatch (original check)
SELECT 
  'FULFILLED orders' as metric,
  COUNT(*) as count
FROM orders
WHERE status = 'FULFILLED'

UNION ALL

SELECT 
  'Successful payments' as metric,
  COUNT(*) as count
FROM payments
WHERE status = 'SUCCESS'

UNION ALL

SELECT 
  'All payments' as metric,
  COUNT(*) as count
FROM payments;

-- Find FULFILLED orders without corresponding payment
SELECT 
  o.order_id,
  o.user_id,
  o.total_amount,
  o.created_at,
  p.payment_id
FROM orders o
LEFT JOIN payments p ON o.order_id = p.order_id
WHERE o.status = 'FULFILLED'
AND p.id IS NULL
ORDER BY o.created_at DESC;

-- Find payments without corresponding FULFILLED order
SELECT 
  p.payment_id,
  p.order_id,
  p.status,
  p.created_at,
  o.status as order_status
FROM payments p
LEFT JOIN orders o ON p.order_id = o.order_id
WHERE p.status = 'SUCCESS'
AND (o.id IS NULL OR o.status != 'FULFILLED')
ORDER BY p.created_at DESC;


-- ============================================================================
-- 17. EVENT PROCESSING DIAGNOSTICS
-- ============================================================================

-- Orders fulfillment events vs actual fulfilled orders
SELECT 
  'order.fulfilled events processed' as metric,
  COUNT(*) as count
FROM processed_events
WHERE event_type = 'order.fulfilled'

UNION ALL

SELECT 
  'Actual FULFILLED orders' as metric,
  COUNT(*) as count
FROM orders
WHERE status = 'FULFILLED'

UNION ALL

SELECT 
  'payment.processed events processed' as metric,
  COUNT(*) as count
FROM processed_events
WHERE event_type = 'payment.processed'

UNION ALL

SELECT 
  'Actual SUCCESS payments' as metric,
  COUNT(*) as count
FROM payments
WHERE status = 'SUCCESS';

-- Find order IDs from fulfilled events that might not have orders
SELECT 
  COUNT(DISTINCT pe.event_id) as total_fulfilled_events,
  COUNT(DISTINCT CASE WHEN o.id IS NOT NULL THEN pe.event_id END) as events_with_matching_orders
FROM processed_events pe
LEFT JOIN orders o ON o.order_id LIKE '%' || pe.event_id || '%'
WHERE pe.event_type = 'order.fulfilled';

