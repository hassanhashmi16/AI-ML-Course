import { useState } from 'react'
import '../landing.css'

function GitHubIcon() {
  return <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 .9a11.1 11.1 0 0 0-3.51 21.63c.55.1.76-.24.76-.54v-2.08c-3.1.67-3.75-1.32-3.75-1.32-.5-1.28-1.23-1.62-1.23-1.62-1.01-.69.08-.68.08-.68 1.12.08 1.71 1.15 1.71 1.15.99 1.7 2.6 1.21 3.24.93.1-.72.39-1.21.71-1.49-2.47-.28-5.07-1.24-5.07-5.5 0-1.21.43-2.2 1.14-2.98-.11-.28-.49-1.41.11-2.94 0 0 .93-.3 3.05 1.14a10.7 10.7 0 0 1 5.55 0c2.12-1.44 3.05-1.14 3.05-1.14.6 1.53.22 2.66.11 2.94.71.78 1.14 1.77 1.14 2.98 0 4.27-2.6 5.21-5.08 5.49.4.35.75 1.02.75 2.06v3.06c0 .3.2.65.76.54A11.1 11.1 0 0 0 12 .9Z" /></svg>
}

function SignIn({ checking, compact = false }) {
  const content = <><GitHubIcon /><span>{checking ? 'Checking session…' : compact ? 'Sign in' : 'Continue with GitHub'}</span><span className="lp-button-arrow" aria-hidden="true">↗</span></>
  const className = `lp-button ${compact ? 'lp-button-small' : ''}`
  return checking
    ? <button className={className} disabled aria-busy="true">{content}</button>
    : <a className={className} href="/auth/login">{content}</a>
}

const tabs = ['Finding', 'Trail', 'Evidence']

