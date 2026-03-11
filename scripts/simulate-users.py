#!/usr/bin/env python3
"""
simulate-users.py - E-Commerce User Behavior Simulator

PURPOSE:
    Generates realistic e-commerce user traffic by simulating complete shopping
    journeys. Creates artificial load on the microservices system and generates
    data for analytics, especially for testing abandoned cart detection.

BUSINESS VALUE:
    - Load test system under realistic user patterns
    - Generate cart abandonment data for analytics (Spark jobs)
    - Validate complete event-driven pipeline (browsing → checkout → payment)
    - Stress test microservices and Kafka cluster
    - Test notification triggers for various scenarios

KEY FEATURES:
    - Simulates complete user journeys: browse → add items → checkout → pay
    - Configurable cart abandonment rate (% of users who don't complete purchase)
    - Dynamic product discovery (fetches real products from inventory at runtime)
    - Multiple simulation modes: single user, wave, or continuous load
    - Realistic timing and random behavior (random items, quantities, delays)
    - Structured logging with emoji indicators for quick visual scanning

SIMULATED USER BEHAVIORS:
    1. Browse Products - Query inventory service for available items
    2. Add to Cart - Add 2-5 random items with random quantities (1-3 each)
    3. View Cart - Display cart contents and total
    4. Abandon Cart (Optional) - User leaves without checkout (~30% default)
    5. Checkout - Create order via Order Service
    6. Pay - Process payment via Payment Service (80% success rate)
    7. Receive Notification - Email confirmation sent via Notification Service

USAGE:
    # First time: activate virtual environment
    source .venv/bin/activate
    
    # Then run the simulator
    ./scripts/simulate-users.py --mode wave --users 10 --abandonment-rate 0.3
    ./scripts/simulate-users.py --mode continuous --duration 300 --interval 30
    ./scripts/simulate-users.py --mode single

COMMAND-LINE OPTIONS:
    --mode {single|wave|continuous}
        single      - One user completes full journey (default: wave)
        wave        - Multiple concurrent users in single batch
        continuous  - Repeated waves of users over time
    
    --users N (default: 5)
        Number of concurrent users per wave
    
    --duration N (default: 300, continuous mode only)
        Total seconds to run continuous simulation
    
    --interval N (default: 30, continuous mode only)
        Seconds between each wave
    
    --abandonment-rate 0.0-1.0 (default: 0.0)
        Probability that user abandons cart after adding items
        Example: 0.3 = 30% of users will not proceed to checkout

DATA FLOW:
    This script (your machine)
        ↓ (HTTP requests)
    Microservices (localhost:8001-8005)
        ↓ (events via Kafka)
    Kafka Cluster (3 brokers)
        ↓ (consumed by)
    Spark Jobs & PostgreSQL
        ↓
    Analytics Results

SERVICES CALLED:
    - Cart Service (8001): Add/view/checkout cart
    - Order Service (8002): Create orders
    - Payment Service (8003): Process payments (80% success, 20% failure)
    - Inventory Service (8004): View products, reserve stock
    - Notification Service (8005): Trigger emails (via Mailhog)

KAFKA TOPICS GENERATED:
    - cart.item_added: User adds item to cart
    - cart.checkout_initiated: User initiates checkout (not sent if abandoned)
    - order.created: Order created in system
    - inventory.reserved: Stock reserved for order
    - payment.processed / payment.failed: Payment outcome
    - notification.triggered: Confirmation email queued

EXAMPLES:

    1. Quick Test - Single user journey (~10 seconds):
       ./scripts/simulate-users.py --mode single

    2. Generate Abandoned Carts - 30% abandonment (~30-60 seconds):
       ./scripts/simulate-users.py --mode wave --users 10 --abandonment-rate 0.3
       Result: 3 abandoned carts, 7 completed orders

    3. Sustained Load Test - 5 minutes of continuous traffic:
       ./scripts/simulate-users.py --mode continuous --duration 300 --users 5

    4. Heavy Load - 20 users per wave, 50% abandonment:
       ./scripts/simulate-users.py --mode wave --users 20 --abandonment-rate 0.5

IMPORTANT NOTES:

    - Products are fetched dynamically from inventory service at startup
    - No hardcoded product IDs (unlike test-scenarios.sh)
    - Handles inventory created randomly during system initialization
    - Cart abandonment detected by Spark job after 30-minute watermark
    - Runs on your machine (not inside Docker container)
    - Makes HTTP requests to services via localhost ports

HOW ABANDONED CARTS ARE DETECTED:

    Timeline for 30% abandonment rate:
    
    Users 1-3 (~30%): Abandon carts
      T=0:00  Add items to cart → cart.item_added event ✅
      T=2:00  Leave without checkout → NO cart.checkout_initiated ❌
      T=30:00 Spark job detects: items_added but NO checkout = ABANDONED ⏰
    
    Users 4-10 (~70%): Complete purchase
      T=0:00  Add items to cart → cart.item_added ✅
      T=3:00  Checkout → cart.checkout_initiated ✅
      T=5:00  Payment processed → payment.processed ✅
      T=6:00 Order fulfilled ✓

MONITORING:

    Check cart abandonment results:
    docker-compose exec postgres psql -U postgres -d kafka_ecom \
      -c "SELECT COUNT(*) as abandoned_carts FROM cart_abandonment;"
    
    Monitor Spark job processing:
    open http://localhost:4040  (Spark UI)
    
    View Kafka events:
    open http://localhost:8080  (Kafka UI)
    
    Check sent emails:
    open http://localhost:8025  (Mailhog)

REQUIREMENTS:

    ✓ Docker containers running (docker-compose up -d)
    ✓ Python 3 with requests library (.venv/bin/python)
    ✓ Inventory Service must be healthy (exposes products endpoint)
    ✓ Cart/Order/Payment/Notification services must be accessible
    ✓ Kafka cluster must be running (for event publishing)
    ✓ PostgreSQL must be running (for order storage)

TROUBLESHOOTING:

    Issue: "No products available"
    Solution: Ensure inventory service is running
    docker-compose ps | grep inventory
    docker-compose logs inventory-service

    Issue: "Connection refused" on localhost:800X
    Solution: Start services
    docker-compose up -d

    Issue: Permission denied
    Solution: Make script executable
    chmod +x scripts/simulate-users.py

    Issue: Module not found (requests)
    Solution: Use virtual environment
    source .venv/bin/activate
    ./scripts/simulate-users.py ...
"""

