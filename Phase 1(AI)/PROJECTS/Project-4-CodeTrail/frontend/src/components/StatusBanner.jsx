export default function StatusBanner({ status }) {
  const complete = status === 'complete'
  return (
    <div className="status">
      <span className={`stamp ${complete ? 'complete' : 'partial'}`}>
        {complete ? 'Complete' : 'Partial'}
      </span>
      <p className="status-text">
        {complete
          ? 'Every claim passed citation and grounding checks and is backed by a quoted source.'
          : 'Some claims were downgraded because their quotes did not establish them. The unresolved list says what is missing.'}
      </p>
    </div>
  )
}
