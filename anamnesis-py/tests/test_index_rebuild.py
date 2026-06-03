# Copyright (c) 2026 Ozan Küsmez. Licensed under Apache-2.0.
"""Verify the in-memory vector index is rebuilt from sqlite on init.

This was a known limitation in v0.2.2: traces persisted to disk survived
a server restart, but query_similar_steps returned empty until the
caller manually re-added the steps. The fix rebuilds the index from
the steps.text column on startup.
"""

from __future__ import annotations

import numpy as np
from anamnesis.storage import ReasoningStep, TraceStore, hash_embedder


def test_index_rebuilds_from_sqlite_on_init(tmp_path):
    db = tmp_path / "rebuild.db"
    embedder = hash_embedder(dim=64)

    s1 = TraceStore(embedder=embedder, db_path=db)
    steps = [
        ReasoningStep.make("cap_a", "Compute the area of a triangle from base and height.", "triangle"),
        ReasoningStep.make("cap_a", "Bake a sourdough loaf overnight.", "bake"),
        ReasoningStep.make("cap_b", "Solve a quadratic equation by completing the square.", "quadratic"),
        ReasoningStep.make("cap_b", "Compute the volume of a sphere with radius r.", "sphere"),
    ]
    s1.add_steps(steps)
    wanted_top_text = steps[0].text
    s1.close()

    s2 = TraceStore(embedder=embedder, db_path=db)
    assert s2.n_steps == 4

    results = s2.query_similar_steps("How do I compute area of a triangle?", k=2)
    assert len(results) == 2
    top_step, _score = results[0]
    assert top_step.text == wanted_top_text


def test_index_rebuild_preserves_score_ordering(tmp_path):
    db = tmp_path / "rebuild_order.db"
    embedder = hash_embedder(dim=64)
    s1 = TraceStore(embedder=embedder, db_path=db)
    s1.add_steps([
        ReasoningStep.make("c", f"step number {i} unique words {i * 7}", f"i_{i}")
        for i in range(20)
    ])

    query = "step number 5 unique words 35"
    pre = s1.query_similar_steps(query, k=5)
    pre_ids = [s.step_id for s, _ in pre]
    s1.close()

    s2 = TraceStore(embedder=embedder, db_path=db)
    post = s2.query_similar_steps(query, k=5)
    post_ids = [s.step_id for s, _ in post]
    assert pre_ids == post_ids


def test_index_rebuild_empty_db_is_silent(tmp_path):
    db = tmp_path / "empty.db"
    s = TraceStore(embedder=hash_embedder(dim=16), db_path=db)
    assert s.n_steps == 0
    assert s.query_similar_steps("nothing", k=3) == []


def test_index_rebuild_size_matches_disk(tmp_path):
    db = tmp_path / "size.db"
    embedder = hash_embedder(dim=32)
    s1 = TraceStore(embedder=embedder, db_path=db)
    s1.add_steps([
        ReasoningStep.make("c", f"text {i}", f"i_{i}")
        for i in range(500)
    ])
    s1.close()

    s2 = TraceStore(embedder=embedder, db_path=db)
    assert s2.n_steps == 500
    matrix = np.vstack(s2._embeddings)
    assert matrix.shape == (500, 32)


def test_full_server_restart_recovers_retrieval(tmp_path):
    from anamnesis.conformal import ConformalCalibrator
    from anamnesis.retrieve import ConformalRetriever

    db = tmp_path / "full_restart.db"
    embedder = hash_embedder(dim=128)

    s1 = TraceStore(embedder=embedder, db_path=db)
    s1.add_steps([
        ReasoningStep.make(
            capture_id="cap",
            text="Compute the area of a triangle from base and height using A equals one half times b times h.",
            intent="triangle area",
        ),
        ReasoningStep.make(
            capture_id="cap",
            text="Solve a linear equation by isolating x.",
            intent="linear eq",
        ),
    ])
    s1.close()

    s2 = TraceStore(embedder=embedder, db_path=db)
    cal = ConformalCalibrator(alpha=0.1, min_calibration=30)
    cal.extend([0.4, 0.5, 0.6, 0.7, 0.75] * 8)
    retriever = ConformalRetriever(store=s2, calibrator=cal, k=2)
    result = retriever.retrieve("How do I compute the area of a triangle?")
    assert len(result.candidates) == 2