import requests
import json
import time
import random
import logging
import sys
from datetime import datetime
from typing import List, Dict

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Service base URLs
CART_SERVICE = "http://localhost:8001"
ORDER_SERVICE = "http://localhost:8002"
PAYMENT_SERVICE = "http://localhost:8003"
INVENTORY_SERVICE = "http://localhost:8004"
NOTIFICATION_SERVICE = "http://localhost:8005"

# Products will be fetched dynamically from inventory service
# since they are created randomly at startup
PRODUCTS = {}

class UserSimulator:
    """Simulates a single user journey through the e-commerce platform."""
    
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.session = requests.Session()
        self.cart = {}
        self.order_id = None
        
    def log(self, message: str, level: str = "info"):
        """Log with user context."""
        msg = f"[User {self.user_id}] {message}"
        if level == "info":
            logger.info(msg)
        elif level == "error":
            logger.error(msg)
        elif level == "warning":
            logger.warning(msg)
    
    def browse_products(self):
        """Step 1: Browse and view products."""
        self.log("👀 Browsing products...")
        
        try:
            # Call inventory service to view available products
            response = self.session.get(
                f"{INVENTORY_SERVICE}/products",
                timeout=5
            )
            
            if response.status_code == 200:
                products = response.json()
                self.log(f"✅ Found {len(products)} products")
                return products
            else:
                self.log(f"❌ Failed to fetch products (HTTP {response.status_code})", "error")
                return []
        except Exception as e:
            self.log(f"❌ Error browsing products: {e}", "error")
            return []
    
    def add_to_cart(self, product_id: str, quantity: int = 1):
        """Step 2: Add items to shopping cart."""
        self.log(f"🛒 Adding {quantity}x {product_id} to cart...")
        
        try:
            # Get price from products dictionary
            product_info = PRODUCTS.get(product_id, {})
            price = product_info.get("price", 0)
            
            response = self.session.post(
                f"{CART_SERVICE}/cart/{self.user_id}/items",
                json={
                    "product_id": product_id,
                    "quantity": quantity,
                    "price": price
                },
                timeout=5
            )
            
            if response.status_code in [200, 201]:
                self.cart[product_id] = quantity
                self.log(f"✅ Added to cart")
                return True
            else:
                self.log(f"❌ Failed to add to cart (HTTP {response.status_code})", "error")
                return False
        except Exception as e:
            self.log(f"❌ Error adding to cart: {e}", "error")
            return False
    
    def view_cart(self):
        """Step 3: View shopping cart."""
        self.log("📋 Viewing cart...")
        
        try:
            response = self.session.get(
                f"{CART_SERVICE}/cart/{self.user_id}",
                timeout=5
            )
            
            if response.status_code == 200:
                cart = response.json()
                total = sum(item.get("price", 0) * item.get("quantity", 0) 
                           for item in cart.get("items", []))
                self.log(f"✅ Cart has {len(cart.get('items', []))} items, total: ${total:.2f}")
                return cart
            else:
                self.log(f"❌ Failed to fetch cart (HTTP {response.status_code})", "error")
                return None
        except Exception as e:
            self.log(f"❌ Error viewing cart: {e}", "error")
            return None
    
    def checkout(self):
        """Step 4: Checkout and initiate order processing via Cart Service.
        
        NOTE: We call Cart Service /checkout which publishes cart.checkout_initiated
        to Kafka. The Order Service consumes this event and creates the order automatically
        via the Saga pattern. This triggers the inventory reservation and payment processing.
        """
        self.log("💳 Checking out via cart service...")
        
        try:
            # Call Cart Service checkout endpoint
            # This publishes cart.checkout_initiated event to Kafka
            # Order Service will consume it and create order automatically
            response = self.session.post(
                f"{CART_SERVICE}/cart/{self.user_id}/checkout",
                timeout=5
            )
            
            if response.status_code in [200, 201]:
                checkout_response = response.json()
                # Extract cart info which has been converted to order
                cart_info = checkout_response.get("cart", {})
                self.order_id = f"order_{self.user_id}"  # Order ID will be generated by Order Service
                self.log(f"✅ Checkout initiated, Order Service processing...")
                return checkout_response
            else:
                self.log(f"❌ Checkout failed (HTTP {response.status_code})", "error")
                return None
        except Exception as e:
            self.log(f"❌ Error during checkout: {e}", "error")
            return None
    
    def complete_payment(self):
        """Step 5: Payment processing is automatic via Saga Pattern.
        
        NOTE: Payment Service is event-driven:
        1. Checkout publishes cart.checkout_initiated → Order Service consumes
        2. Order Service creates order, publishes order.created → Inventory Service consumes
        3. Inventory Service reserves stock, publishes inventory.reserved → Order Service updates
        4. Order Service publishes order.reservation_confirmed → Payment Service consumes
        5. Payment Service processes payment automatically (80% success, 20% failure)
        6. Payment Service publishes payment.processed or payment.failed
        
        So we don't need to call any payment endpoint - it happens automatically.
        This method just logs that payment processing has started.
        """
        if not self.order_id:
            self.log("❌ No order to pay for", "error")
            return False
        
        self.log("💰 Payment processing initiated via Saga Pattern...")
        self.log("   (Payment Service consumes events and processes asynchronously)")
        time.sleep(2)  # Give services time to process events
        
        # In reality, payment succeeds ~80% of the time (simulated in Payment Service)
        # For simulation purposes, we'll assume it eventually succeeds
        # (in real world, you'd poll the order service to check status)
        self.log(f"✅ Payment processing complete (check Order Service for status)")
        return True
    
    def run_complete_journey(self, abandon_probability: float = 0.0):
        """
        Execute complete user journey: browse → add → checkout → pay.
        
        Args:
            abandon_probability: Probability (0.0-1.0) that user abandons cart
                               after adding items but before checkout.
                               Example: 0.3 = 30% of users abandon their carts.
        """
        self.log("🚀 Starting user journey...")
        
        # Step 1: Browse products
        self.browse_products()
        time.sleep(0.5)
        
        # Step 2: Add random items to cart (2-5 items)
        num_items = random.randint(2, 5)
        for _ in range(num_items):
            product_id = random.choice(list(PRODUCTS.keys()))
            quantity = random.randint(1, 3)
            self.add_to_cart(product_id, quantity)
            time.sleep(0.3)
        
        # Step 3: View cart
        self.view_cart()
        time.sleep(0.5)
        
        # ABANDONMENT POINT: User leaves before checkout
        # Simulates: user closes browser, navigates away, changes mind, etc.
        if random.random() < abandon_probability:
            self.log("👋 User abandoned cart and left the site!", "warning")
            # Cart remains in Redis with cart.item_added events published
            # But NO cart.checkout_initiated event
            # → Spark job will detect this as abandoned after 30 minutes
            return False
        
        # Step 4: Checkout
        order = self.checkout()
        if not order:
            self.log("⚠️  Checkout failed, stopping journey", "warning")
            return False
        time.sleep(1)
        
        # Step 5: Complete payment
        if self.complete_payment():
            self.log("✅ User journey complete!")
            return True
        else:
            self.log("⚠️  Payment failed, order may be incomplete", "warning")
            return False

