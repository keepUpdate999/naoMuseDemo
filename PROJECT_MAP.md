# Project Map

This file is the first navigation entry point for people and coding agents.
Verify task-relevant source files before making decisions.

## System overview

Two local presentation modes: the original six fixture pages on18889, and real third-party applications on18892–18894.
GuDuu OS brands the real-app controller and automatically opens seven logged-in Dolibarr/DokuWiki pages on startup.
The original mode has six deterministic fixture pages, a real nanoMuse
agent loop with a constrained multi-tab Playwright tool, and a browser workbench.
Credentials are user-scoped DPAPI encrypted in ignored local configuration; live calls require authorization.
Separate from nanoMuse-showcase's phone simulator.

## Directory responsibilities

| Path | Responsibility | Main entry points |
| --- | --- | --- |
| `business` / `real_server.py` | Independent real-application controller, headed browser, encrypted app credentials, materials, shared model ledger, owned Compose lifecycle. | `business/stack.py`, `business/browser.py`, `business/catalog.py`, `business/web` |
| `web` | Workbench and six local pages. | `index.html`, `scene.js`, `catalog.js` |
| `server.py` | Loopback HTTP API, task lifecycle, control authentication, preview expiry. | `serve`, `execute`, `stop` |
| `browser_agent.py` | Real browser sessions, tab switching, screenshots, native MuseAgent adapter. | `BrowserSession`, `DemoBrowser`, `build_agent` |
| `anthropic_adapter.py` / `secret_store.py` | Official pinned Anthropic SDK transport, Messages tool conversion and Windows DPAPI secret storage. | `AnthropicMessagesLLM`, `protect`, `unprotect` |
| `data.py` / `schemas.py` | Synthetic fixtures, SQLite persistence, validated writes. | `Store`, `validate_data` |
| `vendor` | Unmodified runtime from fixed upstream SHA; license and notice. | `nanomuse/agent/core.py` |
| `tests` | Actual browser flows, protocol contracts, workbench regressions and an explicit offline-only QA process. | `test_demo.py`, `test_anthropic.py`, `test_workbench.py`, `serve_qa.py` |

## Feature map

| Capability | UI or caller | Service or runtime | Data/contracts | Tests |
| --- | --- | --- | --- | --- |
| Six scenes | `web/scene.js` | `server.py` | `data.py`, SQLite | `tests/test_demo.py` |
| Agent and live view | `web/app.js` | `browser_agent.py` | `/api/run`, `/api/frame` | MockLLM with real tools |

## Core flows

Launcher starts the loopback API. Workbench submits text only when a model is configured.
OpenAI-compatible calls use the native OpenAIChatLLM with non-streaming native tools, no retries or vision fallback.
MuseAgent selects browser actions through Sentinel; those actions change real page controls,
which save to the fixture database. Screenshots show that same browser, not a recreated animation.

## Change and test routing

Run pytest for service/tool/page changes. Browser tests use temporary data and finally cleanup.
Real-model acceptance is separately gated until the user provides the model and authorizes calls.
Workbench regression covers screenshots decoding under CSP, zoom/Escape, reset confirm/cancel,
empty drafts, run/stop/error recovery, in-flight refresh, export, reconnection and three viewport sizes.
`tests/serve_qa.py` overrides only its own process with an explicitly labelled local model stub;
the normal launcher never loads it. QA data and processes are separate from user preview state.
`tests/serve_live_acceptance.py --execute` is the explicit authorized live runner. It reads the
protected model configuration in place, isolates fixture data on port18891 and persists a hard
60-request ledger across restarts. `test_live_budget.py` checks refusal before an extra request.
Actual live status and remaining budget are recorded in LIVE_ACCEPTANCE_20261022.md.

## Real application mode

