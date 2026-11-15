import os
from contextlib import contextmanager, asynccontextmanager
from functools import lru_cache
from typing import Any, Iterator

import psycopg
import redis
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from psycopg.rows import dict_row
from pydantic import BaseModel

API_VERSION = "v2"
FETCH_COUNTER_KEY = "meshbay_sample_fetch_count"

SCHEMA_STATEMENT = """
CREATE TABLE IF NOT EXISTS items (
    id serial primary key,
    name text not null,
    created_at timestamptz default now()
)
"""


class ItemPayload(BaseModel):
    name: str


def database_url() -> str:
    configured_url = os.getenv("DATABASE_URL")
    if not configured_url:
        raise RuntimeError("DATABASE_URL is required")
    return configured_url


@contextmanager
def database_connection() -> Iterator[psycopg.Connection]:
    connection = psycopg.connect(database_url(), row_factory=dict_row)
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


@lru_cache
def redis_client() -> redis.Redis | None:
    configured_url = os.getenv("REDIS_URL")
    if not configured_url:
        return None
    return redis.Redis.from_url(configured_url, decode_responses=True, socket_timeout=2)


def increment_fetch_counter() -> None:
    client = redis_client()
    if client is None:
        return
    try:
        client.incr(FETCH_COUNTER_KEY)
    except redis.RedisError:
        return


def read_fetch_counter() -> int | None:
    client = redis_client()
    if client is None:
        return None
    try:
        return int(client.get(FETCH_COUNTER_KEY) or 0)
    except redis.RedisError:
        return None


@asynccontextmanager
async def lifespan(application: FastAPI) -> Iterator[None]:
    with database_connection() as connection:
        connection.execute(SCHEMA_STATEMENT)
    yield


application = FastAPI(title="meshbay-sample-fastapi", lifespan=lifespan)
application.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app = application


@application.get("/health")
def read_health() -> dict[str, str]:
    return {"status": "ok", "version": API_VERSION}


@application.get("/api/items")
def read_items() -> list[dict[str, Any]]:
    with database_connection() as connection:
        records = connection.execute("SELECT id, name, created_at FROM items ORDER BY id").fetchall()
    increment_fetch_counter()
    return records


@application.post("/api/items", status_code=201)
def create_item(payload: ItemPayload) -> dict[str, Any]:
    item_name = payload.name.strip()
    if not item_name:
        raise HTTPException(status_code=400, detail="name is required")
    with database_connection() as connection:
        record = connection.execute(
            "INSERT INTO items (name) VALUES (%s) RETURNING id, name, created_at",
            (item_name,),
        ).fetchone()
    return record


@application.get("/api/items/{item_id}")
def read_item(item_id: int) -> dict[str, Any]:
    with database_connection() as connection:
        record = connection.execute(
            "SELECT id, name, created_at FROM items WHERE id = %s", (item_id,)
        ).fetchone()
    if record is None:
        raise HTTPException(status_code=404, detail="item not found")
    return record


@application.put("/api/items/{item_id}")
def update_item(item_id: int, payload: ItemPayload) -> dict[str, Any]:
    item_name = payload.name.strip()
    if not item_name:
        raise HTTPException(status_code=400, detail="name is required")
    with database_connection() as connection:
        record = connection.execute(
            "UPDATE items SET name = %s WHERE id = %s RETURNING id, name, created_at",
            (item_name, item_id),
        ).fetchone()
    if record is None:
        raise HTTPException(status_code=404, detail="item not found")
    return record


@application.delete("/api/items/{item_id}", status_code=204)
def delete_item(item_id: int) -> None:
    with database_connection() as connection:
        deleted = connection.execute(
            "DELETE FROM items WHERE id = %s RETURNING id", (item_id,)
        ).fetchone()
    if deleted is None:
        raise HTTPException(status_code=404, detail="item not found")
    return None


@application.get("/api/stats")
def read_stats() -> dict[str, Any]:
    with database_connection() as connection:
        record = connection.execute("SELECT count(*) AS total FROM items").fetchone()
    return {"items": record["total"], "fetches": read_fetch_counter()}


if __name__ == "__main__":
    uvicorn.run(application, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
