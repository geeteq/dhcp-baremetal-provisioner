# Redis Security Configuration

## Overview

Secure Redis for production deployment with authentication, network binding, and TLS encryption.

---

## 1. Enable Password Authentication

### Configure Redis Server

Edit Redis configuration file:

**macOS (Homebrew)**:
```bash
nano /opt/homebrew/etc/redis.conf
```

**Linux**:
```bash
sudo nano /etc/redis/redis.conf
```

### Add Authentication

```bash
# Require password for all commands
requirepass YOUR_STRONG_PASSWORD_HERE

# Optional: Rename dangerous commands
rename-command CONFIG ""
rename-command FLUSHDB ""
rename-command FLUSHALL ""
rename-command KEYS ""
```

**Generate Strong Password**:
```bash
# Generate 32-character random password
openssl rand -base64 32
# Example output: Kj8xPq2mNv5tYw7zAb3cDe4fGh6iJk8l
```

### Restart Redis

**macOS**:
```bash
brew services restart redis
```

**Linux**:
```bash
sudo systemctl restart redis
```

### Test Authentication

```bash
# Should fail
redis-cli ping
# Error: NOAUTH Authentication required

# Should succeed
redis-cli -a YOUR_PASSWORD ping
# PONG
```

---

## 2. Network Binding

### Restrict Network Access

Edit `redis.conf`:

```bash
# Option 1: Bind to localhost only (most secure)
bind 127.0.0.1 ::1

# Option 2: Bind to specific interface
bind 10.1.100.5 127.0.0.1

# Option 3: Bind to all interfaces (use with firewall)
bind 0.0.0.0
protected-mode yes
```

### Enable Protected Mode

```bash
# Automatically enabled when binding to 0.0.0.0
protected-mode yes
```

This prevents external connections when no password is set.

---

## 3. TLS/SSL Encryption (Optional but Recommended)

### Generate Certificates

```bash
# Create directory for certs
mkdir -p /opt/redis/tls
cd /opt/redis/tls

# Generate CA certificate
openssl genrsa -out ca-key.pem 4096
openssl req -new -x509 -days 3650 -key ca-key.pem -out ca-cert.pem \
  -subj "/CN=Redis-CA"

# Generate server certificate
openssl genrsa -out redis-key.pem 4096
openssl req -new -key redis-key.pem -out redis.csr \
  -subj "/CN=redis-server"
openssl x509 -req -days 3650 -in redis.csr \
  -CA ca-cert.pem -CAkey ca-key.pem -CAcreateserial \
  -out redis-cert.pem

# Generate client certificate (for workers)
openssl genrsa -out client-key.pem 4096
openssl req -new -key client-key.pem -out client.csr \
  -subj "/CN=redis-client"
openssl x509 -req -days 3650 -in client.csr \
  -CA ca-cert.pem -CAkey ca-key.pem -CAcreateserial \
  -out client-cert.pem

# Set permissions
chmod 600 *-key.pem
chmod 644 *-cert.pem
```

### Configure Redis for TLS

Add to `redis.conf`:

```bash
# Enable TLS
port 0
tls-port 6379
tls-cert-file /opt/redis/tls/redis-cert.pem
tls-key-file /opt/redis/tls/redis-key.pem
tls-ca-cert-file /opt/redis/tls/ca-cert.pem
tls-auth-clients yes
```

### Test TLS Connection

```bash
redis-cli --tls \
  --cert /opt/redis/tls/client-cert.pem \
  --key /opt/redis/tls/client-key.pem \
  --cacert /opt/redis/tls/ca-cert.pem \
  -a YOUR_PASSWORD \
  ping
```

---

## 4. Update Worker Configuration

### Update Environment Variables

Edit `.env`:

```bash
# Redis Authentication
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=YOUR_STRONG_PASSWORD_HERE

# Optional: TLS Configuration
REDIS_USE_TLS=true
REDIS_TLS_CERT=/opt/redis/tls/client-cert.pem
REDIS_TLS_KEY=/opt/redis/tls/client-key.pem
REDIS_TLS_CA=/opt/redis/tls/ca-cert.pem
```

