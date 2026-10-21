"""Official Anthropic Python SDK transport for the native nanoMuse loop."""
import json
import anthropic
import httpx2
from nanomuse.llm.base import BaseLLM
from nanomuse.schema import Function, LLMResponse, Role, ToolCall


class ProviderHTTPError(RuntimeError):
    """Only exposes status, never a provider response body or credential."""
    def __init__(self, status_code):
        self.status_code = int(status_code)
        super().__init__(f'Anthropic HTTP {self.status_code}')


class AnthropicMessagesLLM(BaseLLM):
    name = 'anthropic'
    vision_available = False

    def __init__(self, settings, transport=None, auth_mode='x-api-key'):
        self.settings = settings
        if auth_mode not in ('bearer', 'x-api-key'):
            raise ValueError('Unsupported authentication mode')
        self.auth_mode = auth_mode
        base = (settings.base_url or '').rstrip('/')
        if not base.startswith('https://'):
            raise ValueError('Anthropic endpoint must use HTTPS')
        self.url = base + ('/messages' if base.endswith('/v1') else '/v1/messages')
        self.transport = transport
        self.blocks = {}

    def payload(self, messages, tools, tool_choice, max_tokens):
        system, wire = [], []
        for msg in messages:
            if msg.role == Role.SYSTEM:
                system.append(msg.content or '')
                continue
            role = 'assistant' if msg.role == Role.ASSISTANT else 'user'
            if msg.role == Role.TOOL:
                content = [{'type': 'tool_result', 'tool_use_id': msg.tool_call_id, 'content': msg.content or ''}]
            else:
                content = [{'type': 'text', 'text': msg.content}] if msg.content else []
                for tc in msg.tool_calls or []:
                    content.append({'type': 'tool_use', 'id': tc.id, 'name': tc.name, 'input': tc.arguments})
                if msg.tool_calls and msg.tool_calls[0].id in self.blocks:
                    content = self.blocks[msg.tool_calls[0].id]
            if not content:
                continue
            if wire and wire[-1]['role'] == role:
                wire[-1]['content'].extend(content)
            else:
                wire.append({'role': role, 'content': content})
        payload = {'model': self.settings.model, 'max_tokens': min(max_tokens or self.settings.max_tokens, self.settings.max_tokens), 'messages': wire, 'stream': False}
        if system:
            payload['system'] = '\n\n'.join(system)
        if tools:
            payload['tools'] = [{'name': t['function']['name'], 'description': t['function'].get('description', ''), 'input_schema': t['function']['parameters']} for t in tools]
            payload['tool_choice'] = {'type': 'any' if tool_choice == 'required' else tool_choice}
        return payload

    async def ask(self, messages, tools=None, tool_choice='auto', on_delta=None, max_tokens=None):
        payload = self.payload(messages, tools, tool_choice, max_tokens)
        headers = {'anthropic-version': '2023-06-01', 'Authorization': 'Bearer ' + self.settings.api_key}
        if self.auth_mode == 'x-api-key':
            headers['x-api-key'] = self.settings.api_key
        # Never follow redirects with credentials; no automatic retries or exception bodies.
        try:
            async with httpx2.AsyncClient(timeout=self.settings.timeout, follow_redirects=False, trust_env=False, transport=self.transport) as http_client:
                async with anthropic.AsyncAnthropic(
                    api_key=self.settings.api_key,
                    base_url=self.url.removesuffix('/v1/messages'),
                    max_retries=0,
                    timeout=self.settings.timeout,
                    default_headers=headers,
                    http_client=http_client,
                    open_telemetry=False,
                ) as client:
                    message = await client.messages.create(**payload)
                    body = message.model_dump(mode='json')
        except anthropic.APIStatusError as exc:
            raise ProviderHTTPError(exc.status_code) from None
        except anthropic.APIConnectionError:
            raise RuntimeError('Anthropic connection failed') from None
        except anthropic.APIResponseValidationError:
            raise RuntimeError('Invalid Anthropic response') from None
        try:
            blocks = body['content']
            if not isinstance(blocks, list) or not blocks:
                raise ValueError('Empty response')
            text = '\n'.join(b['text'] for b in blocks if b.get('type') == 'text')
            calls = [ToolCall(id=b['id'], function=Function(name=b['name'], arguments=json.dumps(b['input'], ensure_ascii=False))) for b in blocks if b.get('type') == 'tool_use']
            if not text and not calls:
                raise ValueError('No usable content')
            if calls:
                self.blocks[calls[0].id] = blocks
            usage = body.get('usage') or {}
            usage = {**usage, 'prompt_tokens': usage.get('input_tokens', 0), 'completion_tokens': usage.get('output_tokens', 0)}
            reason = {'max_tokens': 'length', 'tool_use': 'tool_calls'}.get(body.get('stop_reason'), 'stop')
            result = LLMResponse(content=text or None, tool_calls=calls, finish_reason=reason, usage=usage, model=body.get('model'))
        except (ValueError, KeyError, TypeError, AttributeError):
            raise RuntimeError('Invalid Anthropic response') from None
        if text and on_delta:
            on_delta(text)
        return result
