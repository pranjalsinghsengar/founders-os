'use strict';
const $ = s => document.querySelector(s);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const human = s => String(s || '').replaceAll('_',' ').replaceAll('.',' › ');
const short = s => String(s || '').slice(0,8);
const count = xs => xs.length;
const csrf = $('meta[name="csrf-token"]').content;
let data = null, busy = false, view = location.hash.slice(1) || 'overview', search = '', projectFilter = '', statusFilter = '';
const routes = {
 controls:['⚙','Controls','Orchestration controls','Create assignments, manage permissions and run bounded workflows.'],
 overview:['◫','Overview','Control room','A clear view of your employees, projects, and decisions.'],
 projects:['▦','Projects','Your projects','Track scope, permissions, budget, and every handoff.'],
 tasks:['≡','Tasks','Work in progress','Inspect assignments, review evidence, and understand blockers.'],
 employees:['♧','Employees','Your AI team','Logical employee roles and their actual task assignments.'],
 approvals:['◇','Approvals','Founder decisions','Version-bound Gmail requests and investment proposals.'],
 activity:['↗','Activity','Company activity','A durable record of tool calls, reviews, and workflow changes.'],
 connections:['⊞','Connections','Connected capabilities','Local configuration, observed usage, and missing integrations.'],
 milestones:['◎','Milestones','The path to a live company','Implementation checkpoints from your operating blueprint.']
};
const matches = (...values) => !search || values.some(v => String(v ?? '').toLowerCase().includes(search.toLowerCase()));
const project = id => data.projects.find(p => p.id === id);
const taskName = t => t.payload?.objective || (t.audit_task ? 'Independent QA report' : human(t.tool));
const badge = status => {
 const color = ['completed','approved','observed'].includes(status)?'green':['failed','rejected','unknown'].includes(status)?'red':['changes_requested','blocked','awaiting_review','awaiting_approval','exhausted','prepared','sent','missing'].includes(status)?'amber':['running','configured'].includes(status)?'blue':'';
 return `<span class="pill ${color}">${esc(human(status))}</span>`;
};
const projectStatus = p => p.paused?'paused':p.remaining<=0?'exhausted':!p.approved?'awaiting_approval':data.tasks.some(t=>t.project===p.id&&t.status==='running')?'running':data.tasks.some(t=>t.project===p.id&&t.status==='changes_requested')?'changes_requested':p.kind==='research_mandate'?'research':'approved';
const roleName = role => human(role);
const empty = text => `<div class="empty">${esc(text)}</div>`;
const panel = (title,subtitle,body,extra='') => `<section class="panel"><div class="panel-header"><div><h2>${esc(title)}</h2>${subtitle?`<p>${esc(subtitle)}</p>`:''}</div>${extra}</div>${body}</section>`;
const navLink = (to,label) => `<button class="text-button" data-nav="${to}">${label} →</button>`;
function projectTable(projects){
 if(!projects.length) return empty('No matching projects. Create a proposal or research mandate with the CLI.');
 return `<div class="table-wrap"><table><thead><tr><th>Project</th><th>Status</th><th>Budget usage</th><th>Tasks</th></tr></thead><tbody>${projects.map(p=>{
 const ts=data.tasks.filter(t=>t.project===p.id&&!t.audit_task),done=ts.filter(t=>t.status==='completed').length;
 const percent=p.budget?Math.min(100,p.spent/p.budget*100):100;
 return `<tr><td><button class="table-title" data-project="${esc(p.id)}">${esc(p.title)}</button><span class="subtext">${p.kind==='research_mandate'?'Research mandate':'Product candidate'} · ${short(p.id)}</span></td><td>${badge(projectStatus(p))}</td><td>${p.spent} / ${p.budget}<div class="progress ${p.remaining<=0?'exhausted':''}"><span data-width="${percent}"></span></div><span class="subtext">${p.remaining} internal units left</span></td><td>${done}<span class="muted"> / ${ts.length}</span></td></tr>`;
 }).join('')}</tbody></table></div>`;
}
function taskTable(tasks){
 if(!tasks.length)return empty('No tasks match these filters.');
 return `<div class="table-wrap"><table><thead><tr><th>Assignment</th><th>Employee</th><th>Status</th><th>Attempts</th></tr></thead><tbody>${tasks.map(t=>`<tr><td><button class="table-title" data-task="${esc(t.id)}">${esc(taskName(t))}</button><span class="subtext">${esc(project(t.project)?.title || short(t.project))}${t.audit_task?' · Operator audit report':''}</span></td><td>${esc(roleName(t.owner))}</td><td>${badge(t.status)}</td><td>${t.attempts} / ${t.max_attempts}</td></tr>`).join('')}</tbody></table></div>`;
}
function attention(){
 const entries=[];
 for(const p of data.projects.filter(p=>p.remaining<=0))entries.push({title:'Research or product allowance exhausted',body:`${p.title} has no internal allowance remaining. Additional work requires an authorized budget change.`,project:p.id});
 for(const t of data.tasks.filter(t=>!t.audit_task&&['changes_requested','blocked','failed'].includes(t.status)).slice(0,5))entries.push({title:human(t.status),body:t.note || 'Open the task to inspect its assignment and recorded state.',task:t.id});
 return entries;
}
function attentionList(entries){return entries.length?entries.map(e=>`<div class="attention-item"><div class="attention-icon">!</div><div class="attention-body"><h3>${esc(e.title)}</h3><p>${esc(e.body).slice(0,260)}${e.body.length>260?'…':''}</p><button class="text-button" ${e.task?`data-task="${esc(e.task)}"`:`data-project="${esc(e.project)}"`}>Inspect ${e.task?'task':'project'} →</button></div></div>`).join(''):empty('No blocked work or exhausted allowances.');}
function timeline(events){return events.length?`<div class="timeline">${events.map(e=>`<div class="event"><span class="event-dot ${e.kind.includes('failed')?'error':''}"></span><div><div class="event-title">${esc(human(e.kind))}</div><div class="event-time">${esc(e.at)} UTC · ${esc(short(e.details.task||e.details.project||e.details.request))}</div>${e.details.reason?`<div class="subtext">${esc(e.details.reason)}</div>`:''}</div></div>`).join('')}</div>`:empty('Events will appear when the company performs work.');}
function overview(){
 const assignments=data.tasks.filter(t=>!t.audit_task),running=assignments.filter(t=>t.status==='running').length;
 const completed=assignments.filter(t=>t.status==='completed').length;
 const spent=data.projects.reduce((s,p)=>s+p.spent,0),budget=data.projects.reduce((s,p)=>s+p.budget,0);
 const needs=attention();
 const metrics=[['Tracked projects',data.projects.length,'Research mandates and product candidates','▦'],['Running tasks',running,'Persisted running state; not a worker heartbeat','↗'],['Needs attention',needs.length,'Rework, failures, and exhausted allowances','!'],['Internal allowance',`${spent} / ${budget}`,'Configured units · not provider currency bills','◈']];
 return `<div class="metrics">${metrics.map((m,i)=>`<section class="metric ${i===2?'accent':''}"><div class="metric-label">${m[0]}</div><span class="metric-icon">${m[3]}</span><div class="metric-value">${m[1]}</div><div class="metric-note">${m[2]}</div></section>`).join('')}</div><div class="grid-main"><div class="stack">${panel('Project portfolio',`${completed} independently accepted assignments across your workspace`,projectTable(data.projects.filter(p=>matches(p.title,p.id)).slice(0,6)),navLink('projects','All projects'))}${panel('Recent assignments','Real workflow state, including quality rework',taskTable(assignments.filter(t=>matches(taskName(t),t.owner,t.note)).slice(0,5)),navLink('tasks','All tasks'))}</div><div class="stack">${panel('Needs your attention','Make the next decision with context',attentionList(needs.slice(0,4)))}${panel('Latest activity','Saved workflow events',timeline(data.events.slice(0,5)),navLink('activity','View log'))}${panel('Operating mode','Execution is currently operator-driven','<div class="attention-item"><div class="attention-body"><h3>Manual CLI runs & bounded ticks</h3><p>The dashboard watches state. It does not start employees, send email, or deploy products.</p></div></div>')}</div></div>`;
}
function tasks(){
 const selected=data.tasks.filter(t=>(!projectFilter||t.project===projectFilter)&&(!statusFilter||t.status===statusFilter)&&matches(taskName(t),t.id,t.owner,t.note));
 return `<div class="toolbar"><select id="project-filter" aria-label="Filter tasks by project"><option value="">All projects</option>${data.projects.map(p=>`<option value="${esc(p.id)}" ${projectFilter===p.id?'selected':''}>${esc(p.title)} · ${short(p.id)}</option>`).join('')}</select><select id="status-filter" aria-label="Filter tasks by status"><option value="">All states</option>${[...new Set(data.tasks.map(t=>t.status))].map(s=>`<option ${statusFilter===s?'selected':''} value="${esc(s)}">${esc(human(s))}</option>`).join('')}</select><span class="subtext">${selected.length} tasks · QA report tasks are retained for operator audit</span></div>${panel('Task ledger','Select an assignment for criteria, dependencies, feedback, and artifacts',taskTable(selected))}`;
}
function employees(){return `<div class="employee-grid">${data.employees.filter(e=>matches(e.role)).map(e=>{
 const tasks=data.tasks.filter(t=>t.owner===e.role),working=tasks.filter(t=>t.status==='running').length;
 return `<section class="employee-card"><div class="employee-top"><span class="role-avatar">${esc(e.role.slice(0,1).toUpperCase())}</span><div><h3>${esc(roleName(e.role))}</h3><p>${e.configured?'Configured role':'Recorded workflow role'} · ${working?'Running assignment':'No running assignment'}</p></div></div><div class="employee-stats"><div><strong>${tasks.length}</strong><span>Assigned tasks</span></div><div><strong>${tasks.filter(t=>t.status==='completed').length}</strong><span>Accepted</span></div><div><strong>${tasks.filter(t=>t.status==='failed'||t.status==='changes_requested').length}</strong><span>Needs attention</span></div></div><p class="subtext">${e.skills.length?`Skills: ${esc(e.skills.join(', '))}`:'No role skill files configured'}</p><button class="text-button" data-role="${esc(e.role)}">Inspect assignments →</button></section>`;
 }).join('')}</div>`;}
