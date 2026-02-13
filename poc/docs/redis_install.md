# Redis Installation on RHEL 9 with mTLS

Complete guide for installing and configuring Redis with mutual TLS authentication on Red Hat Enterprise Linux 9.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Certificate Setup](#certificate-setup)
- [Redis Configuration](#redis-configuration)
- [Starting Redis](#starting-redis)
- [Testing mTLS Connection](#testing-mtls-connection)
- [Client Configuration](#client-configuration)
- [Troubleshooting](#troubleshooting)
- [Security Best Practices](#security-best-practices)

## Prerequisites

- RHEL 9 system with root or sudo access
- OpenSSL installed
- Basic understanding of TLS/SSL concepts

## Installation

### Step 1: Enable EPEL Repository

```bash
# Install EPEL repository
sudo dnf install -y epel-release

# Update package cache
sudo dnf update -y
```

### Step 2: Install Redis

```bash
# Install Redis and required dependencies
sudo dnf install -y redis

# Verify installation
redis-server --version
```

### Step 3: Install Redis Development Tools (Optional)

```bash
# Install redis-cli and debugging tools
sudo dnf install -y redis-devel redis-doc
```

## Certificate Setup

### Option 1: Using Existing PKI Infrastructure

If you have an existing PKI (like in this project's `pki/` directory):

```bash
# Create Redis certificate directory
sudo mkdir -p /etc/redis/certs
sudo chown redis:redis /etc/redis/certs
sudo chmod 750 /etc/redis/certs

# Copy certificates
sudo cp pki/ca/ca-cert.pem /etc/redis/certs/ca.crt
sudo cp pki/redis/redis-cert.pem /etc/redis/certs/redis.crt
sudo cp pki/redis/redis-key.pem /etc/redis/certs/redis.key

# Set proper permissions
sudo chown redis:redis /etc/redis/certs/*
sudo chmod 640 /etc/redis/certs/redis.key
sudo chmod 644 /etc/redis/certs/redis.crt
sudo chmod 644 /etc/redis/certs/ca.crt
```

### Option 2: Generate New Certificates

#### 2.1: Create Certificate Authority (CA)

```bash
# Create PKI directory structure
sudo mkdir -p /etc/redis/pki/{ca,certs}
cd /etc/redis/pki

# Generate CA private key
sudo openssl genrsa -out ca/ca-key.pem 4096

# Generate CA certificate (valid for 10 years)
sudo openssl req -new -x509 -days 3650 -key ca/ca-key.pem -out ca/ca-cert.pem \
  -subj "/C=US/ST=State/L=City/O=Organization/OU=IT/CN=Redis-CA"

# Protect CA key
sudo chmod 600 ca/ca-key.pem
sudo chmod 644 ca/ca-cert.pem
```

#### 2.2: Generate Redis Server Certificate

```bash
# Generate Redis server private key
sudo openssl genrsa -out certs/redis-key.pem 4096

# Create certificate signing request (CSR)
sudo openssl req -new -key certs/redis-key.pem -out certs/redis.csr \
  -subj "/C=US/ST=State/L=City/O=Organization/OU=IT/CN=redis.example.com"

# Create certificate extension file for SAN
sudo tee certs/redis.ext > /dev/null <<EOF
subjectAltName = @alt_names
extendedKeyUsage = serverAuth

[alt_names]
DNS.1 = redis.example.com
DNS.2 = localhost
DNS.3 = redis
IP.1 = 127.0.0.1
IP.2 = 10.1.100.5
EOF

# Sign the certificate with CA
sudo openssl x509 -req -days 365 -in certs/redis.csr \
  -CA ca/ca-cert.pem -CAkey ca/ca-key.pem -CAcreateserial \
  -out certs/redis-cert.pem -extfile certs/redis.ext

# Create certificate bundle (cert + CA)
sudo cat certs/redis-cert.pem ca/ca-cert.pem > certs/redis-bundle.pem

# Set proper permissions
sudo chmod 640 certs/redis-key.pem
sudo chmod 644 certs/redis-cert.pem
sudo chmod 644 certs/redis-bundle.pem
sudo chown -R redis:redis /etc/redis/pki
```

#### 2.3: Generate Client Certificates (for mTLS)

```bash
# Generate client private key
sudo openssl genrsa -out certs/client-key.pem 4096

# Create client CSR
sudo openssl req -new -key certs/client-key.pem -out certs/client.csr \
  -subj "/C=US/ST=State/L=City/O=Organization/OU=IT/CN=redis-client"

# Create client certificate extension file
sudo tee certs/client.ext > /dev/null <<EOF
extendedKeyUsage = clientAuth
EOF

# Sign the client certificate
sudo openssl x509 -req -days 365 -in certs/client.csr \
  -CA ca/ca-cert.pem -CAkey ca/ca-key.pem -CAcreateserial \
  -out certs/client-cert.pem -extfile certs/client.ext

# Create client bundle
sudo cat certs/client-cert.pem ca/ca-cert.pem > certs/client-bundle.pem

# Set permissions
sudo chmod 640 certs/client-key.pem
sudo chmod 644 certs/client-cert.pem
sudo chmod 644 certs/client-bundle.pem
```

#### 2.4: Verify Certificates

```bash
# Verify server certificate
sudo openssl x509 -in /etc/redis/pki/certs/redis-cert.pem -text -noout | grep -E "(Subject:|Issuer:|Not Before|Not After|DNS:|IP:)"

# Verify certificate chain
sudo openssl verify -CAfile /etc/redis/pki/ca/ca-cert.pem /etc/redis/pki/certs/redis-cert.pem

# Verify client certificate
sudo openssl verify -CAfile /etc/redis/pki/ca/ca-cert.pem /etc/redis/pki/certs/client-cert.pem
```

## Redis Configuration

### Step 1: Backup Original Configuration

```bash
sudo cp /etc/redis/redis.conf /etc/redis/redis.conf.backup
```

### Step 2: Configure Redis for mTLS

Edit `/etc/redis/redis.conf`:

```bash
sudo vi /etc/redis/redis.conf
```

Add or modify the following settings:

```conf
# Network Configuration
bind 0.0.0.0
port 0
tls-port 6379

# TLS/SSL Configuration
tls-cert-file /etc/redis/pki/certs/redis-cert.pem
tls-key-file /etc/redis/pki/certs/redis-key.pem
tls-ca-cert-file /etc/redis/pki/ca/ca-cert.pem

# Mutual TLS Authentication
tls-auth-clients yes
tls-auth-clients optional

# TLS Protocol Versions (TLSv1.2 and TLSv1.3 only)
tls-protocols "TLSv1.2 TLSv1.3"

# Strong cipher suites
tls-ciphers TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256:TLS_AES_128_GCM_SHA256:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-RSA-AES128-GCM-SHA256
tls-ciphersuites TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256:TLS_AES_128_GCM_SHA256

# Prefer server ciphers
tls-prefer-server-ciphers yes

# Authentication (optional but recommended)
requirepass your_strong_password_here

# General Security Settings
protected-mode yes
daemonize yes
supervised systemd
pidfile /var/run/redis/redis.pid
loglevel notice
logfile /var/log/redis/redis.log
dir /var/lib/redis

# Persistence
save 900 1
save 300 10
save 60 10000
dbfilename dump.rdb

# Replication (if needed)
# replicaof <master-ip> <master-port>
# masterauth <master-password>

# Memory Management
maxmemory 2gb
maxmemory-policy allkeys-lru

# Slow Log
slowlog-log-slower-than 10000
slowlog-max-len 128
```

### Step 3: Set SELinux Context (RHEL-specific)

```bash
# Set SELinux context for Redis certificates
sudo semanage fcontext -a -t redis_conf_t "/etc/redis/pki(/.*)?"
sudo restorecon -Rv /etc/redis/pki

# If semanage is not available, install it
sudo dnf install -y policycoreutils-python-utils

# Allow Redis to read certificates
sudo setsebool -P redis_enable_homedirs 1
```

### Step 4: Configure Firewall

```bash
# Allow Redis TLS port
sudo firewall-cmd --permanent --add-port=6379/tcp
sudo firewall-cmd --reload

# Verify
sudo firewall-cmd --list-ports
```

## Starting Redis

### Step 1: Enable and Start Redis Service

```bash
# Enable Redis to start on boot
sudo systemctl enable redis

# Start Redis service
sudo systemctl start redis

# Check status
sudo systemctl status redis
```

### Step 2: Verify Redis is Running with TLS

```bash
# Check if Redis is listening on TLS port
sudo ss -tlnp | grep 6379

# Expected output:
# LISTEN 0 511 0.0.0.0:6379 0.0.0.0:* users:(("redis-server",pid=XXXX,fd=X))

# Check Redis logs
sudo tail -f /var/log/redis/redis.log
```

## Testing mTLS Connection

### Test 1: Using redis-cli with TLS

```bash
# Test connection with client certificate
redis-cli --tls \
  --cert /etc/redis/pki/certs/client-cert.pem \
  --key /etc/redis/pki/certs/client-key.pem \
  --cacert /etc/redis/pki/ca/ca-cert.pem \
  -h localhost -p 6379 \
  --pass your_strong_password_here \
  PING

# Expected output: PONG
```

### Test 2: Using OpenSSL

```bash
# Test TLS handshake
openssl s_client -connect localhost:6379 \
  -cert /etc/redis/pki/certs/client-cert.pem \
  -key /etc/redis/pki/certs/client-key.pem \
  -CAfile /etc/redis/pki/ca/ca-cert.pem

# Type "PING" after connection
# Expected response: +PONG
```

### Test 3: Using Python Client

Create a test script `test_redis_mtls.py`:

```python
#!/usr/bin/env python3
import redis

# Connect to Redis with mTLS
r = redis.Redis(
    host='localhost',
    port=6379,
    password='your_strong_password_here',
    ssl=True,
    ssl_cert_reqs='required',
    ssl_ca_certs='/etc/redis/pki/ca/ca-cert.pem',
    ssl_certfile='/etc/redis/pki/certs/client-cert.pem',
    ssl_keyfile='/etc/redis/pki/certs/client-key.pem',
    decode_responses=True
)

# Test connection
try:
    response = r.ping()
    print(f"✓ Connection successful: {response}")

    # Test set/get
    r.set('test_key', 'test_value')
    value = r.get('test_key')
    print(f"✓ Set/Get test: {value}")

    # Test pub/sub
    pubsub = r.pubsub()
    pubsub.subscribe('test_channel')
    print("✓ Pub/Sub subscription successful")

    print("\n✓ All tests passed!")

except redis.ConnectionError as e:
    print(f"✗ Connection failed: {e}")
except Exception as e:
    print(f"✗ Error: {e}")
```

Run the test:

```bash
# Install redis-py if not already installed
pip3 install redis

# Run test
python3 test_redis_mtls.py
```

## Client Configuration

### Python Application Example

```python
from redis import Redis

def get_redis_client():
    """Create Redis client with mTLS."""
    return Redis(
        host='redis.example.com',
        port=6379,
        password='your_strong_password_here',
        ssl=True,
        ssl_cert_reqs='required',
        ssl_ca_certs='/path/to/ca-cert.pem',
        ssl_certfile='/path/to/client-cert.pem',
        ssl_keyfile='/path/to/client-key.pem',
        socket_connect_timeout=5,
        socket_keepalive=True,
        health_check_interval=30,
        decode_responses=True
    )

# Usage
redis_client = get_redis_client()
redis_client.ping()
```

### Environment Variables (for this project)

Add to your `.env` file:

```bash
# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=your_strong_password_here

# Redis TLS Configuration
REDIS_USE_TLS=true
REDIS_TLS_CA=/etc/redis/pki/ca/ca-cert.pem
REDIS_TLS_CERT=/etc/redis/pki/certs/client-cert.pem
REDIS_TLS_KEY=/etc/redis/pki/certs/client-key.pem
```

## Troubleshooting

### Issue 1: Redis Won't Start

```bash
# Check logs
sudo journalctl -u redis -n 50 --no-pager

# Check configuration syntax
redis-server /etc/redis/redis.conf --test-memory 1

# Verify certificate permissions
sudo ls -la /etc/redis/pki/certs/
# redis-key.pem should be 640 or 600 and owned by redis:redis
```

### Issue 2: Certificate Verification Failed

```bash
# Verify certificate chain
openssl verify -CAfile /etc/redis/pki/ca/ca-cert.pem \
  /etc/redis/pki/certs/redis-cert.pem

# Check certificate dates
openssl x509 -in /etc/redis/pki/certs/redis-cert.pem -noout -dates

# Check certificate SAN/CN matches hostname
openssl x509 -in /etc/redis/pki/certs/redis-cert.pem -noout -text | grep -A1 "Subject Alternative Name"
```

### Issue 3: Connection Refused

```bash
# Check if Redis is listening
sudo netstat -tlnp | grep 6379
# or
sudo ss -tlnp | grep 6379

# Check firewall
sudo firewall-cmd --list-all

# Test with verbose OpenSSL
openssl s_client -connect localhost:6379 \
  -cert /etc/redis/pki/certs/client-cert.pem \
  -key /etc/redis/pki/certs/client-key.pem \
  -CAfile /etc/redis/pki/ca/ca-cert.pem \
  -showcerts -debug
```

### Issue 4: SELinux Denials

```bash
# Check SELinux denials
sudo ausearch -m avc -ts recent | grep redis

# Generate SELinux policy from denials
sudo ausearch -m avc -ts recent | audit2allow -M redis_custom

# Apply policy (if safe)
sudo semodule -i redis_custom.pp

# Or temporarily disable SELinux (not recommended for production)
sudo setenforce 0
```

### Issue 5: Permission Denied on Certificate Files

```bash
# Fix ownership
sudo chown -R redis:redis /etc/redis/pki

# Fix permissions
sudo chmod 750 /etc/redis/pki
sudo chmod 755 /etc/redis/pki/ca
sudo chmod 755 /etc/redis/pki/certs
sudo chmod 600 /etc/redis/pki/certs/redis-key.pem
sudo chmod 644 /etc/redis/pki/certs/redis-cert.pem
sudo chmod 644 /etc/redis/pki/ca/ca-cert.pem
```

### Issue 6: TLS Handshake Errors

```bash
# Enable debug logging in Redis
sudo sed -i 's/loglevel notice/loglevel debug/' /etc/redis/redis.conf
sudo systemctl restart redis

# Check logs for TLS errors
sudo tail -f /var/log/redis/redis.log | grep -i tls
```

## Security Best Practices

### 1. Certificate Management

- **Use strong key sizes**: Minimum 2048-bit RSA, prefer 4096-bit
- **Set appropriate validity periods**: Max 397 days for certificates
- **Implement certificate rotation**: Plan for renewal before expiration
- **Secure private keys**: Never share, use proper file permissions (600)
- **Use separate CAs**: Different CAs for different environments

### 2. Redis Configuration

```conf
# Disable dangerous commands
rename-command FLUSHDB ""
rename-command FLUSHALL ""
rename-command KEYS ""
rename-command CONFIG "CONFIG_abc123xyz"
rename-command SHUTDOWN "SHUTDOWN_abc123xyz"
rename-command DEBUG ""

# Enable protected mode
protected-mode yes

# Limit memory
maxmemory 2gb
maxmemory-policy allkeys-lru

# Disable persistence if not needed
save ""

# Bind to specific interface
bind 10.1.100.5
```

### 3. System Hardening

```bash
# Disable transparent huge pages
echo never > /sys/kernel/mm/transparent_hugepage/enabled
echo never > /sys/kernel/mm/transparent_hugepage/defrag

# Add to /etc/rc.local for persistence
sudo tee -a /etc/rc.local > /dev/null <<EOF
echo never > /sys/kernel/mm/transparent_hugepage/enabled
echo never > /sys/kernel/mm/transparent_hugepage/defrag
EOF

# Optimize network settings
sudo tee -a /etc/sysctl.conf > /dev/null <<EOF
net.core.somaxconn = 65535
vm.overcommit_memory = 1
EOF

sudo sysctl -p
```

### 4. Monitoring

```bash
# Monitor Redis with redis-cli
redis-cli --tls \
  --cert /etc/redis/pki/certs/client-cert.pem \
  --key /etc/redis/pki/certs/client-key.pem \
  --cacert /etc/redis/pki/ca/ca-cert.pem \
  --pass your_password INFO

# Monitor slow queries
redis-cli --tls \
  --cert /etc/redis/pki/certs/client-cert.pem \
  --key /etc/redis/pki/certs/client-key.pem \
  --cacert /etc/redis/pki/ca/ca-cert.pem \
  --pass your_password SLOWLOG GET 10
```

### 5. Backup Strategy

```bash
# Create backup script
sudo tee /usr/local/bin/redis-backup.sh > /dev/null <<'EOF'
#!/bin/bash
BACKUP_DIR=/var/backups/redis
DATE=$(date +%Y%m%d-%H%M%S)

mkdir -p $BACKUP_DIR
redis-cli --tls \
  --cert /etc/redis/pki/certs/client-cert.pem \
  --key /etc/redis/pki/certs/client-key.pem \
  --cacert /etc/redis/pki/ca/ca-cert.pem \
  --pass your_password BGSAVE

sleep 5
cp /var/lib/redis/dump.rdb $BACKUP_DIR/dump-$DATE.rdb
find $BACKUP_DIR -name "dump-*.rdb" -mtime +7 -delete
EOF

sudo chmod +x /usr/local/bin/redis-backup.sh

# Add cron job
echo "0 2 * * * /usr/local/bin/redis-backup.sh" | sudo crontab -
```

## Additional Resources

- [Redis TLS Documentation](https://redis.io/docs/manual/security/encryption/)
- [Redis Security Best Practices](https://redis.io/docs/manual/security/)
- [OpenSSL Documentation](https://www.openssl.org/docs/)
- [RHEL Security Guide](https://access.redhat.com/documentation/en-us/red_hat_enterprise_linux/9/html/security_hardening/)

## Quick Reference Commands

```bash
# Start/Stop/Restart Redis
sudo systemctl start redis
sudo systemctl stop redis
sudo systemctl restart redis
sudo systemctl status redis

# View logs
sudo tail -f /var/log/redis/redis.log
sudo journalctl -u redis -f

# Connect with redis-cli
redis-cli --tls \
  --cert /etc/redis/pki/certs/client-cert.pem \
  --key /etc/redis/pki/certs/client-key.pem \
  --cacert /etc/redis/pki/ca/ca-cert.pem \
  -p 6379 --pass your_password

# Check certificate expiration
openssl x509 -in /etc/redis/pki/certs/redis-cert.pem -noout -enddate

# Test TLS connection
openssl s_client -connect localhost:6379 \
  -cert /etc/redis/pki/certs/client-cert.pem \
  -key /etc/redis/pki/certs/client-key.pem \
  -CAfile /etc/redis/pki/ca/ca-cert.pem
```

---

**Document Version:** 1.0
**Last Updated:** 2026-02-12
**Tested On:** RHEL 9.3, Redis 7.0+
