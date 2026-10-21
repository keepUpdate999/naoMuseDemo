import asyncio
import json
import os
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

from data import Store, ARTICLES
from browser_agent import BrowserSession, build_agent

ROOT = Path(__file__).parent
PORT = int(os.environ.get('DEMO_PORT', '18889'))
BASE = f'http://127.0.0.1:{PORT}'
LOCAL = Path(os.environ.get('DEMO_DATA', str(ROOT / '.local')))
store = Store(LOCAL / 'demo.sqlite3')
token = secrets.token_urlsafe(32)
session = BrowserSession(BASE)
events = []
task = None
agent = None
status = 'idle'
active_scene = 'table'
started = time.time()
shutdown_requested = False


def config():
    path = LOCAL / 'model.json'
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding='utf-8-sig'))
        if not isinstance(value, dict):
            return {}
        if value.get('api_key_dpapi'):
            from secret_store import unprotect
            value['api_key'] = unprotect(value['api_key_dpapi'])
        return value
    except Exception:
        return {}


def configured():
    c = config()
    return bool(c.get('enabled') is True and c.get('base_url') and c.get('model') and c.get('api_key'))


def log(kind, value):
    events.append({'time': time.strftime('%H:%M:%S'), 'kind': kind, 'text': value[:1800]})
    del events[:-100]


def running():
    return task is not None and not task.done()


async def stop():
    global status, agent
    if running():
        status = 'stopping'
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    await session.close()
    agent = None
    status = 'stopped'
    log('status', '已停止，浏览器执行环境已关闭。再次运行将创建新会话，已保存数据保留。')


@asynccontextmanager
async def lifespan(app):
    yield
    await stop()


