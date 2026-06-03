# Copyright (c) 2026 Ozan Küsmez. Licensed under Apache-2.0.
"""Cross-instance TraceStore tests: two stores on the same db file, dimension
mismatches, sqlite journal modes, and the kind of mistakes a deployer
will eventually make.
"""

from __future__ import annotations

import sqlite3

import pytest
from anamnesis.storage import ReasoningStep, TraceStore, hash_embedder


def test_two_stores_on_same_db_file_share_rows(tmp_path):
    db = tmp_path / "shared.db"
    a = TraceStore(embedder=hash_embedder(dim=64), db_path=db)
    a.add_steps([ReasoningStep.make("c", "alpha", "i_a"), ReasoningStep.make("c", "beta", "i_b")])
    a.close()

    b = TraceStore(embedder=hash_embedder(dim=64), db_path=db)
    # Both stores see the same persisted rows.
    assert b.n_steps == 2
    b.close()


def test_dimension_change_between_processes_isolates_via_rebuild(tmp_path):
    """If the user switches embedder dimension between sessions, the rebuild
    will compute new vectors. We just confirm no crash or shape mismatch
    when retrieving."""
    db = tmp_path / "dim.db"
    s1 = TraceStore(embedder=hash_embedder(dim=64), db_path=db)
    s1.add_steps([ReasoningStep.make("c", f"step {i} alpha beta gamma {i * 7}", f"i_{i}") for i in range(10)])
    s1.close()

    # Now reopen with a smaller dim. Embeddings get recomputed at dim=32.
    s2 = TraceStore(embedder=hash_embedder(dim=32), db_path=db)
    assert s2.n_steps == 10
    results = s2.query_similar_steps("step 3 alpha beta gamma 21", k=3)
    assert len(results) == 3


def test_close_releases_db_handle(tmp_path):
    db = tmp_path / "close.db"
    s = TraceStore(embedder=hash_embedder(dim=16), db_path=db)
    s.add_steps([ReasoningStep.make("c", "alpha", "i")])
    s.close()
    # After close we can open another sqlite connection to the file without error.
    conn = sqlite3.connect(str(db))
    row = conn.execute("SELECT COUNT(*) FROM steps").fetchone()
    assert row[0] == 1
    conn.close()


def test_in_memory_stores_are_isolated():
    """`:memory:` stores share no state."""
    s1 = TraceStore(embedder=hash_embedder(dim=16))
    s2 = TraceStore(embedder=hash_embedder(dim=16))
    s1.add_steps([ReasoningStep.make("c", "alpha", "i")])
    assert s1.n_steps == 1
    assert s2.n_steps == 0


def test_file_backed_store_persists_metadata(tmp_path):
    db = tmp_path / "meta.db"
    embedder = hash_embedder(dim=32)
    from anamnesis.capture import CapturedTrace

    s1 = TraceStore(embedder=embedder, db_path=db)
    trace = CapturedTrace(
        provider="anthropic",
        model="m",
        request_id="r",
        thinking_text="alpha",
        answer_text="ok",
        thinking_tokens=10,
        output_tokens=5,
        metadata={"custom_key": "custom_value"},
    )
    tid = s1.add_trace(trace)
    s1.close()

    s2 = TraceStore(embedder=embedder, db_path=db)
    recovered = s2.get_trace(tid)
    assert recovered.metadata == {"custom_key": "custom_value"}


def test_concurrent_opens_against_same_file(tmp_path):
    """Two TraceStore instances against the same file must not deadlock."""
    db = tmp_path / "concurrent.db"
    s1 = TraceStore(embedder=hash_embedder(dim=16), db_path=db)
    s1.add_steps([ReasoningStep.make("c", "alpha", "i")])

    s2 = TraceStore(embedder=hash_embedder(dim=16), db_path=db)
    # s2 reads what s1 already wrote.
    assert s2.n_steps == 1

    # s2 writes -- s1 keeps a stale in-memory count until something forces it
    # to re-query; but the underlying sqlite row count is increased.
    s2.add_steps([ReasoningStep.make("c", "beta", "i_b")])
    s2.close()

    s3 = TraceStore(embedder=hash_embedder(dim=16), db_path=db)
    assert s3.n_steps == 2
    s1.close()


def test_get_unknown_trace_after_reopen_raises(tmp_path):
    db = tmp_path / "unknown.db"
    s1 = TraceStore(embedder=hash_embedder(dim=16), db_path=db)
    s1.close()
    s2 = TraceStore(embedder=hash_embedder(dim=16), db_path=db)
    with pytest.raises(KeyError):
        s2.get_trace("trace_does_not_exist")
