"""Single network worker: reads may reconnect; mutations are never replayed."""
import json
import queue
import re
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler

from PySide6.QtCore import QThread, Signal


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class LocalAPI:
    def __init__(self, port=18892):
        if not 1024 <= int(port) <= 65535:
            raise ValueError('无效本地端口')
        self.base = f'http://127.0.0.1:{int(port)}'
        self.token = None
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def request(self, path, body=None):
        headers = {'Content-Type': 'application/json'}
        if self.token:
            headers['X-Demo-Token'] = self.token
        req = Request(self.base + path, headers=headers,
                      data=json.dumps(body).encode() if body is not None else None)
        with self.opener.open(req, timeout=4) as response:
            return json.load(response)

    def attach(self):
        if self.request('/health').get('app') != 'nanomuse-real-apps':
            raise ValueError('本地服务身份不匹配')
        with self.opener.open(self.base+'/', timeout=4) as response:
            html = response.read(1024*1024).decode('utf-8')
        match = re.search(r'name="demo-token" content="([^"]+)"', html)
        if not match:
            raise ValueError('本地服务缺少控制身份')
        self.token = match[1]


class Connection(QThread):
    state_received = Signal(dict)
    tasks_received = Signal(list)
    history_received = Signal(str, list)
    connection_changed = Signal(bool, str)
    completed = Signal(str, dict)
    failed = Signal(str, str)

    def __init__(self, port=18892):
        super().__init__()
        self.api = LocalAPI(port)
        self.commands = queue.Queue()
        self.halt = threading.Event()

    def command(self, name, body=None):
        self.commands.put((name, body))

    def close(self):
        self.halt.set()

    def run(self):
        connected = False
        next_poll = 0
        next_tasks = 0
        while not self.halt.is_set():
            if not connected:
                # Discard stale commands on disconnect; never replay an edit.
                while not self.commands.empty():
                    try:
                        name, _ = self.commands.get_nowait()
                        self.failed.emit(name, '连接已中断，请先核对实际执行结果。')
                    except queue.Empty:
                        break
                try:
                    self.api.attach(); connected = True
                except (OSError, ValueError, URLError):
                    self.connection_changed.emit(False, '正在等待本地工作区…')
                    self.halt.wait(1)
                    continue
            try:
                try:
                    name, body = self.commands.get(timeout=.1)
                except queue.Empty:
                    name = None
                if name:
                    if name == 'history':
                        data = self.api.request('/api/tasks/'+body+'/events')
                        self.history_received.emit(body, data['events'])
                    else:
                        paths = {'run':'/api/run', 'stop':'/api/stop', 'open':'/api/open',
                                 'reset':'/api/workspace/reset', 'shutdown':'/api/shutdown'}
                        data = self.api.request(paths[name], body or {})
                        self.completed.emit(name, data)
                    next_poll = 0; next_tasks = 0
                now = time.monotonic()
                if now >= next_poll:
                    state = self.api.request('/api/status')
                    if state.get('desktop_protocol') != 1:
                        self.connection_changed.emit(False, '服务版本需要更新：请重启本地工作区。')
                        self.halt.wait(2)
                        continue
                    self.state_received.emit(state)
                    next_poll = now + 1
                if now >= next_tasks:
                    self.tasks_received.emit(self.api.request('/api/tasks')['tasks'])
                    next_tasks = now + 5
            except HTTPError as exc:
                if name:
                    messages = {409:'工作区忙或任务已在执行，请查看工作记录。',
                                422:'任务内容无效，请重新选择预置任务。',
                                503:'工作区尚未就绪，请稍后再试。'}
                    self.failed.emit(name, messages.get(exc.code, f'请求失败（HTTP {exc.code}）。'))
                if exc.code == 403 or not name or exc.code >= 500:
                    connected = False
                    self.connection_changed.emit(False, '服务状态无法确认，正在重新连接；任务不会自动重发。')
                self.halt.wait(.5)
            except (OSError, ValueError, URLError):
                if name:
                    self.failed.emit(name, '连接中断，操作结果尚未确认；不会自动重新提交，请核对工作记录。')
                connected = False
                self.connection_changed.emit(False, '连接中断，正在重新连接；任务不会自动重发。')
