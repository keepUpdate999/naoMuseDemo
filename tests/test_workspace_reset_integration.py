"""Opt-in isolated Docker reset/restore acceptance, never the user's workspace."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import time

import pytest
from fastapi.testclient import TestClient

pytestmark=pytest.mark.skipif(os.environ.get('WORKSPACE_RESET_INTEGRATION')!='1',reason='Starts a dedicated disposable reset QA project')
ROOT=Path(__file__).resolve().parents[1]


def local_hashes():
    return {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() if (ROOT/name).exists() else None
            for name in ('.local/model.json','.local/live-acceptance-20261022/budget.json','.local/business/credentials.json')}


def wait_reset(client,headers):
    for _ in range(1200):
        state=client.get('/api/status',headers=headers).json()
        if not state['resetting']:
            assert state['status']=='idle',state['events'][-2:]
            assert state['browser_open'] and len(state['tabs'])==7
            return state
        time.sleep(.5)
    raise AssertionError('Isolated reset did not finish within ten minutes')


def test_isolated_real_reset_and_restore(tmp_path,monkeypatch):
    import business.stack as module
    import business.browser as browser_module
    import real_server as server
    from business.materials import PAGES
    project='nanomuse-reset-qa-'+secrets.token_hex(4)
    ports=[]
    with socket.socket() as first,socket.socket() as second:
        for sock in (first,second):
            sock.bind(('127.0.0.1',0));ports.append(sock.getsockname()[1])
    for key,value in [('BUSINESS_PROJECT',project),('BUSINESS_ERP_PORT',str(ports[0])),('BUSINESS_WIKI_PORT',str(ports[1]))]:
        monkeypatch.setenv(key,value)
    monkeypatch.setattr(module,'LOCAL',tmp_path)
    erp=f'http://127.0.0.1:{ports[0]}';wiki=f'http://127.0.0.1:{ports[1]}'
    monkeypatch.setattr(browser_module,'ERP',erp);monkeypatch.setattr(browser_module,'WIKI',wiki)
    monkeypatch.setattr(server,'BusinessBrowser',lambda password:browser_module.BusinessBrowser(password,headless=True))
    monkeypatch.setattr(server,'config',lambda:{'model':'OFFLINE reset verification'})
    monkeypatch.setattr(server,'session',None);monkeypatch.setattr(server,'agent',None)
    monkeypatch.setattr(server,'task',None);monkeypatch.setattr(server,'reset_task',None)
    monkeypatch.setattr(server,'events',[]);monkeypatch.setattr(server,'workspace_lock',asyncio.Lock())
    monkeypatch.setattr(server,'started',time.time());monkeypatch.setattr(server,'status','idle')
    def no_model(*a,**k):raise AssertionError('This acceptance must not call a model')
    monkeypatch.setattr(server,'build_agent',no_model)
    protected_before=local_hashes()
    s=module.Stack();monkeypatch.setattr(server,'workspace',s)
    marker='RESET-QA-'+secrets.token_hex(4)

    def counts():
        code="define('NOLOGIN',1);define('NOCSRFCHECK',1);require '/var/www/html/master.inc.php';$out=[];foreach(['societe','commande','socpeople'] as $t){$r=$db->query('SELECT COUNT(*) AS n FROM '.MAIN_DB_PREFIX.$t);$out[$t]=(int)$db->fetch_object($r)->n;}echo json_encode($out);"
        return json.loads(s.compose('exec','-T','erp','php','-r',code).stdout)

    async def inspect(modify=False,fresh=False):
        session=browser_module.BusinessBrowser(module.credentials()['BUSINESS_APP_PASSWORD'],headless=True)
        try:
            await session.start()
            await session.act('open',url=erp+'/societe/note.php?id=1')
            if modify:
                observed=await session.observe()
                edit=next(e for e in observed['elements'] if 'action=editnote_public' in (e.get('href') or ''))
                await session.act('click',target=edit['id'])
                await session.page.locator('[name="note_public"]').fill(marker)
                await session.page.locator('[name="modify"]').click();await session.observe()
                await session.act('open',url=erp+'/contact/card.php?action=create')
                await session.page.locator('[name="lastname"]').fill(marker)
                await session.page.locator('[name="email"]').fill('reset.qa@example.invalid')
                await session.page.locator('select[name="socid"]').select_option('1')
                await session.page.locator('[name="add"]').click();await session.observe()
            else:
                text=await session.page.locator('body').inner_text()
                assert (marker not in text) if fresh else (marker in text)
            await session.act('open',url=wiki+'/doku.php?id=work:checklist'+('&do=edit' if modify else ''))
            if modify:
                await session.page.locator('[name="wikitext"]').fill('====== Reset QA ======\n'+marker)
                await session.page.locator('[name="do[save]"]').click();await session.observe()
            else:
                raw=await session.context.request.get(wiki+'/doku.php?id=work:checklist&do=export_raw')
                text=await raw.text()
                assert text.strip()==PAGES['work:checklist'].strip() if fresh else marker in text
                evidence=ROOT/'.local/business/evidence';evidence.mkdir(parents=True,exist_ok=True)
                await session.page.screenshot(path=str(evidence/('reset-fresh-workspace.png' if fresh else 'reset-restored-workspace.png')),full_page=True)
        finally:await session.close()

    try:
        print('Starting isolated project '+project,flush=True)
        s.start();assert counts()=={'societe':24,'commande':18,'socpeople':1}
        asyncio.run(inspect(modify=True));assert counts()['socpeople']==2
        old=s.volumes()
        with TestClient(server.app) as client:
            headers={'X-Demo-Token':server.token}
            print('Resetting isolated workspace through actual controller API',flush=True)
            assert client.post('/api/workspace/reset',headers=headers,json={'confirm':True}).status_code==202
            state=wait_reset(client,headers)
            assert counts()=={'societe':24,'commande':18,'socpeople':1}
            asyncio.run(inspect(fresh=True))
            backup=state['backups'][0]['id'];assert s.backup_volumes(backup)==old
            print('Restoring retained data through actual controller API',flush=True)
            assert client.post('/api/workspace/reset',headers=headers,json={'confirm':True,'backup_id':backup}).status_code==202
            wait_reset(client,headers)
            assert counts()['socpeople']==2 and s.volumes()!=old and s.backup_volumes(backup)==old
            asyncio.run(inspect(fresh=False))
        assert local_hashes()==protected_before
        record={'passed':True,'project':project,'fresh_counts':{'customers':24,'orders':18,'contacts':1},'old_notes_docs_and_contact_restored':True,'protected_model_credentials_and_ledger_unchanged':True}
        (ROOT/'.local/business/evidence/workspace-reset-integration.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    finally:
        owned=s.owned
        try:
            s.stop()
        finally:
            if owned:
                s.compose('down',check=False)
                names=subprocess.check_output(['docker','volume','ls','--filter',f'label=com.docker.compose.project={project}','--format','{{.Name}}'],text=True).split()
                assert all(name.startswith(project+'_') for name in names)
                if names:subprocess.run(['docker','volume','rm',*names],check=True,capture_output=True)
