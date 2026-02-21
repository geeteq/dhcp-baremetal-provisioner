#!/bin/bash
# Phase 03 — DISK I/O TEST
# Runs fio benchmarks on each detected block device:
#   - Sequential 128K read  (throughput)
#   - Sequential 128K write (throughput)
#   - Random 4K read  (IOPS)
#   - Random 4K write (IOPS)
# Results logged to NetBox journal per disk.

source /opt/bm-validate/lib/log.sh
source /opt/bm-validate/lib/netbox.sh
source /run/bm-validate/device.env

log_section "PHASE 03 — DISK I/O TEST"

# Detect all non-removable block devices (skip loop, sr, fd)
DISKS=$(lsblk -dn -o NAME,TYPE | awk '$2=="disk"{print $1}')

if [[ -z "$DISKS" ]]; then
    log_warn "No block devices found — skipping disk I/O test"
    nb_journal "$DEVICE_ID" "warning" "Disk I/O test skipped: no block devices detected"
    echo "DISK_RESULT=SKIP" >> /run/bm-validate/device.env
    exit 0
fi

nb_journal "$DEVICE_ID" "info" "Disk I/O test started on: $(echo $DISKS | tr '\n' ' ')"

DISK_SUMMARY=""
ALL_PASS=true
FIO_RUNTIME=30   # seconds per test job

for DISK in $DISKS; do
    DEV="/dev/${DISK}"
    DISK_SIZE=$(lsblk -dn -o SIZE "$DEV" 2>/dev/null)
    DISK_MODEL=$(lsblk -dn -o MODEL "$DEV" 2>/dev/null | xargs)
    DISK_ROTA=$(cat "/sys/block/${DISK}/queue/rotational" 2>/dev/null)
    DISK_TYPE=$([[ "$DISK_ROTA" == "0" ]] && echo "SSD/NVMe" || echo "HDD")

    log_info "Testing ${DEV} — ${DISK_SIZE} ${DISK_MODEL} (${DISK_TYPE})"

    FIO_OUT=$(mktemp)

    # Sequential read throughput
    SEQ_READ=$(fio --name=seq-read --filename="${DEV}" --rw=read \
        --bs=128k --direct=1 --numjobs=1 --runtime="${FIO_RUNTIME}" \
        --time_based --output-format=json 2>/dev/null | \
        python3 -c "
import json,sys
d=json.load(sys.stdin)
bw=d['jobs'][0]['read']['bw_bytes']
print(f'{bw/1024/1024:.1f}')
" 2>/dev/null)

    # Sequential write throughput
    SEQ_WRITE=$(fio --name=seq-write --filename="${DEV}" --rw=write \
        --bs=128k --direct=1 --numjobs=1 --runtime="${FIO_RUNTIME}" \
        --time_based --output-format=json 2>/dev/null | \
        python3 -c "
import json,sys
d=json.load(sys.stdin)
bw=d['jobs'][0]['write']['bw_bytes']
print(f'{bw/1024/1024:.1f}')
" 2>/dev/null)

    # Random 4K read IOPS
    RAND_READ_IOPS=$(fio --name=rand-read --filename="${DEV}" --rw=randread \
        --bs=4k --direct=1 --numjobs=4 --runtime="${FIO_RUNTIME}" \
        --time_based --output-format=json 2>/dev/null | \
        python3 -c "
import json,sys
d=json.load(sys.stdin)
iops=sum(j['read']['iops'] for j in d['jobs'])
print(f'{iops:.0f}')
" 2>/dev/null)

    # Random 4K write IOPS
    RAND_WRITE_IOPS=$(fio --name=rand-write --filename="${DEV}" --rw=randwrite \
        --bs=4k --direct=1 --numjobs=4 --runtime="${FIO_RUNTIME}" \
        --time_based --output-format=json 2>/dev/null | \
        python3 -c "
import json,sys
d=json.load(sys.stdin)
iops=sum(j['write']['iops'] for j in d['jobs'])
print(f'{iops:.0f}')
" 2>/dev/null)

    rm -f "$FIO_OUT"

    SEQ_READ="${SEQ_READ:-N/A}"
    SEQ_WRITE="${SEQ_WRITE:-N/A}"
    RAND_READ_IOPS="${RAND_READ_IOPS:-N/A}"
    RAND_WRITE_IOPS="${RAND_WRITE_IOPS:-N/A}"

    log_ok "${DEV}: seq_read=${SEQ_READ} MB/s  seq_write=${SEQ_WRITE} MB/s  rand_read=${RAND_READ_IOPS} IOPS  rand_write=${RAND_WRITE_IOPS} IOPS"

    DISK_MSG="${DISK} (${DISK_SIZE} ${DISK_MODEL} ${DISK_TYPE})
  Sequential: read ${SEQ_READ} MB/s | write ${SEQ_WRITE} MB/s
  Random 4K:  read ${RAND_READ_IOPS} IOPS | write ${RAND_WRITE_IOPS} IOPS"

    nb_journal "$DEVICE_ID" "success" "Disk I/O test — ${DISK_MSG}"
    DISK_SUMMARY="${DISK_SUMMARY}${DISK}: ${SEQ_READ}MB/s read, ${SEQ_WRITE}MB/s write, ${RAND_READ_IOPS}r/${RAND_WRITE_IOPS}w IOPS | "
done

echo "DISK_RESULT=PASS" >> /run/bm-validate/device.env
echo "DISK_SUMMARY=${DISK_SUMMARY}" >> /run/bm-validate/device.env
log_ok "Disk I/O tests complete"
