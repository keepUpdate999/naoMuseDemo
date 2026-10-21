"""Real nanoMuse loop with a constrained browser-only tool, never scripted answers."""
import asyncio
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from pydantic import PrivateAttr
from nanomuse.agent import MuseAgent
from nanomuse.config import Settings
from nanomuse.llm import create_llm
from nanomuse.schema import RiskLevel, ToolResult
from nanomuse.sentinel import AuditLog, Sentinel
from nanomuse.tools import Terminate, ToolCollection
from nanomuse.tools.base import BaseTool, CallAssessment
from nanomuse.ui import HeadlessUI

ROOT = Path(__file__).parent


class BrowserSession:
    def __init__(self, base):
        self.base = base
        self.pw = self.browser = self.context = self.page = None
        self.pages = []
        self.jpeg = None
        self.frame_time = 0
        self.action = '尚未执行'
        self.capture_task = None

    def allowed(self, url):
        u, b = urlsplit(url), urlsplit(self.base)
        return (u.scheme, u.netloc) == (b.scheme, b.netloc) and (u.path.startswith('/scene') or u.path.startswith('/assets/') or u.path == '/api/data')

    async def start(self):
        if self.page:
            return
        from playwright.async_api import async_playwright
        self.pw = await async_playwright().start()
        self.browser = await self.pw.chromium.launch(headless=True)
        self.context = await self.browser.new_context(viewport={'width': 1280, 'height': 850}, service_workers='block')
        async def guard(route):
            if self.allowed(route.request.url):
                await route.continue_()
            else:
                await route.abort()
        await self.context.route('**/*', guard)
        self.page = await self.context.new_page()
        self.pages.append(self.page)
        self.page.on('popup', self.track_popup)
        self.capture_task = asyncio.create_task(self.capture())

    async def track_popup(self, page):
        if len(self.pages) >= 6:
            await page.close()
            return
        self.pages.append(page)
        page.on('popup', self.track_popup)
        self.page = page

    async def capture(self):
        import time
        while True:
            try:
                self.jpeg = await self.page.screenshot(type='jpeg', quality=72)
                self.frame_time = time.time()
            except Exception:
                self.jpeg = None
            await asyncio.sleep(.35)

    async def observe(self):
        return await self.page.evaluate('''() => {
          const elements = [...document.querySelectorAll('a,button,input,textarea,select')].filter(e=>e.getBoundingClientRect().width && e.getBoundingClientRect().height);
          elements.forEach((e,i)=>e.setAttribute('data-agent-id',i));
          return {url:location.href,text:document.body.innerText.slice(0,12000),elements:elements.map((e,i)=>({id:i,tag:e.tagName,label:e.getAttribute('aria-label')||(e.labels?.[0]?.innerText)||e.innerText||e.placeholder||e.name,value:e.value,href:e.href,options:e.tagName==='SELECT'?[...e.options].map(o=>o.text):undefined}))};
        }''')

    async def act(self, action, target=0, text='', url='', tab=0):
        await self.start()
        if action in ('open', 'new_tab'):
            if not self.allowed(url) or not urlsplit(url).path.startswith('/scene'):
                raise ValueError('仅允许演示场景页面')
            if action == 'new_tab':
                if len(self.pages) >= 6:
                    raise ValueError('最多六个标签页')
                self.page = await self.context.new_page()
                self.pages.append(self.page)
                self.page.on('popup', self.track_popup)
            await self.page.goto(url)
        elif action == 'tabs':
            return [{'tab': i, 'url': p.url} for i, p in enumerate(self.pages)]
        elif action == 'switch_tab':
            if not 0 <= tab < len(self.pages):
                raise ValueError('标签页不存在')
            self.page = self.pages[tab]
        elif action in ('click', 'fill', 'select'):
            el = self.page.locator(f'[data-agent-id="{int(target)}"]')
            if action == 'click':
                await el.click(timeout=5000)
            elif action == 'fill':
                await el.fill(text, timeout=5000)
            else:
                await el.select_option(label=text, timeout=5000)
        elif action == 'scroll':
            await self.page.mouse.wheel(0, 500 if text != 'up' else -500)
        elif action != 'read':
            raise ValueError('不支持的操作')
        self.action = f'{action} · {self.page.url.split("/")[-1]}'
        await self.page.wait_for_timeout(180)
        return await self.observe()

    async def close(self):
        if self.capture_task:
            self.capture_task.cancel()
            await asyncio.gather(self.capture_task, return_exceptions=True)
        if self.browser:
            await self.browser.close()
        if self.pw:
            await self.pw.stop()
        self.page = self.context = self.browser = self.pw = None
        self.pages = []
        self.jpeg = None
        self.frame_time = 0


