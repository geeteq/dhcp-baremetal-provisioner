#!/bin/bash
#
# Internal PKI Setup for Baremetal Automation
# Creates self-signed CA and generates certificates for all components
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKI_DIR="${PKI_DIR:-$SCRIPT_DIR/../../../pki}"
VALIDITY_DAYS="${VALIDITY_DAYS:-3650}"  # 10 years

echo "======================================"
echo "Internal PKI Setup"
echo "======================================"
echo ""
echo "PKI Directory: $PKI_DIR"
echo "Certificate Validity: $VALIDITY_DAYS days"
echo ""

# Create directory structure
mkdir -p "$PKI_DIR"/{ca,redis,workers,api,certs}
cd "$PKI_DIR"

echo "Step 1: Creating internal Certificate Authority (CA)"
echo "------------------------------------------------"

# Generate CA private key
if [[ ! -f "ca/ca-key.pem" ]]; then
    openssl genrsa -out ca/ca-key.pem 4096
    chmod 600 ca/ca-key.pem
    echo "✅ CA private key generated"
else
    echo "⚠️  CA key already exists, skipping"
fi

# Generate CA certificate (self-signed)
if [[ ! -f "ca/ca-cert.pem" ]]; then
    openssl req -new -x509 -days $VALIDITY_DAYS \
        -key ca/ca-key.pem \
        -out ca/ca-cert.pem \
        -subj "/C=US/ST=State/L=City/O=Baremetal Automation/OU=Internal CA/CN=Baremetal-Root-CA"
    chmod 644 ca/ca-cert.pem
    echo "✅ CA certificate generated"
else
    echo "⚠️  CA certificate already exists, skipping"
fi

# Display CA info
echo ""
echo "CA Certificate Details:"
openssl x509 -in ca/ca-cert.pem -noout -subject -dates

echo ""
echo "Step 2: Creating Redis Server Certificate"
echo "------------------------------------------------"

# Generate Redis server key
openssl genrsa -out redis/redis-key.pem 4096
chmod 600 redis/redis-key.pem

# Generate Redis server CSR
openssl req -new -key redis/redis-key.pem \
    -out redis/redis.csr \
    -subj "/C=US/ST=State/L=City/O=Baremetal Automation/OU=Redis/CN=redis-server"

# Sign Redis certificate with our CA
openssl x509 -req -days $VALIDITY_DAYS \
    -in redis/redis.csr \
    -CA ca/ca-cert.pem \
    -CAkey ca/ca-key.pem \
    -CAcreateserial \
    -out redis/redis-cert.pem

chmod 644 redis/redis-cert.pem
echo "✅ Redis server certificate generated"

echo ""
echo "Step 3: Creating Worker Client Certificates"
echo "------------------------------------------------"

# Generate worker client key
openssl genrsa -out workers/worker-key.pem 4096
chmod 600 workers/worker-key.pem

# Generate worker client CSR
openssl req -new -key workers/worker-key.pem \
    -out workers/worker.csr \
    -subj "/C=US/ST=State/L=City/O=Baremetal Automation/OU=Workers/CN=worker-client"

# Sign worker certificate with our CA
openssl x509 -req -days $VALIDITY_DAYS \
    -in workers/worker.csr \
    -CA ca/ca-cert.pem \
    -CAkey ca/ca-key.pem \
    -CAcreateserial \
    -out workers/worker-cert.pem

chmod 644 workers/worker-cert.pem
echo "✅ Worker client certificate generated"

echo ""
echo "Step 4: Creating API Server Certificate"
echo "------------------------------------------------"

# Generate API server key
openssl genrsa -out api/api-key.pem 4096
chmod 600 api/api-key.pem

# Generate API server CSR with SAN (Subject Alternative Names)
cat > api/api.cnf <<EOF
[req]
default_bits = 4096
prompt = no
default_md = sha256
distinguished_name = dn
req_extensions = v3_req

[dn]
C = US
ST = State
L = City
O = Baremetal Automation
OU = API
CN = callback-api

[v3_req]
subjectAltName = @alt_names

[alt_names]
DNS.1 = localhost
DNS.2 = callback-api
DNS.3 = *.local
IP.1 = 127.0.0.1
IP.2 = 10.1.100.5
EOF

