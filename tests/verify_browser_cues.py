"""Read-only real ERP/wiki presentation smoke; owns and closes its browser only."""
import asyncio
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from business.browser import BusinessBrowser
from business.stack import credentials
from business.presentation import ActionPresenter
from desktop.connection import LocalAPI

OUTPUT=Path('.local/desktop/browser-cue-evidence')


class EvidencePresenter(ActionPresenter):
    count=0
    async def show(self,page,label,kind='transition',box=None):
        await super().show(page,label,kind,box)
        if self.enabled:
            self.count+=1
            await page.wait_for_timeout(100)
            await page.screenshot(path=str(OUTPUT/f'{self.count:02d}-{kind}.png'))


async def main():
    OUTPUT.mkdir(parents=True,exist_ok=True)
    api=LocalAPI();api.attach();before=api.request('/api/status')
    if before['running'] or before['resetting']:raise RuntimeError('Workspace busy; smoke skipped.')
    session=BusinessBrowser(credentials()['BUSINESS_APP_PASSWORD'])
    session.presenter=EvidencePresenter(enabled=False)
    try:
        await session.prepare_workspace();session.scenario='orders'
        await session.act('switch_tab',tab=2)
        observation=await session.observe()
        field=next(e for e in observation['elements'] if e.get('name')=='search_company')
        await session.act('fill',target=field['id'],text='星河文化传媒')
        observation=await session.observe()
        button=next(e for e in observation['elements'] if e.get('name')=='button_search_x')
        await session.act('click',target=button['id'])
        observation=await session.observe()
        assert '星河文化传媒' in observation['text']
        assert not any('GuDuu OS  ·' in str(e.get('label','')) for e in observation['elements'])
        session.scenario='search';await session.act('switch_tab',tab=1)
        assert '18894' in session.page.url
        after=api.request('/api/status');assert before['calls']==after['calls']
        report={'mode':'actual apps read-only, separate owned Chromium, no model requests',
                'tabs':len(session.pages),'filter':'passed','tab_transition':'passed',
                'model_calls_delta':after['calls']-before['calls'],'screenshots':session.presenter.count}
        (OUTPUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False))
    finally:await session.close()


if __name__=='__main__':asyncio.run(main())
