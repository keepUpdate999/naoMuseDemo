"""Separate real application presentation controller; no embedded business pages."""
import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import secrets
import time
from typing import Literal

from fastapi import FastAPI,HTTPException,Request
from fastapi.responses import HTMLResponse,JSONResponse,Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from browser_agent import build_agent
from business.browser import BusinessBrowser,BusinessBrowserTool
from business.budget import BudgetLLM,read_budget
from business.catalog import SCENARIOS,ERP,WIKI
from business.stack import Stack,credentials
from secret_store import unprotect

ROOT=Path(__file__).parent
PORT=int(os.environ.get('BUSINESS_PORT','18892'))
BASE=f'http://127.0.0.1:{PORT}'
token=secrets.token_urlsafe(32)
session=None
agent=None
task=None
status='idle'
events=[]
shutdown_requested=False
started=time.time()
workspace=None
reset_task=None
workspace_lock=asyncio.Lock()


def resetting():
    return reset_task is not None and not reset_task.done()


def available():
    if resetting() or workspace_lock.locked():raise HTTPException(409,'工作区正在准备或重置，请稍候')


async def wait_for_reset():
    if resetting():await asyncio.shield(reset_task)


def config():
    data=json.loads((ROOT/'.local/model.json').read_text(encoding='utf-8-sig'))
    data['api_key']=unprotect(data['api_key_dpapi'])
    return data


def log(kind,text):
    events.append({'time':time.strftime('%H:%M:%S'),'kind':kind,'text':str(text)[:2400]})
    del events[:-200]


def running():
    return task is not None and not task.done()


async def close_agent():
    global agent
    if agent:
        llm=getattr(agent.llm,'inner',agent.llm)
        if getattr(llm,'client',None):
            await llm.client.close()
        agent=None


async def stop():
    global status
    if running():
        task.cancel();await asyncio.gather(task,return_exceptions=True)
    if session:
        await session.close()
    await close_agent()
    status='stopped'


@asynccontextmanager
async def lifespan(app):
    yield
    await wait_for_reset()
    await stop()


