const $=s=>document.querySelector(s),token=$('meta[name="demo-token"]').content;
let state={},current,pending=false,polling=false,ended=false;
const drafts={};
async function api(path,body){
 const r=await fetch(path,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json','X-Demo-Token':token},body:body===undefined?undefined:JSON.stringify(body)});
 if(!r.ok){const e=await r.json();throw Error(typeof e.detail==='string'?e.detail:'请求失败，请检查输入。')}return r.json();
}
function controls(){const locked=ended||pending||state.running;$('#open').disabled=locked;$('#run').disabled=locked||!current||!$('#prompt').value.trim()||(state.remaining!==null&&state.remaining<=0);$('#stop').disabled=ended||pending||!state.running;$('#shutdown').disabled=ended||pending;document.querySelectorAll('nav button').forEach(b=>b.disabled=locked)}
function choose(s){if(current)drafts[current.id]=$('#prompt').value;current=s;$('#title').textContent=s.name;$('#app').textContent=s.app;$('#checks').textContent=s.checks;$('#prompt').value=drafts[s.id]??s.prompt;document.querySelectorAll('nav button').forEach(b=>b.classList.toggle('active',b.dataset.id===s.id));controls()}
async function action(fn){if(pending)return;pending=true;$('#notice').textContent='';controls();try{await fn()}catch(e){$('#notice').textContent=e.message}finally{pending=false;await poll();controls()}}
$('#prompt').oninput=controls;
$('#open').onclick=()=>action(async()=>{await api('/api/open',{scenario:current.id});$('#notice').textContent='业务操作窗口已打开。请切换到 Chromium 窗口查看；无需再次登录。'});
$('#run').onclick=()=>action(async()=>{await api('/api/run',{scenario:current.id,prompt:$('#prompt').value.trim()})});
$('#stop').onclick=()=>action(async()=>{await api('/api/stop',{});$('#notice').textContent='已停止。已保存的业务记录保留。'});
$('#shutdown').onclick=()=>action(async()=>{await api('/api/shutdown',{});ended=true;$('#connection').textContent='工作区已退出';$('#notice').textContent='应用正在退出，已保存内容保留。';document.querySelectorAll('button').forEach(b=>b.disabled=true)});
$('#export').onclick=()=>{const u=URL.createObjectURL(new Blob([JSON.stringify({exportedAt:new Date().toISOString(),events:state.events,tabs:state.tabs,model:state.model,remaining:state.remaining},null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=u;a.download='guduu-work-records.json';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)};
async function poll(){if(polling||ended)return;polling=true;try{
 state=await api('/api/status');$('#connection').textContent=state.running?'GuDuu OS 正在操作':'工作区已就绪';
 if(!current){for(const [i,s] of state.scenarios.entries()){const b=document.createElement('button');b.textContent=s.name;b.dataset.id=s.id;b.onclick=()=>choose(s);$('#scenarios').append(b)}choose(state.scenarios[0])}
 $('#budget').textContent=state.unlimited?'不限调用次数':`可用 ${state.remaining} 次调用`;
 $('#model').textContent=`由 ${state.model} 提供支持`;
 $('#status').textContent=({idle:'等待任务',running:'正在应用中执行',finished:'任务已完成',error:'执行遇到问题',stopped:'已停止'})[state.status]||state.status;
 $('#tabs').textContent=state.browser_open?`已连接 ${state.tabs.length} 个应用页面`:'执行时自动连接应用';
 $('#logs').replaceChildren();for(const e of state.events.filter(e=>['user','assistant','result','error','stopped'].includes(e.kind)).slice(-35).reverse()){const d=document.createElement('div');d.className='event';const t=document.createElement('small');t.textContent=`${e.time} · ${e.kind}`;const p=document.createElement('p');p.textContent=e.text.replace(/nanomuse/gi,'GuDuu OS');d.append(t,p);$('#logs').append(d)}if(!state.events.length)$('#logs').textContent='等待第一条任务';
 controls();
}catch(e){$('#connection').textContent='连接中断，请刷新';$('#notice').textContent=e.message;$('#run').disabled=true}finally{polling=false}}
await poll();setInterval(poll,1000);