class DemoBrowser(BaseTool):
    name: str = 'demo_browser'
    description: str = 'Operate the visible demo browser. Read first to get element IDs. Use new_tab and switch_tab for cross-tab tasks. No direct state writes.'
    parameters: dict[str, Any] = {'type': 'object', 'properties': {
        'action': {'type': 'string', 'enum': ['open', 'read', 'click', 'fill', 'select', 'scroll', 'new_tab', 'tabs', 'switch_tab']},
        'target': {'type': 'integer'}, 'text': {'type': 'string'}, 'url': {'type': 'string'}, 'tab': {'type': 'integer'}}, 'required': ['action']}
    _session: Any = PrivateAttr()

    def assess(self, args):
        return CallAssessment(risk=RiskLevel.SAFE, summary='操作本地虚构演示页面')

    async def execute(self, action, target=0, text='', url='', tab=0, **kwargs):
        import json
        try:
            return ToolResult(output=json.dumps(await self._session.act(action, target, text, url, tab), ensure_ascii=False))
        except Exception as exc:
            return ToolResult.fail(str(exc))


def build_agent(config, session, log, llm_override=None, data_dir=None, tool_override=None):
    settings = Settings(data_dir=data_dir or ROOT / '.local' / 'runtime')
    settings.ensure_dirs()
    settings.agent.max_steps = 30
    settings.agent.language = 'zh'
    settings.llm.provider = config.get('provider', 'openai')
    settings.llm.model = config.get('model', '')
    settings.llm.base_url = config.get('base_url')
    settings.llm.api_key = config.get('api_key', '')
    settings.llm.max_retries = 0
    settings.llm.timeout = 45
    settings.llm.max_tokens = int(config.get('max_tokens', 1024))
    settings.llm.stream = False
    settings.llm.tool_mode = 'native'
    settings.llm.vision = 'off'
    class DemoUI(HeadlessUI):
        def _log(self, kind, payload):
            if kind in ('tool_call', 'assistant', 'warn', 'sentinel'):
                log(kind, str(payload or ''))
    ui = DemoUI(approve=False)
    audit = AuditLog(settings.audit_file)
    tool = tool_override if tool_override is not None else DemoBrowser()
    tool._session = session
    if llm_override is not None:
        llm = llm_override
    elif settings.llm.provider == 'anthropic':
        from anthropic_adapter import AnthropicMessagesLLM
        llm = AnthropicMessagesLLM(settings.llm, auth_mode=config.get('auth_mode', 'x-api-key'))
    else:
        llm = create_llm(settings.llm)
    agent = MuseAgent(settings, llm, ToolCollection(tool, Terminate()), Sentinel(settings.sentinel, audit, ui), ui, audit)
    agent.prompt_addendum = lambda: f'你在本地演示环境中。只有 demo_browser 工具可操作页面。入口 {session.base}/scene/table。场景路径 table, transfer, notes, orders, search, form。所有素材虚构。跨页搬运使用真实 new_tab/switch_tab。修改后点击保存并读取确认。不得宣称未执行的操作成功。'
    return agent
