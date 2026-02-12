"""
Simple Redis queue wrapper.
Uses Redis lists for queue operations.
"""
import json
import redis
from typing import Optional, Dict, Any


class Queue:
    """Simple Redis-based queue."""

    def __init__(self, host='localhost', port=6379, db=0):
        """
        Initialize Redis connection.

        Args:
            host: Redis host
            port: Redis port
            db: Redis database number
        """
        self.client = redis.Redis(
            host=host,
            port=port,
            db=db,
            decode_responses=True
        )

    def publish(self, queue_name: str, message: Dict[Any, Any]) -> bool:
        """
        Publish a message to a queue.

        Args:
            queue_name: Name of the queue
            message: Message dictionary (will be JSON encoded)

        Returns:
            True if successful
        """
        try:
            message_json = json.dumps(message)
            self.client.rpush(queue_name, message_json)
            return True
        except Exception as e:
            print(f"Failed to publish message: {e}")
            return False

    def consume(self, queue_name: str, timeout: int = 0) -> Optional[Dict[Any, Any]]:
        """
        Consume a message from a queue (blocking).

        Args:
            queue_name: Name of the queue
            timeout: Timeout in seconds (0 = block indefinitely)

        Returns:
            Message dictionary or None if timeout
        """
        try:
            result = self.client.blpop(queue_name, timeout=timeout)
            if result:
                _, message_json = result
                return json.loads(message_json)
            return None
        except Exception as e:
            print(f"Failed to consume message: {e}")
            return None

    def peek(self, queue_name: str) -> Optional[Dict[Any, Any]]:
        """
        Peek at the next message without removing it.

        Args:
            queue_name: Name of the queue

        Returns:
            Message dictionary or None if queue is empty
        """
        try:
            message_json = self.client.lindex(queue_name, 0)
            if message_json:
                return json.loads(message_json)
            return None
        except Exception as e:
            print(f"Failed to peek message: {e}")
            return None

    def length(self, queue_name: str) -> int:
        """
        Get the length of a queue.

        Args:
            queue_name: Name of the queue

        Returns:
            Number of messages in the queue
        """
        try:
            return self.client.llen(queue_name)
        except Exception as e:
            print(f"Failed to get queue length: {e}")
            return 0

    def ping(self) -> bool:
        """
        Test Redis connection.

        Returns:
            True if Redis is reachable
        """
        try:
            return self.client.ping()
        except Exception:
            return False
