# AGENTS.md

## Cursor Cloud specific instructions

### Overview

ATLAS V1 is a Python-based nightly data pipeline for investment management. It uses Poetry for dependency management, SQLite for local dev, and Streamlit for the dashboard.

### Running services

- **CLI**: `poetry run atlas <command>` — see `README.md` "CLI Commands" for the full list.
- **Dashboard**: `ATLAS_ENV=development ATLAS_DB_CONNECTION=sqlite:///atlas_dev.db poetry run streamlit run src/atlas/dashboard/app.py --server.headless true --server.port 8501` — default login: `admin` / `atlas123`.
- **DB init**: `ATLAS_ENV=development ATLAS_DB_CONNECTION=sqlite:///atlas_dev.db poetry run atlas init-db` (avoid `--force` in non-interactive shells since it prompts for confirmation).

### Lint / type-check / test

- **Lint**: `poetry run ruff check src/`
- **Type check**: `poetry run mypy src/atlas/`
- **Tests**: `poetry run pytest` (the `tests/` directory is currently empty)

### Key gotchas

- The project venv is in-project at `.venv/`. Poetry is configured with `virtualenvs.in-project = true`.
- `ATLAS_DB_CONNECTION` env var must be set to `sqlite:///atlas_dev.db` for local dev; otherwise the app falls back to it but logs warnings about Key Vault failures.
- `ATLAS_ENV=development` loads `config/environments/development.yaml` which disables App Insights, raw archiving, and uses SQLite.
- API keys (`TIINGO_API_KEY`, `FRED_API_KEY`) are needed only to run the actual data pipeline (`atlas run`), not for lint/tests/dashboard.
- The `atlas init-db --force` subcommand has an interactive `typer.confirm()` prompt; avoid it in non-interactive contexts (use the Python snippet above instead).
- `PATH` must include `$HOME/.local/bin` for the `poetry` binary installed via pip.
- When running `atlas run` without specifying instruments, the Tiingo provider attempts to fetch its full instrument universe and may fail with a 404. Pass specific tickers via the dashboard or use `--providers fred` to test with FRED only.
- Feature calculation requires OHLCV price data in the database. Running only the FRED provider will log a benign `'adj_close'` error from the feature engine since macro data has no price columns.
