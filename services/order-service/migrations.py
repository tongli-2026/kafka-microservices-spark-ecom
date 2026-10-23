"""Add checkout identity without changing legacy order rows."""

from sqlalchemy import text


def migrate_checkout_identity(engine):
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS checkout_id VARCHAR(36)"))
        connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_orders_checkout_id ON orders (checkout_id)"))
