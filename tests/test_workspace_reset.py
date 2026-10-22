import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def stack(tmp_path,monkeypatch):
    import business.stack as module
    monkeypatch.setattr(module,'LOCAL',tmp_path)
    monkeypatch.setattr(module,'credentials',lambda:{})
    for key in ('BUSINESS_PROJECT','BUSINESS_DB_VOLUME','BUSINESS_DOCUMENTS_VOLUME','BUSINESS_WIKI_VOLUME'):
        monkeypatch.delenv(key,raising=False)
    s=module.Stack();s.owned=True;s.lock=object()
    s.calls=[]
    def compose(*args,**kwargs):
        s.calls.append((args,s.volumes()))
        return SimpleNamespace(stdout=b'',returncode=0)
    monkeypatch.setattr(s,'compose',compose)
    monkeypatch.setattr(s,'_start_services',lambda:s.calls.append(('start',s.volumes())))
    return s


def test_reset_retains_old_volumes_and_commits_new_pointer(stack,tmp_path):
    old=stack.volumes()
    result=stack.reset()
    assert stack.volumes()!=old
    assert json.loads(stack.pointer.read_text())['volumes']==stack.volumes()
    manifest=json.loads((tmp_path/'backups'/f'{result["backup_id"]}.json').read_text())
    assert manifest['volumes']==old and manifest['status']=='ready'
    assert stack.backups()[0]['id']==result['backup_id']
    assert all('down' not in args and 'rm' not in args for args,_ in stack.calls)


def test_reset_failure_reopens_old_workspace_without_losing_pointer(stack,monkeypatch,tmp_path):
    old=stack.volumes();starts=[]
    def start():
        starts.append(stack.volumes())
        if len(starts)==1:raise RuntimeError('offline initialization failure')
    monkeypatch.setattr(stack,'_start_services',start)
    with pytest.raises(RuntimeError,match='已恢复原工作区'):stack.reset()
    assert starts[0]!=old and starts[1]==old
    assert stack.volumes()==old and json.loads(stack.pointer.read_text())['volumes']==old
    backup=json.loads(next((tmp_path/'backups').glob('*.json')).read_text())
    assert backup['status']=='rolled_back' and backup['volumes']==old


def test_restore_also_backs_up_current_data_and_rejects_invalid_ids(stack,monkeypatch):
    old=stack.volumes();backup=stack.reset()['backup_id'];fresh=stack.volumes()
    def inspect(argv,**kwargs):
        assert argv[:3]==['docker','volume','inspect']
        assert set(argv[3:])==set(old.values())
    monkeypatch.setattr('business.stack.subprocess.run',inspect)
    clones=[]
    monkeypatch.setattr(stack,'_clone_volumes',lambda source,target:clones.append((source,target)))
    restore=stack.reset(backup)
    assert stack.volumes()!=old and clones==[(old,stack.volumes())]
    assert stack.backup_volumes(backup)==old
    assert stack.backup_volumes(restore['backup_id'])==fresh
    with pytest.raises(ValueError):stack.backup_volumes('../credentials')
    with pytest.raises(ValueError):stack.set_volumes({'db':'other_database','wiki':'other_wiki','documents':'other_documents'})


def test_unowned_workspace_cannot_reset(stack):
    stack.owned=False
    with pytest.raises(RuntimeError,match='本进程'):stack.reset()
    assert not stack.calls


def test_restore_copy_is_read_only_and_temporary_containers_are_removed(stack,monkeypatch):
    calls=[]
    def run(args,**kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=1 if args[:3]==['docker','volume','inspect'] else 0)
    monkeypatch.setattr('business.stack.subprocess.run',run)
    source=stack.volumes();target={r:v+'_copy' for r,v in source.items()}
    stack._clone_volumes(source,target)
    copies=[args for args in calls if args[:2]==['docker','run']]
    assert len(copies)==3
    for args in copies:
        assert '--rm' in args and '--read-only' in args and 'none' in args
        assert any('target=/from,readonly' in item for item in args)
        assert any('@sha256:' in item for item in args)


