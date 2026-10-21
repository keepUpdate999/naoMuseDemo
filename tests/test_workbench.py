"""Isolated application regression tests. No credentials, no external model requests."""
import asyncio
import json
import os
import re
from pathlib import Path
import socket
import subprocess
import sys
import time

import httpx
import pytest
from playwright.async_api import async_playwright, expect

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def qa_service(tmp_path_factory):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    env = {**os.environ, 'QA_PORT':str(port), 'QA_DATA':str(tmp_path_factory.mktemp('qa-data'))}
    log_path=tmp_path_factory.mktemp('qa-logs')/'server.log'
    log_file=log_path.open('wb')
    proc = subprocess.Popen([sys.executable, 'tests/serve_qa.py'], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=log_file)
    try:
        for _ in range(100):
            try:
                if httpx.get(base+'/health').status_code==200:
                    break
            except httpx.HTTPError:
                pass
            if proc.poll() is not None:
                raise AssertionError(log_path.read_text(encoding='utf-8',errors='replace'))
            time.sleep(.2)
        else:
            raise AssertionError('QA startup failed')
        yield base
    finally:
        if proc.poll() is None:
            try:
                token=re.search('name="demo-token" content="([^"]+)"',httpx.get(base).text)[1]
                httpx.post(base+'/api/shutdown',headers={'X-Demo-Token':token},json={},timeout=15).raise_for_status()
                proc.wait(timeout=15)
            except (httpx.HTTPError, subprocess.TimeoutExpired, TypeError):
                proc.terminate()
                proc.wait(timeout=15)
        log_file.close()


@pytest.mark.asyncio
async def test_task_live_image_zoom_and_reset(qa_service, tmp_path):
    async with async_playwright() as pw:
        browser=await pw.chromium.launch()
        try:
            page=await browser.new_page(viewport={'width':1440,'height':1000})
            errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            await page.goto(qa_service)
            await page.get_by_role('button',name='06  填写表单与追加修改').click()
            await page.get_by_label('你的任务').fill('离线完整流程')
            await page.get_by_role('button',name='智能执行操作').click()
            await expect(page.locator('#activity')).to_contain_text('本轮结束',timeout=15000)
            await expect(page.locator('#frame')).to_be_visible()
            assert await page.locator('#frame').evaluate('(img)=>img.complete && img.naturalWidth>0')
            await page.locator('#enlarge').click()
            assert await page.locator('.stage').evaluate('(e)=>e.getBoundingClientRect().width')>1400
            await page.screenshot(path=str(tmp_path/'live-zoom.png'),full_page=True)
            await page.keyboard.press('Escape')
            await expect(page.locator('#enlarge')).to_have_text('放大演示区')
            await page.get_by_role('button',name='手动彩排',exact=True).click()
            form=page.frame_locator('#preview')
            await expect(form.get_by_label('姓名',exact=True)).to_have_value('离线验收访客')
            await page.get_by_role('button',name='恢复本场素材').click()
            await expect(page.locator('#reset-dialog')).to_be_visible()
            await page.get_by_role('button',name='保留数据').click()
            await expect(form.get_by_label('姓名',exact=True)).to_have_value('离线验收访客')
            await page.get_by_role('button',name='恢复本场素材').click()
            await page.get_by_role('button',name='确认恢复').click()
            await expect(page.locator('#notice')).to_have_text('素材已恢复。')
            await expect(form.get_by_label('姓名',exact=True)).to_have_value('')
            assert not errors
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_stop_failure_and_recovery(qa_service):
    async with async_playwright() as pw:
        browser=await pw.chromium.launch()
        try:
            page=await browser.new_page()
            await page.goto(qa_service)
            await page.get_by_role('button',name='06  填写表单与追加修改').click()
            await page.get_by_label('你的任务').fill('等待取消')
            await page.get_by_role('button',name='智能执行操作').click()
            await expect(page.get_by_role('button',name='停止',exact=True)).to_be_enabled()
            await expect(page.get_by_role('button',name='恢复本场素材')).to_be_disabled()
            await page.reload()
            await expect(page.locator('#liveview')).to_be_visible()
            await expect(page.locator('#preview')).to_be_hidden()
            await page.get_by_role('button',name='停止',exact=True).click()
            await expect(page.locator('#notice')).to_contain_text('已停止执行')
            await expect(page.locator('#frame')).to_be_hidden()
            await expect(page.get_by_role('button',name='智能执行操作')).to_be_enabled()
            await page.get_by_label('你的任务').fill('测试异常')
            await page.get_by_role('button',name='智能执行操作').click()
            await expect(page.locator('#activity')).to_contain_text('执行失败',timeout=10000)
            await page.get_by_label('你的任务').fill('重新填写')
            await page.get_by_role('button',name='智能执行操作').click()
            await expect(page.locator('#activity')).to_contain_text('本轮结束',timeout=15000)
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_drafts_export_and_reconnect(qa_service, tmp_path):
    async with async_playwright() as pw:
        browser=await pw.chromium.launch()
        try:
            page=await browser.new_page(accept_downloads=True)
            await page.goto(qa_service)
            await page.get_by_label('你的任务').fill('   ')
            await expect(page.get_by_role('button',name='智能执行操作')).to_be_disabled()
            await page.get_by_role('button',name='02  跨标签页搬运信息').click()
            await page.get_by_role('button',name='01  网页表格编辑').click()
            await expect(page.get_by_label('你的任务')).to_have_value('   ')
            await page.get_by_role('button',name='AI 执行画面',exact=True).click()
            await page.get_by_role('button',name='06  填写表单与追加修改').click()
            await expect(page.locator('#preview')).to_be_visible()
            await page.get_by_role('button',name='填入这条指令').click()
            assert '下午场' in await page.get_by_label('你的任务').input_value()
            async with page.expect_download() as d:
                await page.get_by_role('button',name='导出演示记录').click()
            download=await d.value
            path=tmp_path/'record.json'
            await download.save_as(path)
            saved=json.loads(path.read_text(encoding='utf-8'))
            assert 'events' in saved and 'data' in saved
            assert 'api_key' not in path.read_text(encoding='utf-8')
            await expect(page.locator('#logs .event p').first).to_have_text(saved['events'][-1]['text'])
            await page.route('**/api/status',lambda route:route.fulfill(status=403,json={'detail':'restart'}))
            await expect(page.locator('#connection')).to_have_text('服务已重启，请刷新页面')
            await expect(page.get_by_role('button',name='智能执行操作')).to_be_disabled()
            await page.unroute('**/api/status')
            await expect(page.locator('#connection')).to_contain_text('本地测试替身')
            await page.screenshot(path=str(tmp_path/'workbench-tested.png'),full_page=True)
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_responsive_layout(qa_service, tmp_path):
    async with async_playwright() as pw:
        browser=await pw.chromium.launch()
        try:
            page=await browser.new_page()
            await page.goto(qa_service)
            for width,height in [(1440,900),(1280,720),(390,844)]:
                await page.set_viewport_size({'width':width,'height':height})
                assert await page.evaluate('document.documentElement.scrollWidth<=window.innerWidth'), f'horizontal overflow at {width}'
                await page.locator('#enlarge').click()
                await expect(page.locator('#enlarge')).to_contain_text('退出放大')
                await page.keyboard.press('Escape')
                await page.screenshot(path=str(tmp_path/f'layout-{width}.png'),full_page=True)
        finally:
            await browser.close()
