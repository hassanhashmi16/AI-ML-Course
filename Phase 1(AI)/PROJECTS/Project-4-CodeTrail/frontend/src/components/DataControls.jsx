import { useEffect, useRef, useState } from 'react'
import { deleteAccount } from '../api.js'

export default function DataControls({ retentionDays, onClose }) {
  const dialog = useRef(null)
  const [confirmation, setConfirmation] = useState('')
  const [pending, setPending] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => {
    const element = dialog.current
    const previous = document.activeElement
    element.showModal()
    return () => { element.close(); if (previous instanceof HTMLElement) previous.focus() }
  }, [])
  async function remove(event) {
    event.preventDefault()
    setPending(true); setError('')
    try { setResult(await deleteAccount(confirmation)) }
    catch (exc) { setError(exc.message); setPending(false) }
  }
  return <dialog className="ws-data-dialog" ref={dialog} aria-labelledby="data-title" onCancel={(event) => { event.preventDefault(); if (!pending) onClose(); else if (result) window.location.reload() }}>
    <p className="ws-kicker">Account & privacy</p><h2 id="data-title">Your data, your decision.</h2>
    {result ? <><p role="status">{result.cleanup_pending ? 'You are signed out and deletion is queued. Sign-in is blocked until the remaining files are removed.' : 'Your CodeTrail account and research data have been deleted.'}</p><a className="btn" href="/">Return to CodeTrail</a></> : <>
      <p>Your questions, reports, source cache, and investigation memory are stored in your account. The server operator can access this storage. Questions and public source excerpts are sent to the configured AI provider.</p>
      <p>{retentionDays ? `Accounts and research data are automatically deleted after ${retentionDays} days without a sign-in or a new investigation. Cleanup runs hourly, between investigations.` : 'Automatic expiry is disabled on this server. Your data stays until you delete your account or the operator removes it.'}</p>
      <p>Deleting your CodeTrail account removes its research data, cancels queued runs, and signs out all your sessions. Wait for any running investigation to finish first. Your GitHub account and repositories are unaffected.</p>
      <p className="muted">A hashed reservation remains to enforce the rolling 24-hour usage limit. Expired reservations are removed during scheduled cleanup. Existing operator backups and provider records follow their own retention policies; local deletion cannot erase those copies.</p>
      <form onSubmit={remove}><label htmlFor="delete-confirmation">Type DELETE to permanently delete your CodeTrail account</label><input id="delete-confirmation" autoComplete="off" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} disabled={pending} />{error && <p role="alert">{error}</p>}<div className="ws-data-actions"><button type="button" className="btn" onClick={onClose} disabled={pending}>Keep my account</button><button className="btn ws-delete-button" disabled={pending || confirmation !== 'DELETE'}>{pending ? 'Deleting…' : 'Delete my account'}</button></div></form>
    </>}
  </dialog>
}
