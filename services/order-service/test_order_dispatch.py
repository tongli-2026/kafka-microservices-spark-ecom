"""A failed saga attempt must not poison the session used on retry."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared"))

from main import handle_order_event


class OrderDispatchTest(unittest.TestCase):
    def test_failure_rolls_back_and_closes_before_retry(self):
        sessions = [MagicMock(), MagicMock()]
        event = SimpleNamespace(event_type="inventory.reserved")
        with patch("saga_handler.SagaHandler") as saga_class:
            saga_class.return_value.handle_inventory_reserved.side_effect = [
                RuntimeError("database error"), None,
            ]
            with self.assertRaisesRegex(RuntimeError, "database error"):
                handle_order_event(event, lambda: sessions[0])
            handle_order_event(event, lambda: sessions[1])

        sessions[0].rollback.assert_called_once_with()
        sessions[0].close.assert_called_once_with()
        sessions[1].rollback.assert_not_called()
        sessions[1].close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
