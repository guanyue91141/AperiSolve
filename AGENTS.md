# Repository Guidelines

## Project Structure

`aperisolve/` contains the Flask application, task queue integration, analyzer implementations (`aperisolve/analyzers/`), templates, static assets, translations, and English wiki/cheatsheet content. `tests/` holds pytest tests and sample files in `tests/fixtures/`. `docs/` contains focused developer guides; `scripts/` holds generators and maintenance tools. Docker, Compose, and deployment configuration live at the repository root and in `docker/`.

## Development and Quality Commands

- `uv sync --extra dev` installs the project and development tools.
- `uv run pytest -q` runs the regular test suite locally.
- `uv run ruff check .` and `uv run ruff format . --check` lint and check formatting.
- `uv run ty check aperisolve` checks application types. `./lint.sh` runs the full local quality pass.
- `docker compose -f compose.dev.yml up -d` starts the services for web workflow tests; run `uv run pytest tests/test_webapp_analyzers.py -v` against that stack. Set `APERISOLVE_BASE_URL` to target another running instance.
- `docker compose up -d` starts the default container stack.

## Code Style and Changes

Use Python 3.12+ and Ruff’s configured 100-character line length. Keep changes focused and follow nearby naming and typing patterns. Put analyzers in `aperisolve/analyzers/`; for a new analyzer, update its registry/result integration and display ordering, add test coverage and any required system tool to `Dockerfile`, and follow `docs/adding-analyzer.md`. When changing translatable UI strings, update and compile gettext catalogs as described in `CONTRIBUTING.md`.

## Testing

Name tests `tests/test_<feature>.py` and test behavior at the narrowest useful level. Analyzer changes should include fixture-based coverage; for new analyzers, cover the analyzer and its web-app result path. CI also checks coverage (`--cov-fail-under=55`), Ruff, `ty`, dependency advisories, and a Docker build on pull requests.

## Commits and Pull Requests

Use concise, descriptive commit subjects. Recent history uses conventional prefixes such as `feat:` and `style:`, while `CONTRIBUTING.md` also favors imperative summaries (for example, `Fix binwalk extraction error handling`). PRs should explain the user-visible change, link relevant issues, describe tests run, and mention any new dependency or Docker/system-tool requirement. Include screenshots for visible UI changes.

## Configuration and Data

Use `.env.example` as the configuration reference and keep secrets out of commits. Treat `data/`, local databases, logs, and analyzer results as runtime/user data; do not include them in changes unless a task explicitly requires it.
