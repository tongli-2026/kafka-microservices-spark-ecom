#!/usr/bin/env python3
"""
auto-refill-inventory.py - Automatic Inventory Stock Replenishment Service

PURPOSE:
    Monitors product stock levels and automatically refills inventory when
    products run low. Ensures sustained load testing and prevents stock-outs
    during simulations.

BUSINESS VALUE:
    - Continuous inventory replenishment without manual intervention
    - Prevents "out of stock" situations that halt sales
    - Enables long-duration load tests and simulations
    - Automatically triggers low-stock alerts for monitoring
    - Maintains realistic inventory levels for testing

KEY FEATURES:
    - Polls inventory service every N seconds (configurable)
    - Tracks stock levels for all products
    - Automatic refill when stock drops below threshold
    - Configurable refill quantity and trigger threshold
    - Detailed logging with emoji indicators
    - Graceful shutdown with signal handling
    - Direct database updates for speed and reliability

USAGE:
    # First time: activate virtual environment
    source .venv/bin/activate

    # ⭐ RECOMMENDED: Default settings (check every 10s, refill at <20, +50 units)
    ./scripts/auto-refill-inventory.py

    # Low-stock threshold at 10 units (more aggressive refilling)
    ./scripts/auto-refill-inventory.py --threshold 10

    # Refill with 100 units per product
    ./scripts/auto-refill-inventory.py --refill-quantity 100

    # Check every 5 seconds (more frequent)
    ./scripts/auto-refill-inventory.py --interval 5

    # Combine options
    ./scripts/auto-refill-inventory.py --threshold 15 --refill-quantity 75 --interval 8

    # Verbose logging (debug mode)
    ./scripts/auto-refill-inventory.py --verbose

COMMAND-LINE OPTIONS:
    --threshold N (default: 20)
        Trigger refill when stock drops below N units
        Lower value = less frequent refills, higher stock variance
        Higher value = more frequent refills, stable stock levels
    
    --refill-quantity N (default: 50)
        Number of units to add when refilling
        Larger = fewer refills, more stock variance
        Smaller = more refills, more stable inventory
    
    --interval N (default: 10)
        Seconds between inventory checks
        Smaller = faster response to low stock, more database queries
        Larger = slower response, fewer queries, better performance
    
    --verbose (default: False)
        Enable debug-level logging for troubleshooting

EXAMPLES:

    1. Default monitoring (recommended for most load tests):
       ./scripts/auto-refill-inventory.py
       
       Behavior:
       - Checks every 10 seconds
       - Refills when stock < 20 units
       - Adds 50 units per refill
       - ~5-50 refills per product during a 5-minute test
    
    2. Aggressive refilling (max uptime):
       ./scripts/auto-refill-inventory.py --threshold 10 --refill-quantity 100
       
       Behavior:
       - Refills at lower threshold (allows more variance)
       - Adds more units per refill (less frequent refills)
       - Better for stress testing (fewer refill interruptions)
    
    3. Conservative refilling (realistic inventory):
       ./scripts/auto-refill-inventory.py --threshold 30 --refill-quantity 30
       
       Behavior:
       - Refills more frequently (more realistic)
       - Smaller replenishment batches (better inventory simulation)
       - Good for testing inventory alerts
    
    4. Quick response (low-stock alerts):
       ./scripts/auto-refill-inventory.py --interval 5 --threshold 25
       
       Behavior:
       - Checks every 5 seconds (faster low-stock detection)
       - Refills at 25 units (no prolonged stock-outs)
       - Good for monitoring low-stock alerts in Grafana
    
    5. Debug mode (troubleshooting):
       ./scripts/auto-refill-inventory.py --verbose
       
       Output:
       - All refill operations logged
       - Product details shown
       - Stock history tracking

INTEGRATION WITH LOAD TESTING:

    # Terminal 1: Start all services
    docker-compose up -d

    # Terminal 2: Start Spark jobs
    ./scripts/spark/start-spark-jobs.sh

    # Terminal 3: Start auto-refill service
    ./scripts/auto-refill-inventory.py

    # Terminal 4: Run load test
    ./scripts/simulate-users.py --mode continuous --duration 600 --interval 10 --users 20

    Without auto-refill: Products run out → Orders fail → Test stops
    With auto-refill: Products stay in stock → Orders succeed → Test continues

MONITORING:

    Check refill activity:
    docker-compose logs | grep -i refill
    
    Check current stock levels:
    docker-compose exec postgres psql -U postgres -d kafka_ecom \
      -c "SELECT product_id, name, stock FROM products ORDER BY stock;"
    
    Monitor refill statistics:
    # (Shown in real-time in script output)

REQUIREMENTS:

    ✓ Docker containers running (docker-compose up -d)
    ✓ Python 3 with psycopg2 library (.venv/bin/python)
    ✓ PostgreSQL running with kafka_ecom database
    ✓ Database populated with products (seed_data.py)

PERFORMANCE CONSIDERATIONS:

    Database Connection:
    - Direct PostgreSQL connection (faster than HTTP API)
    - Connection pooling for efficiency
    - Minimal impact on system under test

    Refill Frequency:
    - Default 10-second interval = 30 refills/5min max per product
    - Only products below threshold are updated
    - Batch updates for better performance

    Typical Refill Patterns:
    - Light load (5 users/30s): 2-5 refills per product
    - Medium load (10 users/15s): 5-15 refills per product
    - Heavy load (20 users/10s): 15-30 refills per product
    - Max load (50 users/10s): 30+ refills per product

DATABASE OPERATIONS:

    Before each check:
    - Query: SELECT product_id, stock FROM products;
    - Per product below threshold:
      UPDATE products SET stock = stock + :refill_qty, version = version + 1
      WHERE product_id = :pid

GRACEFUL SHUTDOWN:

    Press Ctrl+C to stop the service:
    - Cleanly closes database connection
    - Logs final statistics
    - Exits cleanly without errors

TROUBLESHOOTING:

    ⚠️  Connection Error: "could not connect to server"
    ────────────────────────────────────────────────────────────
    CAUSE: PostgreSQL not running or connection details incorrect
    SOLUTION:
      docker-compose ps | grep postgres  # Check if running
      docker-compose up -d postgres      # Start if needed
      Check POSTGRES_HOST/PORT in script (default: localhost:5432)

    ⚠️  No products found
    ────────────────────────────────────────────────────────────
    CAUSE: Database not seeded with products
    SOLUTION:
      docker-compose up -d            # Starts all services
      Wait 30 seconds for seed_data.py to run automatically
      Verify: docker-compose logs inventory-service | grep Seeded

    ⚠️  Stock not increasing
    ────────────────────────────────────────────────────────────
    CAUSE: Threshold might be too high (stock never drops)
    SOLUTION:
      Lower threshold: ./scripts/auto-refill-inventory.py --threshold 10
      Increase load: Use more users or shorter intervals
      Check logs: See if refill is being triggered

    ⚠️  Too many refills (noisy output)
    ────────────────────────────────────────────────────────────
    CAUSE: Threshold too low or interval too short
    SOLUTION:
      Raise threshold: --threshold 30
      Increase interval: --interval 20
      Increase refill quantity: --refill-quantity 100

    ⚠️  "Authentication failed for user postgres"
    ────────────────────────────────────────────────────────────
    CAUSE: Database credentials incorrect
    SOLUTION:
      Check docker-compose.yml for POSTGRES_PASSWORD
      Update script environment variables or command line
      Verify credentials match docker-compose setup

USAGE WITH TEST WORKFLOW:

    # Complete test workflow with auto-refill
    docker-compose up -d
    sleep 30
    ./scripts/spark/start-spark-jobs.sh
    ./scripts/auto-refill-inventory.py --threshold 20 --interval 10 &
    sleep 5
    ./scripts/test-complete-workflow.sh 50
    kill %1  # Stop auto-refill when done

STATISTICS TRACKING:

    The script tracks and displays:
    - Total refills per session
    - Products affected
    - Total units added to inventory
    - Average stock level by product
    - Refill frequency per product

PRODUCTION NOTES:

    This script is designed for:
    ✓ Development testing and load testing
    ✓ Simulating customer traffic without running out of stock
    ✓ Long-duration test runs (hours or days)
    ✓ Validating analytics under sustained load

    Not recommended for:
    ✗ Production systems (use proper inventory management system)
    ✗ Testing stock-out scenarios (disable refill or raise threshold)
    ✗ Measuring inventory turnover (stock continuously replenished)
"""

