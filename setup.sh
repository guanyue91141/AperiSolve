#!/usr/bin/env bash
# One-time native setup. Creates the venv, installs Python deps, compiles
# gettext catalogs. Safe to re-run.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"
source ./env.local.sh

echo "==> project root: $PERISOLVE_DIR"

if [ ! -d .venv ]; then
    echo "==> creating virtualenv (.venv)"
    python3 -m venv .venv
fi

echo "==> installing Python dependencies"
# NOTE: psycopg2-binary is intentionally omitted -- env.local.sh points DB_URI
# at SQLite, so the PostgreSQL driver is dead weight. Everything else mirrors
# [project.dependencies] in pyproject.toml.
./.venv/bin/pip install --quiet --upgrade pip
./.venv/bin/pip install --quiet \
    "Flask>=3.1" "Flask-SQLAlchemy>=3.1" numpy redis rq "Pillow>=12.3" \
    gunicorn "sentry-sdk[flask,sqlalchemy,rq]" Markdown Pygments \
    flask-babel "Flask-Limiter[redis]" flask-sock

echo "==> compiling gettext catalogs"
./.venv/bin/pybabel compile -d aperisolve/translations

echo "==> creating database schema"
./.venv/bin/python - <<'PY'
from aperisolve.app import create_app
from aperisolve.models import db

app = create_app()
with app.app_context():
    db.create_all()
    print("    tables:", ", ".join(sorted(db.metadata.tables)))
PY

echo "==> probing external analyzer binaries"
for tool in file exiftool binwalk foremost strings identify 7z zip \
            steghide outguess openstego pngcheck gm ffmpeg pdfinfo pdfid \
            java jphide jpseek jsteg zsteg; do
    if command -v "$tool" >/dev/null 2>&1; then
        printf '    [ok]   %s\n' "$tool"
    else
        printf '    [MISS] %-10s (its analyzer will report status=error)\n' "$tool"
    fi
done

echo
echo "Setup done. Start the stack with:  ./start.sh"
