import { useState } from 'react'
import { durationLabel, repositoryLabel, shortDateTime } from '../format.js'

export default function JobHistory({ jobs, activeId, disabled, onOpen, onFollow, onInspect, onNew }) {
  const [query, setQuery] = useState('')
  const matches = jobs.filter((job) => `${job.question || job.report?.question || ''} ${job.repository || ''} ${job.thread_id}`.toLowerCase().includes(query.toLowerCase()))
  return <section className="ws-history" aria-label="Your investigation history">
    <div className="ws-sidebar-heading"><h2>Your investigations</h2><span>{jobs.length}</span></div>
    <p className="ws-sidebar-note">Saved to your account. Reopen a report without starting another investigation.</p>
    {jobs.length > 0 && <input className="ws-history-search" aria-label="Search investigations" placeholder="Search your investigations…" value={query} onChange={(event) => setQuery(event.target.value)} />}
    {jobs.length === 0 && <div className="ws-history-empty"><span aria-hidden="true">↳</span><h3>A place for your findings.</h3><p>Your investigations will appear here, including runs you can return to or resume.</p><button className="btn" onClick={onNew}>Start an investigation</button></div>}
    {jobs.length > 0 && matches.length === 0 && <p className="ws-sidebar-note">No investigations match your search.</p>}
    <ul className="ws-job-list">{matches.map((job) => {
      const pending = ['queued', 'running'].includes(job.status)
      const failed = ['failed', 'interrupted'].includes(job.status)
      const label = pending ? job.status === 'queued' ? 'Queued' : 'Running' : failed ? job.status === 'failed' ? 'Needs attention' : 'Interrupted' : job.report?.status === 'partial' ? 'Partial report' : 'Report ready'
      const open = () => pending ? onFollow(job) : failed ? onInspect(job) : onOpen(`${job.thread_id}.json`)
      return <li key={job.thread_id}><button className={`ws-job ${job.thread_id === activeId ? 'selected' : ''}`} disabled={disabled} onClick={open} aria-current={job.thread_id === activeId ? 'true' : undefined}><span className="ws-job-meta"><span className={`ws-job-status ${failed ? 'attention' : pending ? 'pending' : ''}`}><i />{label}</span><span>{job.elapsed_seconds != null && durationLabel(job.elapsed_seconds)}</span></span><span className="ws-job-title">{job.question || job.report?.question || 'Untitled investigation'}</span><span className="ws-job-repo">{repositoryLabel(job.repository || job.report?.snapshot?.repository)}</span><span className="ws-job-bottom"><span>{job.created_at ? shortDateTime(job.created_at) : 'Saved investigation'}</span><span>{pending ? 'Follow progress' : failed ? 'Review run' : 'Open report'} <span aria-hidden="true">↗</span></span></span></button></li>
    })}</ul>
  </section>
}