function approvals(){
 const requests=data.approvals.filter(r=>matches(r.id,project(r.project)?.title,r.state));
 const body=requests.length?`<div class="table-wrap"><table><thead><tr><th>Proposal</th><th>Email state</th><th>Expiry</th><th>Binding</th></tr></thead><tbody>${requests.map(r=>`<tr><td><button class="table-title" data-project="${esc(r.project)}">${esc(project(r.project)?.title||short(r.project))}</button><span class="subtext">Request ${short(r.id)}</span></td><td>${badge(r.state)}</td><td>${esc(new Date(r.expires*1000).toLocaleString())}${r.expires<Date.now()/1000?' <span class="subtext">Expired</span>':''}</td><td><code>${esc(short(r.binding))}</code></td></tr>`).join('')}</tbody></table></div>`:empty('No Gmail approval requests yet. Rejected research is not an investment proposal.');
 return `${panel('Gmail approval requests','Approval remains bound to the proposal, budget, authority, and expiry',body)}<div class="section-gap">${panel('Unapproved candidates','View the complete proposal before requesting investment approval',projectTable(data.projects.filter(p=>!p.approved&&matches(p.title,p.id))))}</div>`;
}
function connections(){return `<div class="connection-grid">${data.connections.filter(c=>matches(c.name,c.detail,c.note)).map(c=>`<section class="panel connection-card"><h3>${esc(c.name)}</h3>${badge(c.status)}<p>${esc(c.detail)}</p><small>${esc(c.note)}</small></section>`).join('')}</div>`;}
function milestones(){const items=[
 ['Reliable internal workflow','Core implemented','SQLite state, permissions, approval gates, dependencies, independent review and bounded attempts work. Process isolation and unattended recovery remain incomplete.'],
 ['Research & founder approval','In progress','Live hosted research has run. Quality review requests evidence improvements. Gmail is configured locally; the complete live proposal-to-email-approval path is not yet proven.'],
 ['Autonomous product delivery','Partially implemented','Reviewed plans, task graphs and executable local QA exist. Local Git and task-scoped MCP tools work; isolated builds, browser QA and a complete live product remain outstanding.'],
 ['Release & operations','Not connected','Approved hosting, production health checks, monitoring, rollback and reliable unattended operation are outstanding. This dashboard adds local visibility.'],
 ['Business feedback loop','Not connected','Customer acquisition, support, payments, analytics and reconciled business outcomes remain outstanding.']];
 return panel('Blueprint milestones','Implementation progress is distinct from product or business success',items.map((m,i)=>`<div class="milestone"><div class="milestone-number">0${i+1}</div><div class="milestone-content"><h3>${m[0]}</h3><span class="pill ${i===0?'green':i<3?'amber':''}">${m[1]}</span><p>${m[2]}</p></div></div>`).join(''));}
