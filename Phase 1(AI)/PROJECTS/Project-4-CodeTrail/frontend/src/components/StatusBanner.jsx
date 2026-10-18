export default function StatusBanner({ report }) {
  const partial = report.status !== 'complete'
  return (
    <div className={`banner ${partial ? 'partial' : 'complete'}`}>
      <strong>{partial ? 'Partial result' : 'Supported explanation'}</strong>
      <span>
        {partial
          ? 'Some claims could not be supported by the cited evidence; the unresolved list says what is missing.'
          : 'Every claim passed citation and grounding checks and is backed by a quoted source.'}
      </span>
    </div>
  )
}
