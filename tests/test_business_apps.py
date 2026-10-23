"""Opt-in real applications integration; browser interactions, no model calls."""
import os
from pathlib import Path
import uuid

import pytest
from playwright.async_api import expect
from business.browser import BusinessBrowser
from business.catalog import ERP,WIKI
from business.stack import credentials

pytestmark=pytest.mark.skipif(os.environ.get('BUSINESS_INTEGRATION')!='1',reason='Requires task-owned real application stack')
EVIDENCE=Path(__file__).resolve().parents[1]/'.local/business/evidence'


@pytest.mark.asyncio
async def test_headed_viewport_follows_native_window_on_all_seven_tabs():
    session=BusinessBrowser(credentials()['BUSINESS_APP_PASSWORD'],headless=False)
    evidence=EVIDENCE/'responsive';evidence.mkdir(parents=True,exist_ok=True)
    try:
        await session.prepare_workspace();session.presenter.enabled=False
        assert len(session.pages)==7 and all(p.viewport_size is None for p in session.pages)
        cdp=await session.context.new_cdp_session(session.page)
        window=(await cdp.send('Browser.getWindowForTarget'))['windowId']
        await cdp.send('Browser.setWindowBounds',{'windowId':window,'bounds':{'windowState':'normal'}})
        await cdp.send('Browser.setWindowBounds',{'windowId':window,'bounds':{'left':10,'top':10,'width':1100,'height':760}})
        await session.page.wait_for_function('innerWidth < 1200')
        small=await session.page.evaluate('innerWidth')
        await cdp.send('Browser.setWindowBounds',{'windowId':window,'bounds':{'width':1900,'height':1050}})
        await session.page.wait_for_function('innerWidth > 1700')
        large=await session.page.evaluate('innerWidth');assert large>small+600
        for page in session.pages:
            await page.bring_to_front()
            await page.wait_for_function('innerWidth > 1700')
            metrics=await page.evaluate('({inner:innerWidth,outer:outerWidth,height:innerHeight,outerHeight})')
            assert 0<=metrics['outer']-metrics['inner']<=40,metrics
            assert 0<metrics['outerHeight']-metrics['height']<180,metrics
        await cdp.send('Browser.setWindowBounds',{'windowId':window,'bounds':{'windowState':'maximized'}})
        contacts=session.pages[3];await contacts.bring_to_front()
        await contacts.wait_for_function('innerWidth >= outerWidth - 40')
        await contacts.screenshot(path=str(evidence/'contacts-maximized.png'))
        wiki=session.pages[1];await wiki.bring_to_front()
        await wiki.wait_for_function('innerWidth >= outerWidth - 40')
        await wiki.screenshot(path=str(evidence/'wiki-maximized.png'))
        await cdp.send('Browser.setWindowBounds',{'windowId':window,'bounds':{'windowState':'normal'}})
        await cdp.send('Browser.setWindowBounds',{'windowId':window,'bounds':{'width':1100,'height':760}})
        await wiki.wait_for_function('innerWidth < 1200')
        assert await wiki.evaluate('innerWidth')<large
        await cdp.detach()
    finally:await session.close()


@pytest.mark.asyncio
async def test_visible_browser_reveal_keeps_geometry_and_logs_real_actions(monkeypatch):
    session=BusinessBrowser(credentials()['BUSINESS_APP_PASSWORD'],headless=False)
    events=[];session.event_log=lambda kind,text:events.append((kind,text))
    try:
        await session.prepare_workspace()
        cdp=await session.context.new_cdp_session(session.page)
        window=await cdp.send('Browser.getWindowForTarget')
        await cdp.send('Browser.setWindowBounds',{'windowId':window['windowId'],'bounds':{'windowState':'normal'}})
        await cdp.send('Browser.setWindowBounds',{'windowId':window['windowId'],'bounds':{'left':100,'top':90,'width':1100,'height':760}})
        before=(await cdp.send('Browser.getWindowForTarget'))['bounds']
        await session.reveal()
        assert (await cdp.send('Browser.getWindowForTarget'))['bounds']==before
        await cdp.send('Browser.setWindowBounds',{'windowId':window['windowId'],'bounds':{'windowState':'maximized'}})
        await session.reveal()
        assert (await cdp.send('Browser.getWindowForTarget'))['bounds']['windowState']=='maximized'
        await cdp.send('Browser.setWindowBounds',{'windowId':window['windowId'],'bounds':{'windowState':'minimized'}})
        await session.reveal()
        assert (await cdp.send('Browser.getWindowForTarget'))['bounds']['windowState'] in ('normal','maximized')
        async def forbidden_focus():raise AssertionError('Reading must not reactivate browser')
        monkeypatch.setattr(session.page,'bring_to_front',forbidden_focus)
        observation=await session.act('read')
        assert observation['elements'] and 'societe' in observation['url']
        assert any(kind=='action' and text.startswith('已完成') for kind,text in events)
        await cdp.detach()
    finally:await session.close()


