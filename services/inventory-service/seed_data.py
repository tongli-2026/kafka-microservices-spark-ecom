import logging
import random
import string

from sqlalchemy.orm import Session

from models import Product
from repository import InventoryRepository

logger = logging.getLogger(__name__)

# Sample product templates
SAMPLE_PRODUCTS = [
    ("Wireless Headphones", "Premium noise-cancelling headphones", 149.99),
    ("USB-C Cable", "Durable 6ft USB-C charging cable", 12.99),
    ("Phone Case", "Protective phone case with shock absorption", 19.99),
    ("Screen Protector", "Tempered glass screen protector", 9.99),
    ("Power Bank", "30000mAh portable power bank", 49.99),
    ("Laptop Stand", "Adjustable aluminum laptop stand", 39.99),
    ("Mechanical Keyboard", "RGB mechanical gaming keyboard", 99.99),
    ("Mouse Pad", "Large extended mouse pad with non-slip base", 24.99),
    ("USB Hub", "4-port USB 3.0 hub", 29.99),
    ("Monitor Stand", "Adjustable dual monitor stand", 89.99),
    ("Desk Lamp", "LED desk lamp with adjustable brightness", 34.99),
    ("Cable Organizer", "Desktop cable management system", 14.99),
    ("Webcam", "1080p HD webcam with microphone", 59.99),
    ("Microphone", "USB condenser microphone for streaming", 79.99),
    ("HDMI Cable", "4K HDMI 2.1 cable", 15.99),
    ("SD Card 128GB", "128GB microSD card class 10", 34.99),
    ("External SSD 1TB", "1TB portable SSD with USB 3.1", 129.99),
    ("Cooling Pad", "Laptop cooling pad with 5 fans", 44.99),
    ("Keyboard Cover", "Silicone keyboard cover for laptops", 9.99),
    ("Phone Holder", "Universal phone holder for desk", 14.99),
]


def seed_products(db: Session) -> None:
    """Seed database with sample products."""
    logger.info("Seeding products...")
    repo = InventoryRepository(db)

    for name, description, price in SAMPLE_PRODUCTS:
        # Check if product already exists
        existing = repo.get_product(name)
        if existing:
            logger.info(f"Product {name} already exists, skipping")
            continue

        # Random stock between 10 and 100
        stock = random.randint(10, 100)
        repo.create_product(name, description, price, stock)

    db.commit()
    logger.info(f"Seeded {len(SAMPLE_PRODUCTS)} products")
