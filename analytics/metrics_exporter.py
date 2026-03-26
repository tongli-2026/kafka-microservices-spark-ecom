"""
Prometheus Metrics Exporter for Spark Analytics Jobs

This service polls PostgreSQL tables created by Spark jobs and exposes
metrics as Prometheus format on http://localhost:9090/metrics

Tables monitored:
- revenue_metrics: 1-minute windowed revenue aggregations
- fraud_alerts: Real-time fraud detection alerts
- inventory_velocity: Hourly product sales velocity
- cart_abandonment: 30-minute windowed cart abandonment
- operational_metrics: System health and throughput monitoring

Metrics Exported (16 total):
- Revenue (4): total_24h, order_count_24h, avg_order_value, revenue_per_minute
- Fraud (3): alerts_total (by severity), alerts_by_type, alerts_rate_per_hour
- Inventory (3): units_sold_24h, top_product_units (ranked), top_product_revenue (ranked)
- Cart (3): abandoned_24h, abandonment_rate (%), recovery_rate
- System (3): health_pct, status_breakdown (by status), critical_alert_count
"""

import os
import logging
import time
from datetime import datetime, timedelta
import psycopg2
from prometheus_client import Counter, Gauge, Histogram, start_http_server
from prometheus_client.core import CollectorRegistry

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database connection parameters
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
POSTGRES_DB = os.getenv("POSTGRES_DB", "kafka_ecom")

# ============ PROMETHEUS METRICS ============

# Revenue metrics
revenue_total_24h = Gauge(
    'spark_revenue_total_24h',
    'Total revenue in last 24 hours',
    ['service']
)

order_count_24h = Gauge(
    'spark_order_count_24h',
    'Total orders processed in last 24 hours',
    ['service']
)

avg_order_value = Gauge(
    'spark_avg_order_value',
    'Average order value',
    ['service']
)

revenue_per_minute = Gauge(
    'spark_revenue_per_minute',
    'Revenue in the latest 1-minute window',
    ['service']
)

# Fraud detection metrics
fraud_alerts_total = Gauge(
    'spark_fraud_alerts_total',
    'Total fraud alerts in last 24 hours',
    ['service', 'severity']
)

fraud_by_type = Gauge(
    'spark_fraud_by_type_total',
    'Fraud alerts by type in last 24 hours',
    ['service', 'alert_type']
)

fraud_alerts_rate = Gauge(
    'spark_fraud_alerts_rate_per_hour',
    'Fraud alert rate per hour',
    ['service']
)

# Inventory velocity metrics
inventory_velocity_total = Gauge(
    'spark_inventory_velocity_units_sold_24h',
    'Total units sold in last 24 hours',
    ['service']
)

top_product_units = Gauge(
    'spark_top_product_units_sold',
    'Units sold for top 10 products (24h)',
    ['service', 'product_id', 'rank']
)

top_product_revenue = Gauge(
    'spark_top_product_revenue',
    'Revenue for top 10 products (24h)',
    ['service', 'product_id', 'rank']
)

# Cart abandonment metrics
cart_abandoned_24h = Gauge(
    'spark_cart_abandoned_24h',
    'Total abandoned carts in last 24 hours',
    ['service']
)

cart_abandonment_rate = Gauge(
    'spark_cart_abandonment_rate',
    'Cart abandonment rate (percent)',
    ['service']
)

cart_recovery_rate = Gauge(
    'spark_cart_recovery_rate',
    'Cart recovery rate (recovered/abandoned)',
    ['service']
)

# System health metrics
system_health_pct = Gauge(
    'spark_system_health_pct',
    'Percentage of job monitoring windows in HEALTHY state (last 1h)',
    ['service']
)

system_status_breakdown = Gauge(
    'spark_system_status_breakdown',
    'Count of monitoring records by health status (last 1h)',
    ['service', 'status']
)

critical_alert_count = Gauge(
    'spark_critical_alert_count',
    'Total CRITICAL status records in last 1 hour',
    ['service']
)

# ============ DATABASE FUNCTIONS ============

def get_db_connection():
    """Create PostgreSQL connection."""
    try:
        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            database=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD
        )
        return conn
    except psycopg2.Error as e:
        logger.error(f"Failed to connect to PostgreSQL: {e}")
        return None

