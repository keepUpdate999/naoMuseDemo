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
| `desktop` | Native PySide6 floating task assistant, preset follow-ups, local-only network worker and pinned portable packaging. | `desktop/main.py`, `desktop/connection.py`, `desktop/presets.py`, `desktop/build_portable.py` |
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
`/api/workspace/reset` requires explicit confirmation and serializes maintenance against browser/model actions.
`Stack.reset` freezes the current three volumes as a retained backup, switches to fresh initialized volumes, and atomically saves `.local/business/workspace.json` only after readiness; failed initialization rolls back.
Backup manifests stay in `.local/business/backups`; restore clones read-only snapshot volumes with a pinned, temporary network-isolated container so snapshots remain immutable. No model config, ledger or audit reset.
The UI reset dialog also provides backup restore. Maintenance survives page refresh, blocks shutdown, and continues running after completion without an expiry timer.
Unit/controller tests: `test_workspace_reset.py`; opt-in `WORKSPACE_RESET_INTEGRATION=1 pytest tests/test_workspace_reset_integration.py` runs against a unique disposable Compose project, random loopback ports and finally cleanup, preserving the user's workspace.
The real-app controller has no automatic expiry; it waits for explicit shutdown. Its finally cleanup stops only its owned project, preserving volumes. /api/status returns expires_at=null. The user explicitly requested this persistent lifecycle.
An OS lock prevents simultaneous owners; existing running project is never adopted.
Tests: `test_business_unit.py`, opt-in `BUSINESS_INTEGRATION=1 pytest tests/test_business_apps.py`.
`test_business_console.py` launches `tests/serve_business_qa.py` on a temporary loopback port to test
drafts/export/layout and run/refresh/stop/error recovery. Its explicitly offline Agent substitutes only
the model/browser boundary: no credential, model ledger, Docker or preview data access; finally shuts down its process.
Application integration separately verifies actual close/relogin persistence and tab limits.
See REAL_APPS_PLAN.md, REAL_APPS_GUIDE.md and REAL_APPS_ACCEPTANCE.md.

## Constraints and environment requirements

`start-floating.ps1` (or `启动GuDuu悬浮助手.cmd`) opens a native always-on-top task assistant and starts/reuses the local service without launching another workbench. Its Qt UI uses a background network worker, rejects redirects/proxies and connects only to loopback; provider credentials remain in the service. Six scenes have two ready task variants; contact tasks search before creating. Execution hides the editor but keeps newest-first action/result records visible; manual folding, tray restore, screen-bound geometry and explicit workspace exit are supported. Background updates never raise the window.

`business/history.py` persists request IDs, task status and sequenced events in ignored `.local/business/history.sqlite3`; interrupted tasks are marked on startup. `/api/tasks` and per-task events require the same controller token. `Run.request_id` deduplicates requests before any extra model call. Stop cancels the agent and preserves browser pages; shutdown/reset still own browser cleanup. Browser action events describe actual completed UI actions and do not equate clicking Save with verified persistence. Reads no longer activate the browser; explicit reveal restores only minimized windows without resizing normal/maximized windows.

`desktop/theme.py` uses sRGB equivalents of the GuDuu OS platform's CosMac 2A cold-gray/navy tokens; `desktop/log_feed.py` paints timeline cards with bounded fade/height reveal for new live entries, stable reading anchors and a persistent reduce-motion option. Initial history loads do not animate and background changes never activate the window.

`business/presentation.py` / `business/action_overlay.js` provide visible target outlines, moving action pointers, trusted-click ripples and tab/navigation notices around real browser actions. The pointer-transparent shadow overlay makes no requests, writes no business fields and stays outside agent observations. Visual failures do not retry business actions; cancellation during preview prevents the later click. Login/preloading and headless integrations skip visual pacing. `tests/test_presentation.py` uses isolated Chromium fixture pages (including strict CSP) for click/fill/select/navigation, write boundaries, cancellation and visual-failure fallback. `tests/verify_browser_cues.py` is an explicit read-only actual-app smoke with its own finally-closed headed browser and screenshots; no model calls.

Headed `BusinessBrowser` contexts use `no_viewport=True` so every tab follows the native window client area; fixed1360×900 is retained only for headless tests. The real-app responsive test covers small/wide/restored/maximized windows across all seven tabs and captures actual contacts/wiki screenshots without modifying business records.

Desktop dependencies are separate, pinned in `requirements-desktop.lock`; `setup-desktop.ps1` installs them after core setup. `build-floating.ps1` builds an allowlisted ZIP with hash-checked CPython 3.12.10, exact dependencies and upstream licenses/source. New machines still require Docker Desktop, Chromium/images and private local model configuration. No production connection or cloud pairing changes. See `FLOATING_ASSISTANT.md`; `tests/test_floating.py` covers Qt interactions, real offline HTTP, durable history and duplicate/cancel behavior. `tests/verify_floating_desktop.py` is an opt-in read-only actual-service smoke, with no model calls or data reset.

Parent workspace AGENTS.md applies. Python 3.12, pinned requirements.lock, installed Chromium.
Original18889 mode uses start.ps1/stop.ps1 and keeps its legacy one-hour expiry. Main18892 GuDuu OS runs persistently until explicit exit, as requested by the user.
For a new Windows checkout, setup.ps1 installs pinned dependencies and configure_model.py prompts for a key, writes DPAPI-encrypted/ACL-restricted local configuration and initializes a ledger only if absent. Reconfiguration never resets usage. Tests: tests/test_configuration.py.
Local model config, data, logs and venv are ignored. See README.md and ACCEPTANCE.md.

<!-- project-context-map:generated:start -->
## Machine-maintained structure snapshot

> Do not edit this section by hand. The project-context-map skill preserves all content outside these markers.

- Structural snapshot: `2026-10-23T07:59:18+00:00`
- Indexed files: `68`
- Inventory SHA-256: `6593f6fcae5d960d6577bdc80b2d2d6a8b078b67c066ca4104fd3da64746367f`
- Last reviewed drift: `7 added, 0 removed`

| Scope | Files | Directories |
| --- | ---: | ---: |
| `web` | 7 | 1 |
| `tests` | 20 | 1 |
| `server.py` | 1 | 0 |
| `browser_agent.py` | 1 | 0 |
| `anthropic_adapter.py` | 1 | 0 |
| `secret_store.py` | 1 | 0 |
| `data.py` | 1 | 0 |
| `schemas.py` | 1 | 0 |
| `start.ps1` | 1 | 0 |
| `stop.ps1` | 1 | 0 |
| `setup.ps1` | 1 | 0 |
| `business` | 14 | 2 |
| `real_server.py` | 1 | 0 |
| `start-real.ps1` | 1 | 0 |
| `stop-real.ps1` | 1 | 0 |
| `configure_model.py` | 1 | 0 |
| `desktop` | 9 | 1 |
| `requirements-desktop.lock` | 1 | 0 |
| `setup-desktop.ps1` | 1 | 0 |
| `start-floating.ps1` | 1 | 0 |
| `build-floating.ps1` | 1 | 0 |
| `启动GuDuu悬浮助手.cmd` | 1 | 0 |

<!-- project-context-map:generated:end -->
