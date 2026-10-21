import pytest
from anthropic_adapter import ProviderHTTPError


@pytest.mark.asyncio
async def test_gateway_auth_failure_reaches_safe_ui_state(monkeypatch):
    import server
    class Session:
        action = ''
        async def start(self):
            pass
        async def act(self, *args, **kwargs):
            pass
    class FailedAgent:
        async def run(self, prompt):
            raise ProviderHTTPError(401)
    monkeypatch.setattr(server,'session',Session())
    monkeypatch.setattr(server,'agent',None)
    monkeypatch.setattr(server,'events',[])
    monkeypatch.setattr(server,'build_agent',lambda *args, **kwargs:FailedAgent())
    monkeypatch.setattr(server,'config',lambda:{})
    monkeypatch.setattr(server,'status','idle')
    await server.execute(server.Run(prompt='演示任务',scene='form'))
    assert server.status=='error' and server.agent is None
    assert 'HTTP 401' in server.events[-1]['text']
    assert '密钥' in server.events[-1]['text']
    assert 'api_key' not in server.events[-1]['text']