app = FastAPI(lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', 'testserver'])


@app.middleware('http')
async def boundary(request, call_next):
    if request.method not in ('GET', 'HEAD'):
        origin = request.headers.get('origin')
        if origin and origin not in (BASE, f'http://localhost:{PORT}'):
            return JSONResponse({'detail': '非同源请求'}, status_code=403)
        if request.headers.get('content-type', '').split(';')[0] != 'application/json':
            return JSONResponse({'detail': '需要 JSON 请求'}, status_code=415)
        if int(request.headers.get('content-length', '0')) > 100000:
            return JSONResponse({'detail': '请求过大'}, status_code=413)
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' data: blob:; style-src 'self'; script-src 'self'; frame-src 'self'; connect-src 'self'; frame-ancestors 'self'"
    return response


def authorize(request):
    if not secrets.compare_digest(request.headers.get('x-demo-token', ''), token):
        raise HTTPException(403, '控制令牌无效，请刷新工作台')


@app.get('/')
def index():
    return HTMLResponse((ROOT / 'web/index.html').read_text(encoding='utf-8').replace('__TOKEN__', token))


@app.get('/scene/{name}')
def scene(name: str):
    if name not in ['table', 'transfer', 'notes', 'orders', 'search', 'form']:
        raise HTTPException(404)
    return HTMLResponse((ROOT / 'web/scene.html').read_text(encoding='utf-8'))


@app.get('/api/data')
def read_data():
    return {**store.read(), 'articles': ARTICLES}


class DataWrite(BaseModel):
    key: str
    value: list | dict


@app.post('/api/data')
def write_data(body: DataWrite):
    # Schema validation prevents corrupted persistent state from breaking later scenes.
    from schemas import validate_data
    try:
        value = validate_data(body.key, body.value)
        store.write(body.key, value)
    except ValueError:
        raise HTTPException(422, '数据格式不正确')
    return {'saved': True}


@app.get('/api/status')
def get_status(request: Request):
    authorize(request)
    return {'configured': configured(), 'model': config().get('model', ''), 'provider': config().get('provider', ''), 'scene': active_scene, 'status': status, 'running': running(), 'events': events, 'action': session.action, 'frame_time': session.frame_time, 'has_frame': session.jpeg is not None, 'tabs': [p.url for p in session.pages if not p.is_closed()], 'data': store.read()}


@app.get('/api/frame')
def frame(request: Request):
    authorize(request)
    if not session.jpeg or time.time() - session.frame_time > 5:
        raise HTTPException(503, '执行画面尚未就绪或已断开')
    return Response(session.jpeg, media_type='image/jpeg')


class Run(BaseModel):
    prompt: str = Field(min_length=1, max_length=6000)
    scene: str

    @field_validator('prompt')
    @classmethod
    def meaningful_prompt(cls, value):
        value = value.strip()
        if not value:
            raise ValueError('请输入任务内容')
        return value


async def execute(body):
    global agent, status
    status = 'running'
    session.action = '正在打开场景'
    log('user', body.prompt)
    try:
        await session.start()
        await session.act('open', url=f'{BASE}/scene/{body.scene}')
        if agent is None:
            agent = build_agent(config(), session, log, data_dir=LOCAL / 'runtime')
        result = await asyncio.wait_for(agent.run(body.prompt), timeout=240)
        status = 'finished'
        log('result', result or '任务回合结束，请核对保存结果。')
    except asyncio.CancelledError:
        status = 'stopped'
        raise
    except Exception as exc:
        status = 'error'
        agent = None
        # Provider exception messages may echo credentials; never return them to the UI.
        code = getattr(exc, 'status_code', None)
        if code == 401:
            log('error', '模型鉴权失败（HTTP 401）：网关拒绝了当前密钥。请检查密钥是否有效，以及它所属的服务地址。')
        elif code == 403:
            log('error', '模型访问被拒绝（HTTP 403）：请检查账号或模型访问权限。')
        elif code == 429:
            log('error', '模型请求受限（HTTP 429）：请检查网关额度或速率限制。')
        else:
            log('error', f'执行失败（{type(exc).__name__}）。请检查模型配置或浏览器安装；没有宣告任务成功。')


@app.post('/api/run')
async def run(body: Run, request: Request):
    global task, active_scene
    authorize(request)
    if body.scene not in ['table', 'transfer', 'notes', 'orders', 'search', 'form']:
        raise HTTPException(422, '未知场景')
    if running():
        raise HTTPException(409, '已有任务执行中，请先停止')
    if not configured():
        raise HTTPException(409, '模型未配置，当前仅可手动彩排')
    active_scene = body.scene
    task = asyncio.create_task(execute(body))
    return {'accepted': True}


@app.post('/api/stop')
async def stop_route(request: Request):
    authorize(request)
    await stop()
    return {'stopped': True}


class Reset(BaseModel):
    scene: str


@app.post('/api/reset')
async def reset(body: Reset, request: Request):
    global agent
    authorize(request)
    if running():
        raise HTTPException(409, '请先停止任务再恢复素材')
    if body.scene not in ['table', 'transfer', 'notes', 'orders', 'search', 'form']:
        raise HTTPException(422)
    await session.close()
    agent = None
    store.reset(body.scene)
    log('reset', '已恢复当前素材；信息搬运与记事本共享笔记，恢复任一会清空演示笔记。')
    return {'reset': True}


@app.get('/health')
def health():
    return {'app': 'nanomuse-browser-demo', 'version': '0.1', 'model_configured': configured()}


@app.post('/api/shutdown')
async def shutdown(request: Request):
    global shutdown_requested
    authorize(request)
    await stop()
    shutdown_requested = True
    return {'stopped': True}


app.mount('/assets', StaticFiles(directory=ROOT / 'web'), name='assets')


async def serve():
    import uvicorn
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=PORT, log_level='warning'))
    async def expiry():
        while not shutdown_requested:
            await asyncio.sleep(1)
            if time.time() - started > 3600 and not running():
                break
        server.should_exit = True
    watchdog = asyncio.create_task(expiry())
    try:
        await server.serve()
    finally:
        watchdog.cancel()
        await asyncio.gather(watchdog, return_exceptions=True)


if __name__ == '__main__':
    asyncio.run(serve())
