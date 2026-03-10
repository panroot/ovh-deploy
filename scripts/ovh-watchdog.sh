#!/bin/bash
# =============================================================================
# OVH AI Deploy WATCHDOG - uruchom na INNYM serwerze jako cron
# Zabija instancje ktore przekrocza limit kosztow lub czasu
#
# Instalacja na zewnetrznym serwerze:
#   1. Zainstaluj ovhai CLI i zaloguj sie (ovhai login)
#   2. Skopiuj ten skrypt
#   3. Dodaj do crona: */5 * * * * /path/to/ovh-watchdog.sh
#
# Konfiguracja (zmien ponizej):
# =============================================================================

MAX_COST_PLN=50           # Max koszt na sesje (PLN) - ubij jesli przekroczy
MAX_HOURS=10              # Max godzin pracy - ubij jesli przekroczy
COST_PER_HOUR=8.90        # L40S brutto PLN/h
ALERT_EMAIL="lukasz@orzechowski.eu"  # Email na alerty
LOG_FILE="/var/log/ovh-watchdog.log"

# =============================================================================

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $1" | tee -a "$LOG_FILE"
}

send_alert() {
    local subject="$1"
    local body="$2"
    echo "$body" | mail -s "[OVH WATCHDOG] $subject" "$ALERT_EMAIL" 2>/dev/null || true
    log "ALERT SENT: $subject"
}

# Sprawdz czy ovhai jest dostepne
if ! command -v ovhai &>/dev/null; then
    source ~/.bashrc 2>/dev/null
    export PATH="$HOME/bin:$PATH"
fi

if ! command -v ovhai &>/dev/null; then
    log "ERROR: ovhai not found"
    exit 1
fi

# Pobierz liste dzialajacych appek
APPS_JSON=$(ovhai app list --output json 2>/dev/null)
if [ -z "$APPS_JSON" ]; then
    exit 0
fi

# Sprawdz kazda appke
echo "$APPS_JSON" | python3 -c "
import sys, json
from datetime import datetime, timezone

apps = json.load(sys.stdin)
MAX_COST = $MAX_COST_PLN
MAX_HOURS = $MAX_HOURS
COST_H = $COST_PER_HOUR

for app in apps:
    state = app.get('status', {}).get('state', '')
    if state not in ('RUNNING', 'SCALING', 'INITIALIZING'):
        continue

    app_id = app['id']
    name = app.get('spec', {}).get('name', '?')
    created = app.get('createdAt', '')

    # Oblicz czas pracy
    try:
        created_dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        hours = (now - created_dt).total_seconds() / 3600
        cost = hours * COST_H
    except:
        hours = 0
        cost = 0

    print(f'APP|{app_id}|{name}|{state}|{hours:.2f}|{cost:.2f}')
" 2>/dev/null | while IFS='|' read -r prefix app_id name state hours cost; do
    log "Check: $name ($app_id) state=$state hours=$hours cost=${cost}PLN"

    # Sprawdz limit kosztow
    if (( $(echo "$cost > $MAX_COST_PLN" | bc -l 2>/dev/null || echo 0) )); then
        log "KILL: $name - cost ${cost}PLN exceeds limit ${MAX_COST_PLN}PLN"
        send_alert "KOSZT PRZEKROCZONY - WYŁĄCZAM" \
            "Aplikacja: $name ($app_id)\nCzas pracy: ${hours}h\nKoszt: ${cost} PLN\nLimit: ${MAX_COST_PLN} PLN\n\nAplikacja zostala WYLACZONA automatycznie."
        ovhai app delete "$app_id" --force 2>/dev/null
        continue
    fi

    # Sprawdz limit czasu
    if (( $(echo "$hours > $MAX_HOURS" | bc -l 2>/dev/null || echo 0) )); then
        log "KILL: $name - uptime ${hours}h exceeds limit ${MAX_HOURS}h"
        send_alert "CZAS PRZEKROCZONY - WYŁĄCZAM" \
            "Aplikacja: $name ($app_id)\nCzas pracy: ${hours}h\nLimit: ${MAX_HOURS}h\nKoszt: ${cost} PLN\n\nAplikacja zostala WYLACZONA automatycznie."
        ovhai app delete "$app_id" --force 2>/dev/null
        continue
    fi

    # Alert na 80% limitu
    WARNING_COST=$(echo "$MAX_COST_PLN * 0.8" | bc -l 2>/dev/null || echo 999)
    if (( $(echo "$cost > $WARNING_COST" | bc -l 2>/dev/null || echo 0) )); then
        log "WARNING: $name approaching cost limit (${cost}/${MAX_COST_PLN} PLN)"
        send_alert "UWAGA - 80% limitu kosztow" \
            "Aplikacja: $name ($app_id)\nCzas pracy: ${hours}h\nKoszt: ${cost} PLN (limit: ${MAX_COST_PLN} PLN)\n\nAplikacja nadal dziala. Zostanie wylaczona przy ${MAX_COST_PLN} PLN."
    fi
done

log "Watchdog check complete."
