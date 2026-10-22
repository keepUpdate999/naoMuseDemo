"""Isolated controller lifecycle QA. No model, credentials or Docker access."""
import asyncio
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['BUSINESS_PORT']=os.environ['QA_PORT']
import real_server as server


class Page:
    url='http://127.0.0.1:18893/societe/list.php'
    closed=False
    def is_closed(self):return self.closed


class Session:
    def __init__(self):
        self.page=Page();self.pages=[self.page];self.scenario=None;self.jpeg=None
    async def act(self,*args,**kwargs):return {}
    async def close(self):self.page.closed=True
    async def reveal(self):pass


async def open_browser():
    if not server.session or server.session.page.is_closed():
        server.session=Session()


class Agent:
    def __init__(self):
        self.settings=SimpleNamespace(agent=SimpleNamespace())
        self.llm=SimpleNamespace()
    async def run(self,prompt):
        # Exercise real execute/stop lifecycle without ever constructing an SDK.
        await asyncio.sleep(60 if prompt=='wait-for-stop' else 1)
        if prompt=='simulate-failure':raise RuntimeError('Offline QA failure')
        return 'OFFLINE QA: completed '+prompt


server.open_browser=open_browser
server.config=lambda:{'model':'OFFLINE QA / no provider'}
server.read_budget=lambda:{'limit':None,'attempts':1000}
server.build_agent=lambda *a,**k:Agent()
server.BudgetLLM=lambda inner,log:inner


class Workspace:
    owned=True
    history=[]
    def backups(self):return self.history
    def backup_volumes(self,backup_id):return {}
    def reset(self,backup_id):
        time.sleep(1)
        self.history=[{'id':'20261022T010000Z-abcdef12','created_at':time.time()}]
        return {'backup_id':self.history[0]['id']}


server.workspace=Workspace()


async def main():
    import uvicorn
    await open_browser()
    uv=uvicorn.Server(uvicorn.Config(server.app,host='127.0.0.1',port=int(os.environ['QA_PORT']),log_level='warning'))
    async def watch():
        while not server.shutdown_requested:await asyncio.sleep(.1)
        uv.should_exit=True
    watcher=asyncio.create_task(watch())
    try:await uv.serve()
    finally:
        watcher.cancel();await asyncio.gather(watcher,return_exceptions=True)
        await server.stop()


if __name__=='__main__':asyncio.run(main())
