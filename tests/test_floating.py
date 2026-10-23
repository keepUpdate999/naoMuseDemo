"""Offline service contracts and real Qt interaction, with no provider calls."""
import asyncio
import json
from pathlib import Path
import time
from types import SimpleNamespace

import pytest
import sqlite3
from fastapi import HTTPException
from business.history import History
from business.catalog import SCENARIOS
from desktop.presets import variants


def test_history_is_durable_and_restart_marks_inflight_interrupted(tmp_path):
    path=tmp_path/'history.sqlite3'; history=History(path)
    history.create_task('t1','request-1','customer','do work')
    first=history.append({'task_id':'t1','kind':'user','time':'12:00:00','text':'do work'})
    second=history.append({'task_id':'t1','kind':'action','time':'12:00:01','text':'clicked'})
    history.create_task('t2','request-2','orders','read orders');history.finish('t2','finished')
    restored=History(path)
    assert restored.by_request('request-1')=='t1'
    assert first['id']<second['id']
    assert [e['text'] for e in restored.events('t1')]==['do work','clicked']
    assert {t['id']:t['status'] for t in restored.tasks()}=={'t1':'interrupted','t2':'finished'}
    with pytest.raises(sqlite3.IntegrityError):restored.create_task('t3','request-1','customer','duplicate')
    assert len(restored.tasks())==2


def test_all_scenarios_have_two_ready_tasks_and_contact_reuse():
    assert len(SCENARIOS)==6
    for scenario in SCENARIOS:
        texts=variants(scenario)
        assert len(texts)==2 and len(set(texts))==2 and all(len(t)>20 for t in texts)
    for text in variants(next(s for s in SCENARIOS if s['id']=='contact')):
        assert '先查找' in text and '重复' in text


def test_workspace_events_do_not_leak_into_previous_task(monkeypatch):
    import real_server as server
    monkeypatch.setattr(server,'events',[]);monkeypatch.setattr(server,'history',None)
    monkeypatch.setattr(server,'active_task_id','previous-task')
    server.log('browser','opened outside task')
    assert server.events[-1]['task_id'] is None
    token=server.task_context.set('current-task')
    try:server.log('action','real task action')
    finally:server.task_context.reset(token)
    assert server.events[-1]['task_id']=='current-task'


def test_portable_source_allowlist_excludes_private_state_and_bytecode(tmp_path):
    from desktop.build_portable import copy_source
    copy_source(tmp_path)
    paths=list(tmp_path.rglob('*'))
    assert (tmp_path/'desktop/main.py').is_file() and (tmp_path/'vendor/LICENSE').is_file()
    assert not any('.local' in p.parts or '__pycache__' in p.parts or p.suffix=='.pyc' for p in paths)
    assert not any(p.name in ('model.json','credentials.json','budget.json') for p in paths)


@pytest.mark.asyncio
async def test_submission_dedup_and_stop_preserve_browser(tmp_path,monkeypatch):
    import real_server as server
    history=History(tmp_path/'history.sqlite3')
    for name,value in {'history':history,'events':[],'task':None,'reset_task':None,'agent':None,'active_task_id':None,'accepted_requests':{}}.items():monkeypatch.setattr(server,name,value)
    closed=[]
    async def close():closed.append(True)
    monkeypatch.setattr(server,'session',SimpleNamespace(close=close))
    monkeypatch.setattr(server,'read_budget',lambda:{'limit':None,'attempts':0})
    started=[]
    async def execute(body):
        started.append(body.prompt)
        try:await asyncio.sleep(60)
        finally:history.finish(server.active_task_id,'stopped')
    monkeypatch.setattr(server,'execute',execute)
    request=SimpleNamespace(headers={'x-demo-token':server.token})
    body=server.Run(scenario='customer',prompt='offline task',request_id='request-001')
    try:
        first=await server.run(body,request);await asyncio.sleep(0)
        again=await server.run(body,request)
        assert first['task_id']==again['task_id'] and again['duplicate']
        with pytest.raises(HTTPException) as exc:await server.run(server.Run(scenario='orders',prompt='other'),request)
        assert exc.value.status_code==409
        await server.stop_route(request)
        assert not closed and started==['offline task']
        assert history.tasks()[0]['status']=='stopped'
        assert (await server.run(body,request))['duplicate']
    finally:
        if server.running():server.task.cancel();await asyncio.gather(server.task,return_exceptions=True)


@pytest.fixture(scope='module')
def qt_app():
    pytest.importorskip('PySide6')
    from PySide6.QtWidgets import QApplication
    app=QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    yield app


@pytest.fixture
def window(qt_app,tmp_path):
    from PySide6.QtCore import QSettings
    from desktop.connection import Connection
    from desktop.main import Assistant
    connection=Connection();sent=[];connection.command=lambda name,body=None:sent.append((name,body))
    settings=QSettings(str(tmp_path/'settings.ini'),QSettings.IniFormat)
    widget=Assistant(connection,settings);widget.sent=sent
    widget.show();qt_app.processEvents()
    yield widget
    widget.quitting=True;widget.tray.hide();widget.close();widget.deleteLater();qt_app.processEvents()


