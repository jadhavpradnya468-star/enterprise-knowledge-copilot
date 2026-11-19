import { useCallback, useEffect, useRef, useState } from "react";
import { api, ChatResult, Doc, EvalReport, Run } from "./api";

type Message = { question: string; result?: ChatResult; error?: string };
const STATUS_LABEL: Record<string, string> = {
  completed: "Answered",
  insufficient_evidence: "Not enough evidence",
  failed: "Failed",
};

export default function App() {
  const [key, setKey] = useState(localStorage.getItem("ekc_api_key") ?? "");
  const [docs, setDocs] = useState<Doc[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [trace, setTrace] = useState<Run | null>(null);
  const [tab, setTab] = useState<"chat" | "eval">("chat");
  const [report, setReport] = useState<EvalReport | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    if (!key) return;
    try {
      setDocs(await api.listDocs(key));
      setNotice("");
    } catch (e) {
      setNotice((e as Error).message);
    }
  }, [key]);

  useEffect(() => {
    localStorage.setItem("ekc_api_key", key);
    refresh();
  }, [key, refresh]);

  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  async function onUpload(files: FileList | null) {
    if (!files?.length) return;
    setBusy(true);
    for (const f of Array.from(files)) {
      try {
        await api.upload(key, f);
      } catch (e) {
        setNotice(`${f.name}: ${(e as Error).message}`);
      }
    }
    if (fileInput.current) fileInput.current.value = "";
    await refresh();
    setBusy(false);
  }

  async function remove(id: string) {
    await api.deleteDoc(key, id).catch((e) => setNotice((e as Error).message));
    setSelected((s) => {
      const n = new Set(s);
      n.delete(id);
      return n;
    });
    refresh();
  }

  async function ask(e: React.FormEvent) {
    e.preventDefault();
    const q = question.trim();
    if (!q || busy) return;
    setQuestion("");
    setBusy(true);
    setMessages((m) => [...m, { question: q }]);
    try {
      const result = await api.chat(key, q, [...selected]);
      setMessages((m) => m.map((x, i) => (i === m.length - 1 ? { ...x, result } : x)));
    } catch (err) {
      setMessages((m) => m.map((x, i) => (i === m.length - 1 ? { ...x, error: (err as Error).message } : x)));
    }
    setBusy(false);
  }

  async function showTrace(runId: string) {
    setTrace(await api.run(key, runId).catch(() => null));
  }

  async function runEval() {
    setBusy(true);
    setNotice("");
    try {
      setReport(await api.runEval(key));
    } catch (e) {
      setNotice((e as Error).message);
    }
    setBusy(false);
  }

  useEffect(() => {
    if (tab === "eval" && key && !report) api.latestEval(key).then(setReport).catch(() => undefined);
  }, [tab, key, report]);

  return (
    <div className="shell">
      <aside className="side">
        <h1>Knowledge Copilot</h1>
        <label className="field">
          API key
          <input type="password" value={key} onChange={(e) => setKey(e.target.value)} placeholder="Paste your key" />
        </label>

        <div className="row">
          <h2>Documents</h2>
          <button onClick={() => fileInput.current?.click()} disabled={!key || busy}>Upload</button>
          <input ref={fileInput} type="file" multiple hidden accept=".pdf,.docx,.txt"
                 onChange={(e) => onUpload(e.target.files)} />
        </div>
        <p className="hint">
          {selected.size ? `Asking about ${selected.size} selected` : "Asking across all your documents"}
        </p>
        <ul className="docs">
          {docs.map((d) => (
            <li key={d.id} className={selected.has(d.id) ? "on" : ""}>
              <label>
                <input type="checkbox" checked={selected.has(d.id)} onChange={() => toggle(d.id)}
                       disabled={d.status !== "indexed"} />
                <span className="name">{d.filename}</span>
              </label>
              <span className="meta">
                {d.status === "indexed" ? `${d.num_chunks} passages` : d.status}
                <button className="link" onClick={() => remove(d.id)} aria-label={`Delete ${d.filename}`}>Delete</button>
              </span>
            </li>
          ))}
          {!docs.length && <li className="empty">Upload a PDF, DOCX or TXT file to get started.</li>}
        </ul>
        {notice && <p className="notice" role="alert">{notice}</p>}
      </aside>

      <main className="main">
        <nav className="tabs">
          <button className={tab === "chat" ? "active" : ""} onClick={() => setTab("chat")}>Ask</button>
          <button className={tab === "eval" ? "active" : ""} onClick={() => setTab("eval")}>Evaluation</button>
        </nav>

        {tab === "chat" ? (
          <>
            <div className="thread">
              {!messages.length && <p className="empty">Ask a question about your documents. Answers cite the passages they rely on.</p>}
              {messages.map((m, i) => (
                <section key={i} className="turn">
                  <p className="q">{m.question}</p>
                  {m.error && <p className="notice">{m.error}</p>}
                  {!m.result && !m.error && <p className="hint">Searching and checking sources…</p>}
                  {m.result && (
                    <div className={`a ${m.result.status}`}>
                      <p className="state">{STATUS_LABEL[m.result.status] ?? m.result.status}</p>
                      <p>{m.result.answer}</p>
                      {m.result.sources.length > 0 && (
                        <ul className="sources">
                          {m.result.sources.map((s) => (
                            <li key={s.chunk_id}>
                              <strong>{s.filename}</strong>{s.page ? `, page ${s.page}` : ""}
                              <span className="meta"> {s.chunk_id.split("_").slice(-2).join("_")}</span>
                            </li>
                          ))}
                        </ul>
                      )}
                      <p className="meta">
                        {(m.result.metrics.latency_ms / 1000).toFixed(2)} s · {m.result.metrics.input_tokens + m.result.metrics.output_tokens} tokens
                        {m.result.metrics.retries ? ` · ${m.result.metrics.retries} retry` : ""}
                        <button className="link" onClick={() => showTrace(m.result!.run_id)}>View run steps</button>
                      </p>
                    </div>
                  )}
                </section>
              ))}
            </div>
            <form className="composer" onSubmit={ask}>
              <input value={question} onChange={(e) => setQuestion(e.target.value)} disabled={!key || busy}
                     placeholder="Ask about your documents" aria-label="Question" />
              <button type="submit" disabled={!key || busy || !question.trim()}>Ask</button>
            </form>
          </>
        ) : (
          <div className="eval">
            <div className="row">
              <h2>Evaluation report</h2>
              <button onClick={runEval} disabled={!key || busy}>{busy ? "Running…" : "Run evaluation"}</button>
            </div>
            {!report && <p className="empty">No report yet. Run the evaluation to score the bundled dataset.</p>}
            {report && (
              <>
                {report.metadata.note && <p className="notice">{String(report.metadata.note)}</p>}
                <table>
                  <tbody>
                    {Object.entries(report.summary).map(([k, v]) => (
                      <tr key={k}><th>{k}</th><td>{v ?? "n/a"}</td></tr>
                    ))}
                  </tbody>
                </table>
                <p className="meta">
                  {Object.entries(report.metadata).filter(([k]) => k !== "note").map(([k, v]) => `${k}: ${v}`).join(" · ")}
                </p>
              </>
            )}
          </div>
        )}
      </main>

      {trace && (
        <div className="drawer" role="dialog" aria-label="Run steps">
          <div className="row"><h2>Run steps</h2><button onClick={() => setTrace(null)}>Close</button></div>
          <p className="meta">{trace.run_id}</p>
          <table>
            <thead><tr><th>Step</th><th>Status</th><th>ms</th><th>Detail</th></tr></thead>
            <tbody>
              {trace.trace.map((t, i) => (
                <tr key={i}>
                  <td>{t.node}</td><td>{t.status}</td><td>{t.latency_ms}</td>
                  <td className="meta">
                    {Array.isArray(t.chunk_ids) ? `${t.chunk_ids.length} chunks` : ""}
                    {t.supported !== undefined ? `supported: ${String(t.supported)}` : ""}
                    {t.insufficient ? "insufficient" : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