`启动真实业务演示.cmd` starts `real_server.py`: dedicated Compose project nanomuse-business,
loopback Dolibarr18893 + DokuWiki18894, and a controller18892 with no iframe. `business/compose.yml`
pins version+digest, restart=no, private persistent volumes. `business/seed_erp.php` seeds native
ERP records; `business/materials.py` supplies20 wiki pages. Initialization is separate from agent actions.
`business/browser.py` logs in through real UI and exposes only browser actions to the native agent.
Writes are scoped to the selected scenario; cross-system tasks can edit customer notes/wiki, while orders stay read-only.
`real_server.task_addendum` pins the current user task in the system context even after native history trimming.
`business/budget.py` continues the existing ledger; limit=null means explicitly user-authorized unlimited calls, while historical attempts/usage remain and each output stays capped at1024 tokens.
`tests/verify_business_live.py` independently reopens application records after real-model runs without making model calls or writing business data.
`BusinessBrowser.prepare_workspace` preloads seven application tabs once per browser context; a stopped browser is automatically restored on the next task. The GuDuu OS controller supports direct execution and an explicit window-open entry. BusinessBrowser.reveal restores minimized headed windows via CDP then activates the selected page. Both web modes use the supplied GuDuu OS PNG and newest-first log display; raw audit/export order is preserved. Stack.brand_assets persists native ERP/wiki logos and wiki title on every start. seed_erp.php applies ERP title/logo constants and replaces only the old product name in existing customer public notes before its seed guard, preserving business edits.
Controller expires60 minutes after readiness when no task runs; finally stops only its owned project, preserving volumes.
An OS lock prevents simultaneous owners; existing running project is never adopted.
Tests: `test_business_unit.py`, opt-in `BUSINESS_INTEGRATION=1 pytest tests/test_business_apps.py`.
`test_business_console.py` launches `tests/serve_business_qa.py` on a temporary loopback port to test
drafts/export/layout and run/refresh/stop/error recovery. Its explicitly offline Agent substitutes only
the model/browser boundary: no credential, model ledger, Docker or preview data access; finally shuts down its process.
Application integration separately verifies actual close/relogin persistence and tab limits.
See REAL_APPS_PLAN.md, REAL_APPS_GUIDE.md and REAL_APPS_ACCEPTANCE.md.

## Constraints and environment requirements

Parent workspace AGENTS.md applies. Python 3.12, pinned requirements.lock, installed Chromium.
Startup is start.ps1; stop.ps1 only shuts down the identified demo service. One-hour idle expiry.
For a new Windows checkout, setup.ps1 installs pinned dependencies and configure_model.py prompts for a key, writes DPAPI-encrypted/ACL-restricted local configuration and initializes a ledger only if absent. Reconfiguration never resets usage. Tests: tests/test_configuration.py.
Local model config, data, logs and venv are ignored. See README.md and ACCEPTANCE.md.

<!-- project-context-map:generated:start -->
## Machine-maintained structure snapshot

> Do not edit this section by hand. The project-context-map skill preserves all content outside these markers.

- Structural snapshot: `2026-10-21T23:21:28+00:00`
- Indexed files: `45`
- Inventory SHA-256: `c6276e262b90ce0f762ed354499a2386da6121a31c56c42b1b2690417f71e0e7`
- Last reviewed drift: `2 added, 0 removed`

| Scope | Files | Directories |
| --- | ---: | ---: |
| `web` | 7 | 1 |
| `tests` | 14 | 1 |
| `server.py` | 1 | 0 |
| `browser_agent.py` | 1 | 0 |
| `anthropic_adapter.py` | 1 | 0 |
| `secret_store.py` | 1 | 0 |
| `data.py` | 1 | 0 |
| `schemas.py` | 1 | 0 |
| `start.ps1` | 1 | 0 |
| `stop.ps1` | 1 | 0 |
| `setup.ps1` | 1 | 0 |
| `business` | 11 | 2 |
| `real_server.py` | 1 | 0 |
| `start-real.ps1` | 1 | 0 |
| `stop-real.ps1` | 1 | 0 |
| `configure_model.py` | 1 | 0 |

<!-- project-context-map:generated:end -->
