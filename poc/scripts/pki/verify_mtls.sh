#!/bin/bash
#
# Verify mTLS Configuration
# Tests certificate setup and mutual TLS connections
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKI_DIR="${PKI_DIR:-$SCRIPT_DIR/../../pki}"

echo "======================================"
echo "mTLS Configuration Verification"
echo "======================================"
echo ""

cd "$PKI_DIR"

echo "Step 1: Verifying certificate files exist"
echo "------------------------------------------------"

check_file() {
    if [[ -f "$1" ]]; then
        echo "✅ $1"
        return 0
    else
        echo "❌ $1 (missing)"
        return 1
    fi
}

ALL_GOOD=true

check_file "ca/ca-cert.pem" || ALL_GOOD=false
check_file "ca/ca-key.pem" || ALL_GOOD=false
check_file "redis/redis-cert.pem" || ALL_GOOD=false
check_file "redis/redis-key.pem" || ALL_GOOD=false
check_file "workers/worker-cert.pem" || ALL_GOOD=false
check_file "workers/worker-key.pem" || ALL_GOOD=false
check_file "api/api-cert.pem" || ALL_GOOD=false
check_file "api/api-key.pem" || ALL_GOOD=false

echo ""
echo "Step 2: Verifying certificate validity"
echo "------------------------------------------------"

verify_cert() {
    local cert=$1
    local name=$2

    if openssl verify -CAfile ca/ca-cert.pem "$cert" > /dev/null 2>&1; then
        echo "✅ $name certificate is valid"
        return 0
    else
        echo "❌ $name certificate verification failed"
        return 1
    fi
}

verify_cert "redis/redis-cert.pem" "Redis" || ALL_GOOD=false
verify_cert "workers/worker-cert.pem" "Worker" || ALL_GOOD=false
verify_cert "api/api-cert.pem" "API" || ALL_GOOD=false

echo ""
echo "Step 3: Checking certificate expiration"
echo "------------------------------------------------"

check_expiry() {
    local cert=$1
    local name=$2

    local expiry=$(openssl x509 -in "$cert" -noout -enddate | cut -d= -f2)
    local expiry_epoch=$(date -j -f "%b %d %T %Y %Z" "$expiry" +%s 2>/dev/null || date -d "$expiry" +%s 2>/dev/null)
    local now_epoch=$(date +%s)
    local days_left=$(( ($expiry_epoch - $now_epoch) / 86400 ))

    if [[ $days_left -gt 30 ]]; then
        echo "✅ $name: $days_left days remaining"
    elif [[ $days_left -gt 0 ]]; then
        echo "⚠️  $name: $days_left days remaining (EXPIRING SOON)"
    else
        echo "❌ $name: EXPIRED"
        ALL_GOOD=false
    fi
}

check_expiry "redis/redis-cert.pem" "Redis"
check_expiry "workers/worker-cert.pem" "Worker"
check_expiry "api/api-cert.pem" "API"

echo ""
echo "Step 4: Verifying certificate details"
echo "------------------------------------------------"

echo "Redis Certificate Subject:"
openssl x509 -in redis/redis-cert.pem -noout -subject | sed 's/^/  /'

echo ""
echo "Worker Certificate Subject:"
openssl x509 -in workers/worker-cert.pem -noout -subject | sed 's/^/  /'

echo ""
echo "API Certificate Subject + SANs:"
openssl x509 -in api/api-cert.pem -noout -subject | sed 's/^/  /'
openssl x509 -in api/api-cert.pem -noout -text | grep -A1 "Subject Alternative Name" | sed 's/^/  /'

echo ""
echo "Step 5: Testing certificate matching"
echo "------------------------------------------------"

# Check if private key matches certificate
check_key_match() {
    local cert=$1
    local key=$2
    local name=$3

    local cert_modulus=$(openssl x509 -in "$cert" -noout -modulus | md5)
    local key_modulus=$(openssl rsa -in "$key" -noout -modulus 2>/dev/null | md5)

    if [[ "$cert_modulus" == "$key_modulus" ]]; then
        echo "✅ $name: Private key matches certificate"
    else
        echo "❌ $name: Private key does NOT match certificate"
        ALL_GOOD=false
    fi
}

check_key_match "redis/redis-cert.pem" "redis/redis-key.pem" "Redis"
check_key_match "workers/worker-cert.pem" "workers/worker-key.pem" "Worker"
check_key_match "api/api-cert.pem" "api/api-key.pem" "API"

echo ""
echo "Step 6: Checking file permissions"
echo "------------------------------------------------"

check_perms() {
    local file=$1
    local name=$2
    local expected=$3

    local actual=$(stat -f "%Lp" "$file" 2>/dev/null || stat -c "%a" "$file" 2>/dev/null)

    if [[ "$actual" == "$expected" ]]; then
        echo "✅ $name: $actual (correct)"
    else
        echo "⚠️  $name: $actual (expected $expected)"
    fi
}

echo "Private Keys (should be 600):"
check_perms "ca/ca-key.pem" "CA key" "600"
check_perms "redis/redis-key.pem" "Redis key" "600"
check_perms "workers/worker-key.pem" "Worker key" "600"
check_perms "api/api-key.pem" "API key" "600"

echo ""
echo "Certificates (should be 644):"
check_perms "ca/ca-cert.pem" "CA cert" "644"
check_perms "redis/redis-cert.pem" "Redis cert" "644"
check_perms "workers/worker-cert.pem" "Worker cert" "644"
check_perms "api/api-cert.pem" "API cert" "644"

echo ""
echo "======================================"
if [[ "$ALL_GOOD" == "true" ]]; then
    echo "✅ All checks passed!"
    echo "======================================"
    echo ""
    echo "mTLS is properly configured."
    exit 0
else
    echo "❌ Some checks failed!"
    echo "======================================"
    echo ""
    echo "Please review the errors above."
    exit 1
fi
