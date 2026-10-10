import { useEffect, useRef, useState } from "react";
import "./chat.css";

// Where the API lives. Defaults to the local dev server; override with
// VITE_API_URL in .env so the same build works in dev and elsewhere.
const API = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";

const EXAMPLES = [
  { label: "Climbing history", question: "How did the first ascent of K2 unfold?" },
  { label: "Routes & terrain", question: "What makes the north face of Annapurna difficult to climb?" },
  { label: "Compare the peaks", question: "How hard is K2 compared to Everest?" },
];

export default function Chat() {
  // The fourteen peaks, the surface's domain artifact: a summit register.
  const [peaks, setPeaks] = useState(null); // null = loading, [] = unavailable
  const [peaksFailed, setPeaksFailed] = useState(false);

  const [question, setQuestion] = useState("");
  const [submittedQuestion, setSubmittedQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [sources, setSources] = useState([]);
  const [status, setStatus] = useState("idle"); // idle | loading | error | success
  const [error, setError] = useState("");

  const inputRef = useRef(null);
  const abortRef = useRef(null);

  // Load the peak list once. If it fails the app still works: the register is
  // supporting matter, not the point of the screen.
  useEffect(() => {
    let cancelled = false;
    fetch(`${API}/peaks`)
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(res.status))))
      .then((data) => {
        if (!cancelled) setPeaks(data);
      })
      .catch(() => {
        if (!cancelled) {
          setPeaks([]);
          setPeaksFailed(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Cancel any in-flight request when the component goes away.
  useEffect(() => () => abortRef.current?.abort(), []);

  async function ask(event) {
    event?.preventDefault();
    const q = question.trim();
    if (!q) return;

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setStatus("loading");
    setSubmittedQuestion(q);
    setAnswer("");
    setSources([]);
    setError("");

    try {
      const res = await fetch(`${API}/ask-stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q }),
        signal: controller.signal,
      });
      if (!res.ok || !res.body) throw new Error(`Server responded ${res.status}`);

      // Read the response as a stream of newline-delimited JSON. Each complete
      // line is one message; the trailing partial line is kept for the next chunk.
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.trim()) continue;
          const message = JSON.parse(line);
          if (message.type === "sources") setSources(message.sources ?? []);
          else if (message.type === "token") setAnswer((prev) => prev + message.text);
          // A failure mid-stream arrives as an event now, not a dead connection.
          // Throwing hands it to the existing error state, message and all.
          else if (message.type === "error") throw new Error(message.message);
        }
      }
      setStatus("success");
    } catch (err) {
      if (err.name === "AbortError") return;
      setError(err.message || "Unexpected error.");
      setStatus("error");
    }
  }

  function selectQuestion(text) {
    setQuestion(text);
    inputRef.current?.focus();
  }

  return (
    <div className="app">
      {/* Screen-reader announcements live here, so the streaming text does not
          chatter at assistive tech token by token. */}
      <p className="sr-only" role="status" aria-live="polite">
        {status === "loading" && "Searching the sources."}
        {status === "error" && "The answer service could not be reached."}
        {status === "success" && "Answer ready."}
      </p>

      <aside className="rail" aria-label="Summit register">
        <a className="wordmark" href="#main"><span className="wordmark__symbol" aria-hidden="true">△</span> FIELD GUIDE <span>01</span></a>
        <div className="rail__heading">
        <p className="label">Summit register / 8,000 m +</p>
        <h2 className="rail__title">The Fourteen</h2>
        <p className="rail__note">
          Peaks above 8,000 m, tallest first. Pick one to start a question.
        </p>
        </div>

        {peaks === null && <p className="rail__status">Loading…</p>}
        {peaksFailed && <p className="rail__status">Peak list unavailable.</p>}

        {peaks && peaks.length > 0 && (
          <ol className="peaks">
            {peaks.map((peak, index) => (
              <li key={peak.name}>
                <button
                  type="button"
                  className="peak"
                  onClick={() => selectQuestion(`Who first climbed ${peak.name}?`)}
                >
                  <span className="peak__rank">{String(index + 1).padStart(2, "0")}</span>
                  <span className="peak__name">{peak.name}</span>
                  <span className="peak__height">
                    {peak.height_m.toLocaleString()}
                    <span className="peak__unit">m</span>
                  </span>
                </button>
              </li>
            ))}
          </ol>
        )}
        <div className="rail__foot"><span className="label">Two mountain ranges</span><p>Himalaya &amp; Karakoram</p><span>Fourteen summits. A world of stories.</span></div>
      </aside>

      <main className="main" id="main">
        <div className="edition"><span>THE EXPEDITION ARCHIVE</span><span>A DOCUMENT Q&amp;A PROJECT</span></div>
        <header className="masthead">
          <div className="masthead__copy">
          <p className="label">Above eight thousand metres</p>
          <h1 className="title">Eight-Thousanders<span className="title__period">.</span></h1>
          <p className="lede">
            Explore the world’s highest peaks, through the accounts that tell their story.
            Ask a question and read the source passages alongside the answer.
          </p>
          </div>
          {/* An illustrative mountain profile, not a geographic elevation model. */}
          <svg
            className="ridge"
            viewBox="0 0 800 180"
            aria-hidden="true"
          >
            <path className="ridge__back" d="M0 169 82 127 122 140 214 72 281 126 345 95 408 138 497 86 554 125 638 55 716 134 800 103V180H0Z" />
            <path className="ridge__front" d="M0 180 109 156 195 115 229 133 353 22 461 120 496 107 583 157 665 120 736 153 800 166V180Z" />
            <path className="ridge__snow" d="m353 22-49 61 34-14 15 20 13-29 26 13Z" />
            <path className="ridge__line" d="m353 22 16 74 92 24m-108-98-72 113-86-20m174-19 30 57 97-46m-143-85-8 115-116-4m116 4 29 43m-93-45-19 45m321-23 82-37 12 40" />
            <path className="ridge__contour" d="M0 174Q142 145 257 165T509 165 800 174M0 180Q165 158 290 174T575 176 800 180" />
          </svg>
          <div className="masthead__caption"><span>14 SUMMITS</span><span>HISTORY · ROUTES · EXPEDITIONS</span><span>8,000–8,849 M</span></div>
        </header>

        <form className="ask" onSubmit={ask}>
          <label className="label" htmlFor="question">
            Ask the archive
          </label>
          <div className="ask__row">
            <input
              id="question"
              ref={inputRef}
              className="ask__input"
              type="text"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="What would you like to know about the peaks?"
              autoComplete="off"
            />
            <button
              type="submit"
              className="ask__submit"
              disabled={!question.trim() || status === "loading"}
            >
              {status === "loading" ? "Searching…" : <>Ask <span aria-hidden="true">↗</span></>}
            </button>
          </div>
        </form>

        <section className="response">
          {status === "idle" && (
            <div className="idle">
              <div className="section-heading"><p className="label">A place to begin</p><span>Follow your curiosity</span></div>
              <ul className="examples">
                {EXAMPLES.map((example) => (
                  <li key={example.label}>
                    <button
                      type="button"
                      className="example"
                      onClick={() => selectQuestion(example.question)}
                    >
                      <span className="example__label">{example.label}</span>
                      <span className="example__question">{example.question}</span>
                      <span className="example__arrow" aria-hidden="true">↗</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {status === "loading" && (
            <p className="state state--loading">
              <span className="pulse" aria-hidden="true" />
              Reading the sources…
            </p>
          )}

          {status === "error" && (
            <div className="state state--error">
              <p className="state__title">Couldn’t reach the answer service.</p>
              <p className="state__detail">{error}</p>
              <button type="button" className="retry" onClick={ask}>
                Try again
              </button>
            </div>
          )}

          {(status === "success" || (status === "loading" && answer)) && (
            <article className="answer-block">
              <div className="section-heading"><p className="label">From the archive</p><span>{status === "loading" ? "Writing answer…" : "Response"}</span></div>
              <h2 className="answer__question">{submittedQuestion}</h2>
              <p className="answer">{answer}</p>

              {sources.length > 0 && (
                <details className="sources" open>
                  <summary className="sources__summary">
                    <span className="label">Source passages</span>
                    <span className="sources__count">{sources.length}</span>
                  </summary>
                  <ul className="sources__list">
                    {sources.map((source, index) => (
                      <li key={`${source.source}-${source.section}-${index}`}>
                        <span className="sources__index">{String(index + 1).padStart(2, "0")}</span>
                        <span className="sources__body">
                          <span className="sources__origin">
                            <strong>{source.source.replace(/\.(txt|md|pdf)$/i, "").replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase())}</strong>
                            <span>{source.section}</span>
                          </span>
                          {source.preview && (
                            <span className="sources__preview">{source.preview}…</span>
                          )}
                        </span>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </article>
          )}
        </section>

        <footer className="colophon">
          <span>Eight-Thousanders / A learning project</span><span>Read the sources. Explore further. ↗</span>
        </footer>
      </main>
    </div>
  );
}
