# AperiSolve — native (non-Docker) runtime environment.
# Source this before running anything:  source env.local.sh
#
# Differences from the upstream Docker Compose setup:
#   * SQLite replaces the postgres service.
#   * A localhost redis replaces the redis service.
#   * MAX_CONTENT_LENGTH is raised: upstream defaults to 1 MB, which rejects
#     anything larger with HTTP 413 before any analyzer runs.
#   * PATH gains the user gem bin dir, otherwise the RQ worker cannot find zsteg.

# Resolve the project root from this file's location so the setup stays portable.
PERISOLVE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
export PERISOLVE_DIR

export DB_URI="sqlite:///${PERISOLVE_DIR}/aperisolve.db"
export REDIS_URL="redis://127.0.0.1:6379/0"
export RATELIMIT_STORAGE_URI="redis://127.0.0.1:6379/1"

# 1 MB -> 16 MB. CTF images are routinely larger than the upstream cap.
export MAX_CONTENT_LENGTH=16777216

export FLASK_HOST="${FLASK_HOST:-0.0.0.0}"
export FLASK_PORT=5000
export PROJECT_VERSION=3.7.12-native

# Canonical origin for absolute links in pages. Empty falls back to the request's
# Host header (see aperisolve/app.py:_base_url).
export SITE_BASE_URL="${SITE_BASE_URL:-http://192.168.204.138:${FLASK_PORT:-5000}}"

# Security: the service is unauthenticated and runs 16 third-party binaries over
# uploaded files, so sweep submissions and results after 1 day rather than the
# upstream 3-day default.
export MAX_STORE_TIME=86400

# Ad/analytics are opt-in upstream; keep them off for local testing.
export GOOGLE_ADS_TXT=""
export CUSTOM_EXTERNAL_SCRIPT=""

# The `if` is load-bearing: callers run with `set -e`, and `[ -d ] && export`
# returns non-zero whenever the path is absent. As the final statement here that
# non-zero would become this file's exit status and abort the caller before it
# runs anything -- with no error message, since the failure is a test result.
for gem_bin in "$HOME/.local/share/gem/ruby/3.3.0/bin" "$HOME/.gem/ruby/3.3.0/bin"; do
    if [ -d "$gem_bin" ]; then
        export PATH="$gem_bin:$PATH"
    fi
done
