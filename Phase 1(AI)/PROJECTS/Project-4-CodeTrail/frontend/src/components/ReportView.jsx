import Timeline from './Timeline.jsx'

function exportReport(report, threadId) {
  const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `codetrail-${threadId || 'report'}.json`
  anchor.click()
  URL.revokeObjectURL(url)
}

function LabelBadge({ label }) {
  return <span className={`label ${label}`}>{label}</span>
}

export default function ReportView({ report, threadId, onOpenEvidence }) {
  const snapshot = report.snapshot
  return (
    <article className="panel report">
      <header className="report-head">
        <div>
          <p className="eyebrow">Investigation report</p>
          <h2>{report.question}</h2>
          <p className="muted">
            {snapshot.repository} @ {snapshot.sha.slice(0, 7)}
            {snapshot.ref_requested ? ` (${snapshot.ref_requested})` : ''}
          </p>
        </div>
        <button type="button" onClick={() => exportReport(report, threadId)}>
          Export JSON
        </button>
      </header>

      <p className="summary">{report.summary}</p>

      <h3>Claims</h3>
      {report.claims.length === 0 ? (
        <p className="muted">No claim survived validation.</p>
      ) : (
        <ul className="claims">
          {report.claims.map((claim, index) => (
            <li key={index} className="claim">
              <LabelBadge label={claim.label} />
              <p>{claim.statement}</p>
              {claim.excerpts.map((excerpt, position) => (
                <button
                  type="button"
                  key={position}
                  className="citation"
                  onClick={() =>
                    onOpenEvidence({
                      source_id: excerpt.source_id,
                      quote: excerpt.quote,
                      start_line: excerpt.start_line,
                      end_line: excerpt.end_line,
                      title: 'Cited excerpt',
                    })
                  }
                >
                  {excerpt.source_id} · lines {excerpt.start_line}–{excerpt.end_line}
                </button>
              ))}
            </li>
          ))}
        </ul>
      )}

      {report.unresolved.length > 0 && (
        <section>
          <h3>Unresolved</h3>
          <ul className="unresolved">
            {report.unresolved.map((item, index) => (
              <li key={index}>{item}</li>
            ))}
          </ul>
        </section>
      )}

      <Timeline events={report.timeline} onOpenEvidence={onOpenEvidence} />

      <section>
        <h3>Scope inspected</h3>
        <p className="muted">
          {report.coverage.files_read} file(s), {report.coverage.commits_read} commit(s),{' '}
          {report.coverage.discussions_read} discussion(s), {report.coverage.comments_read}{' '}
          comment/review(s)
          {report.coverage.complete ? '' : ' — coverage incomplete'}
        </p>
        {report.coverage.notes.length > 0 && (
          <ul className="unresolved">
            {report.coverage.notes.map((note, index) => (
              <li key={index}>{note}</li>
            ))}
          </ul>
        )}
      </section>
    </article>
  )
}