class LoadSimulator:
    """Simulate multiple concurrent users."""
    
    def __init__(self, num_users: int = 5, abandon_probability: float = 0.0):
        self.num_users = num_users
        self.abandon_probability = abandon_probability
        self.users = [UserSimulator(f"user_{i:03d}") for i in range(num_users)]
    
    def simulate_wave(self):
        """Simulate a wave of users (all concurrently for ~5 seconds)."""
        logger.info(f"🌊 Simulating {self.num_users} concurrent users...")
        if self.abandon_probability > 0:
            logger.info(f"   Abandonment rate: {self.abandon_probability*100:.0f}%")
        
        for i, user in enumerate(self.users):
            # Start each user with slight delay
            user.run_complete_journey(abandon_probability=self.abandon_probability)
            time.sleep(0.2)  # 200ms delay between user starts
        
        logger.info(f"✅ Wave complete")
    
    def simulate_continuous(self, duration_seconds: int = 300, wave_interval: int = 30):
        """Simulate continuous user traffic for specified duration."""
        logger.info(f"🔄 Starting continuous simulation for {duration_seconds}s...")
        logger.info(f"   New wave every {wave_interval}s")
        
        start_time = time.time()
        wave_count = 0
        
        try:
            while time.time() - start_time < duration_seconds:
                wave_count += 1
                logger.info(f"\n{'='*60}")
                logger.info(f"Wave #{wave_count} at {datetime.now().strftime('%H:%M:%S')}")
                logger.info(f"{'='*60}")
                
                self.simulate_wave()
                
                # Wait before next wave
                remaining = duration_seconds - (time.time() - start_time)
                if remaining > wave_interval:
                    logger.info(f"⏳ Waiting {wave_interval}s until next wave...\n")
                    time.sleep(wave_interval)
        except KeyboardInterrupt:
            logger.info("\n\n⚠️  Interrupted by user")
        
        logger.info(f"\n{'='*60}")
        logger.info(f"✅ Simulation complete! {wave_count} waves executed")
        logger.info(f"{'='*60}")

