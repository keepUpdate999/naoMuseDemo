# GuDuu OS 智能工作空间

在工作台下达任务，由 AI 在独立 Chromium 窗口操作实际运行的客户、订单、联系人和知识库应用。支持跨系统整理信息、保存并追加修改，工作记录按最新在上排列。

新增 Windows **悬浮任务助手**：双击 `启动GuDuu悬浮助手.cmd`，六类默认任务直接点击执行，实际浏览器操作与实时工作记录同屏可见。初次源码安装运行 `setup-desktop.ps1`；已有服务需重启到本分支版本。停止任务保留业务页面，退出工作区才关闭服务。便携包构建、托盘和备份恢复见 [悬浮助手说明](FLOATING_ASSISTANT.md)。

## Windows 本地安装

要求：Windows、Python 3.12、uv、Git，以及已经运行的 Docker Desktop（Linux 容器）。

```powershell
git clone https://github.com/keepUpdate999/naoMuseDemo.git
cd naoMuseDemo
powershell -ExecutionPolicy Bypass -File .\setup.ps1
.\.venv\Scripts\python.exe configure_model.py --base-url https://www.pygather.cn/v1 --model deepseek-v4.1-flash
```

配置程序在终端隐藏输入 API Key，不将密钥放进命令参数或 Git。它使用当前 Windows 用户的 DPAPI 加密并收紧配置文件权限；不会发送模型请求。
首次配置创建本地调用账本；已有账本和历史不会重置。显式使用 `--replace` 才能替换已有模型配置。

双击 **启动真实业务演示.cmd**，或运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\start-real.ps1
```

首次启动会拉取固定版本及摘要的镜像、初始化本地应用、生成账户并自动登录，可能需要数分钟。就绪后打开 http://127.0.0.1:18892/ 。
独立操作窗口预先打开7个业务页面，选择任务并点击 **智能执行操作**。需要显示或恢复窗口时点击 **打开操作窗口**。

## 已包含功能与素材

- 客户跟进：查找客户、修改公开备注、保留其他信息并保存。
- 订单查询：筛选客户订单、比较金额、打开明细。
- 跨系统简报：读取客户与订单，编辑知识库简报并回写客户备注。
- 文档编辑：整理执行清单，保存后追加修改，保留修订历史。
- 资料检索：搜索并打开停车、签到等原文，汇总结果。
- 联系人管理：建立公司联系人，保存后修改职位并保留联系方式。

业务应用为 Dolibarr 22.0.4、DokuWiki 2025-05-14a、MariaDB 11.4.5。预置24家客户、18张订单和20份运营文档，均为虚构素材；AI 的页面操作、应用保存、搜索和修订历史实际执行。
所有端口仅监听127.0.0.1，不接管日常Chrome/Edge或Windows桌面。原六页面版本保留，可使用“启动演示.cmd”打开18889。

## 调用与退出

本地累计调用次数不设上限，仍保留调用及用量记录；**模型按供应商实际计费**。任务不会在启动时自动发送。单次输出上限1024 tokens，无自动重试，每任务最多24步。
点击“停止”取消当前任务，已保存内容保留，下次执行自动恢复窗口。
点击“退出工作区”或运行“停止真实业务演示.cmd”关闭本轮服务；Docker持久化卷保留。
工作区持续运行，不再按时长自动退出；点击【退出工作区】时关闭本轮服务，已保存数据保留。

## 重置工作区

页眉【重置工作区】支持确认后备份并恢复初始素材；模型密钥与调用记录保留，完成后自动打开7个已登录页面。
同一弹窗可恢复历史工作区，恢复前也会备份当前数据。旧数据卷保留，恢复使用副本，避免后续编辑覆盖历史备份。
重置期间锁定任务和退出操作，初始化失败尝试回退原工作区。详见 [操作指南](REAL_APPS_GUIDE.md)。

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
# 启动上述业务服务后，另行验证实际应用，不调用模型：
$env:BUSINESS_INTEGRATION='1'
.\.venv\Scripts\python.exe -m pytest tests/test_business_apps.py -q
```

默认测试使用临时数据和隔离端口；真实应用集成默认跳过。
完整重置/恢复可在独立临时Docker项目中验收（不会重置当前业务工作区）：

```powershell
$env:WORKSPACE_RESET_INTEGRATION='1'
.\.venv\Scripts\python.exe -m pytest tests/test_workspace_reset_integration.py -q -s
```

该测试使用随机回环端口、专用数据卷，finally停止并清理它自己创建的临时资源；要求Docker Desktop可用，不调用模型。离线QA使用明确标记的测试替身，正式启动不加载它。
历史本机验收记录见 [REAL_APPS_ACCEPTANCE.md](REAL_APPS_ACCEPTANCE.md)，使用方式见 [REAL_APPS_GUIDE.md](REAL_APPS_GUIDE.md)，架构见 [PROJECT_MAP.md](PROJECT_MAP.md)。
本机历史验证不等于新电脑安装或上游完整CI通过。

## 仓库与本机数据

仓库包含源码、界面、Logo、业务素材、固定依赖、上游运行时、启动脚本及测试。
`.local/`、`.venv/`、模型密钥、应用密码、数据库、日志、截图、调用账本和Docker持久化卷不上传。新电脑重新配置密钥和初始化应用。

## 来源与许可证

底层使用 [nanoMuse](https://github.com/nano-muse/nanoMuse) 的原生 MuseAgent、Sentinel 和模型适配器，固定上游提交 `58b9346f3d8a130c226beef5f906277af350dcb5`，版本1.0.5；vendor运行时代码保留来源和版权声明。
本项目组合源码按 **GPL-3.0-or-later** 分发，见 [LICENSE](LICENSE)、[vendor/NOTICE](vendor/NOTICE)。第三方应用通过各自官方容器分发，遵循各自许可证。
GuDuu OS品牌界面不表示本项目与底层开源项目或模型供应商存在隶属关系。
