import { useState } from 'react'
import DebateStats from './DebateStats.jsx'
import DebateChat from './DebateChat.jsx'
import './DebateView.css'

export default function DebateView({ state, busy, onModerate, error, loading }) {
  const [showStats, setShowStats] = useState(true)

  if (loading) {
    return (
      <div className="ar-view-loading">
        <div className="ar-spinner" />
        <p>Loading debate…</p>
      </div>
    )
  }

  if (!state) return null

  return (
    <div className="ar-debate-view">
      <div className="ar-view-header">
        <div>
          <h2>{state.topic}</h2>
          <span className="badge">{state.phase || 'Opening'}</span>
        </div>
        <button className="btn btn-ghost" onClick={() => setShowStats((s) => !s)}>
          {showStats ? 'Hide stats ▲' : 'Show stats ▼'}
        </button>
      </div>

      {showStats && <DebateStats state={state} />}

      <DebateChat state={state} busy={busy} onModerate={onModerate} error={error} />
    </div>
  )
}
