"""Browser-level console tests against an isolated offline controller."""
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
from playwright.async_api import async_playwright,expect

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def console_qa(tmp_path_factory):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    base=f'http://127.0.0.1:{port}'
    log_path=tmp_path_factory.mktemp('business-qa')/'server.log'
    with log_path.open('wb') as log,httpx.Client(trust_env=False,timeout=5) as client:
        proc=subprocess.Popen([sys.executable,'tests/serve_business_qa.py'],cwd=ROOT,
            env={**os.environ,'QA_PORT':str(port)},stdout=log,stderr=log)
        try:
            for _ in range(100):
                try:
                    if client.get(base+'/health').status_code==200:break
                except httpx.HTTPError:pass
                if proc.poll() is not None:raise AssertionError(log_path.read_text(errors='replace'))
                time.sleep(.1)
            else:raise AssertionError('Offline controller startup timed out')
            yield base
        finally:
            if proc.poll() is None:
                try:
                    token=re.search('name="demo-token" content="([^"]+)"',client.get(base).text)[1]
                    client.post(base+'/api/shutdown',json={},headers={'X-Demo-Token':token}).raise_for_status()
                    proc.wait(timeout=10)
                except (httpx.HTTPError,TypeError,subprocess.TimeoutExpired):
                    proc.terminate();proc.wait(timeout=10)


@pytest.mark.asyncio
async def test_drafts_empty_input_export_and_responsive(console_qa,tmp_path):
    async with async_playwright() as pw:
        browser=await pw.chromium.launch()
        try:
            page=await browser.new_page(viewport={'width':1440,'height':1000})
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            await page.goto(console_qa)
            await expect(page.locator('nav button')).to_have_count(6)
            await expect(page).to_have_title('GuDuu OS · 工作台')
            await expect(page.locator('#budget')).to_have_text('不限调用次数')
            assert '演示' not in await page.locator('body').inner_text()
            assert 'nanomuse' not in (await page.locator('body').inner_text()).lower()
            await expect(page.locator('#run')).to_have_text('智能执行操作')
            await page.locator('#prompt').fill('保留我的客户任务草稿')
            await page.locator('nav button').nth(3).click()
            await page.locator('#prompt').fill('文档任务草稿')
            await page.locator('nav button').nth(0).click()
            await expect(page.locator('#prompt')).to_have_value('保留我的客户任务草稿')
            await page.locator('#prompt').fill('  ')
            await expect(page.locator('#run')).to_be_disabled()
            await page.locator('#prompt').fill('offline-completion')
            await page.locator('#run').click()
            await expect(page.locator('#status')).to_have_text('任务已完成',timeout=10000)
            async with page.expect_download() as download:
                await page.locator('#export').click()
            exported=tmp_path/'record.json';await (await download.value).save_as(exported)
            data=json.loads(exported.read_text())
            assert data['remaining'] is None and any(e['kind']=='result' for e in data['events'])
            assert 'demo-token' not in exported.read_text()
            visible=[e for e in data['events'] if e['kind'] in ('user','assistant','result','error','stopped')]
            await expect(page.locator('#logs .event p').first).to_have_text(visible[-1]['text'])
            for width in (1440,1024,390):
                await page.set_viewport_size({'width':width,'height':900})
                assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth'),f'Overflow at {width}'
                await expect(page.locator('#run')).to_be_visible()
            assert not errors
        finally:await browser.close()


@pytest.mark.asyncio
async def test_run_refresh_stop_reopen_and_failure_recovery(console_qa):
    async with async_playwright() as pw:
        browser=await pw.chromium.launch()
        try:
            page=await browser.new_page()
            await page.goto(console_qa)
            await expect(page.locator('nav button')).to_have_count(6)
            await expect(page.locator('#tabs')).to_contain_text('已连接')
            await page.locator('#open').click()
            await expect(page.locator('#notice')).to_contain_text('业务操作窗口已打开')
            await page.locator('#prompt').fill('wait-for-stop')
            await page.locator('#run').click()
            await expect(page.locator('#stop')).to_be_enabled()
            await expect(page.locator('#reset-workspace')).to_be_disabled()
            await expect(page.locator('#open')).to_be_disabled()
            await expect(page.locator('nav button').first).to_be_disabled()
            # Reload must recover the active task, not enable duplicate execution.
            await page.reload()
            await expect(page.locator('#status')).to_have_text('正在应用中执行')
            await expect(page.locator('#run')).to_be_disabled()
            token=await page.locator('meta[name="demo-token"]').get_attribute('content')
            headers={'X-Demo-Token':token}
            r=await page.request.post(console_qa+'/api/run',headers=headers,data={'scenario':'customer','prompt':'duplicate'})
            assert r.status==409
            await page.locator('#stop').click()
            await expect(page.locator('#status')).to_have_text('已停止')
            await expect(page.locator('#tabs')).to_have_text('执行时自动连接应用')
            await page.locator('#open').click()
            await expect(page.locator('#tabs')).to_contain_text('已连接')
            await page.locator('#prompt').fill('simulate-failure')
            await page.locator('#run').click()
            await expect(page.locator('#status')).to_have_text('执行遇到问题',timeout=10000)
            await expect(page.locator('#run')).to_be_enabled()
            await page.locator('#prompt').fill('recovered')
            await page.locator('#run').click()
            await expect(page.locator('#status')).to_have_text('任务已完成',timeout=10000)
            await expect(page.locator('#logs')).to_contain_text('OFFLINE QA: completed recovered')
        finally:await browser.close()


@pytest.mark.asyncio
async def test_workspace_reset_cancel_confirm_refresh_and_restore(console_qa):
    async with async_playwright() as pw:
        browser=await pw.chromium.launch()
        try:
            page=await browser.new_page();await page.goto(console_qa)
            await expect(page.locator('nav button')).to_have_count(6)
            await page.locator('#reset-workspace').click()
            await expect(page.locator('#workspace-dialog')).to_be_visible()
            await page.locator('#workspace-cancel').click()
            await expect(page.locator('#workspace-dialog')).not_to_be_visible()
            await expect(page.locator('#run')).to_be_enabled()
            await page.locator('#prompt').fill('old task draft')
            await page.locator('#reset-workspace').click();await page.locator('#workspace-confirm').click()
            await expect(page.locator('#run')).to_be_disabled()
            await expect(page.locator('#reset-workspace')).to_be_disabled()
            await page.reload()
            await expect(page.locator('#status')).to_have_text('等待任务',timeout=10000)
            await expect(page.locator('#tabs')).to_contain_text('已连接')
            await expect(page.locator('#budget')).to_have_text('不限调用次数')
            await expect(page.locator('#logs')).to_contain_text('模型配置和调用记录保持不变')
            await page.locator('#reset-workspace').click()
            await page.locator('#backup-options summary').click()
            await expect(page.locator('#backup-select option')).to_have_count(1)
            await page.locator('#restore-backup').click()
            await expect(page.locator('#workspace-confirm')).to_have_text('备份并恢复')
            await page.locator('#workspace-confirm').click()
            await expect(page.locator('#status')).to_have_text('等待任务',timeout=10000)
            await expect(page.locator('#run')).to_be_enabled()
        finally:await browser.close()
