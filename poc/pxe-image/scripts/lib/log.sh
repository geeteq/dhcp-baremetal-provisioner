#!/bin/bash
# Logging helpers — writes to stdout and to /var/log/bm-validate.log

LOG_FILE="${LOG_FILE:-/var/log/bm-validate.log}"

_ts() { date '+%Y-%m-%dT%H:%M:%S'; }

log_info()    { echo "$(_ts) [INFO]    $*" | tee -a "$LOG_FILE"; }
log_ok()      { echo "$(_ts) [OK]      $*" | tee -a "$LOG_FILE"; }
log_warn()    { echo "$(_ts) [WARN]    $*" | tee -a "$LOG_FILE"; }
log_error()   { echo "$(_ts) [ERROR]   $*" | tee -a "$LOG_FILE" >&2; }
log_section() {
    local line="══════════════════════════════════════════════════"
    echo "" | tee -a "$LOG_FILE"
    echo "$(_ts) $line" | tee -a "$LOG_FILE"
    echo "$(_ts) ▶  $*" | tee -a "$LOG_FILE"
    echo "$(_ts) $line" | tee -a "$LOG_FILE"
}
