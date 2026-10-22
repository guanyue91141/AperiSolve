#!/usr/bin/env bash
# Run AperiSolve from a terminal and stop the processes started for this run
# when that terminal exits.
set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"
source ./env.local.sh
# Listen on every interface, as requested for this desktop launcher.
export FLASK_HOST=0.0.0.0

read_pidfile() {
    local file="$1"
    if [[ -f "$file" ]]; then
        cat "$file"
    fi
}

old_flask_pid="$(read_pidfile logs/flask.pid)"
old_worker_pid="$(read_pidfile logs/worker.pid)"
old_redis_pid=""
if redis-cli -p 6379 ping >/dev/null 2>&1; then
    old_redis_pid="$(redis-cli -p 6379 info server 2>/dev/null | sed -n 's/^process_id:\([0-9][0-9]*\)\r\{0,1\}$/\1/p' | head -n 1)"
fi

cleaning=0
cleanup() {
    local name pid original_pid match current_cmd
    local flask_pid worker_pid redis_pid
    [[ "$cleaning" -eq 0 ]] || return
    cleaning=1
    trap - EXIT HUP INT TERM
    echo
    echo "Stopping AperiSolve..."

    flask_pid="$(read_pidfile logs/flask.pid)"
    worker_pid="$(read_pidfile logs/worker.pid)"
    for name in flask worker; do
        if [[ "$name" == flask ]]; then
            pid="$flask_pid"
            original_pid="$old_flask_pid"
            match="python -m flask --app aperisolve"
        else
            pid="$worker_pid"
            original_pid="$old_worker_pid"
            match="/.venv/bin/rq worker"
        fi
        [[ -n "$pid" && "$pid" != "$original_pid" ]] || continue
        current_cmd="$(ps -p "$pid" -o args= 2>/dev/null || true)"
        [[ "$current_cmd" == *"$match"* ]] || continue
        kill "$pid" 2>/dev/null || true
        for _ in {1..5}; do
            kill -0 "$pid" 2>/dev/null || break
            sleep 1
        done
        kill -0 "$pid" 2>/dev/null && kill -KILL "$pid" 2>/dev/null || true
        echo "Stopped $name (pid $pid)"
        if [[ "$name" == flask && "$(read_pidfile logs/flask.pid)" == "$pid" ]]; then
            rm -f logs/flask.pid
        elif [[ "$name" == worker && "$(read_pidfile logs/worker.pid)" == "$pid" ]]; then
            rm -f logs/worker.pid
        fi
    done

    if [[ -z "$old_redis_pid" ]] && redis-cli -p 6379 ping >/dev/null 2>&1; then
        redis_pid="$(redis-cli -p 6379 info server 2>/dev/null | sed -n 's/^process_id:\([0-9][0-9]*\)\r\{0,1\}$/\1/p' | head -n 1)"
        if [[ -n "$redis_pid" && "$redis_pid" != "$old_redis_pid" ]]; then
            redis-cli -p 6379 shutdown nosave >/dev/null 2>&1 || true
            echo "Stopped Redis started for this session (pid $redis_pid)"
        fi
    fi
}

trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

echo "Starting AperiSolve..."
if ! ./start.sh; then
    echo "AperiSolve did not start successfully. Check logs/ for details."
    exit 1
fi

flask_pid="$(read_pidfile logs/flask.pid)"
echo "AperiSolve is available at http://127.0.0.1:${FLASK_PORT}/"
echo "Close this terminal window to stop AperiSolve."

while [[ -n "$flask_pid" ]] && kill -0 "$flask_pid" 2>/dev/null; do
    sleep 1
done
