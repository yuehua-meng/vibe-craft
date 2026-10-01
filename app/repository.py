"""SQLite-backed repository. Tasks, reviews and assets survive process restarts."""
import copy
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()

class SqliteRepository:
    """Persists business state to data/app.db while keeping the in-memory dict interface."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        for name in ('assets', 'generated', 'exports'):
            (data_dir / name).mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(data_dir / 'app.db', check_same_thread=False)
        self.conn.execute('PRAGMA journal_mode=WAL')
        self.conn.execute('PRAGMA busy_timeout=5000')
        self.conn.executescript(
            'CREATE TABLE IF NOT EXISTS assets (id TEXT PRIMARY KEY, payload TEXT NOT NULL);'
            'CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, payload TEXT NOT NULL);')
        self.conn.commit()
        self.assets: dict[str, dict] = {}
        self.tasks: dict[str, dict] = {}
        self._load()

    def _load(self):
        for asset_id, payload in self.conn.execute('SELECT id, payload FROM assets'):
            self.assets[asset_id] = json.loads(payload)
        for task_id, payload in self.conn.execute('SELECT id, payload FROM tasks ORDER BY created_at, id'):
            self.tasks[task_id] = json.loads(payload)
        self._recover_interrupted()

    def _recover_interrupted(self):
        # A process that stops mid-run leaves branches 'running'/'queued'. Keep the persisted
        # checkpoint so retry resumes from the last completed node, instead of silently
        # re-running paid steps on startup.
        for task in list(self.tasks.values()):
            changed = False
            for branch in task['branches'].values():
                if branch['status'] in ('running', 'queued'):
                    branch.update(status='error', error='服务重启导致运行中断，请重试该分支')
                    changed = True
            if changed:
                self.save_task(task['id'])

    def create(self, payload: dict):
        task_id = uuid.uuid4().hex
        task = {**payload, 'id': task_id, 'created_at': now(), 'branches': {}, 'events': []}
        for platform in payload['platforms']:
            task['branches'][platform] = {
                'platform': platform, 'status': 'queued', 'stage': 'queued', 'version': 0,
                'interrupt': None, 'data': {}, 'error': None, 'history': [],
            }
        self.tasks[task_id] = task
        self.save_task(task_id)
        return task

    def event(self, task_id, platform, stage, message):
        task = self.tasks[task_id]
        task['events'].append({'id': uuid.uuid4().hex, 'at': now(), 'platform': platform,
                               'stage': stage, 'message': message})
        task['events'] = task['events'][-100:]
        self.save_task(task_id)

    def add_asset(self, asset: dict):
        self.assets[asset['id']] = asset
        self.conn.execute('INSERT INTO assets (id, payload) VALUES (?, ?) '
                          'ON CONFLICT(id) DO UPDATE SET payload = excluded.payload',
                          (asset['id'], json.dumps(asset, ensure_ascii=False)))
        self.conn.commit()

    def save_task(self, task_id):
        task = self.tasks.get(task_id)
        if task is None:
            return
        self.conn.execute('INSERT INTO tasks (id, created_at, payload) VALUES (?, ?, ?) '
                          'ON CONFLICT(id) DO UPDATE SET payload = excluded.payload',
                          (task_id, task['created_at'], json.dumps(task, ensure_ascii=False)))
        self.conn.commit()

    def public(self, task):
        result = copy.deepcopy(task)
        result['assets'] = [self.assets[x] for x in task['asset_ids']]
        statuses = [b['status'] for b in task['branches'].values()]
        result['status'] = ('completed' if all(x == 'completed' for x in statuses) else
                            'running' if any(x in ('running', 'queued') for x in statuses) else
                            'waiting' if 'waiting' in statuses else 'error')
        return result

    def close(self):
        self.conn.close()