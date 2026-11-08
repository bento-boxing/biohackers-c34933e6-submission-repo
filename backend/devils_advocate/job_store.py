"""SQLite-backed local jobs, idempotency, Scout runs and decision audit.

Each worker claims jobs transactionally. Expired jobs are interrupted, never
automatically replayed: a paid provider request may already have completed.
"""
import json
from pathlib import Path
import sqlite3
import time
import uuid
from contextlib import contextmanager

TERMINAL = {'completed', 'failed', 'cancelled', 'interrupted'}

class JobStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, idem TEXT UNIQUE NOT NULL, fingerprint TEXT NOT NULL,
                    selection_key TEXT NOT NULL, state TEXT NOT NULL, payload TEXT NOT NULL,
                    progress TEXT NOT NULL, result TEXT, error TEXT, created REAL NOT NULL,
                    updated REAL NOT NULL, lease REAL NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS scout_runs (id TEXT PRIMARY KEY, mode TEXT NOT NULL, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS decisions (id TEXT PRIMARY KEY, job_id TEXT NOT NULL, data TEXT NOT NULL, created REAL NOT NULL);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def decode(row):
        if row is None:
            return None
        data = dict(row)
        for name in ['payload', 'progress', 'result']:
            if data.get(name) is not None:
                data[name] = json.loads(data[name])
        return data

    def create(self, idem: str, fingerprint: str, selection_key: str, payload: dict):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT * FROM jobs WHERE idem=?', (idem,)).fetchone()
            if old:
                if old['fingerprint'] != fingerprint:
                    raise ValueError('Idempotency key already belongs to a different request.')
                return self.decode(old), False
            active = db.execute("SELECT * FROM jobs WHERE selection_key=? AND state IN ('queued','running','cancel_requested')", (selection_key,)).fetchone()
            if active:
                return self.decode(active), False
            now = time.time()
            identifier = uuid.uuid4().hex
            db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                (identifier, idem, fingerprint, selection_key, 'queued', json.dumps(payload),
                 json.dumps({'stage': 'Queued', 'calls': []}), None, None, now, now, 0))
            return self.decode(db.execute('SELECT * FROM jobs WHERE id=?', (identifier,)).fetchone()), True

    def get(self, identifier):
        with self.connect() as db:
            return self.decode(db.execute('SELECT * FROM jobs WHERE id=?', (identifier,)).fetchone())

    def claim(self):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            now = time.time()
            db.execute("UPDATE jobs SET state='interrupted', error=?, updated=? WHERE state IN ('running','cancel_requested') AND lease < ?",
                       ('Worker lease expired. Previous paid requests may have completed; this job will not be retried automatically.', now, now))
            row = db.execute("SELECT * FROM jobs WHERE state='queued' ORDER BY created LIMIT 1").fetchone()
            if row is None:
                return None
            db.execute("UPDATE jobs SET state='running',lease=?,updated=? WHERE id=?", (now + 45, now, row['id']))
            return self.decode(db.execute('SELECT * FROM jobs WHERE id=?', (row['id'],)).fetchone())

    def heartbeat(self, identifier):
        with self.connect() as db:
            db.execute("UPDATE jobs SET lease=? WHERE id=? AND state IN ('running','cancel_requested')", (time.time() + 45, identifier))

    def progress(self, identifier, stage, calls=None, *, retrieval=None, timings=None):
        old = self.get(identifier)
        value = {**old['progress'], 'stage': stage, 'calls': calls if calls is not None else old['progress'].get('calls', [])}
        if stage != old['progress'].get('stage'):
            value['stage_started_at'] = time.time()
        if retrieval is not None: value['retrieval'] = retrieval
        if timings is not None: value['timings'] = timings
        with self.connect() as db:
            db.execute('UPDATE jobs SET progress=?,updated=? WHERE id=?', (json.dumps(value), time.time(), identifier))

    def finish(self, identifier, state, result=None, error=None):
        with self.connect() as db:
            db.execute('UPDATE jobs SET state=?,result=?,error=?,updated=?,lease=0 WHERE id=?',
                       (state, json.dumps(result) if result is not None else None, error, time.time(), identifier))

    def cancel(self, identifier):
        with self.connect() as db:
            db.execute("UPDATE jobs SET state=CASE WHEN state='queued' THEN 'cancelled' ELSE 'cancel_requested' END,updated=? WHERE id=? AND state IN ('queued','running')", (time.time(), identifier))

    def cancelled(self, identifier):
        return self.get(identifier)['state'] not in ['running', 'queued']

    def save_run(self, identifier, mode, data):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO scout_runs VALUES (?,?,?)', (identifier, mode, json.dumps(data)))

    def get_run(self, identifier):
        with self.connect() as db:
            row = db.execute('SELECT mode,data FROM scout_runs WHERE id=?', (identifier,)).fetchone()
            return {'mode': row['mode'], 'data': json.loads(row['data'])} if row else None

    def decision(self, identifier, job_id, data):
        with self.connect() as db:
            db.execute('INSERT INTO decisions VALUES (?,?,?,?)', (identifier, job_id, json.dumps(data), time.time()))

    def decisions(self, job_id):
        with self.connect() as db:
            return [json.loads(r['data']) for r in db.execute('SELECT data FROM decisions WHERE job_id=? ORDER BY created', (job_id,))]