def update_revenue_metrics(conn):
    """Query revenue_metrics table and update Prometheus metrics."""
    try:
        cursor = conn.cursor()
        
        # Get 24-hour revenue stats
        cursor.execute("""
            SELECT 
                COALESCE(SUM(total_revenue), 0) as total_rev,
                COALESCE(SUM(order_count), 0) as total_orders,
                COALESCE(AVG(avg_order_value), 0) as avg_value
            FROM revenue_metrics
            WHERE window_start > NOW() - INTERVAL '24 hours'
        """)
        
        total_rev, total_orders, avg_val = cursor.fetchone()
        revenue_total_24h.labels(service="spark-analytics").set(total_rev or 0)
        order_count_24h.labels(service="spark-analytics").set(total_orders or 0)
        avg_order_value.labels(service="spark-analytics").set(avg_val or 0)
        
        # Get latest minute revenue
        cursor.execute("""
            SELECT COALESCE(total_revenue, 0) FROM revenue_metrics
            ORDER BY window_start DESC
            LIMIT 1
        """)
        latest = cursor.fetchone()
        if latest:
            revenue_per_minute.labels(service="spark-analytics").set(latest[0])
        
        cursor.close()
        logger.debug("Updated revenue metrics")
        
    except Exception as e:
        logger.error(f"Error updating revenue metrics: {e}")

def update_fraud_metrics(conn):
    """Query fraud_alerts table and update Prometheus metrics."""
    try:
        cursor = conn.cursor()
        
        # Get fraud alerts by severity
        cursor.execute("""
            SELECT severity, COUNT(*) as count
            FROM fraud_alerts
            WHERE alert_timestamp > NOW() - INTERVAL '24 hours'
            GROUP BY severity
        """)
        
        for severity, count in cursor.fetchall():
            fraud_alerts_total.labels(
                service="spark-analytics",
                severity=severity.upper() if severity else "UNKNOWN"
            ).set(count)
        
        # Get fraud alerts by type
        cursor.execute("""
            SELECT alert_type, COUNT(*) as count
            FROM fraud_alerts
            WHERE alert_timestamp > NOW() - INTERVAL '24 hours'
            GROUP BY alert_type
        """)
        
        for alert_type, count in cursor.fetchall():
            fraud_by_type.labels(
                service="spark-analytics",
                alert_type=alert_type or "unknown"
            ).set(count)
        
        # Get fraud alert rate per hour
        cursor.execute("""
            SELECT COALESCE(COUNT(*) * 1.0 / 24, 0) as alerts_per_hour
            FROM fraud_alerts
            WHERE alert_timestamp > NOW() - INTERVAL '24 hours'
        """)
        
        rate = cursor.fetchone()[0]
        fraud_alerts_rate.labels(service="spark-analytics").set(rate or 0)
        
        cursor.close()
        logger.debug("Updated fraud metrics")
        
    except Exception as e:
        logger.error(f"Error updating fraud metrics: {e}")

def update_inventory_metrics(conn):
    """Query inventory_velocity table and update Prometheus metrics."""
    try:
        cursor = conn.cursor()
        
        # Get total units sold
        cursor.execute("""
            SELECT COALESCE(SUM(units_sold), 0)
            FROM inventory_velocity
            WHERE window_start > NOW() - INTERVAL '24 hours'
        """)
        
        total_units = cursor.fetchone()[0]
        inventory_velocity_total.labels(service="spark-analytics").set(total_units or 0)
        
        # Get top 10 products by units sold
        cursor.execute("""
            SELECT product_id, SUM(units_sold) as units, SUM(revenue) as revenue,
                   ROW_NUMBER() OVER (ORDER BY SUM(units_sold) DESC) as rank
            FROM inventory_velocity
            WHERE window_start > NOW() - INTERVAL '24 hours'
            GROUP BY product_id
            ORDER BY units DESC
            LIMIT 10
        """)
        
        for product_id, units, revenue, rank in cursor.fetchall():
            top_product_units.labels(
                service="spark-analytics",
                product_id=str(product_id),
                rank=int(rank)
            ).set(units or 0)
            
            top_product_revenue.labels(
                service="spark-analytics",
                product_id=str(product_id),
                rank=int(rank)
            ).set(revenue or 0)
        
        cursor.close()
        logger.debug("Updated inventory metrics")
        
    except Exception as e:
        logger.error(f"Error updating inventory metrics: {e}")

