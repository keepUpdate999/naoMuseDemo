# 模型接入记录

当前按用户示例使用 OpenAI Chat Completions 协议。

- Base URL：https://www.pygather.cn/v1
- 端点：POST /v1/chat/completions
- 模型：deepseek-v4.1-flash（用户指定的网关模型名）
- 鉴权：Authorization: Bearer，由官方 OpenAI SDK发送。
- 运行链路：原生MuseAgent → nanoMuse原生OpenAIChatLLM → 指定网关。
- 密钥沿用当前Windows用户DPAPI加密配置；示例YOUR_API_KEY不作为密钥。
- 每次输出上限1024 tokens；SDK和nanoMuse均关闭自动重试。
- 使用非流式响应和原生工具调用；关闭图片输入及自动协议回退，实时浏览器画面仍正常显示。
- 历史Anthropic适配器及离线回归保留，可供后续切换协议使用。

首次OpenAI真实请求已成功返回量子纠缠段落，网关报告prompt_tokens=37、completion_tokens=293（含reasoning_tokens=197）。此前6次Anthropic请求均401。
真实浏览器场景结果、累计请求和剩余额度见LIVE_ACCEPTANCE_20261022.md；账本跨重启保留。

本轮13项离线协议、请求预算、失败提示测试通过，其中3项验证OpenAI请求路径、Bearer头、模型名、1024输出上限及401/500不重试。离线测试不发送真实模型请求。
浏览器点击“发送任务”会产生真实模型调用，费用以网关账单为准。

## 独立真实应用版后续验收

独立Dolibarr及DokuWiki六类任务均已通过真实模型及独立浏览器复核。
授权上限经两次追加共160次，累计152次，剩余8次；失败及历史调用全部保留。
详情见REAL_APPS_ACCEPTANCE.md；原46次、客户阶段54次均为历史阶段统计。
