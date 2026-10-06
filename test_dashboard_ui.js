/* Render checks without browser dependencies. HTTP behavior is tested in Python. */
const vm = require('node:vm');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const elements = new Map();
function element(selector) {
  if (!elements.has(selector)) elements.set(selector, {content:'fixture-csrf',innerHTML:'',textContent:'',hidden:false,open:false,value:'',
    addEventListener(){},showModal(){this.open=true;},close(){this.open=false;},replaceChildren(){},append(){}});
  return elements.get(selector);
}
const state = {
  updated_at:new Date().toISOString(), mode:'Local operator',
  projects:[{id:'project-fixture',title:'<script>attack()</script>',kind:'research_mandate',budget:100,spent:100,remaining:0,approved:1,paused:0,proposal:{title:'Fixture'},digest:'abc'}],
  tasks:[{id:'task-fixture',project:'project-fixture',owner:'researcher',reviewer:'product_manager',tool:'research.web_search',status:'changes_requested',attempts:2,max_attempts:3,note:'Needs stronger sources',payload:{objective:'Research fixture',acceptance_criteria:['Use sources']},artifacts:{artifact:'research.md'},audit_task:false}],
  events:[{kind:'task.reviewed',at:'2026-10-04 00:00:00',details:{task:'task-fixture'}}],
  dependencies:[],grants:[],approvals:[],
  employees:[{role:'researcher',configured:true,skills:['skills/researcher.md'],task_ids:['task-fixture']}],
  connections:[{name:'Hosted research',status:'observed',detail:'Saved sources',note:'Real use recorded'}]
};
const context = vm.createContext({console,URL,Date,setTimeout(){},setInterval(){},
  navigator:{clipboard:{writeText:async()=>{}}},
  location:{hash:'#overview'},window:{addEventListener(){}},
  document:{hidden:false,querySelector:element,querySelectorAll(){return []},addEventListener(){},createElement(){return {className:'',textContent:''}}},
  fetch:async()=>({ok:true,json:async()=>state})});
vm.runInContext(fs.readFileSync('dashboard/app.js','utf8'),context);
(async()=>{
  await new Promise(resolve=>setImmediate(resolve));
  for (const view of ['overview','projects','tasks','employees','approvals','activity','connections','milestones']) {
    vm.runInContext(`view='${view}';render();`,context);
    assert.ok(element('#content').innerHTML.length>100,`${view} renders`);
    assert.ok(!element('#content').innerHTML.includes('<script>attack()'),`${view} escapes project title`);
  }
  vm.runInContext("taskDetail('task-fixture')",context);
  assert.match(element('#detail-body').innerHTML,/Needs stronger sources/);
  assert.match(element('#detail-body').innerHTML,/rework-research task-fixture/);
  assert.equal(element('#detail').open,true);
  vm.runInContext("projectDetail('project-fixture')",context);
  assert.match(element('#detail-body').innerHTML,/Pause project/);
  assert.ok(!element('#detail-title').innerHTML.includes('<script>'));
  const controls = vm.runInContext('controls()',context);
  assert.match(controls,/Orchestration|Operator console/);
  assert.match(controls,/Execute selected action/);
  assert.match(controls,/Poll Gmail decisions/);
  assert.ok(!controls.includes('<script>attack()'));
  element('#control-action').value='assign';
  vm.runInContext('controlFields()',context);
  assert.match(element('#control-fields').innerHTML,/Prerequisite task IDs/);
  assert.match(element('#control-fields').innerHTML,/Independent reviewer/);
  console.log('Dashboard UI: 9 views, control fields, detail rendering, and escaped content passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
