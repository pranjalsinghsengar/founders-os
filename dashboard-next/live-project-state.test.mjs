import test from 'node:test';
import assert from 'node:assert/strict';
import {matchingProjects, originalIdea, submittedProject} from './app/live-project-state.mjs';
const project={id:'product',title:'Utility Invoicing',submission_task:'draft',proposal:{research_task:'research',market:'Utilities'}};
const ideas=[{title:'Invoice app',research_task:'research'},{title:'Unresearched idea',research_task:null}];
test('Renamed submitted products remain searchable by original idea',()=>{
  assert.deepEqual(matchingProjects([project],ideas,' Invoice app '),[project]);
  assert.equal(originalIdea(project,ideas).title,'Invoice app');
  assert.equal(originalIdea({proposal:{}},ideas),undefined);
});
test('Submission navigation uses durable draft identity',()=>{
  assert.equal(submittedProject([project],'draft').id,'product');
  assert.equal(submittedProject([project],'other-draft'),undefined);
});