openssl req -new -key api/api-key.pem \
    -out api/api.csr \
    -config api/api.cnf

# Sign API certificate with our CA
openssl x509 -req -days $VALIDITY_DAYS \
    -in api/api.csr \
    -CA ca/ca-cert.pem \
    -CAkey ca/ca-key.pem \
    -CAcreateserial \
    -out api/api-cert.pem \
    -extensions v3_req \
    -extfile api/api.cnf

chmod 644 api/api-cert.pem
echo "✅ API server certificate generated"

echo ""
echo "Step 5: Creating combined certificate bundles"
echo "------------------------------------------------"

# Create certificate bundles (cert + CA chain)
cat redis/redis-cert.pem ca/ca-cert.pem > redis/redis-bundle.pem
cat workers/worker-cert.pem ca/ca-cert.pem > workers/worker-bundle.pem
cat api/api-cert.pem ca/ca-cert.pem > api/api-bundle.pem

echo "✅ Certificate bundles created"

echo ""
echo "Step 6: Verifying certificates"
echo "------------------------------------------------"

# Verify Redis certificate
if openssl verify -CAfile ca/ca-cert.pem redis/redis-cert.pem > /dev/null 2>&1; then
    echo "✅ Redis certificate valid"
else
    echo "❌ Redis certificate verification failed"
fi

# Verify Worker certificate
if openssl verify -CAfile ca/ca-cert.pem workers/worker-cert.pem > /dev/null 2>&1; then
    echo "✅ Worker certificate valid"
else
    echo "❌ Worker certificate verification failed"
fi

# Verify API certificate
if openssl verify -CAfile ca/ca-cert.pem api/api-cert.pem > /dev/null 2>&1; then
    echo "✅ API certificate valid"
else
    echo "❌ API certificate verification failed"
fi

echo ""
echo "Step 7: Creating certificate metadata"
echo "------------------------------------------------"

# Create metadata file
cat > certs/metadata.json <<EOF
{
  "created_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "validity_days": $VALIDITY_DAYS,
  "expires_at": "$(date -u -v+${VALIDITY_DAYS}d +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date -u -d "+${VALIDITY_DAYS} days" +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || echo "N/A")",
  "ca": {
    "cert": "ca/ca-cert.pem",
    "key": "ca/ca-key.pem"
  },
  "redis": {
    "cert": "redis/redis-cert.pem",
    "key": "redis/redis-key.pem",
    "bundle": "redis/redis-bundle.pem"
  },
  "workers": {
    "cert": "workers/worker-cert.pem",
    "key": "workers/worker-key.pem",
    "bundle": "workers/worker-bundle.pem"
  },
  "api": {
    "cert": "api/api-cert.pem",
    "key": "api/api-key.pem",
    "bundle": "api/api-bundle.pem"
  }
}
EOF

echo "✅ Metadata file created: certs/metadata.json"

echo ""
echo "Step 8: Setting permissions"
echo "------------------------------------------------"

# Secure private keys (readable only by owner)
chmod 600 ca/ca-key.pem redis/redis-key.pem workers/worker-key.pem api/api-key.pem

# Public certificates and bundles (readable by all)
chmod 644 ca/ca-cert.pem redis/redis-cert.pem workers/worker-cert.pem api/api-cert.pem
chmod 644 redis/redis-bundle.pem workers/worker-bundle.pem api/api-bundle.pem

echo "✅ Permissions set securely"

echo ""
echo "======================================"
echo "PKI Setup Complete!"
echo "======================================"
echo ""
echo "Certificate Authority:"
echo "  Location: $PKI_DIR/ca/ca-cert.pem"
echo "  Validity: $VALIDITY_DAYS days"
echo ""
echo "Certificates generated for:"
echo "  ✅ Redis server (mTLS)"
echo "  ✅ Workers (mTLS clients)"
echo "  ✅ Callback API (HTTPS)"
echo ""
echo "Next steps:"
echo "  1. Update .env with certificate paths"
echo "  2. Configure Redis with TLS"
echo "  3. Update workers to use mTLS"
echo "  4. Configure API with HTTPS"
echo ""
echo "See: docs/PKI.md for configuration details"
echo ""