async def element(session,**attrs):
    d=await session.observe()
    return next(e for e in d['elements'] if all(e.get(k)==v for k,v in attrs.items()))


async def edit_note(session,text=None):
    d=await session.act('open',url=ERP+'/societe/note.php?id=1')
    edit=next(e for e in d['elements'] if 'action=editnote_public' in (e.get('href') or ''))
    await session.act('click',target=edit['id'])
    field=await element(session,name='note_public')
    old=field['value']
    if text is not None:
        await session.act('fill',target=field['id'],text=text)
        save=await element(session,name='modify')
        await session.act('click',target=save['id'])
    return old


async def save_wiki(session,page_id,text):
    await session.act('open',url=WIKI+f'/doku.php?id={page_id}&do=edit')
    field=await element(session,name='wikitext')
    await session.act('fill',target=field['id'],text=text)
    save=await element(session,name='do[save]')
    await session.act('click',target=save['id'])
    await session.act('open',url=WIKI+f'/doku.php?id={page_id}')
    await expect(session.page.locator('body')).to_contain_text(text.splitlines()[-1])


@pytest.mark.asyncio
async def test_browser_close_reopen_preserves_saved_data_and_tab_limits():
    session=BusinessBrowser(credentials()['BUSINESS_APP_PASSWORD'],headless=True)
    try:
        await session.start()
        before=await edit_note(session)
        await session.act('switch_tab',tab=1)
        await session.act('open',url=WIKI+'/doku.php?id=work:checklist')
        raw=await session.context.request.get(WIKI+'/doku.php?id=work:checklist&do=export_raw')
        assert raw.status==200
        document_before=await raw.text()
        # Actual browser shutdown and new login; no seed or model is involved.
        await session.close()
        assert session.page is None and session.jpeg is None and session.pages==[]
        await session.start()
        assert len(session.pages)==2
        assert await edit_note(session)==before
        await session.act('open',url=WIKI+'/doku.php?id=work:checklist')
        raw=await session.context.request.get(WIKI+'/doku.php?id=work:checklist&do=export_raw')
        assert raw.status==200 and await raw.text()==document_before
        with pytest.raises(ValueError,match='标签页不存在'):
            await session.act('switch_tab',tab=99)
        with pytest.raises(ValueError,match='只能打开'):
            await session.act('open',url='https://example.invalid/')
        for _ in range(session.MAX_TABS-2):await session.act('new_tab',url=WIKI+'/doku.php?id=start')
        assert len(session.pages)==session.MAX_TABS
        with pytest.raises(ValueError,match='最多8个'):
            await session.act('new_tab',url=WIKI+'/doku.php?id=start')
        # Closing the active tab must recover instead of leaving a dead session.
        await session.page.close()
        await session.start()
        assert len(session.pages)==2 and not session.page.is_closed()
    finally:await session.close()


@pytest.mark.asyncio
async def test_workspace_preloads_all_pages_once_and_restores_after_stop():
    session=BusinessBrowser(credentials()['BUSINESS_APP_PASSWORD'],headless=False)
    try:
        await session.prepare_workspace()
        assert len(session.pages)==7
        urls=[p.url for p in session.pages]
        assert ERP+'/commande/list.php' in urls and ERP+'/contact/list.php' in urls
        assert all(WIKI+'/doku.php?id='+i in urls for i in ('start','projects:open_day','work:followup','work:checklist'))
        await session.prepare_workspace()
        assert [p.url for p in session.pages]==urls
        cdp=await session.context.new_cdp_session(session.page)
        try:
            window=(await cdp.send('Browser.getWindowForTarget'))['windowId']
            await cdp.send('Browser.setWindowBounds',{'windowId':window,'bounds':{'windowState':'minimized'}})
            await session.reveal()
            bounds=await cdp.send('Browser.getWindowBounds',{'windowId':window})
            assert bounds['bounds']['windowState']=='normal'
            assert len(session.pages)==7
        finally:await cdp.detach()
        await session.close()
        await session.prepare_workspace()
        assert len(session.pages)==7
    finally:await session.close()


