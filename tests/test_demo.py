import asyncio
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time

import httpx
import pytest
from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from data import Store, seed
from schemas import validate_data
from browser_agent import BrowserSession, build_agent


@pytest.fixture(scope='module')
def service(tmp_path_factory):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    env = {**os.environ, 'DEMO_PORT': str(port), 'DEMO_DATA': str(tmp_path_factory.mktemp('server'))}
    proc = subprocess.Popen([sys.executable, 'server.py'], cwd=Path(__file__).resolve().parents[1], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        for _ in range(100):
            try:
                if httpx.get(base + '/health').status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            if proc.poll() is not None:
                raise AssertionError(proc.stderr.read().decode(errors='replace'))
            time.sleep(.2)
        else:
            raise AssertionError('Server startup timeout')
        token = re.search('name="demo-token" content="([^"]+)"', httpx.get(base).text)[1]
        yield base, {'X-Demo-Token': token}
    finally:
        if proc.poll() is None:
            try:
                token = re.search('name="demo-token" content="([^"]+)"', httpx.get(base).text)[1]
                httpx.post(base+'/api/shutdown',headers={'X-Demo-Token':token},json={},timeout=15).raise_for_status()
                proc.wait(timeout=15)
            except (httpx.HTTPError, subprocess.TimeoutExpired, TypeError):
                proc.terminate()
                proc.wait(timeout=15)
        proc.stderr.close()


def test_storage_and_validation(tmp_path):
    store = Store(tmp_path / 'state.db')
    store.write('form', {'name': '访客', 'session': '下午场', 'people': 3, 'remark': ''})
    assert Store(store.path).read()['form']['people'] == 3
    store.reset('form')
    assert store.read()['form'] == seed()['form']
    with pytest.raises(ValueError):
        validate_data('orders', [])
    with pytest.raises(ValueError):
        validate_data('form', {'name': 'a', 'session': '下午场', 'people': 21, 'remark': ''})
    with pytest.raises(ValueError):
        validate_data('tasks', [])


def test_api_gates(service):
    base, headers = service
    assert httpx.post(base+'/api/run', json={'prompt': '填写', 'scene': 'form'}).status_code == 403
    assert httpx.post(base+'/api/run', headers=headers, json={'prompt': '填写', 'scene': 'form'}).status_code == 409
    assert httpx.post(base+'/api/data', headers={'Origin': 'https://evil.invalid'}, json={'key':'notes','value':[]}).status_code == 403
    assert httpx.post(base+'/api/data', json={'key':'form','value':{'people':99}}).status_code == 422
    assert httpx.get(base+'/api/frame', headers=headers).status_code == 503
    assert httpx.get(base+'/api/status',headers=headers).json()['configured'] is False
    assert httpx.post(base+'/api/reset',headers=headers,json={'scene':'invalid'}).status_code == 422
    assert httpx.post(base+'/api/run',headers=headers,json={'prompt':'   ','scene':'form'}).status_code == 422
    # Live image Object URLs must be permitted by the actual page response policy.
    assert 'blob:' in httpx.get(base).headers['content-security-policy'].split('img-src')[1].split(';')[0]


@pytest.mark.asyncio
async def test_six_scenes_and_persistence(service, tmp_path):
    base, _ = service
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            page = await browser.new_page(viewport={'width':1440,'height':1100})
            errors=[]
            page.on('pageerror', lambda e: errors.append(str(e)))
            await page.goto(base)
            await page.get_by_text('模型未连接 · 可手动彩排').wait_for()
            assert await page.get_by_role('button',name='智能执行操作').is_disabled()
            await page.screenshot(path=str(tmp_path/'workbench.png'),full_page=True)
            # Table: real controls, save, reload and compare unrelated row.
            await page.goto(base+'/scene/table')
            await page.get_by_label('场地布置负责人').fill('演示甲')
            await page.get_by_label('场地布置状态').select_option(label='进行中')
            await page.get_by_role('button',name='保存修改').click()
            await page.get_by_text('已保存 · 刷新后仍可打开').wait_for()
            await page.reload()
            assert await page.get_by_label('场地布置负责人').input_value() == '演示甲'
            assert await page.get_by_label('物资采购负责人').input_value() == '陈舟'
            # Transfer: real popup, source and destination separate tabs.
            await page.goto(base+'/scene/transfer')
            async with page.expect_popup() as popup:
                await page.get_by_role('link',name='在新标签页打开记事本').click()
            note=await popup.value
            await note.get_by_label('笔记标题').fill('开放日信息')
            await note.get_by_label('笔记内容').fill('2026年11月8日09:00至12:00，星河体验中心二楼，携带水杯、笔记本、报名确认信息。')
            await note.get_by_role('button',name='保存笔记').click()
            await note.get_by_text('已保存 · 刷新后仍可打开').wait_for()
            await note.reload()
            await note.get_by_role('button',name='开放日信息',exact=True).click()
            assert '二楼' in await note.get_by_label('笔记内容').input_value()
            # Notes: create and update.
            await note.get_by_role('button',name='新建笔记').click()
            await note.get_by_label('笔记标题').fill('会前准备')
            await note.get_by_label('笔记内容').fill('检查设备\n准备资料\n安排签到')
            await note.get_by_role('button',name='保存笔记').click()
            await note.get_by_role('button',name='会前准备',exact=True).wait_for()
            await note.get_by_label('笔记内容').fill('检查设备\n准备资料\n安排签到\n检查现场网络')
            await note.get_by_role('button',name='保存笔记').click()
            await note.get_by_text('已保存 · 刷新后仍可打开').wait_for()
            await note.reload()
            await note.get_by_role('button',name='会前准备',exact=True).click()
            assert '检查现场网络' in await note.get_by_label('笔记内容').input_value()
            # Orders: boundary, exact target and changed condition.
            await page.goto(base+'/scene/orders')
            await page.get_by_label('订单状态').select_option(label='待处理')
            await page.get_by_label('金额大于').fill('500')
            await page.get_by_role('button',name='应用筛选').click()
            await page.get_by_label('排序').select_option(label='金额从高到低')
            assert await page.locator('#rows button').first.inner_text() == 'DEMO-030'
            await page.get_by_role('button',name='DEMO-030').click()
            assert '3300' in await page.locator('#detail').inner_text()
            await page.get_by_label('金额大于').fill('1500')
            await page.get_by_role('button',name='应用筛选').click()
            assert await page.locator('#count').inner_text() == '找到 6 条订单'
            await page.get_by_label('金额大于').fill('3300')
            await page.get_by_role('button',name='应用筛选').click()
            assert await page.locator('#count').inner_text() == '找到 0 条订单'
            # Search and exact source.
            await page.goto(base+'/scene/search')
            await page.get_by_label('搜索关键词').fill('停车')
            await page.get_by_role('button',name='搜索资料').click()
            await page.locator('[data-article="2"]').click()
            assert '东门' in await page.locator('#article').inner_text()
            # Form follow-up, preserve other fields and reload.
            await page.goto(base+'/scene/form')
            await page.get_by_label('姓名').fill('演示访客')
            await page.get_by_label('参加人数').fill('2')
            await page.get_by_label('备注').fill('需要纸质资料')
            await page.get_by_role('button',name='保存草稿').click()
            await page.get_by_text('已保存 · 刷新后仍可打开').wait_for()
            await page.get_by_label('活动场次').select_option(label='下午场')
            await page.get_by_label('参加人数').fill('3')
            await page.get_by_role('button',name='保存草稿').click()
            await page.get_by_text('已保存 · 刷新后仍可打开').wait_for()
            await page.reload()
            assert await page.get_by_label('参加人数').input_value() == '3'
            assert await page.get_by_label('备注').input_value() == '需要纸质资料'
            assert not errors
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_real_nanomuse_loop(service, tmp_path):
    from nanomuse.llm import MockLLM
    from nanomuse.schema import Function, ToolCall, LLMResponse
    base, _ = service
    session = BrowserSession(base)
    try:
        view = await session.act('open', url=base+'/scene/form')
        def target(label):
            return next(e['id'] for e in view['elements'] if e['label'] == label)
        # IDs come from the real current DOM; mock only the model's choices.
        name = next(e['id'] for e in view['elements'] if e['tag']=='INPUT')
        save = target('保存草稿')
        def call(**args):
            return LLMResponse(tool_calls=[ToolCall(function=Function(name='demo_browser',arguments=json.dumps(args)))])
        mock = MockLLM([call(action='fill',target=name,text='测试模型访客'),call(action='click',target=save),LLMResponse(content='已执行，请检查结果')])
        logs=[]
        agent=build_agent({},session,lambda k,v:logs.append((k,v)),llm_override=mock,data_dir=tmp_path/'runtime')
        await agent.run('填写姓名并保存演示草稿')
        async with httpx.AsyncClient() as client:
            data=(await client.get(base+'/api/data')).json()
        assert data['form']['name']=='测试模型访客'
        assert len(mock.calls)==3
        assert any(k=='tool_call' for k,v in logs)
        await session.act('new_tab',url=base+'/scene/notes')
        assert len(await session.act('tabs'))==2
        await session.act('switch_tab',tab=0)
        assert session.page.url.endswith('/form')
        await session.act('open',url=base+'/scene/transfer')
        await session.page.get_by_role('link',name='在新标签页打开记事本').click()
        await asyncio.sleep(.3)
        assert len(session.pages)==3 and session.page.url.endswith('/notes')
        with pytest.raises(ValueError):
            await session.act('open',url='https://example.com')
        with pytest.raises(ValueError):
            await session.act('open',url=base+'/api/shutdown')
        await asyncio.sleep(.5)
        assert session.jpeg and session.frame_time
    finally:
        await session.close()
    assert not session.pages and session.jpeg is None


@pytest.mark.asyncio
async def test_stop_and_reset_inflight(service, monkeypatch, tmp_path):
    import server
    from fastapi.testclient import TestClient
    monkeypatch.setattr(server, 'store', Store(tmp_path/'cancel.db'))
    writes=[]
    async def delayed_work():
        await asyncio.sleep(60)
        writes.append('must never happen')
    active = asyncio.create_task(delayed_work())
    monkeypatch.setattr(server,'task',active)
    with TestClient(server.app) as client:
        r=client.post('/api/reset',headers={'X-Demo-Token':server.token},json={'scene':'form'})
        assert r.status_code==409
        # Run stop on the task's owning event loop, not TestClient's worker loop.
        await server.stop()
        assert active.cancelled() and not writes
        r=client.post('/api/reset',headers={'X-Demo-Token':server.token},json={'scene':'form'})
        assert r.status_code==200
