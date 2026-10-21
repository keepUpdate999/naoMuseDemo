import json

import httpx2 as httpx
from openai import AsyncOpenAI
import pytest
from nanomuse.config import LLMSettings
from nanomuse.llm.openai_chat import OpenAIChatLLM
from nanomuse.schema import Message


@pytest.mark.asyncio
@pytest.mark.parametrize('status', [200, 401, 500])
async def test_openai_gateway_request_and_no_retry(status):
    calls = []
    def handler(request):
        calls.append(request)
        assert str(request.url) == 'https://gateway.invalid/v1/chat/completions'
        assert request.headers['authorization'] == 'Bearer test-secret'
        body = json.loads(request.content)
        assert body['model'] == 'deepseek-v4.1-flash'
        assert body['max_tokens'] == 1024
        assert body['stream'] is False
        if status != 200:
            return httpx.Response(status, json={'error': {'message': 'test error'}})
        return httpx.Response(200, json={
            'id': 'test', 'object': 'chat.completion', 'created': 0,
            'model': body['model'],
            'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': 'ok'}, 'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 2, 'total_tokens': 12},
        })
    settings = LLMSettings(provider='openai', model='deepseek-v4.1-flash',
        api_key='test-secret', base_url='https://gateway.invalid/v1',
        max_tokens=1024, max_retries=0, stream=False, vision='off', tool_mode='native')
    llm = OpenAIChatLLM(settings)
    await llm.client.close()
    llm.client = AsyncOpenAI(api_key=settings.api_key, base_url=settings.base_url,
        max_retries=0, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    try:
        if status == 200:
            result = await llm.ask([Message.user('test')])
            assert result.content == 'ok'
            assert result.usage['completion_tokens'] == 2
        else:
            from openai import APIStatusError
            with pytest.raises(APIStatusError) as error:
                await llm.ask([Message.user('test')])
            assert error.value.status_code == status
        assert len(calls) == 1
    finally:
        await llm.client.close()
