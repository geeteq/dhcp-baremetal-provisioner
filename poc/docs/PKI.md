# Internal PKI & mTLS Configuration

Complete guide for setting up internal Public Key Infrastructure with mutual TLS (mTLS) authentication.

## Overview

This system uses a self-contained PKI that doesn't depend on external Certificate Authorities (CAs). All certificates are signed by an internal CA, and all communications use mutual TLS where both client and server authenticate each other.

### Architecture

```
Internal Root CA (self-signed)
    │
    ├── Redis Server Certificate
    │   └── Used by: Redis server
    │       Verified by: Workers (clients)
    │
    ├── Worker Client Certificate
    │   └── Used by: All workers
    │       Verified by: Redis server
    │
    └── API Server Certificate
        └── Used by: Callback API
            Verified by: PXE-booted servers
```

### Benefits

✅ **No external dependencies** - Self-contained CA
✅ **Complete control** - Manage entire certificate lifecycle
✅ **Mutual authentication** - Both endpoints verify each other
✅ **Free** - No cost for certificates
✅ **Custom validity periods** - Set your own expiration
✅ **Easy rotation** - Scripts included for renewal
✅ **Secure by default** - mTLS for all connections

---

## Quick Start

### 1. Generate PKI

```bash
cd /Users/gabe/ai/bm/poc
./scripts/pki/setup_pki.sh
```

This creates:
- Internal Root CA (10-year validity)
- Redis server certificate
- Worker client certificate
- API server certificate

### 2. Verify Setup

```bash
./scripts/pki/verify_mtls.sh
```

### 3. Configure Components

Update `.env`:
```bash
# CA Certificate (trusted root)
PKI_CA_CERT=pki/ca/ca-cert.pem

# Redis TLS
REDIS_USE_TLS=true
REDIS_TLS_CERT=pki/workers/worker-cert.pem
REDIS_TLS_KEY=pki/workers/worker-key.pem
REDIS_TLS_CA=pki/ca/ca-cert.pem

# API TLS
API_USE_TLS=true
API_TLS_CERT=pki/api/api-cert.pem
API_TLS_KEY=pki/api/api-key.pem
API_TLS_CA=pki/ca/ca-cert.pem
```

---

## Directory Structure

```
poc/
└── pki/
    ├── ca/
    │   ├── ca-key.pem          # CA private key (SECRET)
    │   ├── ca-cert.pem         # CA certificate (public)
    │   └── ca-cert.srl         # Serial number tracker
    │
    ├── redis/
    │   ├── redis-key.pem       # Redis server private key
    │   ├── redis-cert.pem      # Redis server certificate
    │   ├── redis-bundle.pem    # Cert + CA chain
    │   ├── redis.csr           # Certificate signing request
    │   └── redis.cnf           # OpenSSL config
    │
    ├── workers/
    │   ├── worker-key.pem      # Worker client private key
    │   ├── worker-cert.pem     # Worker client certificate
    │   ├── worker-bundle.pem   # Cert + CA chain
    │   └── worker.csr          # Certificate signing request
    │
    ├── api/
    │   ├── api-key.pem         # API server private key
    │   ├── api-cert.pem        # API server certificate
    │   ├── api-bundle.pem      # Cert + CA chain
    │   ├── api.csr             # Certificate signing request
    │   └── api.cnf             # OpenSSL config with SANs
    │
    └── certs/
        └── metadata.json       # Certificate metadata
```

---

## Component Configuration

### Redis Server

**Configure Redis** (`/opt/homebrew/etc/redis.conf` or `/etc/redis/redis.conf`):

```bash
# Disable standard port
port 0

# Enable TLS port
tls-port 6379

# Server certificate and key
tls-cert-file /Users/gabe/ai/bm/poc/pki/redis/redis-cert.pem
tls-key-file /Users/gabe/ai/bm/poc/pki/redis/redis-key.pem

# CA certificate (to verify clients)
tls-ca-cert-file /Users/gabe/ai/bm/poc/pki/ca/ca-cert.pem

# Require client certificates (mTLS)
tls-auth-clients yes

# Require password (defense in depth)
requirepass YOUR_REDIS_PASSWORD
```

**Restart Redis**:
```bash
brew services restart redis  # macOS
sudo systemctl restart redis # Linux
```

**Test mTLS Connection**:
```bash
redis-cli --tls \
  --cert pki/workers/worker-cert.pem \
  --key pki/workers/worker-key.pem \
  --cacert pki/ca/ca-cert.pem \
  -a YOUR_REDIS_PASSWORD \
  ping
# PONG
```

### Worker Configuration

