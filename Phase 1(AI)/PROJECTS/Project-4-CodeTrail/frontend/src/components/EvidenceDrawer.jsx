export default function EvidenceDrawer({ evidence, onClose }) {
  return (
    <aside className="drawer" role="dialog" aria-modal="true" aria-label="Evidence">
      <div className="drawer-head">
        <h2>Evidence</h2>
        <button type="button" onClick={onClose} aria-label="Close evidence">
          Close
        </button>
      </div>

      {evidence.quote ? (
        <blockquote className="quote">{evidence.quote}</blockquote>
      ) : (
        <p className="muted">
          This timeline entry points at a source record. Open the repository at the pinned
          snapshot to read it in place.
        </p>
      )}

      <dl className="evidence-meta">
        <dt>Source</dt>
        <dd className="mono">{evidence.source_id}</dd>
        {evidence.start_line ? (
          <>
            <dt>Lines</dt>
            <dd>
              {evidence.start_line}–{evidence.end_line}
            </dd>
          </>
        ) : null}
        {evidence.title ? (
          <>
            <dt>Title</dt>
            <dd>{evidence.title}</dd>
          </>
        ) : null}
      </dl>

      <p className="muted small">
        Quotes are stored exactly as they appear in the source; citation validation rejects
        anything that does not match verbatim.
      </p>
    </aside>
  )
}
