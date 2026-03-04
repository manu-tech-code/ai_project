"""
RabbitMQ service — async AMQP message publishing and consuming via aio-pika.

Exchange layout:
  alm.direct (direct, durable)
    -> alm.analyze, alm.map, alm.detect, alm.plan, alm.transform, alm.validate, alm.learn

  alm.dlq (fanout, durable)
    -> alm.dead-letter  (messages after max 3 retries)

Message schema:
  {
    "message_id": "uuid",
    "job_id": "uuid",
    "stage": "analyze|map|detect|plan|transform|validate|learn",
    "timestamp": "ISO8601",
    "retry_count": 0,
    "payload": {}
  }
"""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

import aio_pika
import aio_pika.abc

from app.core.config import settings

logger = logging.getLogger("alm.queue.rabbitmq")

EXCHANGE_NAME = "alm.direct"
DLQ_EXCHANGE_NAME = "alm.dlq"
STAGE_QUEUES = ["analyze", "map", "detect", "plan", "transform", "validate", "learn"]
MAX_RETRIES = 3


class RabbitMQService:
    """
    Async RabbitMQ publisher and consumer using aio-pika.

    Manages connection lifecycle: connect on startup, close on shutdown.
    Falls back to in-process no-op mode when RabbitMQ is not available.
    """

    def __init__(self) -> None:
        self._connection: aio_pika.RobustConnection | None = None
        self._channel: aio_pika.abc.AbstractChannel | None = None
        self._exchange: aio_pika.abc.AbstractExchange | None = None
        self._dlq_exchange: aio_pika.abc.AbstractExchange | None = None
        self._available: bool = False

    async def connect(self) -> None:
        """Establish a robust connection to RabbitMQ and declare topology."""
        try:
            self._connection = await aio_pika.connect_robust(
                settings.get_effective_rabbitmq_url(),
                timeout=10,
            )
            self._channel = await self._connection.channel()
            await self._channel.set_qos(prefetch_count=1)

            # Declare main direct exchange
            self._exchange = await self._channel.declare_exchange(
                EXCHANGE_NAME,
                aio_pika.ExchangeType.DIRECT,
                durable=True,
            )

            # Declare DLQ fanout exchange
            self._dlq_exchange = await self._channel.declare_exchange(
                DLQ_EXCHANGE_NAME,
                aio_pika.ExchangeType.FANOUT,
                durable=True,
            )

            # Declare dead-letter queue bound to DLQ exchange
            dlq = await self._channel.declare_queue(
                "alm.dead-letter",
                durable=True,
                arguments={"x-message-ttl": 7 * 24 * 60 * 60 * 1000},  # 7 days
            )
            await dlq.bind(self._dlq_exchange)

            # Declare per-stage queues bound to alm.direct with matching routing key
            for stage in STAGE_QUEUES:
                queue = await self._channel.declare_queue(
                    f"alm.{stage}",
                    durable=True,
                    arguments={
                        "x-dead-letter-exchange": DLQ_EXCHANGE_NAME,
                        "x-message-ttl": 24 * 60 * 60 * 1000,  # 24 hours
                    },
                )
                await queue.bind(self._exchange, routing_key=stage)

            self._available = True
            logger.info("Connected to RabbitMQ and declared ALM topology.")
        except Exception as exc:
            logger.warning(
                "RabbitMQ not available (%s). Running in in-process mode.", exc
            )
            self._available = False

    async def close(self) -> None:
        """Close connection gracefully."""
        if self._connection:
            try:
                await self._connection.close()
                logger.info("RabbitMQ connection closed.")
            except Exception as exc:
                logger.warning("Error closing RabbitMQ connection: %s", exc)

    async def publish(self, job_id: UUID, stage: str, payload: dict | None = None) -> None:
        """
        Publish a job stage message to the alm.direct exchange.

        Args:
            job_id: The job to process.
            stage: One of the STAGE_QUEUES values.
            payload: Optional additional data for the consumer.
        """
        message_body = {
            "message_id": str(uuid4()),
            "job_id": str(job_id),
            "stage": stage,
            "timestamp": datetime.now(UTC).isoformat(),
            "retry_count": 0,
            "payload": payload or {},
        }

        if not self._available or self._exchange is None:
            logger.info(
                "[%s] RabbitMQ unavailable. Would publish to stage '%s': %s",
                job_id, stage, message_body,
            )
            return

        try:
            body = json.dumps(message_body).encode("utf-8")
            message = aio_pika.Message(
                body=body,
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                message_id=message_body["message_id"],
            )
            await self._exchange.publish(message, routing_key=stage)
            logger.debug("[%s] Published message to stage '%s'.", job_id, stage)
        except Exception as exc:
            logger.error("[%s] Failed to publish to stage '%s': %s", job_id, stage, exc)
            raise

    async def consume(
        self,
        stage: str,
        handler: Callable[[dict], Awaitable[None]],
    ) -> None:
        """
        Start consuming messages from the given stage queue.

        Args:
            stage: Which stage queue to consume.
            handler: Async callable that receives the message body dict.
        """
        if not self._available or self._channel is None:
            logger.warning(
                "RabbitMQ not available. Cannot start consumer for stage '%s'.", stage
            )
            return

        queue_name = f"alm.{stage}"
        try:
            queue = await self._channel.get_queue(queue_name)
        except Exception:
            queue = await self._channel.declare_queue(queue_name, durable=True)

        async def _on_message(message: aio_pika.abc.AbstractIncomingMessage) -> None:
            async with message.process(requeue=False):
                try:
                    body = json.loads(message.body.decode("utf-8"))
                    retry_count = body.get("retry_count", 0)

                    await handler(body)
                    logger.debug(
                        "Processed message for stage '%s', job=%s.",
                        stage, body.get("job_id"),
                    )
                except Exception as exc:
                    logger.error(
                        "Error processing message for stage '%s': %s", stage, exc
                    )
                    retry_count = body.get("retry_count", 0) + 1  # type: ignore[assignment]
                    if retry_count < MAX_RETRIES:
                        # Re-publish with incremented retry_count
                        body["retry_count"] = retry_count  # type: ignore[index]
                        await self.publish(
                            UUID(body["job_id"]),  # type: ignore[index]
                            stage,
                            payload=body.get("payload"),  # type: ignore[index]
                        )
                    else:
                        # Route to DLQ
                        if self._dlq_exchange is not None:
                            try:
                                dlq_msg = aio_pika.Message(
                                    body=message.body,
                                    content_type="application/json",
                                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                                )
                                await self._dlq_exchange.publish(dlq_msg, routing_key="")
                                logger.warning(
                                    "Message for stage '%s' sent to DLQ after %d retries.",
                                    stage, MAX_RETRIES,
                                )
                            except Exception as dlq_exc:
                                logger.error("Failed to route to DLQ: %s", dlq_exc)

        await queue.consume(_on_message)
        logger.info("Started consuming from queue '%s'.", queue_name)


# ── Module-level singleton ────────────────────────────────────────────────────

_service: RabbitMQService | None = None
_lock = asyncio.Lock()


async def get_rabbitmq_service() -> RabbitMQService:
    """Return the module-level RabbitMQ service singleton, connecting on first call."""
    global _service
    async with _lock:
        if _service is None:
            _service = RabbitMQService()
            await _service.connect()
    return _service
