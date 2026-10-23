"""Offset and delivery tests without a running Kafka broker."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from confluent_kafka import TopicPartition
from events import OrderCreatedEvent
from kafka_client import BaseKafkaConsumer, BaseKafkaProducer, KafkaDeliveryError, RetryableProcessingError


class FakeMessage:
    def __init__(self, value):
        self._value = value

    def value(self):
        return self._value

    def topic(self):
        return "order.created"


class FakeConsumer:
    def __init__(self):
        self.commits = []
        self.on_commit = None

    def commit(self, message, asynchronous):
        assert asynchronous is False
        if self.on_commit:
            self.on_commit()
        self.commits.append(message)
        return [TopicPartition("order.created", 0, 1)]

    def subscribe(self, topics):
        self.topics = topics


class FakeProducer:
    def __init__(self):
        self.messages = []
        self.failure = None

    def publish(self, topic, payload):
        if self.failure:
            raise self.failure
        self.messages.append((topic, payload))


class KafkaConsumerOffsetTest(unittest.TestCase):
    def setUp(self):
        self.kafka = FakeConsumer()
        self.dlq = FakeProducer()
        with patch("kafka_client.Consumer", return_value=self.kafka), patch(
            "kafka_client.BaseKafkaProducer", return_value=self.dlq
        ):
            self.client = BaseKafkaConsumer("unused:9092", "test-group", ["order.created"])
        self.message = FakeMessage(OrderCreatedEvent(
            order_id="order-1", user_id="user-1", items=[], total_amount=0,
            correlation_id="correlation-1",
        ).model_dump_json().encode())

    def test_manual_commit_only_after_handler_returns(self):
        self.assertIs(self.client.config["enable.auto.commit"], False)
        self.assertIs(self.client.config["enable.auto.offset.store"], False)

        def handle(_event):
            self.assertEqual(self.kafka.commits, [])

        self.client._process_message(self.message, handle)
        self.assertEqual(self.kafka.commits, [self.message])
        self.client._process_message(self.message, lambda _event: self.fail("duplicate handled"))
        self.assertEqual(self.kafka.commits, [self.message, self.message])

    def test_handler_failure_commits_only_after_dlq_delivery(self):
        attempts = []

        def fail(_event):
            attempts.append(1)
            self.assertEqual(self.kafka.commits, [])
            raise ValueError("business failure")

        with patch("kafka_client.time.sleep"):
            self.client._process_message(self.message, fail)
        self.assertEqual(len(attempts), 3)
        self.assertEqual(self.dlq.messages[0][0], "dlq.events")
        self.assertEqual(self.dlq.messages[0][1]["retry_count"], 3)
        self.assertEqual(self.kafka.commits, [self.message])

    def test_dlq_failure_keeps_offset_uncommitted(self):
        self.dlq.failure = KafkaDeliveryError("DLQ unavailable")
        with patch("kafka_client.time.sleep"):
            with self.assertRaises(KafkaDeliveryError):
                self.client._process_message(self.message, lambda _event: (_ for _ in ()).throw(ValueError("bad")))
        self.assertEqual(self.kafka.commits, [])

    def test_invalid_json_goes_to_dlq_before_commit(self):
        message = FakeMessage(b"not json")
        self.client._process_message(message, lambda _event: self.fail("handler called"))
        self.assertEqual(self.dlq.messages[0][1]["payload"], "not json")
        self.assertEqual(self.kafka.commits, [message])

    def test_delivery_failure_neither_commits_nor_dead_letters(self):
        with patch("kafka_client.time.sleep"):
            with self.assertRaises(KafkaDeliveryError):
                self.client._process_message(
                    self.message,
                    lambda _event: (_ for _ in ()).throw(KafkaDeliveryError("result unavailable")),
                )
        self.assertEqual(self.kafka.commits, [])
        self.assertEqual(self.dlq.messages, [])

    def test_retryable_business_failure_keeps_offset_uncommitted(self):
        with patch("kafka_client.time.sleep"):
            with self.assertRaises(RetryableProcessingError):
                self.client._process_message(
                    self.message,
                    lambda _event: (_ for _ in ()).throw(RetryableProcessingError("SMTP unavailable")),
                )
        self.assertEqual(self.kafka.commits, [])
        self.assertEqual(self.dlq.messages, [])

    def test_commit_failure_does_not_turn_success_into_dlq(self):
        self.kafka.on_commit = lambda: (_ for _ in ()).throw(RuntimeError("commit failed"))
        handled = []
        with self.assertRaisesRegex(RuntimeError, "commit failed"):
            self.client._process_message(self.message, lambda _event: handled.append(1))
        self.assertEqual(handled, [1])
        self.assertEqual(self.dlq.messages, [])


class KafkaProducerDeliveryTest(unittest.TestCase):
    def test_positive_callback_confirms_delivery(self):
        transport = SimpleNamespace()
        transport.produce = lambda **kwargs: setattr(transport, "callback", kwargs["callback"])

        def flush(timeout):
            transport.callback(None, SimpleNamespace(
                topic=lambda: "order.created", partition=lambda: 0, offset=lambda: 1,
            ))
            return 1  # Another thread's message can still be pending.

        transport.flush = flush
        with patch("kafka_client.Producer", return_value=transport):
            producer = BaseKafkaProducer("unused:9092")
        producer.publish("order.created", {"event_type": "order.created", "event_id": "1"})

    def test_timeout_without_callback_is_failure(self):
        transport = SimpleNamespace()
        transport.produce = lambda **kwargs: None
        transport.flush = lambda timeout: 1
        with patch("kafka_client.Producer", return_value=transport):
            producer = BaseKafkaProducer("unused:9092")
        with self.assertRaises(KafkaDeliveryError):
            producer.publish("order.created", {"event_type": "order.created", "event_id": "1"})

    def test_produce_exception_is_failure(self):
        transport = SimpleNamespace()
        transport.produce = lambda **kwargs: (_ for _ in ()).throw(RuntimeError("broker unavailable"))
        transport.flush = lambda timeout: self.fail("flush must not run after produce fails")
        with patch("kafka_client.Producer", return_value=transport):
            producer = BaseKafkaProducer("unused:9092")
        with self.assertRaisesRegex(KafkaDeliveryError, "broker unavailable"):
            producer.publish("order.created", {"event_type": "order.created", "event_id": "1"})

    def test_callback_failure_is_reported(self):
        transport = SimpleNamespace()
        transport.produce = lambda **kwargs: setattr(transport, "callback", kwargs["callback"])

        def flush(timeout):
            transport.callback(RuntimeError("broker rejected"), object())
            return 0

        transport.flush = flush
        with patch("kafka_client.Producer", return_value=transport):
            producer = BaseKafkaProducer("unused:9092")
        with self.assertRaises(KafkaDeliveryError):
            producer.publish("order.created", {"event_type": "order.created", "event_id": "1"})


if __name__ == "__main__":
    unittest.main()
