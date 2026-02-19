from __future__ import annotations

from fk_quant_research_accel.store.migrations import init_db


def test_init_db_enables_wal_and_user_version(tmp_path) -> None:
    db_path = tmp_path / "experiments.db"
    conn = init_db(db_path)
    try:
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        user_version = conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()

    assert str(journal_mode).lower() == "wal"
    assert user_version == 1


def test_init_db_is_idempotent(tmp_path) -> None:
    db_path = tmp_path / "experiments.db"
    conn1 = init_db(db_path)
    conn1.close()

    conn2 = init_db(db_path)
    try:
        user_version = conn2.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn2.close()

    assert user_version == 1
