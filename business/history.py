"""Local task/event history. Never stores model credentials or browser frames."""
import json
import sqlite3
import time


class History:
    def __init__(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL,
                    scenario TEXT NOT NULL, prompt TEXT NOT NULL,
                    status TEXT NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT,
                    payload TEXT NOT NULL);
            ''')
            db.execute("UPDATE tasks SET status='interrupted' WHERE status='running'")

    def connect(self):
        return sqlite3.connect(self.path, timeout=5)

    def create_task(self, task_id, request_id, scenario, prompt):
        with self.connect() as db:
            db.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?)',
                       (task_id, request_id, scenario, prompt, 'running', time.time()))

    def by_request(self, request_id):
        with self.connect() as db:
            row = db.execute('SELECT id FROM tasks WHERE request_id=?', (request_id,)).fetchone()
        return row[0] if row else None

    def finish(self, task_id, status):
        with self.connect() as db:
            db.execute('UPDATE tasks SET status=? WHERE id=?', (status, task_id))

    def append(self, event):
        with self.connect() as db:
            cursor = db.execute('INSERT INTO events (task_id,payload) VALUES (?,?)',
                                (event.get('task_id'), json.dumps(event, ensure_ascii=False)))
            event['id'] = cursor.lastrowid
        return event

    def events(self, task_id=None, limit=200):
        query = 'SELECT id,payload FROM events'
        args = []
        if task_id is not None:
            query += ' WHERE task_id=?'; args.append(task_id)
        query += ' ORDER BY id DESC LIMIT ?'; args.append(limit)
        with self.connect() as db:
            rows = db.execute(query, args).fetchall()
        return [dict(json.loads(payload), id=seq) for seq, payload in reversed(rows)]

    def tasks(self):
        with self.connect() as db:
            db.row_factory = sqlite3.Row
            rows = db.execute('SELECT id,scenario,prompt,status,created FROM tasks ORDER BY created DESC LIMIT 50').fetchall()
        return [dict(row) for row in rows]
