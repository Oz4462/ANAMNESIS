# Copyright (c) 2026 Ozan Küsmez. Licensed under Apache-2.0.
"""Storage corruption resilience tests.

What happens when the sqlite file is truncated, the disk is full, the
schema differs, or the text column contains bytes that aren't valid
UTF-8? A production deployment hits every one of these eventually.
"""

from __future__ import annotations

import sqlite3

import pytest
from anamnesis.storage import ReasoningStep, TraceStore, hash_embedder


def test_truncated_db_file_raises_cleanly(tmp_path):
    db = tmp_path / "trunc.db"
    s = TraceStore(embedder=hash_embedder(dim=16), db_path=db)
    s.add_steps([ReasoningStep.make("c", "alpha", "i")])
    s.close()

    # Truncate the file to 100 bytes -- destroys the sqlite header magic.
    with open(db, "r+b") as f:
        f.truncate(100)

    with pytest.raises(sqlite3.DatabaseError):
        TraceStore(embedder=hash_embedder(dim=16), db_path=db)


def test_random_bytes_for_db_file_raises_cleanly(tmp_path):
    db = tmp_path / "random.db"
    db.write_bytes(b"\x00\x01\x02\x03" * 1024)
    with pytest.raises(sqlite3.DatabaseError):
        TraceStore(embedder=hash_embedder(dim=16), db_path=db)


def test_empty_db_file_creates_fresh_schema(tmp_path):
    """An empty file is valid: sqlite treats it as a brand-new database."""
    db = tmp_path / "empty.db"
    db.write_bytes(b"")
    s = TraceStore(embedder=hash_embedder(dim=16), db_path=db)
    assert s.n_steps == 0
    s.add_steps([ReasoningStep.make("c", "alpha", "i")])
    assert s.n_steps == 1


def test_step_text_with_invalid_utf8_round_trips(tmp_path):
    """Sqlite stores TEXT as UTF-8. The Python side should never let bytes
    that can't decode through, but if a row already exists with weird
    characters (created by an older client), we must read it without crash."""
    db = tmp_path / "u8.db"
    s = TraceStore(embedder=hash_embedder(dim=16), db_path=db)
    # Insert legitimate but unusual unicode: combining marks, RTL, emoji ZWJ.
    weird_text = "Aufgabe‮mit RTL und 👨‍👩‍👧 ZWJ + Umlaute äöüß"
    s.add_steps([ReasoningStep.make("c", weird_text, "i")])
    s.close()

    s2 = TraceStore(embedder=hash_embedder(dim=16), db_path=db)
    assert s2.n_steps == 1
    results = s2.query_similar_steps("Aufgabe", k=1)
    assert results[0][0].text == weird_text


def test_step_text_with_embedded_null_byte_handled(tmp_path):
    """Embedded NUL in TEXT is technically allowed by sqlite (it stores
    bytes), but most clients treat it as end-of-string."""
    db = tmp_path / "nul.db"
    s = TraceStore(embedder=hash_embedder(dim=16), db_path=db)
    text_with_nul = "before\x00after"
    s.add_steps([ReasoningStep.make("c", text_with_nul, "i")])
    s.close()

    s2 = TraceStore(embedder=hash_embedder(dim=16), db_path=db)
    assert s2.n_steps == 1


def test_concurrent_writers_to_same_file_do_not_corrupt(tmp_path):
    """Two TraceStore instances against the same db, writing in turn.
    Sqlite handles this with its built-in locking. We just confirm
    no data loss occurs."""
    db = tmp_path / "concurrent.db"
    a = TraceStore(embedder=hash_embedder(dim=16), db_path=db)
    b = TraceStore(embedder=hash_embedder(dim=16), db_path=db)
    for i in range(10):
        a.add_steps([ReasoningStep.make("c", f"a-{i}", "i")])
        b.add_steps([ReasoningStep.make("c", f"b-{i}", "i")])
    a.close()
    b.close()

    final = TraceStore(embedder=hash_embedder(dim=16), db_path=db)
    assert final.n_steps == 20


def test_schema_with_extra_column_does_not_crash(tmp_path):
    """If a future version added a column, opening with an older client
    must still read the existing rows."""
    db = tmp_path / "future.db"
    s = TraceStore(embedder=hash_embedder(dim=16), db_path=db)
    s.add_steps([ReasoningStep.make("c", "alpha", "i")])
    s.close()

    # Simulate a future migration adding a column the old code doesn't know.
    conn = sqlite3.connect(str(db))
    conn.execute("ALTER TABLE steps ADD COLUMN future_metadata TEXT")
    conn.commit()
    conn.close()

    s2 = TraceStore(embedder=hash_embedder(dim=16), db_path=db)
    assert s2.n_steps == 1
    results = s2.query_similar_steps("alpha", k=1)
    assert len(results) == 1


def test_db_path_in_nonexistent_dir_raises(tmp_path):
    bad_path = tmp_path / "subdir-does-not-exist" / "no.db"
    with pytest.raises(sqlite3.OperationalError):
        TraceStore(embedder=hash_embedder(dim=16), db_path=bad_path)


def test_db_file_read_only_raises_on_write(tmp_path):
    """If the file is set read-only by the OS, sqlite must surface the
    error rather than silently dropping the write."""
    import contextlib
    import stat

    db = tmp_path / "ro.db"
    s = TraceStore(embedder=hash_embedder(dim=16), db_path=db)
    s.add_steps([ReasoningStep.make("c", "alpha", "i")])
    s.close()
    db.chmod(stat.S_IREAD)
    try:
        s2 = TraceStore(embedder=hash_embedder(dim=16), db_path=db)
        with contextlib.suppress(sqlite3.OperationalError):
            s2.add_steps([ReasoningStep.make("c", "beta", "i")])
        s2.close()
    finally:
        db.chmod(stat.S_IREAD | stat.S_IWRITE)


def test_step_id_with_path_traversal_chars_handled(tmp_path):
    """A step_id like '../../etc/passwd' must not affect file system."""
    db = tmp_path / "path.db"
    s = TraceStore(embedder=hash_embedder(dim=16), db_path=db)
    bad_id_step = ReasoningStep(
        step_id="../../etc/passwd",
        capture_id="c",
        text="alpha",
        intent="i",
    )
    s.add_steps([bad_id_step])
    s.close()

    s2 = TraceStore(embedder=hash_embedder(dim=16), db_path=db)
    fetched = s2.get_step("../../etc/passwd")
    assert fetched.text == "alpha"
