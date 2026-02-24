"""
Simple Redis queue wrapper.
Uses Redis lists for queue operations.
Supports authentication and TLS encryption.
"""
import json
import logging
import ssl
import sys
import redis
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
        self._host = host
        self._port = port
        self._db = db
        self._password = password
        self._use_tls = use_tls
        self._tls_cert = tls_cert
        self._tls_key = tls_key
        self._tls_ca = tls_ca

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

    def ping_verbose(self, logger: logging.Logger) -> None:
        """
        Test Redis connection and exit with detailed diagnostics on failure.

        Logs host, port, TLS config, and auth state before attempting the
        ping. On failure, logs the specific error type and actionable hints,
        then calls sys.exit(1).
        """
        auth_enabled = bool(self._password)
        logger.info(
            f"Connecting to Redis — host={self._host} port={self._port} "
            f"db={self._db} tls={self._use_tls} auth={auth_enabled}"
        )
        if self._use_tls:
            logger.info(
                f"  TLS cert: {self._tls_cert or 'not set'}\n"
                f"  TLS key:  {self._tls_key or 'not set'}\n"
                f"  TLS CA:   {self._tls_ca or 'not set'}"
            )

        try:
            self.client.ping()
        except redis.AuthenticationError as e:
            logger.error(f"Redis authentication failed: {e}")
            logger.error(f"  host:               {self._host}:{self._port}")
            logger.error(f"  REDIS_PASSWORD set: {auth_enabled} / length: {len(self._password) if self._password else 0}")
            if self._password:
                logger.error(f"  password preview:   {self._password[:4]}{'*' * (len(self._password) - 4)}")
            else:
                logger.error("  REDIS_PASSWORD is empty or not set — Redis may require auth")
            logger.error("  Verify REDIS_PASSWORD matches the 'requirepass' value in redis.conf")
            sys.exit(1)
        except redis.ConnectionError as e:
            logger.error(f"Cannot reach Redis at {self._host}:{self._port} — {e}")
            if self._use_tls:
                logger.error(
                    "  TLS is enabled — verify the server is listening for TLS, "
                    "the CA cert is correct, and the client cert/key paths exist"
                )
            sys.exit(1)
        except ssl.SSLError as e:
            logger.error(f"TLS handshake failed connecting to Redis: {e}")
            logger.error(
                f"  cert: {self._tls_cert or 'not set'}  "
                f"key: {self._tls_key or 'not set'}  "
                f"CA: {self._tls_ca or 'not set'}"
            )
            sys.exit(1)
        except Exception as e:
            logger.error(f"Unexpected error connecting to Redis ({type(e).__name__}): {e}")
            sys.exit(1)
