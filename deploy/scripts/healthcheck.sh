#!/bin/bash
# Health check pour le service LAPI
# Appele par lapi-healthcheck.timer toutes les 60s

set -euo pipefail

LOG_TAG="lapi-healthcheck"
FAIL_COUNT_FILE="/tmp/lapi-healthcheck-fails"

log() { logger -t "$LOG_TAG" "$1"; }
fail() {
    log "ERREUR: $1"
    COUNT=$(cat "$FAIL_COUNT_FILE" 2>/dev/null || echo "0")
    COUNT=$((COUNT + 1))
    echo "$COUNT" > "$FAIL_COUNT_FILE"

    if [ "$COUNT" -ge 3 ]; then
        log "CRITICAL: $COUNT echecs consecutifs, redemarrage force"
        echo "0" > "$FAIL_COUNT_FILE"
        systemctl restart lapi.service
    fi
    exit 1
}

# 1. Verifier que le service LAPI tourne
if ! systemctl is-active --quiet lapi.service; then
    fail "Service LAPI inactif"
fi

# 2. Verifier que Mosquitto tourne
if ! systemctl is-active --quiet mosquitto.service; then
    log "WARN: Mosquitto inactif, redemarrage..."
    systemctl restart mosquitto.service
fi

# 3. Verifier la memoire du process LAPI
LAPI_PID=$(systemctl show -p MainPID --value lapi.service)
if [ "$LAPI_PID" != "0" ] && [ -d "/proc/$LAPI_PID" ]; then
    MEM_KB=$(awk '/VmRSS/{print $2}' /proc/$LAPI_PID/status 2>/dev/null || echo "0")
    MEM_MB=$((MEM_KB / 1024))
    if [ "$MEM_MB" -gt 600 ]; then
        log "WARN: Memoire LAPI elevee: ${MEM_MB}MB"
    fi
fi

# 4. Verifier l'espace disque
DISK_USAGE=$(df /var/lib/lapi --output=pcent 2>/dev/null | tail -1 | tr -d ' %')
if [ "${DISK_USAGE:-0}" -gt 90 ]; then
    log "WARN: Disque presque plein: ${DISK_USAGE}%"
    # Purger les vieux logs d'acces (> 30 jours)
    sqlite3 /var/lib/lapi/whitelist.db "DELETE FROM access_log WHERE timestamp < strftime('%s','now','-30 days');" 2>/dev/null || true
fi

# 5. Verifier la temperature GPU/CPU (Jetson)
if [ -f /sys/devices/virtual/thermal/thermal_zone0/temp ]; then
    TEMP=$(cat /sys/devices/virtual/thermal/thermal_zone0/temp)
    TEMP_C=$((TEMP / 1000))
    if [ "$TEMP_C" -gt 80 ]; then
        log "CRITICAL: Temperature CPU: ${TEMP_C}C"
    elif [ "$TEMP_C" -gt 70 ]; then
        log "WARN: Temperature CPU elevee: ${TEMP_C}C"
    fi
fi

# 6. Verifier la connectivite MQTT locale
if command -v mosquitto_pub &>/dev/null; then
    if ! timeout 3 mosquitto_pub -h 127.0.0.1 -u lapi -P lapi-local-secret \
         -t "lapi/healthcheck" -m "ping" -q 0 2>/dev/null; then
        fail "MQTT local injoignable"
    fi
fi

# Tout OK: reset compteur d'echecs
echo "0" > "$FAIL_COUNT_FILE"
log "OK (PID=$LAPI_PID, MEM=${MEM_MB:-?}MB, DISK=${DISK_USAGE:-?}%, TEMP=${TEMP_C:-?}C)"
