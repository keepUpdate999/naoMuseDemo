import json
import httpx2 as httpx
import pytest
from nanomuse.config import LLMSettings
from nanomuse.schema import Message, ToolCall, Function
from anthropic_adapter import AnthropicMessagesLLM
from secret_store import protect, unprotect
from types import SimpleNamespace


def settings():
    return SimpleNamespace(base_url='https://gateway.invalid', api_key='test-secret', model='test-model', max_tokens=1024, timeout=45)


@pytest.mark.asyncio
async def test_messages_tool_roundtrip():
    seen=[]
    def handler(request):
        assert str(request.url)=='https://gateway.invalid/v1/messages'
        assert request.headers['x-api-key']=='test-secret'
        assert request.headers['anthropic-version']=='2023-06-01'
        body=json.loads(request.content);seen.append(body)
        assert body['system']=='system'
        assert body['max_tokens']==1024
        if len(seen)==1:
            assert body['tools'][0]['input_schema']['type']=='object'
            return httpx.Response(200,json={'content':[{'type':'tool_use','id':'call_1','name':'demo_browser','input':{'action':'read'}}], 'stop_reason':'tool_use','usage':{'input_tokens':10,'output_tokens':5}})
        assert body['messages'][-1]['content'][0]['tool_use_id']=='call_1'
        return httpx.Response(200,json={'content':[{'type':'text','text':'完成'}], 'stop_reason':'end_turn'})
    llm=AnthropicMessagesLLM(settings(),httpx.MockTransport(handler))
    messages=[Message(role='system',content='system'),Message.user('查看页面')]
    tools=[{'type':'function','function':{'name':'demo_browser','parameters':{'type':'object','properties':{}}}}]
    result=await llm.ask(messages,tools,max_tokens=16384)
    assert result.tool_calls[0].arguments=={'action':'read'}
    result=await llm.ask(messages+[result.to_message(),Message.tool('页面内容','call_1')],tools)
    assert result.content=='完成'


@pytest.mark.asyncio
@pytest.mark.parametrize('code',[401,429,500,302])
async def test_errors_do_not_echo_secrets_or_retry(code):
    requests=[]
    def handler(request):
        requests.append(request)
        return httpx.Response(code,text='test-secret',headers={'Location':'https://other.invalid'})
    llm=AnthropicMessagesLLM(settings(),httpx.MockTransport(handler))
    with pytest.raises(RuntimeError) as error:
        await llm.ask([Message.user('hello')])
    assert 'test-secret' not in str(error.value)
    assert error.value.status_code == code
    assert len(requests)==1


def test_dpapi():
    encrypted=protect('fixture-secret')
    assert 'fixture-secret' not in encrypted
    assert unprotect(encrypted)=='fixture-secret'


def test_agent_uses_custom_adapter_without_network(tmp_path):
    from browser_agent import build_agent, BrowserSession
    agent=build_agent({'provider':'anthropic','base_url':'https://gateway.invalid','model':'test-model','api_key':'fixture','max_tokens':1024},BrowserSession('http://127.0.0.1:18889'),lambda *args:None,data_dir=tmp_path)
    assert isinstance(agent.llm,AnthropicMessagesLLM)
    assert agent.llm.settings.max_tokens==1024


@pytest.mark.asyncio
async def test_bearer_gateway_does_not_send_x_api_key():
    def handler(request):
        assert request.headers['Authorization']=='Bearer test-secret'
        assert 'x-api-key' not in request.headers
        return httpx.Response(200,json={'content':[{'type':'text','text':'OK'}],'stop_reason':'end_turn'})
    llm=AnthropicMessagesLLM(settings(),httpx.MockTransport(handler),auth_mode='bearer')
    assert (await llm.ask([Message.user('hello')])).content=='OK'
