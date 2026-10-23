"""Actual Chromium actions on isolated fixture DOM; no model or business data."""
import asyncio
import pytest
import pytest_asyncio
from playwright.async_api import async_playwright
from business.browser import BusinessBrowser
from business.catalog import ERP,WIKI


@pytest_asyncio.fixture
async def visible_actions():
    async with async_playwright() as pw:
        browser=await pw.chromium.launch()
        context=await browser.new_context(viewport={'width':1000,'height':700})
        html='''<!doctype html><html><head><meta charset="utf-8"></head><body><h1>OFFLINE PRESENTATION QA</h1>
          <form method="get"><label>客户名称<input name="customer"></label>
          <select name="region"><option>华东</option><option>华北</option></select></form>
          <form method="post"><input name="protected" value="unchanged"></form>
          <button name="button_search_x">查询订单</button><p id="result">尚未点击</p></body></html>'''
        async def route(request):
            await request.fulfill(status=200,content_type='text/html',body=html,
                headers={'Content-Security-Policy':"default-src 'self'; script-src 'none'; style-src 'self'"})
        await context.route('**/*',route)
        page=await context.new_page();await page.goto(ERP+'/societe/list.php')
        await page.evaluate('''() => {window.clickCount=0;document.querySelector('button').addEventListener('click',()=>{
          window.clickCount++;document.querySelector('#result').textContent='已查询';});}''')
        session=BusinessBrowser('offline',headless=True)
        session.browser=browser;session.context=context;session.page=page;session.pages=[page]
        session.presenter.enabled=True
        try:yield session
        finally:await browser.close()


@pytest.mark.asyncio
async def test_real_click_ring_highlight_does_not_enter_agent_observation(visible_actions):
    session=visible_actions
    observation=await session.observe();button=next(e for e in observation['elements'] if e['tag']=='BUTTON')
    await session.act('click',target=button['id'])
    assert await session.page.evaluate('window.clickCount')==1
    assert await session.page.locator('#result').inner_text()=='已查询'
    cue=await session.page.locator('#guduu-action-cue').evaluate('''host=>({
      kind:host.dataset.kind,clicked:host.dataset.clicked,position:getComputedStyle(host).position,
      pointerEvents:getComputedStyle(host).pointerEvents,svg:!!host.shadowRoot.querySelector('svg')})''')
    assert cue=={'kind':'complete','clicked':'true','position':'fixed','pointerEvents':'none','svg':True}
    assert '点击「查询」' in await session.page.locator('#guduu-action-cue').get_attribute('data-label')
    after=await session.observe()
    assert 'GuDuu OS' not in after['text'] and len(after['elements'])==len(observation['elements'])
    assert all('GuDuu' not in str(e.get('label','')) for e in after['elements'])


@pytest.mark.asyncio
async def test_fill_selection_navigation_and_write_boundary(visible_actions):
    session=visible_actions;session.scenario='orders'
    observation=await session.observe()
    field=next(e for e in observation['elements'] if e.get('name')=='customer')
    await session.act('fill',target=field['id'],text='星河文化传媒')
    assert await session.page.locator('[name=customer]').input_value()=='星河文化传媒'
    observation=await session.observe();select=next(e for e in observation['elements'] if e['tag']=='SELECT')
    await session.act('select',target=select['id'],text='华北')
    assert await session.page.locator('select').input_value()=='华北'
    # Card writes remain denied before any presentation interaction is attempted.
    session.scenario='orders'
    await session.page.goto(ERP+'/commande/card.php?id=1')
    observation=await session.observe();protected=next(e for e in observation['elements'] if e.get('name')=='protected')
    with pytest.raises(ValueError,match='仅可查阅'):await session.act('fill',target=protected['id'],text='forbidden')
    assert await session.page.locator('[name=protected]').input_value()=='unchanged'
    assert await session.page.locator('#guduu-action-cue').count()==0
    await session.act('open',url=WIKI+'/doku.php?id=start')
    assert await session.page.locator('#guduu-action-cue').get_attribute('data-kind')=='complete'
    assert 'GuDuu OS' not in (await session.observe())['text']


@pytest.mark.asyncio
async def test_failed_visual_layer_does_not_retry_or_block_real_action(visible_actions,monkeypatch):
    import business.presentation as presentation
    session=visible_actions;monkeypatch.setattr(presentation,'SCRIPT','() => { throw new Error("offline visual failure"); }')
    observation=await session.observe();button=next(e for e in observation['elements'] if e['tag']=='BUTTON')
    await session.act('click',target=button['id'])
    assert await session.page.evaluate('window.clickCount')==1
    assert await session.page.locator('#result').inner_text()=='已查询'


@pytest.mark.asyncio
async def test_stop_during_target_preview_does_not_click(visible_actions):
    session=visible_actions
    observation=await session.observe();button=next(e for e in observation['elements'] if e['tag']=='BUTTON')
    task=asyncio.create_task(session.act('click',target=button['id']))
    try:
        await session.page.locator('#guduu-action-cue').wait_for(state='attached')
        task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
        assert await session.page.evaluate('window.clickCount')==0
    finally:
        if not task.done():task.cancel();await asyncio.gather(task,return_exceptions=True)
