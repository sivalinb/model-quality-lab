"""Durable local inbox with at-least-once acceptance and atomic projections.

SQLite/WAL is a single-host learning mode, not a highly available distributed DB.
Leases support multiple local workers; fencing prevents a stale worker committing.
"""
from __future__ import annotations
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
import json
import sqlite3
import time
import uuid


class Store:
    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS inbox (
              id TEXT PRIMARY KEY, kind TEXT NOT NULL, request_id TEXT NOT NULL,
              body TEXT NOT NULL, digest TEXT NOT NULL, received REAL NOT NULL,
              processed REAL, lease_until REAL NOT NULL DEFAULT 0, token TEXT,
              attempts INTEGER NOT NULL DEFAULT 0, error TEXT);
            CREATE INDEX IF NOT EXISTS pending_events ON inbox(processed, lease_until, received);
            CREATE TABLE IF NOT EXISTS predictions (
              request_id TEXT NOT NULL, model TEXT NOT NULL, body TEXT NOT NULL,
              PRIMARY KEY(request_id, model));
            CREATE TABLE IF NOT EXISTS labels (request_id TEXT PRIMARY KEY, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS dead_letters (id TEXT PRIMARY KEY, reason TEXT NOT NULL, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, created REAL NOT NULL, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, action TEXT, detail TEXT, created REAL);
            """)

    @contextmanager
    def connection(self):
        c = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=FULL")
        c.execute("PRAGMA busy_timeout=30000")
        try:
            yield c
        finally:
            c.close()

    def accept(self, event_id: str, kind: str, request_id: str, body: dict) -> bool:
        if kind not in ("prediction", "label"):
            raise ValueError("Unsupported event kind")
        encoded = json.dumps(body, sort_keys=True, allow_nan=False)
        digest = sha256((kind + request_id + encoded).encode()).hexdigest()
        with self.connection() as c:
            c.execute("BEGIN IMMEDIATE")
            old = c.execute("SELECT digest FROM inbox WHERE id=?", (event_id,)).fetchone()
            if old:
                c.rollback()
                if old[0] != digest:
                    raise ValueError("Event ID reused with different content")
                return False
            c.execute("INSERT INTO inbox(id,kind,request_id,body,digest,received) VALUES(?,?,?,?,?,?)",
                      (event_id, kind, request_id, encoded, digest, time.time()))
            c.commit()
        return True

    def claim(self, lease_seconds: float = 30) -> dict | None:
        now = time.time(); token = uuid.uuid4().hex
        with self.connection() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT * FROM inbox WHERE processed IS NULL AND lease_until<=? ORDER BY received,id LIMIT 1", (now,)).fetchone()
            if not row:
                c.rollback(); return None
            c.execute("UPDATE inbox SET lease_until=?,token=?,attempts=attempts+1 WHERE id=?",
                      (now + lease_seconds, token, row["id"]))
            c.commit()
            return {**dict(row), "token": token, "attempts": row["attempts"] + 1}

    def accept_many(self, events: list[tuple[str, str, str, dict]]) -> int:
        accepted = 0
        with self.connection() as c:
            c.execute("BEGIN IMMEDIATE")
            for event_id, kind, request_id, body in events:
                if kind not in ("prediction", "label"):
                    c.rollback(); raise ValueError("Unsupported event kind")
                encoded = json.dumps(body, sort_keys=True, allow_nan=False)
                digest = sha256((kind + request_id + encoded).encode()).hexdigest()
                old = c.execute("SELECT digest FROM inbox WHERE id=?", (event_id,)).fetchone()
                if old:
                    if old[0] != digest:
                        c.rollback(); raise ValueError("Event ID reused with different content")
                    continue
                c.execute("INSERT INTO inbox(id,kind,request_id,body,digest,received) VALUES(?,?,?,?,?,?)",
                          (event_id, kind, request_id, encoded, digest, time.time()))
                accepted += 1
            c.commit()
        return accepted

    def complete(self, event: dict) -> None:
        with self.connection() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT processed,token FROM inbox WHERE id=?", (event["id"],)).fetchone()
            if not row or row["processed"] is not None or row["token"] != event["token"]:
                c.rollback(); raise ValueError("Expired worker receipt; event has been reclaimed or completed")
            payload = json.loads(event["body"])
            if event["kind"] == "prediction":
                model = payload["model"]
                old = c.execute("SELECT body FROM predictions WHERE request_id=? AND model=?", (event["request_id"], model)).fetchone()
                if old and old[0] != event["body"]:
                    c.rollback(); raise ValueError("Conflicting prediction projection")
                c.execute("INSERT OR IGNORE INTO predictions VALUES(?,?,?)", (event["request_id"], model, event["body"]))
            else:
                old = c.execute("SELECT body FROM labels WHERE request_id=?", (event["request_id"],)).fetchone()
                if old and old[0] != event["body"]:
                    c.rollback(); raise ValueError("Conflicting label projection; explicit correction workflow required")
                c.execute("INSERT OR IGNORE INTO labels VALUES(?,?)", (event["request_id"], event["body"]))
            c.execute("UPDATE inbox SET processed=?,lease_until=0 WHERE id=?", (time.time(), event["id"]))
            c.commit()

    def reject(self, event: dict, error: str, max_attempts: int = 3) -> None:
        with self.connection() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT token,processed FROM inbox WHERE id=?", (event["id"],)).fetchone()
            if not row or row["token"] != event["token"] or row["processed"] is not None:
                c.rollback(); return
            if event["attempts"] >= max_attempts:
                c.execute("INSERT OR REPLACE INTO dead_letters VALUES(?,?,?)", (event["id"], error[:300], time.time()))
                c.execute("UPDATE inbox SET processed=?,error=? WHERE id=?", (time.time(), error[:300], event["id"]))
            else:
                c.execute("UPDATE inbox SET lease_until=0,error=? WHERE id=?", (error[:300], event["id"]))
            c.commit()

    def drain(self, limit: int = 100000) -> int:
        from .telemetry import tracer
        completed = 0
        with tracer().start_as_current_span("inbox.consume") as span:
            for _ in range(limit):
                event = self.claim()
                if event is None:
                    break
                try:
                    self.complete(event); completed += 1
                except (KeyError, ValueError, TypeError) as exc:
                    self.reject(event, str(exc))
            span.set_attribute("mql.events.projected", completed)
        return completed

    def drain_batch(self, batch_size: int = 250) -> int:
        """A short transaction atomically projects each batch. A crash rolls it back.

        Leased rows are excluded, so this also coexists with the lease-based worker.
        Invalid records are dead-lettered; they cannot block later valid events.
        """
        completed = 0
        from .telemetry import tracer
        with tracer().start_as_current_span("inbox.project_batch") as span:
            while True:
                with self.connection() as c:
                    c.execute("BEGIN IMMEDIATE")
                    rows = c.execute("SELECT * FROM inbox WHERE processed IS NULL AND lease_until<=? ORDER BY received,id LIMIT ?",
                                     (time.time(), batch_size)).fetchall()
                    if not rows:
                        c.rollback(); break
                    for r in rows:
                        try:
                            body = json.loads(r["body"])
                            if r["kind"] == "prediction":
                                old = c.execute("SELECT body FROM predictions WHERE request_id=? AND model=?", (r["request_id"], body["model"])).fetchone()
                                if old and old[0] != r["body"]:
                                    raise ValueError("Conflicting prediction projection")
                                c.execute("INSERT OR IGNORE INTO predictions VALUES(?,?,?)", (r["request_id"], body["model"], r["body"]))
                            else:
                                old = c.execute("SELECT body FROM labels WHERE request_id=?", (r["request_id"],)).fetchone()
                                if old and old[0] != r["body"]:
                                    raise ValueError("Conflicting label projection")
                                c.execute("INSERT OR IGNORE INTO labels VALUES(?,?)", (r["request_id"], r["body"]))
                            completed += 1
                        except (KeyError, ValueError, TypeError) as exc:
                            c.execute("INSERT OR REPLACE INTO dead_letters VALUES(?,?,?)", (r["id"], str(exc)[:300], time.time()))
                        c.execute("UPDATE inbox SET processed=?,lease_until=0,attempts=attempts+1 WHERE id=?", (time.time(), r["id"]))
                    c.commit()
            span.set_attribute("mql.events.projected", completed)
        return completed

    def joined(self, prefix: str | None = None) -> list[dict]:
        with self.connection() as c:
            rows = c.execute("SELECT p.request_id,p.body,l.body AS label_body FROM predictions p JOIN labels l USING(request_id)").fetchall()
        return [{"request_id": r["request_id"], "prediction": json.loads(r["body"]), "label": json.loads(r["label_body"])}
                for r in rows if prefix is None or r["request_id"].startswith(prefix)]

    def stats(self) -> dict:
        with self.connection() as c:
            counts = {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                      for t in ("inbox", "predictions", "labels", "dead_letters", "runs")}
            counts["pending"] = c.execute("SELECT COUNT(*) FROM inbox WHERE processed IS NULL").fetchone()[0]
            counts["joined_predictions"] = c.execute("SELECT COUNT(*) FROM predictions JOIN labels USING(request_id)").fetchone()[0]
            counts["oldest_pending_age_seconds"] = max(0, time.time() - (c.execute("SELECT MIN(received) FROM inbox WHERE processed IS NULL").fetchone()[0] or time.time()))
        return counts

    def save_run(self, report: dict) -> None:
        with self.connection() as c:
            c.execute("INSERT OR REPLACE INTO runs VALUES(?,?,?)", (report["id"], time.time(), json.dumps(report, allow_nan=False)))

    def runs(self, limit: int = 50) -> list[dict]:
        with self.connection() as c:
            return [json.loads(r[0]) for r in c.execute("SELECT body FROM runs ORDER BY created DESC LIMIT ?", (limit,))]

    def audit(self, action: str, detail: dict) -> None:
        with self.connection() as c:
            c.execute("INSERT INTO audit(action,detail,created) VALUES(?,?,?)", (action, json.dumps(detail), time.time()))

    def audit_rows(self) -> list[dict]:
        with self.connection() as c:
            return [dict(r) for r in c.execute("SELECT action,detail,created FROM audit ORDER BY id DESC LIMIT 30")]
