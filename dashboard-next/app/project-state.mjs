export const DELIVERY_KEYS=['repository','scaffold','implementation','verification','commit','push','handoff','release'];
export const hasAuthority = project => project.approved === true || project.founderDecision === 'Approve';
export const pendingProjects = projects => projects.filter(p => p.stage === 'Needs approval' && !p.founderDecision);
export function nextAction(project, companyPaused = false) {
 if (companyPaused || project.paused) return {label:'Execution paused',detail:'Resume the company or project before advancing delivery.',tab:'Overview',tone:'slate'};
 if (project.stage === 'Rejected') return {label:'Submission rejected',detail:'Revisit the idea and evidence before preparing a new submission.',tab:'Decisions',tone:'orange'};
 if (project.stage === 'Changes requested') return {label:'Revise the proposal',detail:'Resolve founder feedback and request a new decision.',tab:'Research',tone:'orange'};
 if (project.stage === 'Researching') return {label:'Complete the research',detail:'Collect sources and resolve critical evidence gaps.',tab:'Research',tone:'blue'};
 if (!hasAuthority(project)) return {label:'Founder decision needed',detail:'Review scope, flaws and requested allowance before authorizing work.',tab:'Decisions',tone:'orange'};
 if ((project.taskItems || []).some(t=>t.status==='Changes requested') || (!project.taskItems && project.stage==='Building')) return {label:'Repair the QA defect',detail:'Developer fixes the issue; independent reviewer checks fresh evidence.',tab:'Tasks',tone:'orange'};
 if (!DELIVERY_KEYS.every(key=>(project.deliverySteps||[]).includes(key))) return {label:'Advance the delivery package',detail:'Inspect repository, implementation, test and release gates.',tab:'Repository',tone:'purple'};
 return {label:'Demo sequence complete',detail:'Live verification is still required before declaring a product ready.',tab:'Repository',tone:'green'};
}
export function taskSummary(project) {
 if (!project.taskItems) return project.tasks;
 return `${project.taskItems.filter(t=>t.status==='Completed').length} / ${project.taskItems.length}`;
}