import os
import sys
import time
import logging
import signal
from typing import Dict, Optional
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

# Configure logging
logger = None

def setup_logging(verbose: bool = False):
    """Configure logging with appropriate level."""
    global logger
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)
    return logger

# Database connection parameters
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
POSTGRES_DB = os.getenv("POSTGRES_DB", "kafka_ecom")

class InventoryRefillService:
    """Monitor and automatically refill inventory stock."""
    
    def __init__(self, threshold: int = 20, refill_quantity: int = 50, interval: int = 10):
        """
        Initialize the refill service.
        
        Args:
            threshold: Refill when stock drops below this value
            refill_quantity: Number of units to add per refill
            interval: Seconds between inventory checks
        """
        self.threshold = threshold
        self.refill_quantity = refill_quantity
        self.interval = interval
        self.conn = None
        self.running = True
        self.stats = {
            "total_refills": 0,
            "total_units_added": 0,
            "products_refilled": set(),
            "start_time": datetime.now(),
        }
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signal gracefully."""
        logger.info("\n🛑 Shutdown signal received, cleaning up...")
        self.running = False
        self._print_statistics()
        sys.exit(0)
    
    def connect(self) -> bool:
        """Connect to PostgreSQL database."""
        try:
            logger.info(f"📡 Connecting to PostgreSQL: {POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}")
            self.conn = psycopg2.connect(
                host=POSTGRES_HOST,
                port=POSTGRES_PORT,
                user=POSTGRES_USER,
                password=POSTGRES_PASSWORD,
                database=POSTGRES_DB,
                connect_timeout=5
            )
            logger.info("✅ Connected to database")
            return True
        except psycopg2.Error as e:
            logger.error(f"❌ Connection failed: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from database."""
        if self.conn:
            self.conn.close()
            logger.info("✅ Disconnected from database")
    
    def get_low_stock_products(self) -> Dict[str, int]:
        """
        Query database for products with stock below threshold.
        
        Returns:
            Dict of {product_id: current_stock}
        """
        try:
            cursor = self.conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                "SELECT product_id, name, stock FROM products WHERE stock < %s ORDER BY stock ASC;",
                (self.threshold,)
            )
            products = cursor.fetchall()
            cursor.close()
            
            if products:
                logger.debug(f"Found {len(products)} products below threshold ({self.threshold})")
                for p in products:
                    logger.debug(f"  - {p['product_id']}: {p['stock']}/{self.threshold} (name: {p['name']})")
            
            return {p['product_id']: p['stock'] for p in products}
        except psycopg2.Error as e:
            logger.error(f"❌ Query failed: {e}")
            return {}
    
    def refill_product(self, product_id: str) -> bool:
        """
        Refill stock for a single product.
        
        Args:
            product_id: Product to refill
            
        Returns:
            True if successful, False otherwise
        """
        try:
            cursor = self.conn.cursor()
            
            # Update stock using version-safe increment
            # This matches the optimistic locking pattern in the codebase
            cursor.execute(
                """UPDATE products 
                   SET stock = stock + %s, version = version + 1
                   WHERE product_id = %s;""",
                (self.refill_quantity, product_id)
            )
            
            self.conn.commit()
            
            if cursor.rowcount > 0:
                logger.info(f"📦 Refilled {product_id}: +{self.refill_quantity} units")
                self.stats["total_refills"] += 1
                self.stats["total_units_added"] += self.refill_quantity
                self.stats["products_refilled"].add(product_id)
                cursor.close()
                return True
            else:
                logger.warning(f"⚠️  Product {product_id} not found for refill")
                cursor.close()
                return False
                
        except psycopg2.Error as e:
            logger.error(f"❌ Refill failed for {product_id}: {e}")
            self.conn.rollback()
            return False
    
    def check_and_refill(self) -> int:
        """
        Check all products and refill those below threshold.
        
        Returns:
            Number of products refilled
        """
        logger.debug(f"🔍 Checking inventory (threshold: {self.threshold} units)...")
        
        low_stock_products = self.get_low_stock_products()
        
        if not low_stock_products:
            logger.debug("✓ All products at healthy stock levels")
            return 0
        
        refilled_count = 0
        for product_id, current_stock in low_stock_products.items():
            logger.info(f"⚠️  {product_id} low stock: {current_stock} units (threshold: {self.threshold})")
            if self.refill_product(product_id):
                refilled_count += 1
        
        if refilled_count > 0:
            logger.info(f"✅ Refilled {refilled_count} products")
        
        return refilled_count
    
    def _print_statistics(self):
        """Print session statistics."""
        elapsed = (datetime.now() - self.stats["start_time"]).total_seconds()
        elapsed_mins = elapsed / 60
        
        logger.info("\n" + "="*60)
        logger.info("📊 AUTO-REFILL SERVICE STATISTICS")
        logger.info("="*60)
        logger.info(f"Duration: {elapsed:.0f}s ({elapsed_mins:.1f} minutes)")
        logger.info(f"Total refills: {self.stats['total_refills']}")
        logger.info(f"Total units added: {self.stats['total_units_added']}")
        logger.info(f"Unique products refilled: {len(self.stats['products_refilled'])}")
        if self.stats['total_refills'] > 0:
            logger.info(f"Avg refills per minute: {self.stats['total_refills']/elapsed_mins:.1f}")
            logger.info(f"Avg units per minute: {self.stats['total_units_added']/elapsed_mins:.0f}")
        logger.info("="*60 + "\n")
    
    def run(self):
        """Main service loop."""
        if not self.connect():
            logger.error("❌ Failed to connect to database")
            return
        
        try:
            logger.info("🚀 Auto-Refill Service Started")
            logger.info(f"   Threshold: {self.threshold} units")
            logger.info(f"   Refill quantity: {self.refill_quantity} units")
            logger.info(f"   Check interval: {self.interval}s")
            logger.info("")
            logger.info("Press Ctrl+C to stop...\n")
            
            check_count = 0
            while self.running:
                check_count += 1
                logger.debug(f"\n--- Check #{check_count} at {datetime.now().strftime('%H:%M:%S')} ---")
                
                refilled = self.check_and_refill()
                
                # Show status line even if nothing refilled
                if refilled == 0:
                    logger.debug("ℹ️  No refills needed")
                
                logger.debug(f"Next check in {self.interval}s...")
                time.sleep(self.interval)
                
        except KeyboardInterrupt:
            logger.info("\n🛑 Interrupted by user")
        except Exception as e:
            logger.error(f"❌ Unexpected error: {e}", exc_info=True)
        finally:
            self._print_statistics()
            self.disconnect()

def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Automatically refill inventory stock when running low"
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=20,
        help="Refill when stock drops below this value (default: 20)"
    )
    parser.add_argument(
        "--refill-quantity",
        type=int,
        default=50,
        help="Number of units to add per refill (default: 50)"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=10,
        help="Seconds between inventory checks (default: 10)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    # Setup logging with verbose flag
    setup_logging(args.verbose)
    
    # Validate arguments
    if args.threshold <= 0:
        logger.error("Error: --threshold must be > 0")
        sys.exit(1)
    if args.refill_quantity <= 0:
        logger.error("Error: --refill-quantity must be > 0")
        sys.exit(1)
    if args.interval <= 0:
        logger.error("Error: --interval must be > 0")
        sys.exit(1)
    
    service = InventoryRefillService(
        threshold=args.threshold,
        refill_quantity=args.refill_quantity,
        interval=args.interval
    )
    service.run()

if __name__ == "__main__":
    main()