### Update config.py

Add Redis password support:

```python
# Redis Configuration
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))
REDIS_DB = int(os.getenv('REDIS_DB', '0'))
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD')  # Add this
REDIS_USE_TLS = os.getenv('REDIS_USE_TLS', 'false').lower() == 'true'  # Add this

# TLS Configuration (if enabled)
REDIS_TLS_CERT = os.getenv('REDIS_TLS_CERT')
REDIS_TLS_KEY = os.getenv('REDIS_TLS_KEY')
REDIS_TLS_CA = os.getenv('REDIS_TLS_CA')
```

### Update lib/queue.py

Add authentication support:

```python
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
            tls_cert: Client certificate path
            tls_key: Client key path
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
            ssl_context = ssl.create_default_context(
                ssl.Purpose.CLIENT_AUTH,
                cafile=tls_ca
            )
            if tls_cert and tls_key:
                ssl_context.load_cert_chain(
                    certfile=tls_cert,
                    keyfile=tls_key
                )
            connection_kwargs['ssl'] = True
            connection_kwargs['ssl_cert_reqs'] = ssl.CERT_REQUIRED
            connection_kwargs['ssl_ca_certs'] = tls_ca
            connection_kwargs['ssl_certfile'] = tls_cert
            connection_kwargs['ssl_keyfile'] = tls_key

        self.client = redis.Redis(**connection_kwargs)
```

### Update Worker Initialization

Example for discovery worker:

```python
# Initialize Redis queue with authentication
queue = Queue(
    host=config.REDIS_HOST,
    port=config.REDIS_PORT,
    db=config.REDIS_DB,
    password=config.REDIS_PASSWORD,  # Add this
    use_tls=config.REDIS_USE_TLS,    # Add this
    tls_cert=config.REDIS_TLS_CERT,  # Add this
    tls_key=config.REDIS_TLS_KEY,    # Add this
    tls_ca=config.REDIS_TLS_CA       # Add this
)
```

---

## 5. Firewall Configuration

### Allow Only Specific IPs

**iptables (Linux)**:

```bash
# Allow Redis only from specific IPs
sudo iptables -A INPUT -p tcp --dport 6379 -s 10.1.100.5 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 6379 -s 10.1.100.6 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 6379 -j DROP

# Save rules
sudo iptables-save > /etc/iptables/rules.v4
```

**firewalld (RHEL/CentOS)**:

```bash
# Create zone for Redis
sudo firewall-cmd --permanent --new-zone=redis
sudo firewall-cmd --permanent --zone=redis --add-port=6379/tcp
sudo firewall-cmd --permanent --zone=redis --add-source=10.1.100.5
sudo firewall-cmd --permanent --zone=redis --add-source=10.1.100.6
sudo firewall-cmd --reload
```

**macOS (pf firewall)**:

```bash
# Edit /etc/pf.conf
pass in on en0 proto tcp from 10.1.100.5 to any port 6379
pass in on en0 proto tcp from 10.1.100.6 to any port 6379
block in proto tcp to any port 6379

# Reload rules
sudo pfctl -f /etc/pf.conf
```

---

## 6. Docker Configuration

### docker-compose.yml with Security

```yaml
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    container_name: bm-redis
    command: >
      redis-server
      --requirepass ${REDIS_PASSWORD}
      --bind 0.0.0.0
      --protected-mode yes
      --maxmemory 256mb
      --maxmemory-policy allkeys-lru
    ports:
      - "127.0.0.1:6379:6379"  # Bind to localhost only
    volumes:
      - redis-data:/data
    environment:
      - REDIS_PASSWORD=${REDIS_PASSWORD}
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD}", "ping"]
      interval: 10s
      timeout: 3s
      retries: 3

  workers:
    build: .
    depends_on:
      redis:
        condition: service_healthy
    environment:
      REDIS_HOST: redis
      REDIS_PORT: 6379
      REDIS_PASSWORD: ${REDIS_PASSWORD}
    networks:
      - backend

networks:
  backend:
    driver: bridge
    internal: true  # No external access

volumes:
  redis-data:
```

