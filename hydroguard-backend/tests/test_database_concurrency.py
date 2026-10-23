"""Tests for SQLite concurrency, WAL mode, busy timeout, and transaction robustness."""

import concurrent.futures
from datetime import datetime, timezone
import time
from typing import List

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session

from app.db.database import engine, get_db, get_db_context, init_db
from app.db.models import Base, Node, SensorReading


def test_sqlite_pragmas_configured():
    """Verify WAL mode is set via init_db and connection pragmas are active."""
    init_db()
    with engine.connect() as conn:
        journal_mode = conn.execute(text("PRAGMA journal_mode;")).scalar()
        busy_timeout = conn.execute(text("PRAGMA busy_timeout;")).scalar()
        synchronous = conn.execute(text("PRAGMA synchronous;")).scalar()

    # journal_mode returns 'wal' for disk files, or 'memory' for in-memory databases
    assert str(journal_mode).lower() in ("wal", "memory")
    assert busy_timeout == 5000
    assert synchronous == 1  # 1 = NORMAL


def test_get_db_context_rollback_on_exception():
    """Verify that unhandled exceptions inside get_db_context trigger rollback without masking the error."""
    init_db()
    test_node_id = f"test_rollback_{int(time.time() * 1000)}"

    with pytest.raises(RuntimeError, match="Simulated transaction error"):
        with get_db_context() as session:
            node = Node(
                node_id=test_node_id,
                name="Rollback Node",
                location="Test Lab",
                status="online",
            )
            session.add(node)
            session.flush()
            raise RuntimeError("Simulated transaction error")

    # Verify the row was not persisted
    with get_db_context() as session:
        persisted = session.query(Node).filter(Node.node_id == test_node_id).first()
        assert persisted is None


def test_get_db_generator_rollback_on_exception():
    """Verify that generator-based get_db handles exception propagation and rollback."""
    init_db()
    gen = get_db()
    session = next(gen)
    test_node_id = f"test_dep_rollback_{int(time.time() * 1000)}"

    try:
        node = Node(
            node_id=test_node_id,
            name="Dependency Rollback Node",
            location="Test Lab",
            status="online",
        )
        session.add(node)
        session.flush()
        # Simulate FastAPI dependency tear-down on exception
        gen.throw(RuntimeError("Endpoint raised error"))
    except RuntimeError as exc:
        assert "Endpoint raised error" in str(exc)

    with get_db_context() as verify_session:
        persisted = verify_session.query(Node).filter(Node.node_id == test_node_id).first()
        assert persisted is None


def test_concurrent_readers_and_writers_isolated(tmp_path):
    """Simulate concurrent background writes and foreground reads on an isolated WAL database."""
    isolated_db_path = str(tmp_path / "concurrent_test.db")
    isolated_url = f"sqlite:///{isolated_db_path}"

    test_engine = create_engine(
        isolated_url,
        connect_args={"check_same_thread": False, "timeout": 15.0},
    )

    @event.listens_for(test_engine, "connect")
    def _set_test_pragmas(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA busy_timeout=5000;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.close()

    # Set WAL mode once on file initialization
    with test_engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL;"))
        conn.commit()

    Base.metadata.create_all(bind=test_engine)

    node_id = "test_concurrent_node"
    with Session(test_engine) as session:
        node = Node(
            node_id=node_id,
            name="Concurrency Test Node",
            location="Unit Test",
            status="online",
        )
        session.add(node)
        session.commit()

    write_errors: List[Exception] = []
    read_errors: List[Exception] = []
    read_counts: List[int] = []

    def writer_task(writer_id: int):
        """Simulate background telemetry ingestion with transaction hold."""
        try:
            for i in range(5):
                with Session(test_engine) as session:
                    reading = SensorReading(
                        node_id=node_id,
                        ph=7.2 + (i * 0.05),
                        temperature=25.0,
                        tds=150.0,
                        turbidity=1.0,
                        optical_colour_index=0.02,
                        timestamp=datetime.now(timezone.utc),
                        source="real",
                    )
                    session.add(reading)
                    session.flush()
                    # Small sleep while in transaction to simulate processing
                    time.sleep(0.02)
                    session.commit()
                time.sleep(0.01)
        except Exception as e:
            write_errors.append(e)

    def reader_task(reader_id: int):
        """Simulate foreground client read requests during background writes."""
        try:
            for _ in range(8):
                with Session(test_engine) as session:
                    count = (
                        session.query(SensorReading)
                        .filter(SensorReading.node_id == node_id)
                        .count()
                    )
                    read_counts.append(count)
                time.sleep(0.015)
        except Exception as e:
            read_errors.append(e)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(writer_task, 1),
            executor.submit(reader_task, 1),
            executor.submit(reader_task, 2),
        ]
        concurrent.futures.wait(futures)

    assert not write_errors, f"Writer errors encountered: {write_errors}"
    assert not read_errors, f"Reader errors encountered: {read_errors}"
    assert len(read_counts) > 0

    with Session(test_engine) as session:
        total = session.query(SensorReading).filter(SensorReading.node_id == node_id).count()
        assert total == 5

    test_engine.dispose()
