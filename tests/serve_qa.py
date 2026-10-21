"""Explicit offline QA process, never used by the production launcher.

Run from the project root with its venv. Only synthetic model responses are used.
All application/browser actions still pass through the native nanoMuse loop.
"""
import asyncio
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['DEMO_PORT'] = os.environ.get('QA_PORT', '18890')
os.environ['DEMO_DATA'] = os.environ.get('QA_DATA', str(ROOT / '.local' / 'offline-qa'))
import server
from browser_agent import build_agent as real_build
from nanomuse.llm.base import BaseLLM
from nanomuse.schema import Function, LLMResponse, Role, ToolCall


class OfflineModel(BaseLLM):
    async def ask(self, messages, **kwargs):
        user = next(m.content for m in reversed(messages) if m.role == Role.USER)
        if '异常' in user:
            raise RuntimeError('Synthetic provider failure')
        if '等待取消' in user:
            await asyncio.sleep(120)
        await asyncio.sleep(.6)
        prior = next((m for m in reversed(messages) if m.role == Role.TOOL), None)
        if prior and prior.content and '已保存' in prior.content:
            return LLMResponse(content='本地测试替身：已完成页面操作，请核对保存的结果。')
        observed = await server.session.observe()
        elements = observed['elements']
        name = next((e for e in elements if e['tag'] == 'INPUT' and '姓名' in (e.get('label') or '')), None)
        if name and name.get('value') != '离线验收访客':
            args = {'action':'fill','target':name['id'],'text':'离线验收访客'}
        else:
            save = next((e for e in elements if e['tag']=='BUTTON' and e['label']=='保存草稿'),None)
            args = {'action':'click','target':save['id']} if save else {'action':'read'}
        return LLMResponse(tool_calls=[ToolCall(function=Function(name='demo_browser',arguments=json.dumps(args)))])


server.config = lambda: {'enabled': True, 'provider':'qa_stub', 'model':'offline-qa-model', 'base_url':'https://offline.invalid', 'api_key':'synthetic-only'}
server.build_agent = lambda config, session, log, **kw: real_build({}, session, log, llm_override=OfflineModel(), **kw)
if __name__ == '__main__':
    asyncio.run(server.serve())
