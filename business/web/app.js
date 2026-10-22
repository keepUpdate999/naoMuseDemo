const $=s=>document.querySelector(s),token=$('meta[name="demo-token"]').content;
let state={},current,pending=false,polling=false,ended=false,restoreId=null;
const drafts={};
async function api(path,body){
 const r=await fetch(path,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json','X-Demo-Token':token},body:body===undefined?undefined:JSON.stringify(body)});
 if(!r.ok){const e=await r.json();throw Error(typeof e.detail==='string'?e.detail:'请求失败，请检查输入。')}return r.json();
}
function controls(){const locked=ended||pending||state.running||state.resetting;$('#reset-workspace').disabled=locked;$('#open').disabled=locked;$('#run').disabled=locked||!current||!$('#prompt').value.trim()||(state.remaining!==null&&state.remaining<=0);$('#stop').disabled=ended||pending||state.resetting||!state.running;$('#shutdown').disabled=ended||pending||state.resetting;document.querySelectorAll('nav button').forEach(b=>b.disabled=locked)}
function choose(s){if(current)drafts[current.id]=$('#prompt').value;current=s;$('#title').textContent=s.name;$('#app').textContent=s.app;$('#checks').textContent=s.checks;$('#prompt').value=drafts[s.id]??s.prompt;document.querySelectorAll('nav button').forEach(b=>b.classList.toggle('active',b.dataset.id===s.id));controls()}
async function action(fn){if(pending)return;pending=true;$('#notice').textContent='';controls();try{await fn()}catch(e){$('#notice').textContent=e.message}finally{pending=false;await poll();controls()}}
$('#prompt').oninput=controls;
$('#reset-workspace').onclick=()=>{restoreId=null;$('#workspace-dialog-title').textContent='重置工作区？';$('#workspace-dialog-description').textContent='将先保留当前数据备份，再恢复客户、订单、联系人及知识库初始素材。模型配置、密钥和调用记录保留。完成后自动打开操作页面。';$('#workspace-confirm').textContent='备份并重置';$('#backup-options').hidden=!state.backups?.length;$('#backup-select').replaceChildren();for(const backup of state.backups||[]){const o=document.createElement('option');o.value=backup.id;o.textContent=new Date(backup.created_at*1000).toLocaleString();$('#backup-select').append(o)}$('#workspace-dialog').showModal()};
$('#workspace-cancel').onclick=()=>$('#workspace-dialog').close();
$('#restore-backup').onclick=()=>{restoreId=$('#backup-select').value;$('#workspace-dialog-title').textContent='恢复所选备份？';$('#workspace-dialog-description').textContent='当前工作区会先保存为新备份，再恢复所选历史数据。模型配置、密钥和调用记录不变。';$('#workspace-confirm').textContent='备份并恢复';$('#backup-options').hidden=true};
$('#workspace-confirm').onclick=()=>{const backup=restoreId;$('#workspace-dialog').close();action(async()=>{await api('/api/workspace/reset',{confirm:true,backup_id:backup});$('#notice').textContent='正在恢复数据并重新登录，初始化可能需要几分钟。'})};

$('#open').onclick=()=>action(async()=>{await api('/api/open',{scenario:current.id});$('#notice').textContent='业务操作窗口已打开。请切换到 Chromium 窗口查看；无需再次登录。'});
$('#run').onclick=()=>action(async()=>{await api('/api/run',{scenario:current.id,prompt:$('#prompt').value.trim()})});
$('#stop').onclick=()=>action(async()=>{await api('/api/stop',{});$('#notice').textContent='已停止。已保存的业务记录保留。'});
$('#shutdown').onclick=()=>action(async()=>{await api('/api/shutdown',{});ended=true;$('#connection').textContent='工作区已退出';$('#notice').textContent='应用正在退出，已保存内容保留。';document.querySelectorAll('button').forEach(b=>b.disabled=true)});
$('#export').onclick=()=>{const u=URL.createObjectURL(new Blob([JSON.stringify({exportedAt:new Date().toISOString(),events:state.events,tabs:state.tabs,model:state.model,remaining:state.remaining},null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=u;a.download='guduu-work-records.json';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)};
async function poll(){if(polling||ended)return;polling=true;try{
 const wasResetting=state.resetting;state=await api('/api/status');$('#connection').textContent=state.resetting?'正在恢复工作区':state.running?'GuDuu OS 正在操作':'工作区已就绪';
 if(wasResetting&&!state.resetting&&state.status==='idle'){for(const key of Object.keys(drafts))delete drafts[key];current=null;$('#scenarios').replaceChildren();$('#notice').textContent='工作区已恢复，可以开始新任务。'}
 if(!current){for(const [i,s] of state.scenarios.entries()){const b=document.createElement('button');b.textContent=s.name;b.dataset.id=s.id;b.onclick=()=>choose(s);$('#scenarios').append(b)}choose(state.scenarios[0])}
 $('#budget').textContent=state.unlimited?'不限调用次数':`可用 ${state.remaining} 次调用`;
 $('#model').textContent=`由 ${state.model} 提供支持`;
 $('#status').textContent=({resetting:'正在备份并恢复工作区',idle:'等待任务',running:'正在应用中执行',finished:'任务已完成',error:'执行遇到问题',stopped:'已停止'})[state.status]||state.status;
 $('#tabs').textContent=state.resetting?'正在恢复操作页面':state.browser_open?`已连接 ${state.tabs.length} 个应用页面`:'执行时自动连接应用';
 $('#logs').replaceChildren();for(const e of state.events.filter(e=>['user','assistant','result','error','stopped','workspace'].includes(e.kind)).slice(-35).reverse()){const d=document.createElement('div');d.className='event';const t=document.createElement('small');t.textContent=`${e.time} · ${e.kind}`;const p=document.createElement('p');p.textContent=e.text.replace(/nanomuse/gi,'GuDuu OS');d.append(t,p);$('#logs').append(d)}if(!state.events.length)$('#logs').textContent='等待第一条任务';
 controls();
}catch(e){$('#connection').textContent='连接中断，请刷新';$('#notice').textContent=e.message;$('#run').disabled=true}finally{polling=false}}
await poll();setInterval(poll,1000);
