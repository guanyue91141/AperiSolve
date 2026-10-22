#!/usr/bin/env bash
# Start the native stack: redis -> rq worker -> flask.
# Logs go to ./logs/. Stop everything with ./stop.sh
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"
source ./env.local.sh

[ -d .venv ] || { echo "No .venv found. Run ./setup.sh first."; exit 1; }

mkdir -p logs

echo "==> local HTTPS certificate"
./.venv/bin/python scripts/generate_local_cert.py
TLS_DIR="${LOCAL_TLS_DIR:-$PERISOLVE_DIR/data/tls}"

echo "==> redis"
if redis-cli -p 6379 ping >/dev/null 2>&1; then
    echo "    already running"
else
    redis-server --daemonize yes --port 6379 --save '' --appendonly no
    for _ in $(seq 1 20); do
        redis-cli -p 6379 ping >/dev/null 2>&1 && break
        sleep 0.25
    done
    redis-cli -p 6379 ping >/dev/null 2>&1 || { echo "    FAILED to start redis"; exit 1; }
    echo "    started"
fi

echo "==> rq worker"
./.venv/bin/rq worker --url "$REDIS_URL" > logs/worker.log 2>&1 &
echo $! > logs/worker.pid
sleep 1.5

echo "==> flask"

# A stale instance from an earlier run holds the port and keeps answering on
# loopback, so the readiness probe below would go green while the server just
# launched died with EADDRINUSE. Reap a leftover of ours first, then refuse to
# continue if anything else still owns the port.
port_busy() { ss -tln 2>/dev/null | grep -q ":${FLASK_PORT}\b"; }

if port_busy; then
    mapfile -t stale < <(pgrep -f '\.venv/bin/python -m flask --app aperisolve' 2>/dev/null || true)
    if [ "${#stale[@]}" -gt 0 ]; then
        echo "    port ${FLASK_PORT} held by a previous AperiSolve (pid ${stale[*]}) - stopping it"
        kill "${stale[@]}" 2>/dev/null || true
        sleep 2
        kill -9 "${stale[@]}" 2>/dev/null || true
    fi
    if port_busy; then
        echo "    port ${FLASK_PORT} is still held by another program."
        echo "    Run ./stop.sh or free the port, then retry."
        exit 1
    fi
fi

./.venv/bin/python -m flask --app aperisolve.app:create_app run \
    --host "$FLASK_HOST" --port "$FLASK_PORT" \
    --cert "$TLS_DIR/server.crt" --key "$TLS_DIR/server.key" > logs/flask.log 2>&1 &
flask_pid=$!
echo "$flask_pid" > logs/flask.pid

for _ in $(seq 1 30); do
    curl -kfs -m 2 -o /dev/null "https://127.0.0.1:${FLASK_PORT}/" && break
    sleep 0.5
done

if ! curl -kfs -m 2 -o /dev/null "https://127.0.0.1:${FLASK_PORT}/"; then
    echo "Flask did not come up. See logs/flask.log:"
    tail -20 logs/flask.log
    exit 1
fi

# A green probe is not proof: confirm the listener belongs to the pid we just
# spawned, since anything else on this port would also answer.
if ! ss -tlnp 2>/dev/null | grep -q ":${FLASK_PORT} .*pid=${flask_pid},"; then
    echo "Warning: port ${FLASK_PORT} answers, but not from pid ${flask_pid}."
    echo "Another process is serving; expected bound address was ${FLASK_HOST}:${FLASK_PORT}."
fi

echo
echo "AperiSolve is up on ${FLASK_HOST}:${FLASK_PORT}"
echo
echo "  local:  https://127.0.0.1:${FLASK_PORT}/"
while read -r addr; do
    [ "$addr" = "127.0.0.1" ] && continue
    echo "  LAN:    https://${addr}:${FLASK_PORT}/"
done < <(ip -4 -o addr show scope global | awk '{split($4,a,"/"); print a[1]}')
echo
echo "On Windows, open the home page, download the local root certificate, then install it under Trusted Root Certification Authorities."
echo "Upload an image from the web form. Results are kept for ${MAX_STORE_TIME}s."
exit 0
