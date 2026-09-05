import { useEffect, useRef, useState } from 'react'
import './DebateChat.css'

const QUICK_ACTIONS = [
  { key: '2', label: 'Challenge Elena', icon: '💬' },
  { key: '3', label: 'Challenge Marcus', icon: '💬' },
  { key: '4', label: 'Request Evidence', icon: '📚' },
  { key: '5', label: 'Request Rebuttal', icon: '⚔️' },
  { key: '6', label: 'Ask Clarification', icon: '❓' },
  { key: '7', label: 'Expose Contradiction', icon: '⚠️' },
]

function speakerClass(name) {
  if (name === 'elena') return 'elena'
  if (name === 'marcus') return 'marcus'
  return 'moderator'
}

function speakerLabel(name) {
  if (name === 'elena') return 'Elena'
  if (name === 'marcus') return 'Marcus'
  return name || 'Moderator'
}

function normalizeEvidenceEntry(entry) {
  if (typeof entry === 'string') {
    return { title: entry, url: '', agent: '' }
  }

  const source = entry?.source || {}
  return {
    title: entry?.title || entry?.name || source.title || '',
    url: entry?.url || entry?.link || source.url || '',
    agent: entry?.agent || source.agent || '',
  }
}

export default function DebateChat({ state, busy, onModerate, error }) {
  const [freeText, setFreeText] = useState('')
  const endRef = useRef(null)

  const messages = state?.messages || []
  const finished = Boolean(state?.final_summary || state?.exit_requested)
  const evidence = (state?.evidence_log || [])
    .slice(-5)
    .map(normalizeEvidenceEntry)
    .filter((entry) => entry.title || entry.url)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages.length, busy])

  const submitFreeText = (e) => {
    e.preventDefault()
    if (!freeText.trim() || busy || finished) return
    onModerate({ text: freeText.trim() })
    setFreeText('')
  }

  return (
    <div className="ar-chat card">
      <div className="ar-chat-messages">
        {messages.map((m, i) => (
          <div key={i} className={`ar-msg ${speakerClass(m.name)}`}>
            <div className="ar-msg-avatar">{speakerLabel(m.name)[0]}</div>
            <div className="ar-msg-body">
              <div className="ar-msg-name">{speakerLabel(m.name)}</div>
              <div className="ar-msg-content">{m.content}</div>
            </div>
          </div>
        ))}

        {busy && (
          <div className="ar-msg thinking">
            <div className="ar-msg-avatar">…</div>
            <div className="ar-msg-body">
              <div className="ar-typing">
                <span /> <span /> <span />
                <em>agents are thinking…</em>
              </div>
            </div>
          </div>
        )}

        <div ref={endRef} />
      </div>

      {evidence.length > 0 && (
        <details className="ar-evidence">
          <summary>Sources used ({evidence.length} recent)</summary>
          <ul>
            {evidence.map((ev, i) => (
              <li key={i}>
                <span className={`ar-evidence-agent ${speakerClass(ev.agent)}`}>
                  {speakerLabel(ev.agent)}
                </span>{' '}
                {ev.title}
                {ev.url && (
                  <a href={ev.url} target="_blank" rel="noreferrer">
                    {' '}
                    ↗
                  </a>
                )}
              </li>
            ))}
          </ul>
        </details>
      )}

      {error && <div className="ar-chat-error">{error}</div>}

      {finished ? (
        <div className="ar-final-summary">
          <h4>Final Summary</h4>
          <p>{state.final_summary || 'Debate ended.'}</p>
        </div>
      ) : (
        <div className="ar-moderator-panel">
          <div className="ar-moderator-heading">Moderator</div>

          <div className="ar-moderator-actions">
            <button
              className="btn btn-primary ar-continue-btn"
              disabled={busy}
              onClick={() => onModerate({ choice: '1' })}
            >
              ▶ Continue
            </button>

            {QUICK_ACTIONS.map((a) => (
              <button
                key={a.key}
                className="btn btn-outline ar-quick-btn"
                disabled={busy}
                onClick={() => onModerate({ choice: a.key })}
              >
                <span>{a.icon}</span> {a.label}
              </button>
            ))}

            <button
              className="btn btn-outline ar-end-btn"
              disabled={busy}
              onClick={() => onModerate({ choice: '8' })}
            >
              ⏹ End Debate
            </button>
          </div>

          <form className="ar-moderator-freeform" onSubmit={submitFreeText}>
            <input
              className="input-field"
              placeholder="Or type a free-form challenge question…"
              value={freeText}
              onChange={(e) => setFreeText(e.target.value)}
              disabled={busy}
            />
            <button className="btn btn-primary" type="submit" disabled={busy || !freeText.trim()}>
              Send
            </button>
          </form>
        </div>
      )}
    </div>
  )
}