def test_copy_timeout_removes_only_the_task_owned_helper(stack,monkeypatch):
    import subprocess
    calls=[]
    def run(args,**kwargs):
        calls.append(args)
        if args[:2]==['docker','run']:raise subprocess.TimeoutExpired(args,300)
        return SimpleNamespace(returncode=1 if args[:3]==['docker','volume','inspect'] else 0)
    monkeypatch.setattr('business.stack.subprocess.run',run)
    source=stack.volumes()
    with pytest.raises(subprocess.TimeoutExpired):
        stack._clone_volumes(source,{r:v+'_copy' for r,v in source.items()})
    helper=next(args for args in calls if args[:2]==['docker','run'])
    name=helper[helper.index('--name')+1]
    assert name.startswith(stack.project+'-copy-')
    assert calls[-1]==['docker','rm','-f',name]


def test_stop_failure_attempts_to_reopen_original_workspace(stack,monkeypatch):
    old=stack.volumes();base=stack.compose
    def stop_fails(*args,**kwargs):
        if args==('stop',) and kwargs.get('check',True):raise RuntimeError('offline stop failure')
        return base(*args,**kwargs)
    monkeypatch.setattr(stack,'compose',stop_fails)
    with pytest.raises(RuntimeError,match='已恢复原工作区'):stack.reset()
    assert stack.volumes()==old and stack.calls[-1]==('start',old)


def test_reset_api_confirmation_busy_state_and_retained_model_usage(monkeypatch):
    import real_server as server
    class Workspace:
        owned=True
        def backups(self):return []
        def reset(self,backup_id):return {'backup_id':'20261022T010000Z-abcdef12'}
    class Session:
        page=None;pages=[];scenario=None
        async def close(self):pass
        async def reveal(self):pass
    async def opened():await asyncio.sleep(.15)
    monkeypatch.setattr(server,'workspace',Workspace())
    monkeypatch.setattr(server,'session',Session())
    monkeypatch.setattr(server,'agent',None)
    monkeypatch.setattr(server,'task',None)
    monkeypatch.setattr(server,'reset_task',None)
    monkeypatch.setattr(server,'workspace_lock',asyncio.Lock())
    monkeypatch.setattr(server,'status','idle')
    monkeypatch.setattr(server,'events',[])
    monkeypatch.setattr(server,'started',server.started)
    monkeypatch.setattr(server,'open_browser',opened)
    monkeypatch.setattr(server,'config',lambda:{'model':'offline'})
    monkeypatch.setattr(server,'read_budget',lambda:{'limit':None,'attempts':400})
    with TestClient(server.app) as client:
        headers={'X-Demo-Token':server.token}
        assert client.post('/api/workspace/reset',json={'confirm':True}).status_code==403
        assert client.post('/api/workspace/reset',headers=headers,json={'confirm':False}).status_code==422
        assert client.post('/api/workspace/reset',headers=headers,json={}).status_code==422
        assert client.post('/api/workspace/reset',headers=headers,json={'confirm':True,'backup_id':'../credentials'}).status_code==422
        assert client.post('/api/workspace/reset',headers={**headers,'Origin':'https://example.invalid'},json={'confirm':True}).status_code==403
        server.task=SimpleNamespace(done=lambda:False)
        try:assert client.post('/api/workspace/reset',headers=headers,json={'confirm':True}).status_code==409
        finally:server.task=None
        assert client.post('/api/workspace/reset',headers=headers,json={'confirm':True}).status_code==202
        assert client.post('/api/workspace/reset',headers=headers,json={'confirm':True}).status_code==409
        for endpoint,body in [('/api/run',{'scenario':'customer','prompt':'blocked'}),('/api/open',{}),('/api/stop',{}),('/api/shutdown',{})]:
            assert client.post(endpoint,headers=headers,json=body).status_code==409
        import time
        for _ in range(50):
            state=client.get('/api/status',headers=headers).json()
            if not state['resetting']:break
            time.sleep(.02)
        assert state['status']=='idle' and state['calls']==400 and state['unlimited']
