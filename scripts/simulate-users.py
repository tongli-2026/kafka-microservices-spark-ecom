#!/usr/bin/env python3
"""
Simulate real e-commerce user behavior:
- Browse products (view inventory)
- Add items to cart
- Checkout (create order)
- Complete payment
- Trigger notifications
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

# Sample products (IDs and prices)
PRODUCTS = {
    "PROD001": {"name": "Laptop", "price": 999.99, "quantity": 50},
    "PROD002": {"name": "Mouse", "price": 29.99, "quantity": 200},
    "PROD003": {"name": "Keyboard", "price": 79.99, "quantity": 150},
    "PROD004": {"name": "Monitor", "price": 299.99, "quantity": 30},
    "PROD005": {"name": "USB-C Cable", "price": 19.99, "quantity": 500},
}

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
                f"{INVENTORY_SERVICE}/inventory/products",
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
            response = self.session.post(
                f"{CART_SERVICE}/cart/{self.user_id}/items",
                json={
                    "product_id": product_id,
                    "quantity": quantity
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
        """Step 4: Checkout and create order."""
        self.log("💳 Checking out...")
        
        try:
            # Calculate total
            items = [
                {
                    "product_id": product_id,
                    "quantity": quantity,
                    "price": PRODUCTS.get(product_id, {}).get("price", 0)
                }
                for product_id, quantity in self.cart.items()
            ]
            total_amount = sum(
                item["price"] * item["quantity"] for item in items
            )
            
            response = self.session.post(
                f"{ORDER_SERVICE}/orders",
                json={
                    "user_id": self.user_id,
                    "items": items,
                    "total_amount": total_amount,
                    "shipping_address": f"{self.user_id}@example.com",
                    "email": f"{self.user_id}@example.com"
                },
                timeout=5
            )
            
            if response.status_code in [200, 201]:
                order = response.json()
                self.order_id = order.get("order_id", "unknown")
                self.log(f"✅ Order created: {self.order_id}")
                return order
            else:
                self.log(f"❌ Checkout failed (HTTP {response.status_code})", "error")
                return None
        except Exception as e:
            self.log(f"❌ Error during checkout: {e}", "error")
            return None
    
    def complete_payment(self):
        """Step 5: Complete payment."""
        if not self.order_id:
            self.log("❌ No order to pay for", "error")
            return False
        
        self.log("💰 Processing payment...")
        
        try:
            response = self.session.post(
                f"{PAYMENT_SERVICE}/payments",
                json={
                    "order_id": self.order_id,
                    "amount": random.uniform(50, 2000),
                    "currency": "USD",
                    "payment_method": "credit_card"
                },
                timeout=5
            )
            
            if response.status_code in [200, 201]:
                payment = response.json()
                self.log(f"✅ Payment successful: {payment.get('transaction_id', 'unknown')}")
                return True
            else:
                self.log(f"❌ Payment failed (HTTP {response.status_code})", "error")
                return False
        except Exception as e:
            self.log(f"❌ Error processing payment: {e}", "error")
            return False
    
    def run_complete_journey(self):
        """Execute complete user journey: browse → add → checkout → pay."""
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
    
    def __init__(self, num_users: int = 5):
        self.num_users = num_users
        self.users = [UserSimulator(f"user_{i:03d}") for i in range(num_users)]
    
    def simulate_wave(self):
        """Simulate a wave of users (all concurrently for ~5 seconds)."""
        logger.info(f"🌊 Simulating {self.num_users} concurrent users...")
        
        for i, user in enumerate(self.users):
            # Start each user with slight delay
            user.run_complete_journey()
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

def main():
    import argparse
    
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
    
    args = parser.parse_args()
    
    logger.info("🎬 E-Commerce User Simulator")
    logger.info(f"   Mode: {args.mode}")
    logger.info(f"   Users: {args.users}")
    if args.mode == "continuous":
        logger.info(f"   Duration: {args.duration}s")
        logger.info(f"   Wave interval: {args.interval}s")
    logger.info("")
    
    simulator = LoadSimulator(num_users=args.users)
    
    if args.mode == "single":
        # Single user journey
        user = UserSimulator("test_user_001")
        user.run_complete_journey()
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