def update_cart_abandonment_metrics(conn):
    """Query cart_abandonment table and update Prometheus metrics."""
    try:
        cursor = conn.cursor()
        
        # Get abandoned carts in 24h
        # Note: All rows in cart_abandonment table represent abandoned carts
        cursor.execute("""
            SELECT COALESCE(COUNT(*), 0) as abandoned_count
            FROM cart_abandonment
            WHERE detected_at > NOW() - INTERVAL '24 hours'
        """)
        
        abandoned = cursor.fetchone()[0]
        cart_abandoned_24h.labels(service="spark-analytics").set(abandoned or 0)
        
        # Get abandonment rate (100% since all rows are abandonments)
        # TODO: Enhance when cart_abandonment table includes status column for recovery tracking
        cursor.execute("""
            SELECT COALESCE(COUNT(*), 0) as total_carts
            FROM cart_abandonment
            WHERE detected_at > NOW() - INTERVAL '24 hours'
        """)
        
        total = cursor.fetchone()[0]
        if total > 0:
            abandon_rate = 100.0  # All rows are abandonments
        else:
            abandon_rate = 0.0
        cart_abandonment_rate.labels(service="spark-analytics").set(abandon_rate)
        
        # Recovery rate set to 0 (not tracked in current schema)
        # TODO: Add status column or separate recovered_carts table
        cart_recovery_rate.labels(service="spark-analytics").set(0.0)
        
        cursor.close()
        logger.debug("Updated cart abandonment metrics")
        
    except Exception as e:
        logger.error(f"Error updating cart abandonment metrics: {e}")

def update_system_health_metrics(conn):
    """Query operational_metrics table and update Prometheus system health metrics."""
    try:
        cursor = conn.cursor()
        
        # Get total count and HEALTHY count in last 1 hour
        cursor.execute("""
            SELECT 
                COALESCE(COUNT(*), 0) as total_count,
                COALESCE(SUM(CASE WHEN status = 'HEALTHY' THEN 1 ELSE 0 END), 0) as healthy_count
            FROM operational_metrics
            WHERE window_start > NOW() - INTERVAL '1 hour'
        """)
        
        total_count, healthy_count = cursor.fetchone()
        
        # Calculate health percentage
        if total_count > 0:
            health_pct = (healthy_count / total_count) * 100.0
        else:
            health_pct = 0.0
        
        system_health_pct.labels(service="spark-analytics").set(health_pct)
        
        # Get breakdown by status
        cursor.execute("""
            SELECT status, COUNT(*) as count
            FROM operational_metrics
            WHERE window_start > NOW() - INTERVAL '1 hour'
            GROUP BY status
        """)
        
        for status, count in cursor.fetchall():
            system_status_breakdown.labels(
                service="spark-analytics",
                status=status or "UNKNOWN"
            ).set(count)
        
        # Get CRITICAL alert count
        cursor.execute("""
            SELECT COALESCE(COUNT(*), 0) as critical_count
            FROM operational_metrics
            WHERE status = 'CRITICAL'
            AND window_start > NOW() - INTERVAL '1 hour'
        """)
        
        critical_count = cursor.fetchone()[0]
        critical_alert_count.labels(service="spark-analytics").set(critical_count or 0)
        
        cursor.close()
        logger.debug("Updated system health metrics")
        
    except Exception as e:
        logger.error(f"Error updating system health metrics: {e}")

def update_all_metrics():
    """Update all Prometheus metrics from PostgreSQL."""
    conn = get_db_connection()
    if not conn:
        logger.warning("Could not connect to PostgreSQL, skipping metrics update")
        return
    
    try:
        update_revenue_metrics(conn)
        update_fraud_metrics(conn)
        update_inventory_metrics(conn)
        update_cart_abandonment_metrics(conn)
        update_system_health_metrics(conn)
        logger.info("Successfully updated all metrics")
    finally:
        conn.close()

def metrics_update_loop():
    """Continuously update metrics every 30 seconds."""
    logger.info("Starting metrics update loop...")
    while True:
        try:
            update_all_metrics()
            time.sleep(30)  # Update every 30 seconds
        except Exception as e:
            logger.error(f"Error in metrics loop: {e}")
            time.sleep(30)

# ============ MAIN ============

if __name__ == "__main__":
    logger.info("Starting Spark Metrics Exporter...")
    logger.info(f"Connecting to PostgreSQL: {POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}")
    
    # Start Prometheus HTTP server on port 9090
    start_http_server(9090)
    logger.info("Prometheus metrics server started on port 9090")
    logger.info("Metrics available at http://localhost:9090/metrics")
    
    # Start metrics update loop
    metrics_update_loop()
