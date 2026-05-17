"""Local storage for captured traces and distilled reasoning steps.

The MVP keeps everything on the same machine to remove cloud-account friction:

    * Trace + step metadata live in a sqlite database (works in-memory for tests).
    * Step embeddings live in a numpy matrix held alongside the database.

The TraceStore exposes a small surface that the rest of the pipeline consumes:
add a trace, add its distilled steps, query for similar past steps, and
recover the full step record by id for prompt composition or audit replay.

This module is intentionally embedder-agnostic. An `Embedder` is just a
callable that maps a string to a 1-D float ndarray. Production callers will
plug in an actual model (e.g. text-embedding-3-small). Tests use a deterministic
hash-based embedder so behaviour is reproducible without network access.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from anamnesis.capture import CapturedTrace

Embedder = Callable[[str], np.ndarray]


@dataclass(frozen=True, slots=True)
class ReasoningStep:
    """An atomic, retrievable unit of reasoning extracted from a trace."""

    step_id: str
    capture_id: str
    text: str
    intent: str
    preconditions: tuple[str, ...] = ()
    produces: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()

    @classmethod
    def make(
        cls,
        capture_id: str,
        text: str,
        intent: str,
        preconditions: Iterable[str] = (),
        produces: Iterable[str] = (),
        tags: Iterable[str] = (),
    ) -> ReasoningStep:
        return cls(
            step_id="step_" + uuid.uuid4().hex[:16],
            capture_id=capture_id,
            text=text,
            intent=intent,
            preconditions=tuple(preconditions),
            produces=tuple(produces),
            tags=tuple(tags),
        )


@dataclass(slots=True)
class StoredTrace:
    """A captured trace as recorded in storage, with its persistent id."""

    trace_id: str
    trace: CapturedTrace


_SCHEMA = """
CREATE TABLE IF NOT EXISTS traces (
    trace_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    request_id TEXT NOT NULL,
    thinking_text TEXT NOT NULL,
    answer_text TEXT NOT NULL,
    thinking_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    signature TEXT,
    content_hash TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS steps (
    step_id TEXT PRIMARY KEY,
    capture_id TEXT NOT NULL,
    text TEXT NOT NULL,
    intent TEXT NOT NULL,
    preconditions_json TEXT NOT NULL DEFAULT '[]',
    produces_json TEXT NOT NULL DEFAULT '[]',
    tags_json TEXT NOT NULL DEFAULT '[]',
    embedding_idx INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_steps_capture_id ON steps(capture_id);
"""


class TraceStore:
    """Sqlite + in-process numpy vector index for traces and steps."""

    def __init__(self, embedder: Embedder, db_path: str | Path = ":memory:") -> None:
        self._embedder = embedder
        self._db_path = str(db_path)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        self._lock = threading.RLock()

        self._embeddings: list[np.ndarray] = []
        self._step_ids: list[str] = []
        self._rebuild_index_from_sqlite()

    def _rebuild_index_from_sqlite(self) -> None:
        """Recompute embeddings for every step row that already exists.

        Called once on __init__ so a file-backed TraceStore is queryable as
        soon as the process starts. Without this, sqlite rows survive across
        a restart but `query_similar_steps` returns empty until the caller
        re-adds the steps. The cost is one embedder call per persisted step;
        for moderate stores this is small (10K steps × hash_embedder ~= 1s).
        """
        with self._lock:
            cur = self._conn.execute(
                "SELECT step_id, text FROM steps ORDER BY embedding_idx ASC"
            )
            rows = cur.fetchall()
            for row in rows:
                vec = _normalize(self._embedder(row["text"]))
                self._embeddings.append(vec)
                self._step_ids.append(row["step_id"])

    @property
    def n_steps(self) -> int:
        return len(self._step_ids)

    @property
    def n_traces(self) -> int:
        cur = self._conn.execute("SELECT COUNT(*) AS c FROM traces")
        return int(cur.fetchone()["c"])

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def add_trace(self, trace: CapturedTrace) -> str:
        trace_id = "trace_" + uuid.uuid4().hex[:16]
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO traces (
                    trace_id, provider, model, request_id,
                    thinking_text, answer_text, thinking_tokens, output_tokens,
                    signature, content_hash, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trace_id,
                    trace.provider,
                    trace.model,
                    trace.request_id,
                    trace.thinking_text,
                    trace.answer_text,
                    trace.thinking_tokens,
                    trace.output_tokens,
                    trace.signature,
                    trace.content_hash,
                    json.dumps(trace.metadata, sort_keys=True),
                ),
            )
            self._conn.commit()
        return trace_id

    def add_steps(self, steps: Iterable[ReasoningStep]) -> list[str]:
        rows: list[tuple] = []
        added_ids: list[str] = []
        with self._lock:
            for step in steps:
                vec = _normalize(self._embedder(step.text))
                idx = len(self._embeddings)
                self._embeddings.append(vec)
                self._step_ids.append(step.step_id)
                rows.append(
                    (
                        step.step_id,
                        step.capture_id,
                        step.text,
                        step.intent,
                        json.dumps(list(step.preconditions)),
                        json.dumps(list(step.produces)),
                        json.dumps(list(step.tags)),
                        idx,
                    )
                )
                added_ids.append(step.step_id)
            if rows:
                self._conn.executemany(
                    """
                    INSERT INTO steps (
                        step_id, capture_id, text, intent,
                        preconditions_json, produces_json, tags_json, embedding_idx
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    rows,
                )
                self._conn.commit()
        return added_ids

    def get_step(self, step_id: str) -> ReasoningStep:
        with self._lock:
            cur = self._conn.execute("SELECT * FROM steps WHERE step_id = ?", (step_id,))
            row = cur.fetchone()
        if row is None:
            raise KeyError(step_id)
        return _row_to_step(row)

    def get_trace(self, trace_id: str) -> CapturedTrace:
        with self._lock:
            cur = self._conn.execute("SELECT * FROM traces WHERE trace_id = ?", (trace_id,))
            row = cur.fetchone()
        if row is None:
            raise KeyError(trace_id)
        return CapturedTrace(
            provider=row["provider"],
            model=row["model"],
            request_id=row["request_id"],
            thinking_text=row["thinking_text"],
            answer_text=row["answer_text"],
            thinking_tokens=row["thinking_tokens"],
            output_tokens=row["output_tokens"],
            signature=row["signature"],
            metadata=json.loads(row["metadata_json"]),
        )

    def query_similar_steps(
        self,
        text: str,
        k: int = 5,
    ) -> list[tuple[ReasoningStep, float]]:
        """Return up to k most similar steps with the non-conformity score d = 1 - cos."""
        with self._lock:
            if not self._embeddings:
                return []
            q = _normalize(self._embedder(text))
            matrix = np.vstack(self._embeddings)
            sims = matrix @ q
            scores = 1.0 - sims
            order = np.argsort(scores)[: max(0, k)]
            ids_to_fetch = [self._step_ids[int(idx)] for idx in order]
            local_scores = [float(scores[int(idx)]) for idx in order]
        return [
            (self.get_step(sid), s)
            for sid, s in zip(ids_to_fetch, local_scores, strict=True)
        ]

    def list_steps_for_trace(self, capture_id: str) -> list[ReasoningStep]:
        with self._lock:
            cur = self._conn.execute("SELECT * FROM steps WHERE capture_id = ?", (capture_id,))
            rows = cur.fetchall()
        return [_row_to_step(r) for r in rows]


def _row_to_step(row: sqlite3.Row) -> ReasoningStep:
    return ReasoningStep(
        step_id=row["step_id"],
        capture_id=row["capture_id"],
        text=row["text"],
        intent=row["intent"],
        preconditions=tuple(json.loads(row["preconditions_json"])),
        produces=tuple(json.loads(row["produces_json"])),
        tags=tuple(json.loads(row["tags_json"])),
    )


def _normalize(v: np.ndarray) -> np.ndarray:
    arr = np.asarray(v, dtype=np.float64)
    n = np.linalg.norm(arr)
    if n == 0.0:
        raise ValueError("cannot normalize a zero vector")
    return arr / n


def hash_embedder(dim: int = 64) -> Embedder:
    """Deterministic test-friendly embedder.

    Maps each token to a unit vector derived from a SHA-256 hash and sums
    them. Stable across runs, free of network calls, sufficient for
    similarity-based unit tests.
    """

    def embed(text: str) -> np.ndarray:
        vec = np.zeros(dim, dtype=np.float64)
        if not text:
            vec[0] = 1.0
            return vec
        for token in text.lower().split():
            h = hashlib.sha256(token.encode()).digest()
            for i in range(dim):
                vec[i] += (h[i % len(h)] / 255.0) - 0.5
        n = np.linalg.norm(vec)
        if n == 0.0:
            vec[0] = 1.0
            return vec
        return vec / n

    return embed


def fastembed_embedder(
    model_name: str = "BAAI/bge-small-en-v1.5",
    cache_dir: str | Path | None = None,
) -> Embedder:
    """Real sentence-embedder powered by `fastembed` (ONNX runtime, no API keys).

    Lazy-imports `fastembed` so the package stays an optional extra.
    """
    try:
        from fastembed import TextEmbedding  # type: ignore
    except ImportError as e:
        raise ImportError(
            "fastembed is not installed. Install with: "
            "uv pip install 'anamnesis[embed]' or `uv pip install fastembed`."
        ) from e

    model = TextEmbedding(
        model_name=model_name,
        cache_dir=str(cache_dir) if cache_dir else None,
    )

    def embed(text: str) -> np.ndarray:
        if not text:
            text = " "
        gen = model.embed([text])
        vec = np.asarray(next(iter(gen)), dtype=np.float64)
        n = np.linalg.norm(vec)
        if n == 0.0:
            vec[0] = 1.0
            return vec
        return vec / n

    return embed


def embedder_for(name: str | None = None, **kwargs) -> Embedder:
    """Factory: pick an embedder by name.

    Names:
        "hash"      -> hash_embedder(**kwargs)
        "fastembed" -> fastembed_embedder(**kwargs)
        None        -> defaults to fastembed if available, else hash. kwargs
                       are dropped in the default path because the two
                       embedders share no parameters.
    """
    if name is None:
        try:
            return fastembed_embedder()
        except ImportError:
            return hash_embedder()
    n = name.lower()
    if n == "hash":
        return hash_embedder(**kwargs)
    if n == "fastembed":
        return fastembed_embedder(**kwargs)
    raise ValueError(f"unknown embedder {name!r}")