@pytest.mark.asyncio
async def test_read_only_profile_allows_search_but_blocks_order_note_edit():
    session=BusinessBrowser(credentials()['BUSINESS_APP_PASSWORD'],headless=True)
    try:
        await session.start()
        session.scenario='search'
        await session.act('open',url=WIKI+'/doku.php?id=start')
        field=await element(session,name='q')
        await session.act('fill',target=field['id'],text='停车')
        d=await session.observe()
        search=next(e for e in d['elements'] if e.get('tag')=='BUTTON' and e.get('label')=='搜索')
        await session.act('click',target=search['id'])
        await expect(session.page.locator('body')).to_contain_text('开放日停车说明')
        session.scenario='transfer'
        d=await session.act('open',url=ERP+'/commande/note.php?id=7')
        edit=next(e for e in d['elements'] if 'action=editnote_public' in (e.get('href') or ''))
        await session.act('click',target=edit['id'])
        field=await element(session,name='note_public')
        with pytest.raises(ValueError,match='仅可查阅'):
            await session.act('fill',target=field['id'],text='Must not be saved')
        assert (await element(session,name='note_public'))['value']==field['value']
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_six_real_application_flows():
    EVIDENCE.mkdir(parents=True,exist_ok=True)
    session=BusinessBrowser(credentials()['BUSINESS_APP_PASSWORD'],headless=True)
    original=None
    try:
        await session.start()
        assert len(session.pages)==2
        # 1: Edit and reopen a real ERP customer note, including floated icon.
        original=await edit_note(session)
        marker='浏览器集成验收：11月5日确认设备与纸质资料。'
        await edit_note(session,original+'\n'+marker)
        await session.act('open',url=ERP+'/societe/note.php?id=1')
        await expect(session.page.locator('body')).to_contain_text(marker)
        await session.page.screenshot(path=str(EVIDENCE/'customer-note.png'),full_page=True)

        # 2: Filter orders through the actual form, then open a matching detail.
        await session.act('open',url=ERP+'/commande/list.php')
        search=await element(session,name='search_company')
        await session.act('fill',target=search['id'],text='星河文化传媒')
        submit=await element(session,name='button_search_x')
        await session.act('click',target=submit['id'])
        rows=session.page.locator('tr.oddeven')
        assert await rows.count()==3
        await session.page.screenshot(path=str(EVIDENCE/'orders-filter.png'),full_page=True)
        await session.page.locator('a[href*="/commande/card.php?id=7"]').first.click()
        await session.observe()
        body=await session.page.locator('body').inner_text()
        assert 'NM-ORD-007' in body and '7440.00' in body

        # 3: Move actual order information to the other system and back.
        await session.act('switch_tab',tab=1)
        page_id='qa:integration_'+uuid.uuid4().hex[:8]
        text='====== 浏览器集成验收简报 ======\n客户：星河文化传媒\n客户订单号：NM-ORD-007\n金额：7,440\n下一步：确认设备清单。'
        await save_wiki(session,page_id,text)
        await session.act('switch_tab',tab=0)
        await edit_note(session,original+'\n跟进简报已整理（浏览器集成验收）')
        await session.act('open',url=ERP+'/societe/note.php?id=1')
        await expect(session.page.locator('body')).to_contain_text('跟进简报已整理')

        # 4: Edit a real wiki page twice, retaining original items and revision.
        await session.act('switch_tab',tab=1)
        updated=text+'\n设备08:00、资料08:30、签到08:45。\n检查现场网络并准备离线资料。'
        await save_wiki(session,page_id,updated)
        await expect(session.page.locator('body')).to_contain_text('NM-ORD-007')
        await session.page.screenshot(path=str(EVIDENCE/'wiki-edited.png'),full_page=True)

        # 5: Search through DokuWiki and open the original source.
        await session.act('open',url=WIKI+'/doku.php?id=start')
        search=await element(session,name='q')
        await session.act('fill',target=search['id'],text='停车')
        await session.page.locator('#dw__search button[type="submit"]').click()
        await session.observe()
        await session.page.locator('a[href*="id=handbook%3Aparking"],a[href*="id=handbook:parking"]').first.click()
        await session.observe()
        body=await session.page.locator('body').inner_text()
        assert '东门' in body and 'B区' in body
        assert 'Unable to save cache' not in body

        # 6: Create a contact and update its position, preserving association/email.
        await session.act('switch_tab',tab=0)
        await session.act('open',url=ERP+'/contact/card.php?action=create')
        name='自动验收联系人-'+uuid.uuid4().hex[:6]
        for field,value in [('lastname',name),('poste','上午场联络人'),('email','qa.visitor@example.invalid')]:
            e=await element(session,name=field);await session.act('fill',target=e['id'],text=value)
        options=await session.page.locator('select[name="socid"] option').all_text_contents()
        label=next(t for t in options if '星河文化传媒' in t)
        e=await element(session,name='socid');await session.act('select',target=e['id'],text=label)
        e=await element(session,name='add');await session.act('click',target=e['id'])
        await expect(session.page.locator('body')).to_contain_text(name)
        edit=session.page.locator('a[href*="action=edit"]').filter(has_text='修改')
        if not await edit.count():edit=session.page.locator('a[href*="action=edit"]').first
        await edit.click();await session.observe()
        e=await element(session,name='poste');await session.act('fill',target=e['id'],text='下午场联络人')
        e=await element(session,name='save');await session.act('click',target=e['id'])
        await session.page.reload();await session.observe()
        body=await session.page.locator('body').inner_text()
        assert name in body and '下午场联络人' in body
        assert '星河文化传媒' in body and 'qa.visitor@example.invalid' in body
        await session.page.screenshot(path=str(EVIDENCE/'contact-updated.png'),full_page=True)
    finally:
        try:
            if original is not None and session.page and not session.page.is_closed():
                await edit_note(session,original)
        finally:
            await session.close()
