# ALM Test Suite

## Backend tests

```bash
cd /path/to/ai_project

# Install backend with dev dependencies
pip install -e "backend[dev]"
pip install aiosqlite  # for SQLite in-memory test DB

# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=app --cov-report=html

# Run only unit tests
pytest tests/unit/ -v

# Run only API tests
pytest tests/api/ -v

# Run only integration tests
pytest tests/integration/ -v
```

## Frontend tests

```bash
cd frontend

# Install dependencies
npm install

# Run unit tests (watch mode)
npm run test:unit

# Run tests once with coverage
npm run test:unit -- --coverage

# Run a specific test file
npm run test:unit -- src/__tests__/stores/analysis.test.ts
```

## Test categories

- `tests/unit/` — unit tests for individual agents, adapters, services, and models
- `tests/api/` — FastAPI endpoint tests using the async in-process test client
- `tests/integration/` — multi-component pipeline tests (parse -> UCG -> smell detection)

## Notes

- All backend tests use SQLite in-memory (`sqlite+aiosqlite:///:memory:`) — no PostgreSQL required.
- Redis, RabbitMQ, and LLM APIs are fully mocked.
- Frontend tests use Vitest with jsdom and a mocked Cytoscape.js.
- Set `PYTHONPATH` to the `backend/` directory if pytest cannot find the `app` package:
  ```bash
  PYTHONPATH=backend pytest tests/ -v
  ```
