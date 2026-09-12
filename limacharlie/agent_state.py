"""Local durable workflow evidence. No credentials or command arguments are stored."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from contextlib import contextmanager


def directory():
    return Path(os.environ.get('LC_AGENT_STATE_DIR', str(Path.cwd() / '.lc-agent')))


@contextmanager
def database():
    root = directory()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    db = sqlite3.connect(root / 'state.sqlite3', timeout=130)
    try:
        db.execute('PRAGMA synchronous=FULL')
        db.execute('CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, body TEXT NOT NULL)')
        db.commit()
        yield db
    finally:
        db.close()


def identifier(*parts):
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()


def read(db, key):
    row = db.execute('SELECT body FROM records WHERE id=?', (key,)).fetchone()
    return json.loads(row[0]) if row else None


def save(db, key, value):
    db.execute('INSERT OR REPLACE INTO records VALUES (?, ?)', (key, json.dumps(value)))
    db.commit()


@contextmanager
def resource_lock(key):
    """Serialize processes for a resource without holding an uncommitted receipt."""
    # The runner and supported CLI platforms are Unix. Windows uses msvcrt.
    root = directory() / 'locks'
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (root / key).open('a+b') as handle:
        if os.name == 'nt':
            import msvcrt
            handle.write(b'0'); handle.flush(); handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == 'nt':
                handle.seek(0); msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)