function render(){
 if(!data)return;
 if(!routes[view])view='overview';
 $('#nav').innerHTML=Object.entries(routes).map(([key,r])=>`<a href="#${key}" class="${view===key?'selected':''}"><span class="nav-icon">${r[0]}</span>${r[1]}${key==='tasks'?`<span class="nav-count">${data.tasks.filter(t=>!t.audit_task).length}</span>`:''}</a>`).join('');
 $('#breadcrumb').textContent=routes[view][1];$('#title').textContent=routes[view][2];$('#subtitle').textContent=routes[view][3];
 const pages={controls,overview,projects:()=>panel('Project portfolio','Research mandates and product candidates are shown separately',projectTable(data.projects.filter(p=>matches(p.title,p.id)))),tasks,employees,approvals,activity:()=>panel('Audit trail','Most recent 250 durable events',timeline(data.events.filter(e=>matches(e.kind,JSON.stringify(e.details),e.at)))),connections,milestones};
 if(view!=='controls'||!$('#control-form')){$('#content').innerHTML=pages[view]();if(view==='controls')controlFields();}else{const result=controls();const holder=document.createElement('div');holder.innerHTML=result;const panels=$('#content').querySelectorAll('.panel');if(panels.length>1)panels[1].replaceWith(holder.querySelectorAll('.panel')[1]);}
 document.querySelectorAll('[data-width]').forEach(e=>{e.style.width=Number(e.dataset.width)+'%';});
 $('#updated').textContent='Updated '+new Date(data.updated_at).toLocaleTimeString();
}
async function load(){
 if(busy)return;busy=true;
 try{const response=await fetch('/api/state',{cache:'no-store'});if(!response.ok)throw Error('Dashboard state unavailable');data=await response.json();$('#connection').textContent='Live state · refreshes every 5s';$('#notice').hidden=true;render();}
 catch(error){$('#connection').textContent='Connection interrupted';$('#notice').textContent='Cannot refresh the local workspace. Showing the last loaded state. Check the dashboard terminal.';$('#notice').hidden=false;}
 finally{busy=false;}
}
function modal(title,kind,html){$('#detail-title').textContent=title;$('#detail-kind').textContent=kind;$('#detail-body').innerHTML=html;if(!$('#detail').open)$('#detail').showModal();}
function commandFor(t){
 const prefix='.venv/bin/python company_cli.py ';
 if(t.tool==='research.web_search'&&t.status==='changes_requested')return prefix+'rework-research '+t.id;
 if(t.status==='awaiting_review'&&!t.audit_task)return prefix+'qa '+t.id;
 if(t.tool==='research.web_search'&&t.status==='completed')return prefix+'draft-proposal '+t.id;
 return prefix+'status';
}
function taskDetail(id){const t=data.tasks.find(t=>t.id===id);if(!t)return;
 const deps=data.dependencies.filter(d=>d.task===id).map(d=>data.tasks.find(t=>t.id===d.dependency)).filter(Boolean);
 const command=commandFor(t);
 modal(taskName(t),'TASK · '+short(id),`<div class="detail-grid"><div class="detail-field"><span>Employee / reviewer</span>${esc(roleName(t.owner))} / ${esc(roleName(t.reviewer))}</div><div class="detail-field"><span>Status</span>${badge(t.status)} · Attempt ${t.attempts} of ${t.max_attempts}</div><div class="detail-field"><span>Project</span>${esc(project(t.project)?.title)}</div><div class="detail-field"><span>Task identifier</span>${esc(id)}</div></div><section class="detail-section"><h3>Acceptance criteria</h3>${t.payload?.acceptance_criteria?.length?`<ul>${t.payload.acceptance_criteria.map(c=>`<li>${esc(c)}</li>`).join('')}</ul>`:'<p>No source assignment criteria. This may be an operator audit report.</p>'}</section>${t.note?`<section class="detail-section"><h3>Latest review or failure</h3><p>${esc(t.note)}</p></section>`:''}<section class="detail-section"><h3>Dependencies</h3>${deps.length?deps.map(d=>`<p>${esc(taskName(d))} ${badge(d.status)}</p>`).join(''):'<p>No prerequisites recorded.</p>'}</section><div class="artifact-actions">${Object.entries(t.artifacts).map(([kind,name])=>`<button class="button" data-artifact="${esc(kind)}" data-artifact-task="${esc(id)}">Read ${esc(kind)} ↗</button>`).join('')}</div><div id="artifact-preview"></div><section class="detail-section"><h3>Next CLI action</h3><div class="command"><code>${esc(command)}</code><button class="text-button" data-copy="${esc(command)}">Copy</button></div><p class="subtext">Commands run only when you execute them in your terminal. Paid work still requires available allowance and credentials.</p></section>`);
}
function projectDetail(id){const p=project(id);if(!p)return;
 const tasks=data.tasks.filter(t=>t.project===id),grants=data.grants.filter(g=>g.project===id);
 modal(p.title,p.kind==='research_mandate'?'RESEARCH MANDATE':'PRODUCT CANDIDATE',`<div class="detail-grid"><div class="detail-field"><span>Authorization</span>${p.approved?'Approved scope':'Awaiting founder approval'} ${p.paused?' · Paused':''}</div><div class="detail-field"><span>Allowance</span>${p.spent} spent / ${p.budget} total · ${p.remaining} left</div><div class="detail-field"><span>Proposal digest</span>${esc(p.digest)}</div><div class="detail-field"><span>Project ID</span>${esc(id)}</div></div><button class="button" data-pause="${esc(id)}" data-paused="${p.paused?'false':'true'}">${p.paused?'Resume project':'Pause project'}</button><p class="subtext">Pause blocks new actions. Resume does not automatically start workers.</p><section class="detail-section"><h3>Recorded proposal</h3><pre class="code-block">${esc(JSON.stringify(p.proposal,null,2))}</pre></section><section class="detail-section"><h3>Granted capabilities</h3>${grants.length?`<ul>${grants.map(g=>`<li>${esc(roleName(g.role))} · <code>${esc(g.tool)}</code></li>`).join('')}</ul>`:'<p>No tool permissions granted.</p>'}</section><section class="detail-section"><h3>Project assignments</h3>${taskTable(tasks)}</section>`);
}
function toast(text){$('#toast').textContent=text;$('#toast').hidden=false;setTimeout(()=>$('#toast').hidden=true,3000);}
async function pauseProject(id,paused,button){
 button.disabled=true;
 try{const response=await fetch('/api/pause',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({project:id,paused})});if(!response.ok)throw Error();await load();projectDetail(id);toast(paused?'Project paused':'Project resumed; no workers started');}
 catch(error){toast('Could not update project state. Check the dashboard connection.');button.disabled=false;}
}
document.addEventListener('click',async event=>{
 if(event.target.closest('[data-control-submit]')){await submitControl();return;}

 const target=event.target.closest('button');if(!target)return;
 if(target.dataset.nav){location.hash=target.dataset.nav;return;}
 if(target.dataset.task){taskDetail(target.dataset.task);return;}
 if(target.dataset.project){projectDetail(target.dataset.project);return;}
 if(target.dataset.role){search=target.dataset.role;$('#search').value=search;location.hash='tasks';return;}
 if(target.dataset.pause){await pauseProject(target.dataset.pause,target.dataset.paused==='true',target);return;}
 if(target.dataset.copy){try{await navigator.clipboard.writeText(target.dataset.copy);toast('Command copied');}catch(error){toast('Select the command to copy it manually');}return;}
 if(target.dataset.artifact){
  target.disabled=true;
  try{const response=await fetch(`/api/artifact?task=${encodeURIComponent(target.dataset.artifactTask)}&kind=${encodeURIComponent(target.dataset.artifact)}`);if(!response.ok)throw Error();const artifact=await response.json();const box=$('#artifact-preview');box.replaceChildren();const heading=document.createElement('h3');heading.textContent=artifact.name;const text=document.createElement('pre');text.className='code-block';text.textContent=artifact.content;box.append(heading,text);}
  catch(error){toast('Artifact is unavailable or exceeds the preview limit');}finally{target.disabled=false;}
 }
});
$('#refresh').addEventListener('click',load);$('#close-detail').addEventListener('click',()=>$('#detail').close());
$('#search').addEventListener('input',e=>{search=e.target.value;render();});
document.addEventListener('change',e=>{if(e.target.id==='project-filter'){projectFilter=e.target.value;render();}if(e.target.id==='status-filter'){statusFilter=e.target.value;render();}});
window.addEventListener('hashchange',()=>{view=location.hash.slice(1)||'overview';$('#detail').close();render();});
load();setInterval(()=>{if(!document.hidden)load();},5000);

