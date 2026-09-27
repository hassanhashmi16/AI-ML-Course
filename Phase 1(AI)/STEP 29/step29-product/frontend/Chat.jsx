// Step 29 deliverable: the React side of a React <-> FastAPI connection.
//
// Drop this into a Vite React app (e.g. src/Chat.jsx) and call <Chat />.
// It POSTs a question to the backend and STREAMS the answer back token by
// token, with explicit idle / loading / error / success states.
//
// The backend it talks to is in ../backend/main.py (runs on localhost:8000).

import { useState } from "react";

const BACKEND = "http://localhost:8000"; // or use Vite proxy: "/api" -> backend

export default function Chat() {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [status, setStatus] = useState("idle"); // idle | loading | error | success

  // Ask the backend and stream the answer.
  const ask = async () => {
    if (!question.trim()) return;

    setStatus("loading");
    setAnswer(""); // clear the previous answer before the new one streams in

    try {
      const res = await fetch(`${BACKEND}/ask-stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }), // the body EventSource can't send
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      // Read the response as a STREAM, not as one JSON blob.
      const reader = res.body.getReader();
      const decoder = new TextDecoder(); // bytes -> text

      while (true) {
        const { done, value } = await reader.read(); // grab the next chunk
        if (done) break;
        // Append each chunk; every setAnswer triggers a re-render, so the
        // answer appears to type itself out.
        setAnswer((prev) => prev + decoder.decode(value));
      }

      setStatus("success");
    } catch (err) {
      // network down, backend 500, timeout, etc.
      setStatus("error");
    }
  };

  return (
    <div>
      <input
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        placeholder="Ask something..."
      />
      <button onClick={ask} disabled={status === "loading"}>
        Ask
      </button>

      {/* The four UI states: loading, error, and the (success) answer. */}
      {status === "loading" && <p>Thinking…</p>}

      {status === "error" && (
        <p>
          Something went wrong. <button onClick={ask}>Retry</button>
        </p>
      )}

      {answer && <p>{answer}</p>}
    </div>
  );
}
