#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# build.sh — Build the BM-Validate live ISO
#
# Requirements (run on a Rocky Linux 9 / RHEL9 host):
#   dnf install lorax livemedia-creator
#   dnf install epel-release && dnf install memtester fio lldpad
#
# Usage:
#   sudo ./build.sh [--output /path/to/output]
#
# The ISO will be written to ./output/bm-validate.iso by default.
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUTPUT_DIR="${OUTPUT_DIR:-${SCRIPT_DIR}/output}"
ISO_NAME="bm-validate.iso"
ISO_LABEL="BM-VALIDATE"

# ── Preflight checks ─────────────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
    echo "ERROR: Must be run as root (livemedia-creator requires root)"
    exit 1
fi

if ! command -v livemedia-creator &>/dev/null; then
    echo "Installing livemedia-creator…"
    dnf install -y lorax
fi

mkdir -p "$OUTPUT_DIR"

# ── Stage scripts into /tmp for kickstart %post ───────────────────────────────
echo "Staging scripts…"
rm -rf /tmp/bm-validate-scripts /tmp/bm-validate-systemd
cp -r "${SCRIPT_DIR}/scripts"  /tmp/bm-validate-scripts
cp -r "${SCRIPT_DIR}/systemd"  /tmp/bm-validate-systemd
chmod -R +x /tmp/bm-validate-scripts

# ── Build the ISO ─────────────────────────────────────────────────────────────
echo "Building ISO — this takes 10-20 minutes…"
livemedia-creator \
    --ks "${SCRIPT_DIR}/ks.cfg" \
    --no-virt \
    --resultdir "${OUTPUT_DIR}" \
    --project "BM Validate" \
    --make-iso \
    --iso-only \
    --iso-name "${ISO_NAME}" \
    --releasever 9 \
    --volid "${ISO_LABEL}" \
    --logfile "${OUTPUT_DIR}/build.log" \
    2>&1 | tee "${OUTPUT_DIR}/build-console.log"

if [[ -f "${OUTPUT_DIR}/${ISO_NAME}" ]]; then
    SIZE=$(du -sh "${OUTPUT_DIR}/${ISO_NAME}" | cut -f1)
    echo ""
    echo "══════════════════════════════════════════════════════"
    echo "  ISO built successfully!"
    echo "  Path: ${OUTPUT_DIR}/${ISO_NAME}  (${SIZE})"
    echo ""
    echo "  Boot via IPMI virtual media or USB:"
    echo "    dd if=${OUTPUT_DIR}/${ISO_NAME} of=/dev/sdX bs=4M status=progress"
    echo ""
    echo "  PXE boot — add to your GRUB/syslinux config:"
    echo "    kernel vmlinuz root=live:LABEL=${ISO_LABEL} rd.live.image quiet"
    echo "    append bm.netbox_url=http://YOUR_NETBOX:8000"
    echo "           bm.netbox_token=YOUR_TOKEN"
    echo "           bm.callback_url=http://YOUR_ESB:5000"
    echo "══════════════════════════════════════════════════════"
else
    echo "ERROR: ISO not found at ${OUTPUT_DIR}/${ISO_NAME}"
    echo "Check ${OUTPUT_DIR}/build.log for errors"
    exit 1
fi
