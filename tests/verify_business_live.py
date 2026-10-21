"""Read-only independent browser verification after authorized real-model tasks.

Does not call a model or change business records. Run one scenario after it ends.
"""
import argparse
import asyncio
import json
from pathlib import Path
import re
import sys

import httpx

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from business.browser import BusinessBrowser
from business.catalog import ERP,WIKI
from business.stack import credentials

EVIDENCE=ROOT/'.local/business/evidence'
BASE='http://127.0.0.1:18892'


def capture(scenario):
    EVIDENCE.mkdir(parents=True,exist_ok=True)
    with httpx.Client(trust_env=False,timeout=10) as c:
        token=re.search('name="demo-token" content="([^"]+)"',c.get(BASE).text)[1]
        headers={'X-Demo-Token':token}
        state=c.get(BASE+'/api/status',headers=headers).json()
        assert not state['running'] and state['status']=='finished', 'Task did not finish normally'
        (EVIDENCE/f'live-{scenario}-events.json').write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
        frame=c.get(BASE+'/api/frame',headers=headers);frame.raise_for_status()
        (EVIDENCE/f'live-{scenario}-result.jpg').write_bytes(frame.content)
        return state


async def verify(scenario):
    state=capture(scenario)
    s=BusinessBrowser(credentials()['BUSINESS_APP_PASSWORD'],headless=True)
    facts={}
    try:
        await s.start()
        if scenario=='orders':
            await s.act('open',url=ERP+'/commande/card.php?id=7')
            text=await s.page.locator('body').inner_text()
            assert 'NM-ORD-007' in text and '7440.00' in text and '星河文化传媒' in text
            facts={'customer_order':'NM-ORD-007','amount':7440,'currency':'CNY'}
        elif scenario=='transfer':
            await s.act('switch_tab',tab=1)
            await s.act('open',url=WIKI+'/doku.php?id=work:followup')
            text=await s.page.locator('body').inner_text()
            assert '星河文化传媒' in text
            amounts={'001':1560,'007':7440,'013':5880}
            match=re.search(r'客户订单号(?:[（(][^）)\n]*[）)])?[：:\s]+NM-ORD-(001|007|013)',text)
            assert match,'Customer order reference must have its own correct label'
            assert '系统订单号' in text,'System order reference must be separately labeled'
            amount=amounts[match[1]]
            assert str(amount) in text.replace(',','').replace(' ','')
            await s.page.screenshot(path=str(EVIDENCE/'verified-followup-document.png'),full_page=True)
            await s.act('switch_tab',tab=0)
            await s.act('open',url=ERP+'/societe/note.php?id=1')
            note=await s.page.locator('body').inner_text()
            assert '跟进简报已整理' in note and '11月5日前确认设备清单和纸质资料数量' in note
            await s.act('open',url=ERP+'/commande/note.php?id=7')
            order_note=await s.page.locator('body').inner_text()
            assert '开放日活动服务订单（虚构业务素材）' in order_note
            assert '跟进简报已整理' not in order_note,'Read-only source order was accidentally changed'
            facts={'customer_order':'NM-ORD-'+match[1],'amount':amount,'document_saved':True,'customer_writeback':True}
        elif scenario=='document':
            await s.act('switch_tab',tab=1)
            raw=await s.context.request.get(WIKI+'/doku.php?id=work:checklist&do=export_raw')
            assert raw.status==200
            text=await raw.text()
            assert all(t in text for t in ('设备','资料','签到','08:00','08:30','08:45','检查现场网络并准备离线资料'))
            await s.act('open',url=WIKI+'/doku.php?id=work:checklist')
            await s.page.screenshot(path=str(EVIDENCE/'verified-execution-checklist.png'),full_page=True)
            await s.act('open',url=WIKI+'/doku.php?id=work:checklist&do=revisions')
            revisions=await s.page.locator('input[name="rev2[]"]').count()
            baseline=EVIDENCE/'document-revisions-before.json'
            before=json.loads(baseline.read_text())['count'] if baseline.exists() else 0
            assert revisions>=before+2,'Two additional saved revisions required'
            facts={'saved_text':text,'revision_entries':revisions}
        elif scenario=='search':
            result=next(e['text'] for e in reversed(state['events']) if e['kind']=='result')
            assert all(t in result for t in ('东门','B','15','水杯','笔记本','报名确认信息'))
            for page_id,expected in [('handbook:parking',['东门','B区']),('handbook:checkin',['15','水杯','笔记本','报名确认信息'])]:
                await s.act('open',url=WIKI+'/doku.php?id='+page_id)
                text=await s.page.locator('body').inner_text()
                assert all(t in text for t in expected)
            facts={'answer_matches_two_source_documents':True}
        elif scenario=='contact':
            await s.act('open',url=ERP+'/contact/list.php')
            d=await s.observe()
            contact=next(e for e in d['elements'] if '演示访客' in e.get('label','') and '/contact/card.php' in e.get('href',''))
            await s.act('click',target=contact['id'])
            text=await s.page.locator('body').inner_text()
            assert all(t in text for t in ('演示访客','下午场联络人','星河文化传媒','visitor@example.invalid'))
            await s.page.screenshot(path=str(EVIDENCE/'verified-contact.png'),full_page=True)
            facts={'name':'演示访客','position':'下午场联络人','email':'visitor@example.invalid','company':'星河文化传媒'}
        record={'scenario':scenario,'passed':True,'remaining':state['remaining'],'facts':facts}
        (EVIDENCE/f'verified-{scenario}.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'scenario':scenario,'passed':True,'remaining':state['remaining']}))
    finally:
        await s.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('scenario',choices=['orders','transfer','document','search','contact'])
    asyncio.run(verify(parser.parse_args().scenario))
