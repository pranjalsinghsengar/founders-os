export function originalIdea(project, ideas) {
  return ideas.find(i => i.research_task && i.research_task === project.proposal?.research_task);
}
export function matchingProjects(projects, ideas, query) {
  const term = query.trim().toLowerCase();
  return projects.filter(p => [p.title, p.proposal?.market, originalIdea(p, ideas)?.title]
    .filter(Boolean).join(' ').toLowerCase().includes(term));
}
export function submittedProject(projects, task) {
  return projects.find(p => p.submission_task === task);
}
