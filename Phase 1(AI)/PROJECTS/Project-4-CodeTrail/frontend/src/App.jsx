import { useCallback, useEffect, useRef, useState } from 'react'
import { account, logout, investigation, listInvestigations, fetchEvents, health, listReports, loadReport, resumeInvestigation, startInvestigation } from './api.js'
import EmptyState from './components/EmptyState.jsx'
import EvidenceDrawer from './components/EvidenceDrawer.jsx'
import InvestigationForm from './components/InvestigationForm.jsx'
import ReportView from './components/ReportView.jsx'
import SavedRuns from './components/SavedRuns.jsx'
import StageLog from './components/StageLog.jsx'
import LandingPage from './components/LandingPage.jsx'
import WorkspaceHeader from './components/WorkspaceHeader.jsx'
import JobHistory from './components/JobHistory.jsx'
import { RunningPanel, ErrorPanel } from './components/RunState.jsx'
import { durationLabel } from './format.js'
import './workspace.css'

export default function App() {
  const [api, setApi] = useState(null)
  const [identity, setIdentity] = useState(undefined)
  const [jobs, setJobs] = useState([])
  const [runs, setRuns] = useState([])
  const [phase, setPhase] = useState('idle')
  const [sidebar, setSidebar] = useState('new')
  const [preset, setPreset] = useState(null)
  const [formVersion, setFormVersion] = useState(0)
  const [jobStatus, setJobStatus] = useState('queued')
  const [startedAt, setStartedAt] = useState(null)
  const [elapsed, setElapsed] = useState(0)
  const [finishedSeconds, setFinishedSeconds] = useState(null)
  const [error, setError] = useState('')
  const [question, setQuestion] = useState('')
  const [report, setReport] = useState(null)
  const [events, setEvents] = useState([])
  const [threadId, setThreadId] = useState('')
  const [drawer, setDrawer] = useState(null)
  const [openingReport, setOpeningReport] = useState(false)
  const monitor = useRef(null)
  const busy = phase === 'running' || openingReport
  const activeJob = jobs.find((job) => job.thread_id === threadId)
  const focusWorkspace = () => requestAnimationFrame(() => {
    const workspace = document.getElementById('workspace')
    workspace?.focus({ preventScroll: true })
    workspace?.scrollIntoView({ block: 'start', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' })
  })

  useEffect(() => {
    let canceled = false
    async function initialize() {
      try {
        const info = await health()
        if (canceled) return
        setApi(info)
        if (info.public_app) {
          const auth = await account()
          if (canceled) return
          setIdentity(auth.user)
          if (!auth.user) return
        }
        const [saved, history] = await Promise.allSettled([listReports(), info.public_app ? listInvestigations() : Promise.resolve({ investigations: [] })])
        if (canceled) return
        if (saved.status === 'fulfilled') setRuns(saved.value.reports)
        if (history.status === 'fulfilled') {
          setJobs(history.value.investigations)
          if (history.value.investigations.some((job) => ['queued', 'running'].includes(job.status))) setSidebar('history')
        }
      } catch {
        if (!canceled) { setApi((old) => old || { status: 'unreachable' }); setIdentity(null) }
      }
    }
    initialize()
    return () => { canceled = true; monitor.current?.abort() }
  }, [])

  const refreshRuns = useCallback(async () => {
    const [saved, history] = await Promise.allSettled([listReports(), api?.public_app ? listInvestigations() : Promise.resolve(null)])
    if (saved.status === 'fulfilled') setRuns(saved.value.reports)
    if (history.status === 'fulfilled' && history.value) setJobs(history.value.investigations)
  }, [api?.public_app])

  useEffect(() => {
    if (phase !== 'running') return undefined
    const start = startedAt ? new Date(startedAt).getTime() : Date.now()
    const update = () => setElapsed(Math.max(0, Math.floor((Date.now() - start) / 1000)))
    update()
    const timer = setInterval(update, 1000)
    return () => clearInterval(timer)
  }, [phase, startedAt])

  useEffect(() => {
    if (!identity || phase === 'running' || !jobs.some((job) => ['queued', 'running'].includes(job.status))) return undefined
    const timer = setInterval(refreshRuns, 5000)
    return () => clearInterval(timer)
  }, [identity, jobs, phase, refreshRuns])

  const settle = async (initial) => {
    monitor.current?.abort()
    const controller = new AbortController()
    monitor.current = controller
    setThreadId(initial.thread_id)
    setJobStatus(initial.status)
    if (initial.created_at) setStartedAt(initial.created_at)
    if (initial.question) setQuestion(initial.question)
    let result = initial
    if (api?.public_app) {
      setJobs((old) => [initial, ...old.filter((job) => job.thread_id !== initial.thread_id)])
      fetchEvents(initial.thread_id, (event) => { if (!controller.signal.aborted) setEvents((old) => [...old, event]) }, controller.signal).catch(() => {})
      while (['queued', 'running'].includes(result.status)) {
        await new Promise((resolve) => setTimeout(resolve, 1000))
        if (controller.signal.aborted) return
        result = await investigation(initial.thread_id)
        if (controller.signal.aborted) return
        setJobStatus(result.status)
      }
      controller.abort()
      setJobs((old) => [result, ...old.filter((job) => job.thread_id !== result.thread_id)])
      if (!result.report) throw new Error(result.error || 'This run was interrupted. You can resume it from History.')
    }
    setReport(result.report)
    setFinishedSeconds(result.elapsed_seconds ?? null)
    setPhase('done')
    if (result.report) {
      try {
        const replay = await fetchEvents(result.thread_id)
        if (monitor.current === controller) setEvents(replay.events)
      } catch { /* a saved report remains useful if activity replay is unavailable */ }
    }
    refreshRuns()
  }

  const prepareRun = (nextQuestion = '') => {
    setPhase('running'); setError(''); setReport(null); setEvents([]); setDrawer(null)
    setQuestion(nextQuestion); setStartedAt(new Date().toISOString()); setElapsed(0)
    setFinishedSeconds(null); setJobStatus('queued')
    focusWorkspace()
  }
  const fail = (exc) => {
    monitor.current?.abort()
    if (exc.name !== 'AbortError') { setError(exc.message); setPhase('error'); refreshRuns() }
  }
  const run = async (payload) => {
    prepareRun(payload.question); setThreadId('')
    try { await settle(await startInvestigation(payload)) } catch (exc) { fail(exc) }
  }
  const resume = async (id) => {
    prepareRun(jobs.find((job) => job.thread_id === id)?.question || '')
    setThreadId(id)
    try { await settle(await resumeInvestigation(id)) } catch (exc) { fail(exc) }
  }
  const follow = async (job) => {
    prepareRun(job.question)
    try { await settle(job) } catch (exc) { fail(exc) }
  }
  const openRun = async (name) => {
    if (busy) return
    monitor.current?.abort()
    const controller = new AbortController()
    monitor.current = controller
    setOpeningReport(true); setDrawer(null)
    try {
      const loaded = await loadReport(name)
      const id = /^[a-f0-9]{32}\.json$/.test(name) ? name.slice(0, -5) : ''
      if (monitor.current !== controller) return
      setReport(loaded); setThreadId(id); setQuestion(loaded.question)
      setFinishedSeconds(jobs.find((job) => job.thread_id === id)?.elapsed_seconds ?? null)
      setEvents([]); setError(''); setPhase('done')
      focusWorkspace()
      if (id) {
        try {
          const replay = await fetchEvents(id, null, controller.signal)
          if (monitor.current === controller) setEvents(replay.events)
        } catch { /* the report is already available */ }
      }
    } catch (exc) { fail(exc) }
    finally { if (monitor.current === controller) setOpeningReport(false) }
  }
  const startOver = () => {
    monitor.current?.abort()
    setPhase('idle'); setReport(null); setEvents([]); setError(''); setQuestion('')
    setThreadId(''); setDrawer(null); setSidebar('new'); setFinishedSeconds(null)
    setPreset(null); setFormVersion((old) => old + 1)
  }
  const chooseCase = (item) => {
    setPreset({ ...item }); setSidebar('new')
    requestAnimationFrame(() => document.getElementById('investigation-form')?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }))
  }
  const inspectJob = (job) => {
    setThreadId(job.thread_id); setQuestion(job.question || ''); setReport(null)
    setEvents([]); setError(job.error || 'This investigation was interrupted.'); setPhase('error')
    focusWorkspace()
  }
  const live = phase === 'running' ? `Investigation ${jobStatus}.` : phase === 'error' ? 'Investigation needs attention.' : report ? `Report available: ${report.status}.` : ''

  if (!api || (api.public_app && !identity)) return <LandingPage checkingSession={!api || identity === undefined} />
  return <div className="app workspace-app" data-view={phase}>
    <a className="skip-link" href="#workspace">Skip to the report</a>
    <p className="sr-only" role="status">{live}</p>
    <div inert={drawer ? true : undefined}>
      <WorkspaceHeader identity={identity} connected={api.status === 'ok'} running={phase === 'running'} disabled={busy} onNew={startOver} onSignOut={async () => { await logout(); window.location.reload() }} />
      <div className="ws-intro"><div><p className="ws-kicker">Your investigation desk</p><h1>Follow the evidence.</h1></div><div className="ws-intro-note"><span>{api.public_app ? `${jobs.length} investigations` : 'Local workspace'}</span><span>{runs.length} saved reports</span></div></div>
      {api.status !== 'ok' && <p className="ws-service-note" role="alert">The service is unavailable. Check that the backend is running, then refresh.</p>}
      <main className="layout ws-layout">
        <aside className="rail ws-sidebar" aria-label="Investigation brief and history">
          <div className="ws-sidebar-tabs" role="group" aria-label="Workspace sections"><button aria-pressed={sidebar === 'new'} onClick={() => setSidebar('new')}>New investigation</button><button aria-pressed={sidebar === 'history'} onClick={() => setSidebar('history')}>History <span>{api.public_app ? jobs.length : runs.length}</span></button></div>
          <div className="ws-sidebar-pane" hidden={sidebar !== 'new'}><InvestigationForm key={formVersion} running={phase === 'running'} onRun={run} onResume={resume} preset={preset} showResume={!api.public_app} /></div>
          <div className="ws-sidebar-pane" hidden={sidebar !== 'history'}>{api.public_app ? <JobHistory jobs={jobs} activeId={threadId} disabled={busy} onOpen={openRun} onFollow={follow} onInspect={inspectJob} onNew={startOver} /> : <SavedRuns runs={runs} onOpen={openRun} disabled={busy} />}</div>
          <p className="ws-private-note"><span aria-hidden="true">&#9671;</span> {api.public_app ? 'Your history and reports belong to your account.' : 'Your reports are saved in this local workspace.'}</p>
        </aside>
        <section className="workspace" id="workspace" tabIndex={-1} aria-label="Investigation report" aria-busy={openingReport}>
          <div className="ws-document-stack">
            {phase === 'idle' && <EmptyState onChooseCase={chooseCase} />}
            {phase === 'running' && <RunningPanel question={question} elapsed={elapsed} threadId={threadId} jobStatus={jobStatus} events={events} />}
            {phase === 'error' && <ErrorPanel message={error} question={question} onNew={startOver} resumable={!!threadId && ['failed','interrupted'].includes(activeJob?.status)} onResume={() => resume(threadId)} />}
            {phase === 'done' && report && <><div className="ws-report-context"><span>Saved investigation</span>{finishedSeconds != null && <span>Completed in {durationLabel(finishedSeconds)}</span>}</div><ReportView report={report} threadId={threadId} onOpenEvidence={setDrawer} /></>}
            {events.length > 0 && <StageLog events={events} />}
          </div>
        </section>
      </main>
      <footer className="ws-footer"><span>CodeTrail / Trace the decisions.</span><span>Public sources. Inspectable findings.</span></footer>
    </div>
    {drawer && <EvidenceDrawer evidence={drawer} onClose={() => setDrawer(null)} />}
  </div>
}
