#!/usr/bin/env bash
# Keep the selected component in the foreground for systemd supervision.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
source ./env.local.sh

case "${1:-}" in
    web)
        exec ./.venv/bin/python -m flask --app aperisolve.app:create_app run \
            --host "$FLASK_HOST" --port "$FLASK_PORT"
        ;;
    worker)
        exec ./.venv/bin/rq worker --url "$REDIS_URL"
        ;;
    *)
        echo "Usage: $0 {web|worker}" >&2
        exit 2
        ;;
esac