Workers automatically use mTLS when configured in `.env`:

```python
# lib/queue.py automatically loads from config
queue = Queue(
    host=config.REDIS_HOST,
    port=config.REDIS_PORT,
    password=config.REDIS_PASSWORD,
    use_tls=True,  # From REDIS_USE_TLS
    tls_cert=config.REDIS_TLS_CERT,
    tls_key=config.REDIS_TLS_KEY,
    tls_ca=config.REDIS_TLS_CA
)
```

### Callback API

**Enable HTTPS with mTLS** in `callback_api.py`:

```python
if __name__ == '__main__':
    if config.API_USE_TLS:
        import ssl
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(
            certfile=config.API_TLS_CERT,
            keyfile=config.API_TLS_KEY
        )
        # Optional: Require client certificates
        if config.API_REQUIRE_CLIENT_CERT:
            context.load_verify_locations(cafile=config.API_TLS_CA)
            context.verify_mode = ssl.CERT_REQUIRED

        app.run(
            host=config.CALLBACK_API_HOST,
            port=config.CALLBACK_API_PORT,
            ssl_context=context
        )
    else:
        app.run(
            host=config.CALLBACK_API_HOST,
            port=config.CALLBACK_API_PORT
        )
```

### Validation ISO

**Configure validation script** to use HTTPS:

```bash
# In validate_server.sh
API_ENDPOINT="https://10.1.100.5:5000/api/v1/validation/report"

# Send with CA certificate
curl -X POST "$API_ENDPOINT" \
  --cacert /path/to/ca-cert.pem \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD"
```

---

## Certificate Management

### Check Expiration

```bash
./scripts/pki/verify_mtls.sh
```

Output shows days remaining for each certificate.

### Renew Certificates

**Automatic renewal** (before expiration):
```bash
./scripts/pki/renew_certs.sh
```

**Manual renewal** (force):
```bash
VALIDITY_DAYS=3650 ./scripts/pki/setup_pki.sh
```

### Certificate Rotation

1. **Generate new certificates**:
   ```bash
   ./scripts/pki/renew_certs.sh
   ```

2. **Update services with new certs**:
   ```bash
   # Redis
   brew services restart redis

   # Workers (rolling restart)
   pkill -HUP -f discovery_worker.py
   pkill -HUP -f provisioning_worker.py
   # ... etc
   ```

3. **Verify new certs**:
   ```bash
   ./scripts/pki/verify_mtls.sh
   ```

### Revocation (Future)

Currently, certificate revocation is handled by:
1. Not renewing expired certificates
2. Regenerating CA if compromised (nuclear option)

**TODO**: Implement CRL (Certificate Revocation List) or OCSP

---

## Security Considerations

### Private Key Protection

🔒 **CA Private Key** (`ca/ca-key.pem`):
- **MOST CRITICAL** - Can sign any certificate
- Permissions: `600` (owner read/write only)
- Consider encrypting with passphrase
- Store backup offline
- Restrict access to root/admin only

🔒 **Server/Client Private Keys**:
- Permissions: `600`
- Never commit to git
- Rotate annually or on compromise

### Certificate Chain Validation

All services validate the complete chain:
```
Leaf Certificate → Internal CA → (trusted)
```

### Defense in Depth

mTLS + Password Authentication:
```
Layer 1: Network (firewall)
Layer 2: TLS encryption (confidentiality)
Layer 3: mTLS (mutual authentication)
Layer 4: Redis password (additional auth)
```

### Monitoring

Monitor certificate expiration:
```bash
# Add to cron
0 0 * * * /Users/gabe/ai/bm/poc/scripts/pki/verify_mtls.sh | grep "EXPIRING"
```

---

## Troubleshooting

### Connection Refused

```
Error: Connection refused
```

**Check**:
- Redis TLS port enabled: `tls-port 6379`
- Firewall allows TLS port
- Redis listening on correct interface

### Certificate Verification Failed

```
Error: certificate verify failed
```

**Check**:
- CA certificate path correct
- Certificate signed by correct CA: `openssl verify -CAfile ca/ca-cert.pem redis/redis-cert.pem`
- Certificate not expired: `openssl x509 -in redis/redis-cert.pem -noout -enddate`

### Client Certificate Required

```
Error: peer did not return a certificate
```

**Check**:
- Client certificate and key provided
- Redis configured with `tls-auth-clients yes`
- Client certificate signed by same CA

### Hostname Mismatch

```
Error: certificate is valid for redis-server, not localhost
```

