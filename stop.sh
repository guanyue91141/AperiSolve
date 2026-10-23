#!/usr/bin/env bash
# Stop the native stack started by start.sh.
# Kills by recorded PID first, then sweeps leftovers by exact command match.
# pkill -f on these patterns also matches the invoking shell, so avoid it here.
set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

for name in flask worker; do
    pidfile="logs/${name}.pid"
    if [ -f "$pidfile" ]; then
        pid="$(cat "$pidfile")"
        if kill "$pid" 2>/dev/null; then
            echo "==> stopped ${name} (pid ${pid})"
        fi
        rm -f "$pidfile"
    fi
done

# Sweep any orphans from a previous run, matching only real AperiSolve processes.
for pid in $(pgrep -f '\.venv/bin/python -m flask --app aperisolve' 2>/dev/null); do
    kill "$pid" 2>/dev/null && echo "==> stopped orphan flask (pid ${pid})"
done
for pid in $(pgrep -f '\.venv/bin/rq worker' 2>/dev/null); do
    kill "$pid" 2>/dev/null && echo "==> stopped orphan rq worker (pid ${pid})"
done
for pid in $(pgrep -x redis-server 2>/dev/null); do
    kill "$pid" 2>/dev/null && echo "==> stopped redis (pid ${pid})"
done

echo "Done."
