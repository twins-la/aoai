"""Concurrency test for the per-resource signing-key cold-start race.

Closes twins-la/aoai#2: under sustained parallel cold-start traffic against
a fresh resource, ``crypto.ensure_keypair`` must produce exactly one stored
keypair, not one per racing thread. The fix is the atomic
``storage.get_or_create_signing_key`` primitive.
"""

import threading
import sqlite3

import pytest

from twins_aoai.crypto import ensure_keypair
from twins_aoai_local.storage_sqlite import SQLiteStorage


@pytest.fixture
def storage(tmp_path):
    return SQLiteStorage(db_path=str(tmp_path / "race_test.db"))


def test_ensure_keypair_serializes_concurrent_first_calls(storage):
    """N threads calling ensure_keypair against a fresh resource must yield:
    (a) exactly one row in the signing_keys table,
    (b) every returned dict carrying the same kid (the canonical first key).
    """
    resource_id = "race-resource"
    n_threads = 16
    results: list[dict] = []
    errors: list[BaseException] = []
    barrier = threading.Barrier(n_threads)

    def worker():
        try:
            barrier.wait()  # release all threads simultaneously
            results.append(ensure_keypair(storage, resource_id))
        except BaseException as exc:  # pragma: no cover — surfaces in test
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"workers raised: {errors}"
    assert len(results) == n_threads

    # Every caller must see the same kid — the one that won the race and was
    # persisted. If any caller saw a different kid, the get-or-create
    # primitive failed to serialize.
    kids = {r["kid"] for r in results}
    assert len(kids) == 1, f"expected one canonical kid, got {len(kids)}: {kids}"

    # And the table must have exactly one row.
    conn = sqlite3.connect(str(storage._db_path))
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM signing_keys WHERE resource_id = ?",
            (resource_id,),
        ).fetchone()[0]
    finally:
        conn.close()
    assert count == 1, f"expected one signing_keys row, got {count}"


def test_ensure_keypair_is_idempotent_on_steady_state(storage):
    """Sequential calls after the key exists must return the same dict each time."""
    resource_id = "steady-resource"
    first = ensure_keypair(storage, resource_id)
    second = ensure_keypair(storage, resource_id)
    third = ensure_keypair(storage, resource_id)
    assert first["kid"] == second["kid"] == third["kid"]
    assert first["private_pem"] == second["private_pem"] == third["private_pem"]