---

## 7. Security Best Practices

### Password Management

✅ **DO**:
- Use strong passwords (32+ characters)
- Store passwords in environment variables
- Use secrets management (Vault, AWS Secrets Manager)
- Rotate passwords regularly
- Different passwords per environment

❌ **DON'T**:
- Hardcode passwords in code
- Commit passwords to git
- Use default or simple passwords
- Share passwords via email/chat

### Network Security

✅ **DO**:
- Bind to localhost if workers are on same host
- Use private network for multi-host setup
- Enable firewall rules
- Use TLS for production
- Monitor connection attempts

❌ **DON'T**:
- Expose Redis to public internet
- Disable protected mode
- Allow connections from 0.0.0.0 without firewall

### Monitoring

Monitor Redis security:

```bash
# Check connected clients
redis-cli -a PASSWORD CLIENT LIST

# Monitor commands
redis-cli -a PASSWORD MONITOR

# Check failed auth attempts
redis-cli -a PASSWORD INFO stats | grep rejected_connections
```

---

## 8. Quick Setup Scripts

### Setup Script for Testing

```bash
#!/bin/bash
# setup_redis_auth.sh

# Generate password
REDIS_PASSWORD=$(openssl rand -base64 32)

# Update Redis config
echo "requirepass $REDIS_PASSWORD" | sudo tee -a /etc/redis/redis.conf
echo "bind 127.0.0.1" | sudo tee -a /etc/redis/redis.conf

# Restart Redis
sudo systemctl restart redis

# Save password to .env
echo "REDIS_PASSWORD=$REDIS_PASSWORD" >> .env

echo "Redis secured!"
echo "Password saved to .env"
```

### Test Connection Script

```bash
#!/bin/bash
# test_redis_auth.sh

source .env

echo "Testing Redis authentication..."
redis-cli -a $REDIS_PASSWORD ping

if [ $? -eq 0 ]; then
    echo "✅ Authentication successful"
else
    echo "❌ Authentication failed"
fi
```

---

## 9. Production Checklist

- [ ] Strong password configured (32+ characters)
- [ ] Password stored securely (not in code)
- [ ] Network binding restricted (not 0.0.0.0)
- [ ] Protected mode enabled
- [ ] Firewall rules configured
- [ ] TLS enabled (for sensitive data)
- [ ] Dangerous commands renamed/disabled
- [ ] Maxmemory limit set
- [ ] Persistence configured
- [ ] Monitoring enabled
- [ ] Regular backups scheduled
- [ ] All workers updated with auth
- [ ] Connection tested from each worker host

---

## 10. Troubleshooting

### Authentication Errors

```
Error: NOAUTH Authentication required
```
**Solution**: Add password to connection or environment variable

```
Error: ERR invalid password
```
**Solution**: Check password in .env matches redis.conf

### Connection Refused

```
Error: Connection refused
```
**Solution**: Check bind address in redis.conf and firewall rules

### TLS Errors

```
Error: SSL handshake failed
```
**Solution**: Verify certificate paths and permissions

---

## Summary

**Minimal Security** (Development):
```bash
requirepass STRONG_PASSWORD
bind 127.0.0.1
```

**Production Security**:
```bash
requirepass STRONG_PASSWORD
bind 10.1.100.5
protected-mode yes
tls-port 6379
tls-cert-file /path/to/cert.pem
rename-command CONFIG ""
rename-command FLUSHALL ""
```

**Workers**:
```bash
export REDIS_PASSWORD=YOUR_PASSWORD
export REDIS_HOST=10.1.100.5
export REDIS_USE_TLS=true
```

---

**Security Level**: 🔒 Development → 🔒🔒 Production → 🔒🔒🔒 High Security (TLS)
