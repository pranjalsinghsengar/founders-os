import test from 'node:test';
import assert from 'node:assert/strict';
import {DELIVERY_KEYS,hasAuthority,nextAction,pendingProjects,taskSummary} from './app/project-state.mjs';
test('A stage label alone does not authorize execution',()=>{assert.equal(hasAuthority({stage:'Building'}),false);assert.equal(hasAuthority({approved:true}),true)});
test('Global and individual pauses take priority over delivery',()=>{assert.equal(nextAction({approved:true},true).label,'Execution paused');assert.equal(nextAction({approved:true,paused:true}).tab,'Overview')});
test('New project submissions appear in the decision inbox',()=>{const projects=[{stage:'Needs approval'},{stage:'Planning',founderDecision:'Approve'},{stage:'Needs approval',founderDecision:'Reject'}];assert.equal(pendingProjects(projects).length,1)});
test('A rejected or revised submission is not routed into delivery',()=>{assert.equal(nextAction({stage:'Rejected',approved:false}).tab,'Decisions');assert.equal(nextAction({stage:'Changes requested',approved:false}).tab,'Research')});
test('QA repair precedes remaining repository steps',()=>{assert.equal(nextAction({approved:true,taskItems:[{status:'Changes requested'}]}).tab,'Tasks');assert.equal(nextAction({approved:true,taskItems:[]}).tab,'Repository')});
test('A completed demo is explicitly distinguished from live readiness',()=>{const result=nextAction({approved:true,deliverySteps:DELIVERY_KEYS});assert.equal(result.label,'Demo sequence complete');assert.match(result.detail,/Live verification/);assert.equal(taskSummary({taskItems:[{status:'Completed'},{status:'Queued'}]}),'1 / 2')});

test('Duplicate delivery records cannot masquerade as completion',()=>{assert.equal(nextAction({approved:true,deliverySteps:Array(8).fill('repository')}).label,'Advance the delivery package')});
