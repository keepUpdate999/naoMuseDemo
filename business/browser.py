import asyncio
from urllib.parse import urlsplit,unquote
import posixpath

from browser_agent import BrowserSession,DemoBrowser
from nanomuse.tools.base import CallAssessment
from nanomuse.schema import RiskLevel
from business.catalog import ERP,WIKI


class BusinessBrowserTool(DemoBrowser):
    description:str='Operate the visible standalone Dolibarr ERP and DokuWiki browser. Read first for element IDs. Switch real tabs for cross-application tasks. Business records are fictional.'

    def assess(self,args):
        return CallAssessment(risk=RiskLevel.SAFE,summary='操作本地客户系统或知识库')


class BusinessBrowser(BrowserSession):
    MAX_TABS=8
    def __init__(self,password,headless=False):
        super().__init__(ERP)
        self.password=password
        self.headless=headless
        self.scenario=None
        self.workspace_context=None
        self.control_labels={}

    async def prepare_workspace(self):
        await self.start()
        if self.workspace_context is self.context:
            return
        for url in (ERP+'/commande/list.php',ERP+'/contact/list.php',
                    WIKI+'/doku.php?id=projects:open_day',WIKI+'/doku.php?id=work:followup',
                    WIKI+'/doku.php?id=work:checklist'):
            if not any(not p.is_closed() and p.url==url for p in self.pages):
                await self.act('new_tab',url=url)
        self.workspace_context=self.context
        await self.act('switch_tab',tab=0)

    async def track_popup(self,page):
        if len(self.pages)>=self.MAX_TABS:
            await page.close()
            return
        self.pages.append(page)
        page.on('popup',self.track_popup)
        self.page=page

    async def reveal(self):
        await self.prepare_workspace()
        if not self.headless:
            cdp=await self.context.new_cdp_session(self.page)
            try:
                window=await cdp.send('Browser.getWindowForTarget')
                if window.get('bounds',{}).get('windowState')=='minimized':
                    await cdp.send('Browser.setWindowBounds',{'windowId':window['windowId'],'bounds':{'windowState':'normal'}})
            finally:
                await cdp.detach()
        await self.page.bring_to_front()

    def can_write(self,url):
        if self.scenario is None:
            return True
        u=urlsplit(url);path=posixpath.normpath(unquote(u.path)).lower()
        if u.netloc==urlsplit(ERP).netloc:
            if path.endswith('/list.php'):
                return True  # Actual list filters submit forms but do not edit records.
            targets={'customer':('/societe/card.php','/societe/note.php'),
                     'transfer':('/societe/note.php',),
                     'contact':('/contact/card.php','/contact/note.php')}
            return path in targets.get(self.scenario,())
        if u.netloc==urlsplit(WIKI).netloc:
            return self.scenario in ('transfer','document') and path in ('/doku.php','/lib/exe/ajax.php')
        return False

    def allowed(self,url):
        u=urlsplit(url)
        if u.scheme!='http' or u.username or u.password:
            return False
        path=posixpath.normpath(unquote(u.path)).lower()
        if u.netloc==urlsplit(ERP).netloc:
            return not (path+'/').startswith(('/admin/','/install/','/user/','/api/','/public/'))
        if u.netloc==urlsplit(WIKI).netloc:
            return path!='/install.php'
        return False

    async def start(self):
        if self.page and not self.page.is_closed():
            return
        if self.pw:
            await self.close()
        from playwright.async_api import async_playwright
        self.pw=await async_playwright().start()
        self.browser=await self.pw.chromium.launch(headless=self.headless,args=['--window-size=1440,1000'])
        self.context=await self.browser.new_context(viewport={'width':1360,'height':900},locale='zh-CN',service_workers='block')
        async def guard(route):
            if self.allowed(route.request.url) and (route.request.method in ('GET','HEAD','OPTIONS') or self.can_write(route.request.url)):
                await route.continue_()
            else:
                await route.abort()
        await self.context.route('**/*',guard)
        try:
            erp=await self.context.new_page()
            await erp.goto(ERP+'/index.php')
            await erp.locator('input[name="username"]').fill('presenter')
            await erp.locator('input[name="password"]').fill(self.password)
            await erp.locator('input[type="submit"]').click()
            await erp.wait_for_load_state('domcontentloaded')
            if await erp.locator('input[name="password"]').count():
                raise RuntimeError('客户系统登录失败')
            await erp.goto(ERP+'/societe/list.php')
            wiki=await self.context.new_page()
            await wiki.goto(WIKI+'/doku.php?id=start&do=login')
            await wiki.locator('input[name="u"]').fill('presenter')
            await wiki.locator('input[name="p"]').fill(self.password)
            await wiki.locator('form').filter(has=wiki.locator('input[name="p"]')).locator('button[type="submit"]').click()
            await wiki.wait_for_load_state('domcontentloaded')
            if await wiki.locator('input[name="p"]').count():
                raise RuntimeError('知识库登录失败')
            self.pages=[erp,wiki]
            for p in self.pages:
                p.on('popup',self.track_popup)
            self.page=erp
            await erp.bring_to_front()
            self.capture_task=asyncio.create_task(self.capture())
        except BaseException:
            await self.close()
            raise

    async def observe(self):
        await self.page.wait_for_load_state('domcontentloaded')
        await self.page.locator('body').wait_for(state='attached',timeout=10000)
        observation=await self.page.evaluate('''() => {
          const elements=[...document.querySelectorAll('a,button,input,textarea,select,[contenteditable="true"],[role="button"],span[title],i[title]')]
            .filter(e=>e.checkVisibility({checkVisibilityCSS:true,checkOpacity:true}) && e.getBoundingClientRect().width && e.getBoundingClientRect().height && !e.disabled && e.type!=='password' && e.type!=='hidden');
          elements.forEach((e,i)=>e.setAttribute('data-agent-id',i));
          return {url:location.href,text:document.body.innerText.slice(0,18000),
            elements:elements.slice(0,260).map((e,i)=>({id:i,tag:e.tagName,type:e.type,
              label:e.getAttribute('aria-label')||e.labels?.[0]?.innerText||e.innerText?.trim().slice(0,160)||e.placeholder||(['submit','button'].includes(e.type)?e.value:'')||e.getAttribute('title')||e.name,
              name:e.name,value:typeof e.value==='string'?e.value.slice(0,6000):e.value,href:e.href||e.closest('a')?.href,options:e.tagName==='SELECT'?[...e.options].map(o=>o.text):undefined}))};
        }''')
        self.control_labels={e['id']:str(e.get('label') or '')[:60] for e in observation['elements']}
        return observation

    async def act(self,action,target=0,text='',url='',tab=0):
        await self.start()
        labels={'open':'打开页面','new_tab':'打开新标签页','switch_tab':'切换业务标签页',
                'click':'点击页面控件','fill':'填写页面字段','select':'选择下拉选项','scroll':'滚动页面'}
        label=labels.get(action)
        if action in ('click','fill','select') and self.control_labels.get(target):
            label+='「'+self.control_labels[target]+'」'
        emit=getattr(self,'event_log',None)
        if emit and label:emit('action','正在'+label)
        if action in ('open','new_tab'):
            if not self.allowed(url):
                raise ValueError('只能打开本次客户系统和知识库')
            if action=='new_tab':
                if len(self.pages)>=self.MAX_TABS:
                    raise ValueError(f'最多{self.MAX_TABS}个标签页')
                self.page=await self.context.new_page();self.pages.append(self.page)
                self.page.on('popup',self.track_popup)
            await self.page.goto(url)
        elif action=='tabs':
            return [{'tab':i,'url':p.url} for i,p in enumerate(self.pages) if not p.is_closed()]
        elif action=='switch_tab':
            if not 0<=tab<len(self.pages) or self.pages[tab].is_closed():
                raise ValueError('标签页不存在')
            self.page=self.pages[tab]
        elif action in ('click','fill','select'):
            el=self.page.locator(f'[data-agent-id="{int(target)}"]')
            if action in ('fill','select') and not self.can_write(self.page.url):
                query_form=await el.evaluate("e=>e.form?.method.toLowerCase()==='get'")
                if not query_form:
                    raise ValueError('当前场景在此页面仅可查阅。跨系统任务只修改客户卡片公开备注和知识库；订单保持只读。')
            if action=='click':
                await el.click(timeout=5000)
            elif action=='select':
                await el.select_option(label=text,timeout=5000)
            else:
                await el.fill(text,timeout=5000)
        elif action=='scroll':
            await self.page.mouse.wheel(0,-650 if text=='up' else 650)
        elif action!='read':
            raise ValueError('不支持的操作')
        if action in ('switch_tab','new_tab','open'):
            await self.page.bring_to_front()
        self.action=f'{action} · {urlsplit(self.page.url).netloc}'
        await self.page.wait_for_timeout(250)
        observation=await self.observe()
        if emit and label:emit('action','已完成'+label+'；保存结果以重新读取核验为准。' if action=='click' else '已完成'+label)
        return observation
