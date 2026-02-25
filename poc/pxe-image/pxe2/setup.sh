#!/bin/bash
# Run from your Mac after the VM is booted with run.sh.
# Installs required packages and copies bm-validate scripts to /opt on the VM.
#
# Requires sshpass: brew install hudochenkov/sshpass/sshpass
set -e

PASS="${VM_PASS:-bm2024}"
PORT="${VM_PORT:-2222}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BM_VALIDATE_SRC="$SCRIPT_DIR/../scripts"

# NetBox connection for the QEMU test VM (host is reachable at 10.0.2.2 via SLIRP)
NETBOX_URL="${NETBOX_URL:-http://10.0.2.2:8000}"
NETBOX_TOKEN="${NETBOX_TOKEN:-0123456789abcdef0123456789abcdef01234567}"

COMMON_OPTS=(-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null)

if ! command -v sshpass &>/dev/null; then
    echo "sshpass not found. Install it:"
    echo "  brew install hudochenkov/sshpass/sshpass"
    echo ""
    echo "Or run manually on the VM (ssh -p $PORT root@localhost, password: $PASS):"
    echo "  dnf install -y epel-release"
    echo "  dnf install -y memtester fio lldpad curl python3 ethtool iproute dmidecode"
    echo "  mkdir -p /opt/bm-validate && <copy scripts from $BM_VALIDATE_SRC>"
    exit 1
fi

ssh()  { sshpass -p "$PASS" command ssh  "${COMMON_OPTS[@]}" -p "$PORT"  "$@"; }
scp()  { sshpass -p "$PASS" command scp  "${COMMON_OPTS[@]}" -P "$PORT"  "$@"; }

# Wait for SSH to come up
echo "Waiting for SSH on port $PORT..."
until ssh -o ConnectTimeout=3 root@localhost true 2>/dev/null; do
    printf "."
    sleep 3
done
echo " connected."

echo ""
echo "── Installing packages ──────────────────────────────────────────"
ssh root@localhost "dnf install -y epel-release"
ssh root@localhost "dnf install -y memtester fio lldpad curl python3 ethtool iproute dmidecode"

echo ""
echo "── Copying bm-validate scripts to /opt/bm-validate ─────────────"
ssh root@localhost "mkdir -p /opt/bm-validate"
scp -r "$BM_VALIDATE_SRC"/. root@localhost:/opt/bm-validate/
ssh root@localhost "find /opt/bm-validate -name '*.sh' -exec chmod +x {} \;"

echo ""
echo "── Writing /etc/bm-validate.conf ───────────────────────────────"
ssh root@localhost "cat > /etc/bm-validate.conf <<'CONF'
NETBOX_URL=${NETBOX_URL}
NETBOX_TOKEN=${NETBOX_TOKEN}
CONF"
ssh root@localhost "chmod 600 /etc/bm-validate.conf"
echo "  NETBOX_URL=${NETBOX_URL}"

echo ""
echo "── Done ─────────────────────────────────────────────────────────"
echo "SSH in:  ssh -p $PORT root@localhost  (password: $PASS)"
echo "Verify:  ls /opt/bm-validate/"
