import { useEffect, useRef, useState } from 'react'

const FOCUSABLE =
  'button, [href], input, textarea, select, [tabindex]:not([tabindex="-1"])'

export default function EvidenceDrawer({ evidence, onClose }) {
  const sheetRef = useRef(null)
  const [leaving, setLeaving] = useState(false)

  const reduceMotion = () =>
    window.matchMedia('(prefers-reduced-motion: reduce)').matches

  const close = () => {
    if (reduceMotion()) onClose()
    else setLeaving(true)
  }

  // Focus moves into the sheet on open and returns to the triggering citation
  // on close.
  useEffect(() => {
    const previous = document.activeElement
    sheetRef.current?.focus()
    return () => {
      if (previous instanceof HTMLElement) previous.focus()
    }
  }, [])

  useEffect(() => {
    const onKeyDown = (event) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        if (reduceMotion()) onClose()
        else setLeaving(true)
        return
      }
      if (event.key !== 'Tab' || !sheetRef.current) return
      const items = Array.from(sheetRef.current.querySelectorAll(FOCUSABLE)).filter(
        (element) => !element.disabled,
      )
      if (items.length === 0) {
        event.preventDefault()
        return
      }
      const first = items[0]
      const last = items[items.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  return (
    <>
      <div className="backdrop" onClick={close} aria-hidden="true" />
      <aside
        ref={sheetRef}
        className={`sheet${leaving ? ' leaving' : ''}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="evidence-title"
        tabIndex={-1}
        onAnimationEnd={() => {
          if (leaving) onClose()
        }}
      >
        <div className="sheet-head">
          <h2 className="sheet-title" id="evidence-title">
            Evidence
          </h2>
          <button type="button" className="btn" onClick={close}>
            Close
          </button>
        </div>

        {evidence.quote ? (
          <blockquote className="quote">{evidence.quote}</blockquote>
        ) : (
          <p className="sheet-note">
            This trail entry points at a source record. The repository at the pinned
            snapshot holds the full text.
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

        {evidence.quote ? (
          <p className="sheet-note">
            Quotes are stored exactly as they appear in the source. Citation validation
            rejects anything that does not match verbatim.
          </p>
        ) : null}
      </aside>
    </>
  )
}