const actions={
 'create-project':'Create product proposal',assign:'Assign employee task',grant:'Grant capability',revoke:'Revoke capability',
 discover:'Research opportunities (paid)',run:'Run employee (paid)',qa:'Independent model QA (paid)',
 plan:'Generate delivery plan (paid)','apply-plan':'Install reviewed plan',tick:'Run one scheduler action (paid)',
 'rework-research':'Rework research (paid)','draft-proposal':'Draft proposal (paid)','register-proposal':'Register reviewed proposal',
 'workspace-init':'Initialize approved repository','email-proposal':'Send founder approval email','email-poll':'Poll Gmail decisions',
 'email-reconcile':'Reconcile email delivery',doctor:'Check local setup',recover:'Recover interrupted tasks'
};
function controls(){
 const projects=data.projects.map(p=>`<option value="${esc(p.id)}">${esc(p.title)} · ${short(p.id)}</option>`).join('');
 const roles=data.employees.filter(e=>e.configured).map(e=>`<option>${esc(e.role)}</option>`).join('');
 const jobs=(data.jobs||[]).map(j=>`<tr><td>${esc(human(j.action))}<span class="subtext">${esc(j.id)}</span></td><td>${badge(j.status)}</td><td>${esc(j.created_at)}</td><td>${esc(j.result||'')}</td></tr>`).join('');
 return panel('Operator console','Actions use the existing workflow gates. Select an action to see its fields.',`
 <form id="control-form" class="control-form">
 <label>Action<select id="control-action">${Object.entries(actions).map(([k,v])=>`<option value="${k}">${esc(v)}</option>`).join('')}</select></label>
 <div id="control-fields"></div>
 <label class="control-confirm"><input id="control-confirm" type="checkbox"> I authorize this action, including provider charges or founder email access if applicable.</label>
 <button type="button" class="button" data-control-submit>Execute selected action</button>
 <p id="control-result" role="status"></p></form>
 <template id="control-project-options">${projects}</template><template id="control-role-options">${roles}</template>
 <p class="subtext">Investment decisions remain authenticated through Gmail. Recover only after checking that no CLI worker is active. Failed or interrupted external actions require reconciliation before retrying. Deployment is not connected.</p>`)+panel('Action jobs','Persisted action status; task details and Activity contain the underlying workflow evidence',jobs?`<div class="table-wrap"><table><thead><tr><th>Action</th><th>Status</th><th>Created</th><th>Outcome</th></tr></thead><tbody>${jobs}</tbody></table></div>`:empty('No dashboard actions yet.'));
}
function controlFields(){
 const action=$('#control-action')?.value;if(!action)return;
 const input=(id,label,value='')=>`<label>${label}<input id="control-${id}" value="${esc(value)}"></label>`;
 const json=(id,label,value)=>`<label>${label}<textarea id="control-${id}" rows="7">${esc(JSON.stringify(value,null,2))}</textarea></label>`;
 let fields='';
 if(['assign','grant','revoke','plan','tick','workspace-init','email-proposal'].includes(action))fields+=`<label>Project<select id="control-project">${$('#control-project-options').innerHTML}</select></label>`;
 if(['run','qa','apply-plan','rework-research','draft-proposal','register-proposal'].includes(action))fields+=`<label>Task<select id="control-task">${data.tasks.map(t=>`<option value="${esc(t.id)}">${esc(taskName(t))} · ${esc(t.status)} · ${short(t.id)}</option>`).join('')}</select></label>`;
 if(action==='create-project')fields+=json('proposal','Complete proposal JSON',{title:'New product proposal',authority_requested:'Describe requested scope'})+input('budget','Internal allowance',100);
 if(action==='discover')fields+=input('market','Market','Small service businesses')+input('budget','Internal allowance',100);
 if(action==='register-proposal')fields+=input('budget','Proposed internal allowance',100);
 if(['assign','grant','revoke'].includes(action))fields+=`<label>Employee<select id="control-role">${$('#control-role-options').innerHTML}</select></label>`;
 if(action==='assign')fields+=`<label>Independent reviewer<select id="control-reviewer">${$('#control-role-options').innerHTML}</select></label>`+json('payload','Assignment JSON',{objective:'Describe the deliverable',acceptance_criteria:['Define verifiable acceptance']})+json('dependencies','Prerequisite task IDs',[]);
 if(['grant','revoke'].includes(action))fields+=input('tool','Allowlisted capability (employee.role or server/tool)');
 if(action==='email-reconcile')fields+=input('request','Email request ID');
 if(action==='workspace-init')fields+='<label><input type="checkbox" id="control-grant_tools"> Grant local delivery capabilities</label>';
 $('#control-fields').innerHTML=fields;
}
async function submitControl(){
 const action=$('#control-action').value,body={action,confirmed:$('#control-confirm').checked};
 if(!body.confirmed){$('#control-result').textContent='Confirm the selected action first.';return;}
 try{
 for(const key of ['project','task','role','reviewer','tool','request','market','budget','proposal','payload','dependencies','grant_tools']){
 const e=$('#control-'+key);if(!e)continue;
 body[key]=['proposal','payload','dependencies'].includes(key)?JSON.parse(e.value):key==='budget'?Number(e.value):key==='grant_tools'?e.checked:e.value;
 }
 const endpoint=['create-project','assign','grant','revoke'].includes(action)?'/api/control':'/api/action';
 const response=await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(body)});
 const result=await response.json();if(!response.ok)throw Error(result.error||'Action rejected');
 $('#control-result').textContent=JSON.stringify(result);toast(result.job?'Action queued; follow its job status':'Change saved');
 }catch(error){$('#control-result').textContent=error.message;}
}
document.addEventListener('change',e=>{if(e.target.id==='control-action')controlFields();});
