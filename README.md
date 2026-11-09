# meshbay-sample-fastapi

FastAPI on Python 3.12 (managed with `uv`), backed by Postgres and Redis, for the Meshbay vs Railway side-by-side
test. Table creation runs on startup, so no migration step is needed.

## Environment

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | yes | none | Postgres connection string, e.g. `postgres://user:password@host:5432/app` |
| `REDIS_URL` | no | none | Redis connection string, e.g. `redis://host:6379/0`. Without it `/api/stats` returns `fetches: null` |
| `PORT` | no | `8080` | HTTP port |

Redis is used for the request counter behind `/api/stats`; the item list itself lives in Postgres. If Redis is
unreachable the API keeps serving items and `fetches` is `null`.

## Run locally

```sh
uv sync
DATABASE_URL=postgres://postgres:postgres@localhost:5432/app \
REDIS_URL=redis://localhost:6379/0 \
uv run uvicorn main:app --host 0.0.0.0 --port 8080
```

or, for the framework's own runner:

```sh
uv run fastapi run main.py --port 8080
```

`main.py` also runs standalone (`uv run python main.py`), reading `PORT`.

## Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | `200 {"status":"ok","version":"v1"}` |
| GET | `/api/items` | JSON array of items |
| POST | `/api/items` | Body `{"name":"..."}` → `201` with the created item |
| GET | `/api/stats` | `{"items": <count>, "fetches": <redis counter or null>}` |

```sh
curl localhost:8080/health
curl -X POST localhost:8080/api/items -H 'content-type: application/json' -d '{"name":"first"}'
curl localhost:8080/api/items
curl localhost:8080/api/stats
```

Interactive docs are at `/docs`. CORS is open for every origin.

`version` in `/health` is `API_VERSION` in `main.py`; change it to test a redeploy.