app=FastAPI(lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost','testserver'])


@app.middleware('http')
async def boundary(request,call_next):
    if request.method not in ('GET','HEAD'):
        if request.headers.get('origin') not in (None,BASE,f'http://localhost:{PORT}'):
            return JSONResponse({'detail':'非同源请求'},403)
        if request.headers.get('content-type','').split(';')[0]!='application/json':
            return JSONResponse({'detail':'需要JSON请求'},415)
    response=await call_next(request)
    response.headers['Cache-Control']='no-store'
    response.headers['Content-Security-Policy']="default-src 'self'; img-src 'self' blob:; style-src 'self'; script-src 'self'; frame-src 'none'; frame-ancestors 'none'"
    return response


def authorize(request):
    if not secrets.compare_digest(request.headers.get('x-demo-token',''),token):
        raise HTTPException(403,'服务已重启，请刷新控制台')


@app.get('/')
def index():
    return HTMLResponse((ROOT/'business/web/index.html').read_text(encoding='utf-8').replace('__TOKEN__',token))


@app.get('/health')
def health():
    return {'app':'nanomuse-real-apps','ready':True}


@app.get('/api/status')
def get_status(request:Request):
    authorize(request)
    b={}
    try:
        b=read_budget();limit=b.get('limit',60)
        remaining=None if limit is None else max(0,int(limit)-b['attempts'])
    except (RuntimeError,ValueError):
        remaining=0
    return {'running':running(),'resetting':resetting(),'status':status,'events':events,'remaining':remaining,
        'unlimited':remaining is None,'calls':b.get('attempts',0),
        'scenarios':SCENARIOS,'browser_open':bool(session and session.page and not session.page.is_closed()),
        'tabs':[p.url for p in session.pages if not p.is_closed()] if session else [],
        'model':config().get('model',''),'expires_at':started+3600,
        'backups':workspace.backups() if workspace else []}


async def open_browser():
    global session
    if session is None:
        session=BusinessBrowser(credentials()['BUSINESS_APP_PASSWORD'])
    await session.start()
    await session.prepare_workspace()


async def focus_scenario(s):
    pages=getattr(session,'pages',[])
    tab=next((i for i,p in enumerate(pages) if not p.is_closed() and p.url==s['url']),
             1 if s['url'].startswith(WIKI) else 0)
    await session.act('switch_tab',tab=tab)
    if not pages or session.page.url!=s['url']:
        await session.act('open',url=s['url'])


class Open(BaseModel):
    scenario:str='customer'


def scenario_for(name):
    for s in SCENARIOS:
        if s['id']==name:return s
    raise HTTPException(422,'未知场景')


@app.post('/api/open')
async def open_route(body:Open,request:Request):
    authorize(request)
    available()
    if running():raise HTTPException(409,'任务正在运行')
    s=scenario_for(body.scenario)
    try:
        async with workspace_lock:
            await open_browser()
            await focus_scenario(s)
            await session.reveal()
    except Exception as exc:
        log('error',f'打开应用失败：{type(exc).__name__}')
        raise HTTPException(503,'应用打开失败，请检查两套本地应用是否就绪') from None
    log('browser','业务工作区已就绪。')
    return {'opened':True}


class Run(BaseModel):
    scenario:str
    prompt:str=Field(min_length=1,max_length=6000)


def task_addendum(prompt):
    return f'''你操作两套真实本地应用，所有业务数据虚构。
Dolibarr客户订单联系人系统：{ERP}，DokuWiki知识库：{WIKI}。已预先登录，绝不索要、读取或输入密码。
只有demo_browser工具能操作；先read获取当前控件编号，修改必须点击保存，重新打开核验。
下拉框使用select，文本框fill；可click真实链接、new_tab、tabs、switch_tab。跨系统任务请切换标签页。
不得删除记录，不得进入管理员设置或安装页，不得发邮件。保留任务未要求更改的信息。
跨系统场景的订单只读，跟进文字须写回客户卡片的公开备注，不能写入订单备注。客户订单号指订单明细的“顾客编号”，系统草稿单号须另列。
观察和回答都以实际页面为准，不得宣称没有完成的步骤成功。请中文简洁说明进度。
下面是用户本轮的完整任务。即使早期对话被裁剪，此任务仍然有效。逐项完成，不进行无关浏览，不要再次索要已经给出的任务。
<current_user_task>
{prompt}
</current_user_task>'''


async def execute(body):
    global agent,status
    status='running';log('user',body.prompt)
    try:
        await open_browser()
        s=scenario_for(body.scenario)
        await focus_scenario(s)
        await session.reveal()
        session.scenario=body.scenario
        if agent is None:
            agent=build_agent(config(),session,log,data_dir=ROOT/'.local/business/runtime',tool_override=BusinessBrowserTool())
            agent.settings.agent.max_steps=24
            agent.settings.agent.max_context_messages=30
            agent.llm=BudgetLLM(agent.llm,log)
        agent.prompt_addendum=lambda:task_addendum(body.prompt)
        result=await asyncio.wait_for(agent.run(body.prompt),timeout=300)
        status='finished';log('result',result or '本轮结束，请在应用中核对结果。')
    except asyncio.CancelledError:
        log('stopped','任务已取消，已保存记录保留。');raise
    except Exception as exc:
        code=getattr(exc,'status_code',None)
        status='error'
        log('error',f'执行失败：HTTP {code}' if code else f'执行失败：{type(exc).__name__}。请检查页面和剩余额度。')
        await close_agent()
    finally:
        if session:
            session.scenario=None


@app.post('/api/run')
async def run(body:Run,request:Request):
    global task,status
    authorize(request);available();scenario_for(body.scenario)
    if not body.prompt.strip():raise HTTPException(422,'请输入任务')
    if running():raise HTTPException(409,'已有任务运行中')
    budget=read_budget()
    if budget.get('limit',60) is not None and budget['attempts']>=int(budget.get('limit',60)):raise HTTPException(409,'授权请求额度已用完')
    status='running';task=asyncio.create_task(execute(body))
    return {'accepted':True}


@app.post('/api/stop')
async def stop_route(request:Request):
    authorize(request);available();await stop();return {'stopped':True}


@app.post('/api/shutdown')
async def shutdown(request:Request):
    global shutdown_requested
    authorize(request);available();await stop();shutdown_requested=True
    return {'stopped':True}


class Reset(BaseModel):
    confirm:Literal[True]
    backup_id:str|None=Field(default=None,pattern=r'^\d{8}T\d{6}Z-[a-f0-9]{8}$')


async def reset_workspace(body):
    global status,started
    async with workspace_lock:
        try:
            await stop()
            status='resetting'
            log('workspace','正在保留当前工作区备份，并恢复'+('备份数据。' if body.backup_id else '初始素材。'))
            result=await asyncio.to_thread(workspace.reset,body.backup_id)
            log('workspace','数据已就绪，正在重新登录并打开业务页面。')
            await open_browser();await session.reveal()
            started=time.time();status='idle'
            log('workspace',f'工作区已恢复，7个业务页面已打开。重置前备份：{result["backup_id"]}。模型配置和调用记录保持不变。')
        except Exception as exc:
            status='error'
            log('error',f'工作区操作失败：{type(exc).__name__}。原数据备份保留；请检查本地服务日志。')
            # A failed initialization rolls back its data volumes inside Stack.reset.
            try:await open_browser();await session.reveal()
            except Exception:pass
        finally:
            started=time.time()


@app.post('/api/workspace/reset',status_code=202)
async def reset_route(body:Reset,request:Request):
    global reset_task,status
    authorize(request);available()
    if running():raise HTTPException(409,'请等待当前任务完成，或先停止任务')
    if not workspace or not workspace.owned:raise HTTPException(503,'工作区服务尚未就绪')
    if body.backup_id:
        try:workspace.backup_volumes(body.backup_id)
        except (OSError,ValueError,KeyError):raise HTTPException(422,'备份不可用') from None
    status='resetting';reset_task=asyncio.create_task(reset_workspace(body))
    return {'accepted':True}


@app.get('/api/frame')
def frame(request:Request):
    authorize(request)
    if not session or not session.jpeg:raise HTTPException(503)
    return Response(session.jpeg,media_type='image/jpeg')


app.mount('/assets',StaticFiles(directory=ROOT/'business/web'),name='assets')


async def serve():
    global started,workspace
    import uvicorn
    stack=Stack()
    workspace=stack
    try:
        print('正在启动本地真实应用，请稍候。',flush=True)
        await asyncio.to_thread(stack.start)
        await open_browser()
        await session.reveal()
        started=time.time()
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=PORT,log_level='warning'))
        async def expiry():
            while not shutdown_requested:
                await asyncio.sleep(1)
                if time.time()-started>3600 and not running() and not resetting():break
            server.should_exit=True
        watchdog=asyncio.create_task(expiry())
        try:
            print(f'READY {BASE}',flush=True)
            await server.serve()
        finally:
            watchdog.cancel();await asyncio.gather(watchdog,return_exceptions=True)
            await stop()
    finally:
        await wait_for_reset()
        await stop()
        await asyncio.to_thread(stack.stop)


if __name__=='__main__':
    asyncio.run(serve())
