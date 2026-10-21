import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from business.browser import BusinessBrowser
from business.catalog import SCENARIOS
from business.materials import PAGES


def test_real_app_boundary_and_materials():
    browser=BusinessBrowser('never-show')
    for s in SCENARIOS:
        assert browser.allowed(s['url'])
    for url in ['https://example.com','http://127.0.0.1:18889/api/data',
                'http://127.0.0.1:18892/','http://127.0.0.1:18893/admin/index.php',
                'http://evil@127.0.0.1:18893/societe/list.php',
                'http://127.0.0.1:18893/%61dmin/index.php',
                'http://127.0.0.1:18893/societe/%2e%2e/admin/index.php',
                'http://127.0.0.1:18894/install.php']:
        assert not browser.allowed(url)
    assert len(PAGES)==20
    assert '东门' in PAGES['handbook:parking'] and 'B区' in PAGES['handbook:parking']


def test_cross_system_write_targets_keep_orders_read_only():
    browser=BusinessBrowser('offline')
    browser.scenario='transfer'
    assert browser.can_write('http://127.0.0.1:18893/societe/note.php?id=1')
    assert browser.can_write('http://127.0.0.1:18894/doku.php?id=work:followup')
    assert browser.can_write('http://127.0.0.1:18893/commande/list.php')
    assert not browser.can_write('http://127.0.0.1:18893/commande/note.php?id=7')
    assert not browser.can_write('http://127.0.0.1:18893/commande/card.php?id=7')
    browser.scenario='contact'
    assert browser.can_write('http://127.0.0.1:18893/contact/card.php?action=create')
    assert not browser.can_write('http://127.0.0.1:18894/doku.php?id=work:followup')