**Solution**: Add SAN (Subject Alternative Name) to certificate:
```bash
# Edit api/api.cnf to add DNS/IP entries
[alt_names]
DNS.1 = localhost
DNS.2 = redis-server
DNS.3 = 10.1.100.5
IP.1 = 127.0.0.1
IP.2 = 10.1.100.5
```

### Permission Denied

```
Error: Permission denied reading key file
```

**Fix permissions**:
```bash
chmod 600 pki/*/.*-key.pem
chmod 644 pki/*/.*-cert.pem
```

---

## Advanced Topics

### Multi-Site Deployment

**Option 1**: Shared CA (recommended)
- Use same CA across all sites
- Generate site-specific certificates
- Easy cross-site communication

**Option 2**: Per-site CAs
- Each site has own CA
- Sites trust each other's CAs
- More complex but better isolation

### Hardware Security Modules (HSM)

For production, consider storing CA key in HSM:
```bash
# Using PKCS#11
openssl ... -engine pkcs11 \
  -keyform engine \
  -key "pkcs11:token=HSM;object=ca-key"
```

### Certificate Monitoring

**Prometheus exporter** for certificate expiration:
```yaml
- job_name: 'cert-exporter'
  static_configs:
    - targets: ['localhost:9117']
  metric_relabel_configs:
    - source_labels: [cert_path]
      regex: '.*pki/.*'
      action: keep
```

### Automated Rotation

**Automated certificate renewal** with cron:
```bash
# /etc/cron.daily/renew-certs
#!/bin/bash
cd /Users/gabe/ai/bm/poc
./scripts/pki/renew_certs.sh
if [ $? -eq 0 ]; then
    # Reload services
    brew services restart redis
    pkill -HUP -f "worker.py"
fi
```

---

## Comparison with External CAs

| Feature | Internal PKI | External CA (Let's Encrypt) |
|---------|-------------|----------------------------|
| **Cost** | Free | Free |
| **Setup** | 5 minutes | Varies |
| **Validity** | Custom (10 years) | 90 days |
| **Renewal** | Manual/scripted | Automatic |
| **Private services** | ✅ Perfect | ❌ Public DNS required |
| **Control** | ✅ Complete | ❌ Limited |
| **Revocation** | Manual | ✅ Automatic (OCSP) |
| **Public trust** | ❌ No | ✅ Yes |
| **Internal services** | ✅ Yes | ⚠️ Possible |

**Recommendation**: Internal PKI for private services, External CA for public-facing APIs.

---

## Scripts Reference

### setup_pki.sh

Creates complete PKI infrastructure.

**Usage**:
```bash
# Default (10-year validity)
./scripts/pki/setup_pki.sh

# Custom validity
VALIDITY_DAYS=365 ./scripts/pki/setup_pki.sh

# Custom location
PKI_DIR=/opt/pki ./scripts/pki/setup_pki.sh
```

### renew_certs.sh

Renews certificates approaching expiration.

**Usage**:
```bash
# Renew if < 30 days remaining
./scripts/pki/renew_certs.sh

# Custom threshold
RENEW_DAYS=90 ./scripts/pki/renew_certs.sh
```

### verify_mtls.sh

Verifies PKI setup and certificate validity.

**Usage**:
```bash
./scripts/pki/verify_mtls.sh
```

---

## FAQ

**Q: Can I use these certificates for public websites?**
A: No, browsers won't trust your internal CA. Use Let's Encrypt for public sites.

**Q: How do I backup the PKI?**
A: Backup the entire `pki/` directory, especially `ca/ca-key.pem`.

**Q: What if CA private key is compromised?**
A: Regenerate entire PKI, redistribute CA certificate to all endpoints.

**Q: Can I have multiple worker certificates?**
A: Yes! Generate additional certs with setup script or manually.

**Q: Do I need to restart services after cert renewal?**
A: Yes, most services need restart to reload certificates.

**Q: Can I use different CAs for Redis and API?**
A: Yes, but complicates trust management. Single CA recommended.

---

## Production Checklist

- [ ] PKI generated with long validity (10 years)
- [ ] CA private key backed up offline
- [ ] CA private key encrypted with passphrase
- [ ] Private keys have 600 permissions
- [ ] Certificates verified with verify_mtls.sh
- [ ] Redis configured for mTLS
- [ ] Workers configured for mTLS
- [ ] API configured for HTTPS
- [ ] Certificate expiration monitoring enabled
- [ ] Renewal script in cron
- [ ] Documentation updated with certificate locations
- [ ] Team trained on certificate rotation
- [ ] Incident response plan for compromise

---

**Version**: 1.0
**Last Updated**: 2026-02-12
**Status**: Production Ready
