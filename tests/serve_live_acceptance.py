"""Explicit live acceptance process. Requires --execute; never loaded by normal startup.

Current task authorization: 60 requests total, <=1024 output tokens per request,
no transport retries. Separate local data; protected model config is read in place.
"""
import asyncio
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['DEMO_PORT'] = '18891'
os.environ['DEMO_DATA'] = str(ROOT / '.local' / 'live-acceptance-20261022')
import server
from nanomuse.llm.base import BaseLLM
from secret_store import unprotect

BUDGET = Path(os.environ['DEMO_DATA']) / 'budget.json'
LIMIT = 60
original_build = server.build_agent


def protected_config():
    data = json.loads((ROOT / '.local' / 'model.json').read_text(encoding='utf-8-sig'))
    if data.get('api_key_dpapi'):
        data['api_key'] = unprotect(data['api_key_dpapi'])
    data['max_tokens'] = min(int(data.get('max_tokens', 1024)), 1024)
    return data


def budget_read():
    if BUDGET.exists():
        return json.loads(BUDGET.read_text(encoding='utf-8'))
    return {'limit': LIMIT, 'attempts': 0, 'responses': 0, 'input_tokens': 0, 'output_tokens': 0, 'requests': []}


def budget_save(data):
    temp = BUDGET.with_suffix('.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(BUDGET)


class BudgetLLM(BaseLLM):
    vision_available = False
    def __init__(self, inner):
        self.inner = inner
        self.settings = inner.settings

    async def ask(self, *args, **kwargs):
        data = budget_read()
        if data['attempts'] >= LIMIT:
            raise RuntimeError('Authorized request budget exhausted')
        data['attempts'] += 1
        record = {'number':data['attempts'], 'time':time.time(), 'status':'sent'}
        data['requests'].append(record)
        budget_save(data)
        server.log('budget', f'真实模型请求 {data["attempts"]}/{LIMIT}，单次输出上限1024 tokens。')
        try:
            response = await self.inner.ask(*args, **kwargs)
        except Exception as exc:
            record['status'] = 'failed'
            record['error_type'] = type(exc).__name__
            # Adapter errors contain only a code/type, never provider bodies or keys.
            code = getattr(exc, 'status_code', None)
            safe = f'Provider HTTP {code}' if isinstance(code, int) else ''
            if safe:
                record['error'] = safe
                server.log('provider', safe)
            budget_save(data)
            raise
        record['status'] = 'responded'
        record['seconds'] = round(time.time() - record['time'], 2)
        record['usage'] = response.usage
        data['responses'] += 1
        data['input_tokens'] += int(response.usage.get('input_tokens', response.usage.get('prompt_tokens', 0)))
        data['output_tokens'] += int(response.usage.get('output_tokens', response.usage.get('completion_tokens', 0)))
        budget_save(data)
        return response


def build(config, session, log, **kwargs):
    agent = original_build(config, session, log, **kwargs)
    agent.llm = BudgetLLM(agent.llm)
    agent.settings.agent.max_steps = 12
    return agent


server.config = protected_config
server.build_agent = build

if __name__ == '__main__':
    if '--execute' not in sys.argv:
        raise SystemExit('Explicit --execute required for this authorized live run')
    asyncio.run(server.serve())
