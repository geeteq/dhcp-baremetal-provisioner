#!/bin/bash
#
# Certificate Renewal Script
# Renews certificates before expiration
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKI_DIR="${PKI_DIR:-$SCRIPT_DIR/../../pki}"
VALIDITY_DAYS="${VALIDITY_DAYS:-3650}"

cd "$PKI_DIR"

echo "======================================"
echo "Certificate Renewal"
echo "======================================"
echo ""

# Check certificate expiration
check_expiry() {
    local cert=$1
    local name=$2

    if [[ ! -f "$cert" ]]; then
        echo "⚠️  $name: Certificate not found"
        return 1
    fi

    local expiry=$(openssl x509 -in "$cert" -noout -enddate | cut -d= -f2)
    local expiry_epoch=$(date -j -f "%b %d %T %Y %Z" "$expiry" +%s 2>/dev/null || date -d "$expiry" +%s 2>/dev/null)
    local now_epoch=$(date +%s)
    local days_left=$(( ($expiry_epoch - $now_epoch) / 86400 ))

    echo "$name expires in $days_left days ($expiry)"

    if [[ $days_left -lt 30 ]]; then
        echo "  ⚠️  EXPIRING SOON - Renewing..."
        return 0
    elif [[ $days_left -lt 0 ]]; then
        echo "  ❌ EXPIRED - Renewing..."
        return 0
    else
        echo "  ✅ OK"
        return 1
    fi
}

echo "Checking certificate expiration:"
echo "------------------------------------------------"

RENEW_REDIS=false
RENEW_WORKER=false
RENEW_API=false

if check_expiry "redis/redis-cert.pem" "Redis"; then
    RENEW_REDIS=true
fi

if check_expiry "workers/worker-cert.pem" "Workers"; then
    RENEW_WORKER=true
fi

if check_expiry "api/api-cert.pem" "API"; then
    RENEW_API=true
fi

echo ""

if [[ "$RENEW_REDIS" == "false" && "$RENEW_WORKER" == "false" && "$RENEW_API" == "false" ]]; then
    echo "All certificates are valid. No renewal needed."
    exit 0
fi

echo "Renewing certificates..."
echo "------------------------------------------------"

# Renew Redis certificate
if [[ "$RENEW_REDIS" == "true" ]]; then
    echo "Renewing Redis certificate..."

    # Backup old cert
    mv redis/redis-cert.pem redis/redis-cert.pem.old

    # Generate new CSR
    openssl req -new -key redis/redis-key.pem \
        -out redis/redis.csr \
        -subj "/C=US/ST=State/L=City/O=Baremetal Automation/OU=Redis/CN=redis-server"

    # Sign with CA
    openssl x509 -req -days $VALIDITY_DAYS \
        -in redis/redis.csr \
        -CA ca/ca-cert.pem \
        -CAkey ca/ca-key.pem \
        -CAcreateserial \
        -out redis/redis-cert.pem

    # Update bundle
    cat redis/redis-cert.pem ca/ca-cert.pem > redis/redis-bundle.pem

    echo "✅ Redis certificate renewed"
fi

# Renew Worker certificate
if [[ "$RENEW_WORKER" == "true" ]]; then
    echo "Renewing Worker certificate..."

    mv workers/worker-cert.pem workers/worker-cert.pem.old

    openssl req -new -key workers/worker-key.pem \
        -out workers/worker.csr \
        -subj "/C=US/ST=State/L=City/O=Baremetal Automation/OU=Workers/CN=worker-client"

    openssl x509 -req -days $VALIDITY_DAYS \
        -in workers/worker.csr \
        -CA ca/ca-cert.pem \
        -CAkey ca/ca-key.pem \
        -CAcreateserial \
        -out workers/worker-cert.pem

    cat workers/worker-cert.pem ca/ca-cert.pem > workers/worker-bundle.pem

    echo "✅ Worker certificate renewed"
fi

# Renew API certificate
if [[ "$RENEW_API" == "true" ]]; then
    echo "Renewing API certificate..."

    mv api/api-cert.pem api/api-cert.pem.old

    openssl req -new -key api/api-key.pem \
        -out api/api.csr \
        -config api/api.cnf

    openssl x509 -req -days $VALIDITY_DAYS \
        -in api/api.csr \
        -CA ca/ca-cert.pem \
        -CAkey ca/ca-key.pem \
        -CAcreateserial \
        -out api/api-cert.pem \
        -extensions v3_req \
        -extfile api/api.cnf

    cat api/api-cert.pem ca/ca-cert.pem > api/api-bundle.pem

    echo "✅ API certificate renewed"
fi

echo ""
echo "======================================"
echo "Certificate Renewal Complete!"
echo "======================================"
echo ""
echo "⚠️  IMPORTANT: Restart services to use new certificates:"
echo "  - Redis: brew services restart redis"
echo "  - Workers: Restart all worker processes"
echo "  - API: Restart callback API"
echo ""