def state(**overrides):
    return dict({'status':'idle','running':False,'resetting':False,'remaining':None,
                 'scenarios':SCENARIOS,'events':[],'backups':[],'desktop_protocol':1},**overrides)


def test_qt_default_task_click_guard_live_records_and_history(window,qt_app,tmp_path):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    window.update_state(state())
    assert window.scenario.count()==6 and window.run.isEnabled()
    original=window.prompt.toPlainText();QTest.mouseClick(window.swap,Qt.LeftButton)
    assert window.prompt.toPlainText()!=original
    QTest.mouseClick(window.run,Qt.LeftButton);QTest.mouseClick(window.run,Qt.LeftButton)
    assert len(window.sent)==1 and window.sent[0][0]=='run'
    assert window.sent[0][1]['request_id']
    window.command_done('run',{'accepted':True})
    assert not window.run.isEnabled()
    events=[{'id':1,'task_id':'t','kind':'user','time':'12:00:00','text':'OFFLINE QA 任务'},
            {'id':2,'task_id':'t','kind':'action','time':'12:00:01','text':'OFFLINE QA 已打开订单页面'}]
    window.update_state(state(status='running',running=True,events=events,task_id='t'))
    qt_app.processEvents()
    assert window.task_area.isHidden() and window.record_area.isVisible() and window.stop.isEnabled()
    assert '已打开' in window.logs.item(0).text() and not window.run.isEnabled()
    window.update_state(state(events=events,status='finished'));qt_app.processEvents()
    assert window.task_area.isVisible() and window.run.isEnabled()
    window.update_tasks([{'id':'t','created':time.time(),'prompt':'old task','status':'finished'}])
    window.history.setCurrentIndex(1);assert window.sent[-1]==('history','t')
    window.show_history('t',events);assert window.logs.count()==2
    window.connection_status(False,'连接中断');assert not window.run.isEnabled() and not window.stop.isEnabled()
    # Screenshot is generated from an explicitly offline fixture, not a model run.
    window.grab().save(str(tmp_path/'floating-offline-qa.png'))


def test_qt_reset_confirmation_fold_and_no_focus_on_updates(window,qt_app,monkeypatch):
    window.update_state(state())
    calls=[];monkeypatch.setattr(window,'raise_',lambda:calls.append('raise'))
    monkeypatch.setattr(window,'activateWindow',lambda:calls.append('activate'))
    window.update_state(state(status='running',running=True));assert not calls
    window.toggle_fold();assert window.collapsed and window.record_area.isHidden()
    window.toggle_fold();assert window.record_area.isVisible() and window.task_area.isHidden()
    window.update_state(state())
    monkeypatch.setattr(window,'confirm',lambda *a:False)
    window.reset();assert not window.sent
    monkeypatch.setattr(window,'confirm',lambda *a:True)
    window.reset();assert window.sent==[('reset',{'confirm':True,'backup_id':None})]
    window.command_done('reset',{})
    window.update_state(state(resetting=True,status='resetting'));assert not window.run.isEnabled()
    window.update_state(state());assert window.prompt.toPlainText()==variants(SCENARIOS[0])[0]


def test_connection_real_http_and_qt_run_stop_reconnect(qt_app,console_qa):
    from desktop.connection import Connection
    connection=Connection(int(console_qa.rsplit(':',1)[1]));states=[];completed=[];errors=[];links=[]
    original=connection.api.request;cut=[False];writes=[]
    def request(path,body=None):
        if path=='/api/status' and cut[0]:
            cut[0]=False;raise OSError('offline simulated transport interruption')
        if body is not None:writes.append(path)
        return original(path,body)
    connection.api.request=request
    connection.connection_changed.connect(lambda connected,message:links.append(connected))
    connection.state_received.connect(states.append)
    connection.completed.connect(lambda name,result:completed.append((name,result)))
    connection.failed.connect(lambda name,message:errors.append((name,message)))
    def wait(predicate):
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            qt_app.processEvents()
            if predicate():return
            time.sleep(.02)
        raise AssertionError('Desktop/HTTP integration timeout: '+str(errors))
    connection.start()
    try:
        wait(lambda:bool(states))
        connection.command('run',{'scenario':'customer','prompt':'wait-for-stop','request_id':'desktop-qa-001'})
        wait(lambda:any(s['running'] for s in states))
        connection.command('stop',{})
        wait(lambda:any(name=='stop' for name,_ in completed))
        wait(lambda:states[-1]['status']=='stopped')
        assert states[-1]['browser_open'] and not errors
        previous=len(states);cut[0]=True
        wait(lambda:False in links)
        wait(lambda:len(states)>previous)
        assert writes==['/api/run','/api/stop']
    finally:
        connection.close();assert connection.wait(6000)


# Reuse the isolated offline process; its finally stops only its own service.
from test_business_console import console_qa