@pytest.mark.asyncio
@pytest.mark.parametrize('limit',[60,120,160])
async def test_budget_limit_and_output_cap(tmp_path,monkeypatch,limit):
    import business.budget as budget
    path=tmp_path/'budget.json';monkeypatch.setattr(budget,'LEDGER',path)
    initial={'limit':limit,'attempts':limit-1,'responses':0,'input_tokens':0,'output_tokens':0,'requests':[]}
    path.write_text(json.dumps(initial))
    calls=[]
    class Inner:
        settings=SimpleNamespace()
        async def ask(self,*args,**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(usage={'prompt_tokens':20,'completion_tokens':5})
    llm=budget.BudgetLLM(Inner(),lambda *a:None)
    await llm.ask([],max_tokens=8000)
    assert calls==[{'max_tokens':1024}]
    assert budget.read_budget()['input_tokens']==20
    assert budget.read_budget()['output_tokens']==5
    with pytest.raises(RuntimeError,match=str(limit)):
        await llm.ask([])
    assert len(calls)==1


@pytest.mark.asyncio
async def test_cancelled_request_is_charged_once_and_unlocks_ledger(tmp_path,monkeypatch):
    import asyncio
    import business.budget as budget
    path=tmp_path/'budget.json';monkeypatch.setattr(budget,'LEDGER',path)
    path.write_text(json.dumps({'limit':160,'attempts':152,'responses':146,'input_tokens':0,'output_tokens':0,'requests':[]}))
    entered=asyncio.Event()
    class Inner:
        settings=SimpleNamespace()
        count=0
        async def ask(self,*args,**kwargs):
            self.count+=1
            if self.count==1:
                entered.set();await asyncio.Event().wait()
            return SimpleNamespace(usage={'prompt_tokens':2,'completion_tokens':1})
    inner=Inner();llm=budget.BudgetLLM(inner,lambda *a:None)
    task=asyncio.create_task(llm.ask([]))
    await asyncio.wait_for(entered.wait(),timeout=3)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    cancelled=budget.read_budget()
    assert cancelled['attempts']==153 and cancelled['responses']==146
    assert cancelled['requests'][-1]['status']=='failed'
    assert cancelled['requests'][-1]['error_type']=='CancelledError'
    # A new explicit call can acquire the released lock; cancellation never retries.
    assert inner.count==1
    await llm.ask([])
    assert inner.count==2 and budget.read_budget()['attempts']==154
    assert budget.read_budget()['responses']==147


@pytest.mark.asyncio
async def test_unlimited_budget_preserves_history_and_output_cap(tmp_path,monkeypatch):
    import business.budget as budget
    path=tmp_path/'budget.json';monkeypatch.setattr(budget,'LEDGER',path)
    path.write_text(json.dumps({'limit':None,'attempts':1000,'responses':999,'input_tokens':1,'output_tokens':1,'requests':[{'number':1000,'status':'failed'}]}))
    class Inner:
        settings=SimpleNamespace()
        async def ask(self,*a,**k):
            assert k['max_tokens']==1024
            return SimpleNamespace(usage={'prompt_tokens':2,'completion_tokens':1})
    await budget.BudgetLLM(Inner(),lambda *a:None).ask([],max_tokens=8000)
    data=budget.read_budget()
    assert data['limit'] is None and data['attempts']==1001
    assert data['requests'][0]=={'number':1000,'status':'failed'}
    assert data['responses']==1000


def test_console_no_embed_auth_and_validation(monkeypatch):
    import real_server as server
    monkeypatch.setattr(server,'config',lambda:{'model':'offline'})
    monkeypatch.setattr(server,'read_budget',lambda:{'attempts':46})
    with TestClient(server.app) as client:
        html=client.get('/').text
        assert '<iframe' not in html
        assert 'GuDuu' in html and 'OS' in html
        assert 'id="open"' in html and '打开操作窗口' in html and '演示' not in html
        assert 'src="/assets/logo.png"' in html
        assert client.get('/api/status').status_code==403
        headers={'X-Demo-Token':server.token}
        assert client.get('/api/status',headers=headers).json()['remaining']==14
        assert client.post('/api/run',headers=headers,json={'scenario':'customer','prompt':'   '}).status_code==422
        assert client.post('/api/open',headers=headers,json={'scenario':'missing'}).status_code==422
        assert client.post('/api/open',headers={**headers,'origin':'https://evil.invalid'},json={}).status_code==403


@pytest.mark.asyncio
async def test_execute_constructs_native_agent_before_model_call(monkeypatch,tmp_path):
    import real_server as server
    from browser_agent import build_agent
    class Session:
        base='http://127.0.0.1:18893'
        async def act(self,*args,**kwargs):return {}
        async def reveal(self):pass
    settings_used=[]
    prompts_seen=[]
    async def opened():pass
    class FakeAgent:
        def __init__(self,actual):
            self.settings=actual.settings;self.llm=actual.llm
        async def run(self,prompt):
            settings_used.append(self.settings.agent.max_context_messages)
            prompts_seen.append(self.prompt_addendum())
            return 'offline construction passed'
    def make(config,session,log,**kwargs):
        config={**config,'api_key':'offline','provider':'openai','model':'offline'}
        actual=build_agent(config,session,log,data_dir=tmp_path)
        return FakeAgent(actual)
    monkeypatch.setattr(server,'agent',None)
    monkeypatch.setattr(server,'session',Session())
    monkeypatch.setattr(server,'open_browser',opened)
    monkeypatch.setattr(server,'config',lambda:{})
    monkeypatch.setattr(server,'build_agent',make)
    monkeypatch.setattr(server,'events',[])
    try:
        await server.execute(server.Run(scenario='customer',prompt='offline startup'))
        assert server.status=='finished'
        assert settings_used==[30]
        await server.execute(server.Run(scenario='document',prompt='new task must replace old task'))
        assert '<current_user_task>\noffline startup\n</current_user_task>' in prompts_seen[0]
        assert '<current_user_task>\nnew task must replace old task\n</current_user_task>' in prompts_seen[1]
        assert 'offline startup' not in prompts_seen[1]
    finally:
        await server.close_agent()


@pytest.mark.asyncio
async def test_current_task_survives_native_history_trimming(tmp_path):
    from browser_agent import build_agent
    from nanomuse.schema import Message
    from real_server import task_addendum
    a=build_agent({'provider':'openai','model':'offline','api_key':'offline'},SimpleNamespace(base='http://127.0.0.1:18893'),lambda *x:None,data_dir=tmp_path)
    try:
        a.settings.agent.max_context_messages=2
        a.messages=[Message.user('current-goal-anchor')]+[Message(role='assistant',content='intermediate observation') for _ in range(8)]
        a.prompt_addendum=lambda:task_addendum('current-goal-anchor')
        assert all(m.content!='current-goal-anchor' for m in a.context_messages())
        assert 'current-goal-anchor' in a.build_system_prompt('current-goal-anchor','')
    finally:
        await a.llm.client.close()