function ExampleReport() {
  const [active, setActive] = useState('Finding')
  const switchWithKeys = (event) => {
    const index = tabs.indexOf(active)
    let next
    if (event.key === 'ArrowRight') next = (index + 1) % tabs.length
    if (event.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length
    if (event.key === 'Home') next = 0
    if (event.key === 'End') next = tabs.length - 1
    if (next === undefined) return
    event.preventDefault()
    setActive(tabs[next])
    event.currentTarget.querySelectorAll('[role="tab"]')[next].focus()
  }

  return (
    <div className="lp-example-stage" id="example">
      <div className="lp-example-caption"><span className="lp-eyebrow">Inside an investigation</span><span className="lp-example-number">CT / 001</span></div>
      <article className="lp-report" aria-label="Example CodeTrail report">
        <div className="lp-report-top"><span><GitHubIcon /> pallets<span className="lp-repo-divider">/</span><strong>flask</strong></span><span className="lp-ref">2.2.0 <span aria-hidden="true">⌁</span></span></div>
        <div className="lp-report-heading"><p className="lp-eyebrow">The question</p><h2>Why did Flask replace<br /><code>LocalStack</code>?</h2></div>
        <div className="lp-tabs" role="tablist" aria-label="Explore the example report" onKeyDown={switchWithKeys}>
          {tabs.map((tab, index) => <button key={tab} id={`lp-tab-${tab}`} role="tab" aria-selected={active === tab} aria-controls="lp-example-panel" tabIndex={active === tab ? 0 : -1} onClick={() => setActive(tab)}><span aria-hidden="true">0{index + 1}</span>{tab}</button>)}
        </div>
        <div className="lp-report-body" id="lp-example-panel" role="tabpanel" aria-labelledby={`lp-tab-${active}`} tabIndex={0}>
          {active === 'Finding' && <>
            <span className="lp-status"><span /> Documented</span>
            <h3>Less stack. Less overhead.</h3>
            <p>Flask switched to direct ContextVar handling to avoid copying a stack on every context push and pop.</p>
            <div className="lp-source-note"><span className="lp-source-icon" aria-hidden="true">↳</span><div><span className="lp-eyebrow">Connected to the source</span><a href="https://github.com/pallets/flask/pull/4682" target="_blank" rel="noreferrer">Pull request #4682 <span aria-hidden="true">↗</span></a><p>Rationale recorded by the author.</p></div></div>
          </>}
          {active === 'Trail' && <>
            <span className="lp-eyebrow">From discussion to release</span>
            <ol className="lp-sample-trail">
              <li><span className="lp-trail-date">08 JUL 2022</span><h3>The change is merged</h3><p>PR #4682 replaces internal LocalStack usage with direct ContextVar handling.</p></li>
              <li><span className="lp-trail-date">02 AUG 2022</span><h3>The release carries it forward</h3><p>Flask 2.2.0 includes the refactor, with a deprecated compatibility shim.</p></li>
            </ol>
          </>}
          {active === 'Evidence' && <>
            <span className="lp-eyebrow">An excerpt you can inspect</span>
            <blockquote>“performance and memory overhead on every <code>push</code> and <code>pop</code>.”</blockquote>
            <a className="lp-evidence-link" href="https://github.com/pallets/flask/pull/4682" target="_blank" rel="noreferrer">Read the original discussion <span aria-hidden="true">↗</span></a>
            <div className="lp-evidence-limit"><span className="lp-eyebrow">What this does not establish</span><p>An exact throughput improvement. Removing overhead isn’t a measured benchmark result.</p></div>
          </>}
        </div>
        <div className="lp-report-bottom"><span className="lp-snapshot-dot" /> Pinned snapshot <code>b17bb9e</code><span className="lp-report-bottom-right">Evidence, attached.</span></div>
      </article>
      <p className="lp-preview-note">Illustrative report · based on the public Flask source history.</p>
    </div>
  )
}

export default function LandingPage({ checkingSession }) {
  return (
    <div className="lp-page">
      <a className="skip-link" href="#lp-main">Skip to content</a>
      <header className="lp-nav">
        <a href="#" className="lp-brand" aria-label="CodeTrail home"><span className="lp-brand-symbol" aria-hidden="true"><svg viewBox="0 0 32 32" fill="none"><path d="M10 8v16m0-8h7a6 6 0 0 0 6-6V8" stroke="currentColor" strokeWidth="1.5" /><circle cx="10" cy="7" r="3" /><circle cx="10" cy="25" r="3" /><circle cx="23" cy="7" r="3" /></svg></span>CodeTrail<span className="lp-brand-period">.</span></a>
        <nav aria-label="Main navigation"><a href="#how-it-works">How it works</a><a href="#example">Example report</a><SignIn checking={checkingSession} compact /></nav>
      </header>

      <main id="lp-main">
        <section className="lp-hero" aria-labelledby="lp-title">
          <div className="lp-hero-copy">
            <p className="lp-eyebrow lp-hero-eyebrow"><span /> Follow the decisions behind the code</p>
            <h1 id="lp-title">Every change<br />has a <em>backstory.</em></h1>
            <p className="lp-hero-description">Go beyond the diff. Follow code, commits, and conversations to understand why a public repository changed—with sources you can check.</p>
            <div className="lp-hero-actions"><SignIn checking={checkingSession} /><a className="lp-text-link" href="#example">Explore an example <span aria-hidden="true">↓</span></a></div>
            <p className="lp-signin-note">Your GitHub identity. Public repositories only.</p>
            <div className="lp-hero-footnote"><span className="lp-small-branch" aria-hidden="true">↳</span><p>For the moment when <code>git blame</code><br />tells you who, but you still need to know why.</p></div>
          </div>
          <ExampleReport />
        </section>

        <section className="lp-method" id="how-it-works" aria-labelledby="lp-method-title">
          <div className="lp-section-heading"><p className="lp-eyebrow">A trail, not a guess</p><h2 id="lp-method-title">From a question to the record.</h2><p>The explanation is only as useful as the evidence behind it.</p></div>
          <div className="lp-steps">
            <article><span className="lp-step-number">01 <span aria-hidden="true">↗</span></span><h3>Bring a repository.</h3><p>Paste a public GitHub link and ask about a design decision. Add a file or revision to narrow the search.</p><span className="lp-step-detail">A question with a starting point</span></article>
            <article><span className="lp-step-number">02 <span aria-hidden="true">↗</span></span><h3>Follow the connections.</h3><p>CodeTrail follows the code through commits, pull requests, and discussions to find the recorded reasoning.</p><span className="lp-step-detail">Code → history → context</span></article>
            <article><span className="lp-step-number">03 <span aria-hidden="true">↗</span></span><h3>Read. Inspect. Revisit.</h3><p>Get a cited explanation and timeline. Open the evidence, see the limits, and return to your saved report.</p><span className="lp-step-detail">An explanation you can examine</span></article>
          </div>
        </section>

        <section className="lp-principle" aria-labelledby="lp-principle-title"><div><p className="lp-eyebrow">Confidence has a paper trail</p><h2 id="lp-principle-title">Know what’s recorded.<br /><em>And what isn’t.</em></h2></div><div className="lp-label-list"><p><span className="lp-label lp-label-documented">Documented</span><span>The source states the reason.</span></p><p><span className="lp-label lp-label-inferred">Inferred</span><span>A conclusion drawn from the evidence.</span></p><p><span className="lp-label lp-label-unresolved">Unresolved</span><span>The inspected record doesn’t establish it.</span></p></div></section>

        <section className="lp-final-cta"><div><p className="lp-eyebrow">Your next rabbit hole, with a map</p><h2>Start with “why?”</h2><p>Your investigations and saved reports stay in your account.</p></div><SignIn checking={checkingSession} /></section>
      </main>

      <footer className="lp-footer"><span>CodeTrail <span aria-hidden="true">/</span> Trace the decisions.</span><div><a href="https://github.com/hassanhashmi16/codetrail" target="_blank" rel="noreferrer">View source <span aria-hidden="true">↗</span></a><details><summary>Privacy & access</summary><p>Sign-in does not request private-repository access. Your questions and public source excerpts are sent to the configured AI provider. Saved reports are private to your account; the server operator can access the underlying storage. Open your account menu → Your data to see this server’s expiry policy or delete your account. Shared usage limits apply.</p></details></div></footer>
    </div>
  )
}
