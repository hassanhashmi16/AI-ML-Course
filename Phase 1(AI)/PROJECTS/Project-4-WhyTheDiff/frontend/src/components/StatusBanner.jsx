export default function StatusBanner({ status }) {
  const complete = status === 'complete'
  return (
    <div className="status">
      <span className={`stamp ${complete ? 'complete' : 'partial'}`}>
        {complete ? 'Supported report' : 'Partial report'}
      </span>
      <p className="status-text">
        {complete
          ? 'The surviving findings have citations and passed the report’s grounding checks.'
          : 'Some questions remain unresolved or the search reached a limit. Review the findings and limitations below.'}
      </p>
    </div>
  )
}
