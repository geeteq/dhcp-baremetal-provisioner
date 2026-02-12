"""
Simple Redis queue wrapper.
Uses Redis lists for queue operations.
Supports authentication and TLS encryption.
"""
import json
import redis
import ssl
from typing import Optional, Dict, Any


class Queue:
    """Simple Redis-based queue with authentication support."""

    def __init__(self, host='localhost', port=6379, db=0, password=None,
                 use_tls=False, tls_cert=None, tls_key=None, tls_ca=None):
        """
        Initialize Redis connection with optional authentication and TLS.

        Args:
            host: Redis host
            port: Redis port
            db: Redis database number
            password: Redis password (optional)
            use_tls: Enable TLS encryption
            tls_cert: Client certificate path (for mTLS)
            tls_key: Client key path (for mTLS)
            tls_ca: CA certificate path
        """
        connection_kwargs = {
            'host': host,
            'port': port,
            'db': db,
            'decode_responses': True
        }

        # Add password if provided
        if password:
            connection_kwargs['password'] = password

        # Add TLS if enabled
        if use_tls:
            ssl_context = ssl.create_default_context()
            if tls_ca:
                ssl_context.load_verify_locations(cafile=tls_ca)
            if tls_cert and tls_key:
                ssl_context.load_cert_chain(certfile=tls_cert, keyfile=tls_key)

            connection_kwargs['ssl'] = True
            connection_kwargs['ssl_cert_reqs'] = ssl.CERT_REQUIRED if tls_ca else ssl.CERT_NONE
            if tls_ca:
                connection_kwargs['ssl_ca_certs'] = tls_ca
            if tls_cert:
                connection_kwargs['ssl_certfile'] = tls_cert
            if tls_key:
                connection_kwargs['ssl_keyfile'] = tls_key

        self.client = redis.Redis(**connection_kwargs)

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