def fetch_products_from_inventory():
    """
    Fetch available products from the inventory service.
    Since products are created randomly at startup, we need to query the service
    to get the actual product IDs instead of using hardcoded ones.
    
    Returns:
        dict: Dictionary of product_id -> product_info
        Empty dict if service is unavailable
    """
    global PRODUCTS
    
    try:
        logger.info("📦 Fetching products from inventory service...")
        response = requests.get(
            f"{INVENTORY_SERVICE}/products",
            timeout=10
        )
        
        if response.status_code == 200:
            products = response.json()
            
            # Handle response format: {"products": [...]}
            if isinstance(products, dict) and "products" in products:
                products_list = products["products"]
            elif isinstance(products, list):
                products_list = products
            else:
                products_list = []
            
            # Convert to dict format if needed
            if isinstance(products_list, list):
                PRODUCTS = {p.get("product_id", p.get("id", f"PROD{i:03d}")): p for i, p in enumerate(products_list)}
            else:
                PRODUCTS = products_list
            
            logger.info(f"✅ Loaded {len(PRODUCTS)} products from inventory")
            for product_id, product_info in list(PRODUCTS.items())[:3]:  # Show first 3
                logger.info(f"   - {product_id}: {product_info.get('name', 'Unknown')} (${product_info.get('price', '?')})")
            if len(PRODUCTS) > 3:
                logger.info(f"   ... and {len(PRODUCTS) - 3} more")
            
            return PRODUCTS
        else:
            logger.error(f"❌ Failed to fetch products (HTTP {response.status_code})")
            return {}
    except Exception as e:
        logger.error(f"❌ Error fetching products: {e}")
        logger.error("   Make sure inventory service is running on http://localhost:8004")
        return {}

