import {scenes} from './catalog.js';
const $ = s => document.querySelector(s);
const token = $('meta[name="demo-token"]').content;
let current = scenes.find(s => s.id === sessionStorage.getItem('demo-scene')) || scenes[0], state = {}, mode = 'manual', objectURL;
let pending = false, polling = false, connected = false, ended = false;
const drafts = {};

async function api(path, body) {
  const r = await fetch(path, {
    method: body === undefined ? 'GET' : 'POST',
    headers: {'Content-Type': 'application/json', 'X-Demo-Token': token},
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!r.ok) {
    const e = await r.json();
    const error = Error(typeof e.detail === 'string' ? e.detail : '请求失败，请检查输入。');
    error.status = r.status;
    throw error;
  }
  return r.json();
}
function notice(s) { $('#notice').textContent = s; }
function controls() {
  const locked = pending || state.running;
  $('#run').disabled = !connected || !state.configured || locked || !$('#prompt').value.trim();
  $('#stop').disabled = !connected || pending || !state.running;
  $('#reset').disabled = !connected || locked;
  $('#manual').disabled = locked;
  $('#use-followup').disabled = locked;
  $('#shutdown').disabled = !connected || pending;
  document.querySelectorAll('#scenes button').forEach(b => b.disabled = locked);
}
function select(s, initial = false) {
  if (!initial && (pending || state.running)) return notice('任务正在执行，请先停止。');
  if (!initial) drafts[current.id] = $('#prompt').value;
  current = s;
  sessionStorage.setItem('demo-scene', s.id);
  $('#title').textContent = s.name;
  $('#description').textContent = s.description;
  $('#number').textContent = `SCENE ${s.tag} / SIX BROWSER TASKS`;
  $('#prompt').value = Object.hasOwn(drafts, s.id) ? drafts[s.id] : s.prompt;
  $('#followup').textContent = s.followup;
  $('#checks').textContent = s.checks;
  $('#preview').src = `/scene/${s.id}`;
  document.querySelectorAll('#scenes button').forEach(b => b.classList.toggle('active', b.dataset.id === s.id));
  view('manual'); controls();
}
for (const s of scenes) {
  const b = document.createElement('button'); b.dataset.id = s.id;
  b.textContent = `${s.tag}  ${s.name}`; b.onclick = () => select(s); $('#scenes').append(b);
}
function view(v) {
  mode = v; $('#preview').hidden = v !== 'manual'; $('#liveview').hidden = v !== 'live';
  $('#manual').classList.toggle('selected', v === 'manual'); $('#live').classList.toggle('selected', v === 'live');
  $('#activity').textContent = v === 'manual' ? '手动操作不代表 AI 验收' : statusText();
}
function statusText() {
  const names = {idle:'等待任务', running:'执行中', stopping:'正在停止', stopped:'已停止', finished:'本轮结束，请核对结果', error:'执行失败'};
  return `${names[state.status] || '等待任务'} · ${state.action || '尚未执行'}`;
}
async function action(fn) {
  if (pending) return;
  pending = true; controls(); notice('');
  try { await fn(); } catch (e) { notice(e.message); }
  finally { pending = false; await poll(); controls(); }
}
$('#prompt').oninput = controls;
function enlarge(enabled) {
  $('.stage').classList.toggle('expanded', enabled);
  $('#enlarge').setAttribute('aria-pressed', String(enabled));
  $('#enlarge').textContent = enabled ? '退出放大（Esc）' : '放大演示区';
}
$('#enlarge').onclick = () => enlarge(!$('.stage').classList.contains('expanded'));
document.addEventListener('keydown', e => { if (e.key === 'Escape') enlarge(false); });
$('#manual').onclick = () => {
  if (pending || state.running) return notice('执行期间不能手动彩排，请先停止。');
  view('manual'); $('#preview').src = `/scene/${current.id}`;
};
$('#live').onclick = () => { view('live'); poll(); };
$('#run').onclick = () => action(async () => {
  const prompt = $('#prompt').value.trim(); if (!prompt) throw Error('请输入任务内容。');
  await api('/api/run', {prompt, scene: current.id}); view('live');
});
$('#stop').onclick = () => action(async () => {
  await api('/api/stop', {}); notice('已停止执行，保存的数据保留。');
});
$('#reset').onclick = () => {
  $('#reset-dialog').showModal();
};
$('#reset-cancel').onclick = () => $('#reset-dialog').close();
$('#reset-confirm').onclick = () => {
  $('#reset-dialog').close();
  action(async () => {
    await api('/api/reset', {scene: current.id}); $('#preview').src = `/scene/${current.id}`;
    view('manual'); notice('素材已恢复。');
  });
};
$('#use-followup').onclick = () => { $('#prompt').value = current.followup; $('#prompt').focus(); controls(); };
$('#results').onclick = () => { $('.journal details').open = true; };
$('#export').onclick = () => {
  const u = URL.createObjectURL(new Blob([JSON.stringify({exportedAt:new Date().toISOString(),modelConfigured:state.configured,events:state.events || [],data:state.data || {}}, null, 2)], {type:'application/json'}));
  const a = document.createElement('a'); a.href = u; a.download = 'GuDuu OS-demo-record.json'; a.click();
  setTimeout(() => URL.revokeObjectURL(u), 1000); notice('演示记录已导出。');
};
$('#shutdown').onclick = () => action(async () => {
  await api('/api/shutdown', {}); ended = true; connected = false;
  $('#connection').textContent = '演示已结束'; blankFrame('演示已结束。重新启动后刷新工作台。');
  notice('演示已结束，后台服务正在退出。');
});
function blankFrame(text) {
  $('#frame').hidden = true; $('#frame').removeAttribute('src');
  $('#empty').hidden = false; $('#empty').textContent = text;
  if (objectURL) { URL.revokeObjectURL(objectURL); objectURL = undefined; }
}
async function poll() {
  if (polling || ended) return;
  polling = true;
  try {
    state = await api('/api/status'); connected = true;
    const activeScene = scenes.find(s => s.id === state.scene);
    if (state.running && activeScene && current.id !== activeScene.id) select(activeScene, true);
    if (state.running && mode !== 'live') view('live');
    $('#connection').textContent = state.provider === 'qa_stub' ? '本地测试替身 · 无真实模型调用' : state.configured ? '模型已配置 · 待真实验收' : '模型未连接 · 可手动彩排';
    $('#hint').textContent = state.configured ? `模型：${state.model || '已配置'}。发送任务会调用模型；结束后请检查结果。` : '未配置模型，可以先在下方手动彩排。';
    $('#activity').textContent = mode === 'manual' ? '手动操作不代表 AI 验收' : statusText();
    $('#saved').textContent = JSON.stringify(state.data, null, 2); $('#logs').replaceChildren();
    for (const e of state.events.slice(-30).reverse()) {
      const d = document.createElement('div'); d.className = 'event';
      const t = document.createElement('small'); t.textContent = `${e.time} · ${e.kind}`;
      const p = document.createElement('p'); p.textContent = e.text.replace(/nanomuse/gi, 'GuDuu OS'); d.append(t, p); $('#logs').append(d);
    }
    if (!state.events.length) $('#logs').textContent = '等待第一条任务';
    if (mode === 'live' && state.has_frame && Date.now()/1000 - state.frame_time < 5) {
      const r = await fetch('/api/frame', {headers:{'X-Demo-Token':token}});
      if (r.ok) {
        const next = URL.createObjectURL(await r.blob()); const img = new Image(); img.src = next;
        try { await img.decode(); } catch { URL.revokeObjectURL(next); throw Error('执行画面加载失败'); }
        $('#frame').src = next; if (objectURL) URL.revokeObjectURL(objectURL);
        objectURL = next; $('#frame').hidden = false; $('#empty').hidden = true;
      } else blankFrame('执行画面暂不可用，正在等待恢复。');
    } else if (mode === 'live') {
      blankFrame(state.configured ? '暂无实时执行画面，请发送任务。' : '模型尚未连接。可以手动彩排，AI 执行暂不可用。');
    }
  } catch (e) {
    connected = false;
    $('#connection').textContent = e.status === 403 ? '服务已重启，请刷新页面' : '服务已断开';
    blankFrame(e.status === 403 ? '服务已重启，请刷新工作台重新连接。' : '连接已断开，旧画面已隐藏。');
  } finally { polling = false; controls(); }
}
select(current, true); await poll(); setInterval(poll, 1000);
