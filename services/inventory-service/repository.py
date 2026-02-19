import logging
from typing import Optional
from uuid import uuid4

from sqlalchemy import and_
from sqlalchemy.orm import Session

from models import Product, StockReservation

logger = logging.getLogger(__name__)


class InventoryRepository:
    """Repository for inventory operations with optimistic locking."""

    MAX_RETRIES = 3

    def __init__(self, db: Session):
        """Initialize with database session."""
        self.db = db

    def create_product(self, name: str, description: str, price: float, stock: int) -> Product:
        """Create a new product."""
        product_id = f"PROD-{uuid4().hex[:12].upper()}"
        product = Product(
            product_id=product_id,
            name=name,
            description=description,
            price=price,
            stock=stock,
        )
        self.db.add(product)
        self.db.flush()
        logger.info(f"Created product {product_id}: {name}, stock: {stock}")
        return product

    def get_product(self, product_id: str) -> Optional[Product]:
        """Get product by ID."""
        return self.db.query(Product).filter(Product.product_id == product_id).first()

    def reserve_stock(self, order_id: str, product_id: str, quantity: int) -> bool:
        """
        Reserve stock for an order with optimistic locking.
        Returns True if successful, False if concurrent conflict or insufficient stock.
        """
        for attempt in range(self.MAX_RETRIES):
            product = self.get_product(product_id)

            if not product:
                logger.error(f"Product {product_id} not found")
                return False

            if product.stock < quantity:
                logger.error(f"Insufficient stock for product {product_id}: need {quantity}, have {product.stock}")
                return False

            current_version = product.version

            # Try to update with optimistic lock
            updated = self.db.query(Product).filter(
                and_(
                    Product.product_id == product_id,
                    Product.version == current_version,
                )
            ).update({Product.stock: Product.stock - quantity, Product.version: current_version + 1})

            if updated == 0:
                # Concurrent conflict
                if attempt < self.MAX_RETRIES - 1:
                    logger.warning(f"Concurrent conflict for product {product_id}, retry {attempt + 1}/{self.MAX_RETRIES}")
                    continue
                else:
                    logger.error(f"Failed to reserve stock after {self.MAX_RETRIES} retries")
                    return False

            # Record reservation
            reservation = StockReservation(
                order_id=order_id,
                product_id=product_id,
                quantity=quantity,
            )
            self.db.add(reservation)
            self.db.flush()
            logger.info(f"Reserved {quantity} units of {product_id} for order {order_id}")
            return True

        return False

    def release_stock(self, product_id: str, quantity: int) -> bool:
        """Release reserved stock (for cancelled orders)."""
        product = self.get_product(product_id)

        if not product:
            logger.error(f"Product {product_id} not found")
            return False

        product.stock += quantity
        product.version += 1
        self.db.flush()
        logger.info(f"Released {quantity} units of {product_id}")
        return True

    def get_stock_level(self, product_id: str) -> Optional[int]:
        """Get current stock level for a product."""
        product = self.get_product(product_id)
        return product.stock if product else None