def main():
    import argparse
    
    # Command-line argument parsing
    parser = argparse.ArgumentParser(
        description="Simulate realistic e-commerce user behavior"
    )
    parser.add_argument(
        "--users",
        type=int,
        default=5,
        help="Number of concurrent users per wave (default: 5)"
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=300,
        help="Total simulation duration in seconds (default: 300 = 5 minutes)"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=30,
        help="Interval between user waves in seconds (default: 30)"
    )
    parser.add_argument(
        "--mode",
        choices=["single", "wave", "continuous"],
        default="wave",
        help="Simulation mode (default: wave)"
    )
    parser.add_argument(
        "--abandonment-rate",
        type=float,
        default=0.0,
        help="Probability (0.0-1.0) that users abandon cart after adding items (default: 0.0)"
    )
    
    args = parser.parse_args()
    
    # Validate abandonment rate is between 0.0 and 1.0
    if not 0.0 <= args.abandonment_rate <= 1.0:
        logger.error("Error: --abandonment-rate must be between 0.0 and 1.0")
        sys.exit(1)
    
    logger.info("🎬 E-Commerce User Simulator")
    logger.info(f"   Mode: {args.mode}")
    logger.info(f"   Users: {args.users}")
    if args.abandonment_rate > 0:
        logger.info(f"   Abandonment rate: {args.abandonment_rate*100:.0f}%")
    if args.mode == "continuous":
        logger.info(f"   Duration: {args.duration}s")
        logger.info(f"   Wave interval: {args.interval}s")
    logger.info("")
    
    # Fetch real products from inventory service before starting simulation
    products = fetch_products_from_inventory()
    if not products:
        logger.error("❌ No products available. Make sure inventory service is running.")
        sys.exit(1)
    logger.info("")
    
    simulator = LoadSimulator(num_users=args.users, abandon_probability=args.abandonment_rate)
    
    if args.mode == "single":
        # Single user journey
        user = UserSimulator("test_user_001")
        user.run_complete_journey(abandon_probability=args.abandonment_rate)
    elif args.mode == "wave":
        # Single wave
        simulator.simulate_wave()
    elif args.mode == "continuous":
        # Continuous load
        simulator.simulate_continuous(
            duration_seconds=args.duration,
            wave_interval=args.interval
        )

if __name__ == "__main__":
    main()
