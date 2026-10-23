"""Serialize SMTP delivery for each source event using a database row lock."""

import hashlib

from sqlalchemy import func, text
from sqlalchemy.exc import SQLAlchemyError

from models import NotificationDelivery
from kafka_client import RetryableProcessingError


class NotificationDeliveryService:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    def send(self, event, email_sender, recipient, subject, body):
        """Return True if sent now, None if this notification was already sent.

        The row lock spans SMTP delivery so another live consumer cannot send
        concurrently. A process death rolls back an unfinished attempt; SMTP
        acceptance before that death remains inherently ambiguous.
        """
        identity = f"{event.event_id}:{event.event_type}:email"
        delivery_id = hashlib.sha256(identity.encode()).hexdigest()
        failed = False
        try:
            with self.session_factory.begin() as db:
                db.execute(text("""
                    INSERT INTO notification_deliveries
                        (id, source_event_id, notification_type, channel)
                    VALUES (:id, :event_id, :event_type, 'email')
                    ON CONFLICT (id) DO NOTHING
                """), {"id": delivery_id, "event_id": event.event_id,
                       "event_type": event.event_type})
                row = db.query(NotificationDelivery).filter_by(id=delivery_id).with_for_update().one()
                if row.status == "SENT":
                    return None
                row.attempts += 1
                row.last_error = None
                try:
                    accepted = email_sender.send_email(recipient, subject, body)
                except Exception as error:
                    accepted = False
                    row.last_error = str(error)[:4000]
                if accepted:
                    row.status = "SENT"
                    row.sent_at = func.now()
                    row.last_error = None
                else:
                    row.status = "FAILED"
                    row.last_error = row.last_error or "SMTP sender returned False"
                    failed = True
        except SQLAlchemyError as error:
            raise RetryableProcessingError("Notification database unavailable") from error
        if failed:
            raise RetryableProcessingError(f"SMTP delivery failed for {delivery_id}")
        return True
