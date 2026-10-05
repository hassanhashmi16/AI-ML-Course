import { useEffect, useRef, useState } from "react";
import "./chat.css";

// Where the API lives. Defaults to the local dev server; override with
// VITE_API_URL in .env so the same build works in dev and elsewhere.
const API = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";

const EXAMPLES = [
  "Which eight-thousander is the deadliest?",
  "Who first climbed Annapurna?",
  "How hard is K2 compared to Everest?",
];

export default function Chat() {
  // The fourteen peaks, the surface's domain artifact: a summit register.
  const [peaks, setPeaks] = useState(null); // null = loading, [] = unavailable
  const [peaksFailed, setPeaksFailed] = useState(false);

  const [question, setQuestion] = useState("");
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

  function useQuestion(text) {
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
        <p className="label">Summit register</p>
        <h2 className="rail__title">The Fourteen</h2>
        <p className="rail__note">
          Peaks above 8,000 m, tallest first. Pick one to start a question.
        </p>

        {peaks === null && <p className="rail__status">Loading…</p>}
        {peaksFailed && <p className="rail__status">Peak list unavailable.</p>}

        {peaks && peaks.length > 0 && (
          <ol className="peaks">
            {peaks.map((peak, index) => (
              <li key={peak.name}>
                <button
                  type="button"
                  className="peak"
                  onClick={() => useQuestion(`Who first climbed ${peak.name}?`)}
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
      </aside>

      <main className="main">
        <header className="masthead">
          {/* A ridge line, drawn not photographed: monochrome, one hairline. */}
          <svg
            className="ridge"
            viewBox="0 0 1200 90"
            preserveAspectRatio="none"
            aria-hidden="true"
          >
            <path
              d="M0 78 L96 44 L150 62 L228 22 L300 58 L372 34 L444 66 L520 14 L596 54 L666 38 L742 70 L820 30 L900 62 L980 42 L1064 74 L1140 50 L1200 68"
              fill="none"
              stroke="currentColor"
              strokeWidth="1"
              vectorEffect="non-scaling-stroke"
            />
          </svg>

          <p className="label">Expedition knowledge base</p>
          <h1 className="title">Eight-Thousanders</h1>
          <p className="lede">
            Ask about the 14 peaks above 8,000 m. Every answer is drawn from the
            source articles and cites the passage it came from.
          </p>
        </header>

        <form className="ask" onSubmit={ask}>
          <label className="label" htmlFor="question">
            Your question
          </label>
          <div className="ask__row">
            <input
              id="question"
              ref={inputRef}
              className="ask__input"
              type="text"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Who first climbed Annapurna?"
              autoComplete="off"
            />
            <button
              type="submit"
              className="ask__submit"
              disabled={!question.trim() || status === "loading"}
            >
              {status === "loading" ? "Searching" : "Ask"}
            </button>
          </div>
        </form>

        <section className="response">
          {status === "idle" && (
            <div className="idle">
              <p className="label">Try</p>
              <ul className="examples">
                {EXAMPLES.map((example) => (
                  <li key={example}>
                    <button
                      type="button"
                      className="example"
                      onClick={() => useQuestion(example)}
                    >
                      {example}
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

          {status === "success" && (
            <article className="answer-block">
              <p className="label">Answer</p>
              <p className="answer">{answer}</p>

              {sources.length > 0 && (
                <details className="sources" open>
                  <summary className="sources__summary">
                    <span className="label">Sources</span>
                    <span className="sources__count">{sources.length}</span>
                  </summary>
                  <ul className="sources__list">
                    {sources.map((source, index) => (
                      <li key={`${source.source}-${source.section}-${index}`}>
                        <span className="sources__index">{index + 1}</span>
                        <span className="sources__body">
                          <span className="sources__origin">
                            {source.source} · {source.section}
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
          Grounded in 15 source articles · hybrid retrieval (dense + keyword) ·
          cross-encoder rerank
        </footer>
      </main>
    </div>
  );
}
