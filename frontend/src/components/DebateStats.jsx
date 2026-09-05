import './DebateStats.css'

function Meter({ label, elena, marcus, suffix = '' }) {
  const total = (elena || 0) + (marcus || 0)
  const elenaPct = total > 0 ? (elena / total) * 100 : 50

  return (
    <div className="ar-meter">
      <div className="ar-meter-label">
        <span>{label}</span>
        <span className="ar-meter-values">
          <b className="elena-text">{elena?.toFixed ? elena.toFixed(1) : elena}{suffix}</b>
          {' · '}
          <b className="marcus-text">{marcus?.toFixed ? marcus.toFixed(1) : marcus}{suffix}</b>
        </span>
      </div>
      <div className="ar-meter-track">
        <div className="ar-meter-fill" style={{ width: `${elenaPct}%` }} />
      </div>
    </div>
  )
}

// Verdict counts per agent, derived from claims_log (already present in
// the state payload, previously unused by the UI - see Core Problem #14:
// the frontend only showed aggregate numbers, not the "why" behind them).
function claimLedger(claimsLog) {
  const ledger = { elena: {}, marcus: {} }
  for (const c of claimsLog || []) {
    const agent = c.agent
    if (!ledger[agent]) continue
    const verdict = c.verdict || 'NOT_SUPPORTED'
    ledger[agent][verdict] = (ledger[agent][verdict] || 0) + 1
  }
  return ledger
}

const VERDICT_LABELS = {
  SUPPORTED: 'Supported',
  PARTIALLY_SUPPORTED: 'Partially supported',
  INSUFFICIENT_EVIDENCE: 'Insufficient evidence',
  NOT_SUPPORTED: 'Not supported',
  CONTRADICTED: 'Contradicted',
}

export default function DebateStats({ state }) {
  if (!state) return null

  const turn = state.turn_count ?? 0
  const max = state.max_turns ?? 0
  const progressPct = max > 0 ? Math.min(100, (turn / max) * 100) : 0

  const weighted = state.weighted_scores || { elena: 0, marcus: 0 }
  const grounding = state.grounding_scores || { elena: 0, marcus: 0 }
  const judge = state.scores || { elena: 0, marcus: 0 }
  const momentum = state.momentum_scores || { elena: 0, marcus: 0 }
  const unresolved = state.unresolved_contradictions || []
  const ledger = claimLedger(state.claims_log)
  const hasLedger = Object.keys(ledger.elena).length > 0 || Object.keys(ledger.marcus).length > 0

  return (
    <div className="card ar-stats">
      <div className="ar-stats-progress">
        <div className="ar-stats-progress-label">
          <span>
            Turn {turn} / {max || '—'}
          </span>
          <span className="badge">{state.phase || 'Opening'}</span>
        </div>
        <div className="ar-progress-track">
          <div className="ar-progress-fill" style={{ width: `${progressPct}%` }} />
        </div>
      </div>

      <Meter label="Composite score (decides winner)" elena={weighted.elena} marcus={weighted.marcus} />
      <Meter label="Evidence grounding" elena={grounding.elena} marcus={grounding.marcus} suffix="%" />
      <Meter label="AI judge (subjective)" elena={judge.elena} marcus={judge.marcus} />
      <Meter label="Activity / momentum" elena={momentum.elena} marcus={momentum.marcus} />

      {unresolved.length > 0 && (
        <div className="ar-contradiction-alert">
          ⚠ {unresolved.length} unresolved contradiction{unresolved.length > 1 ? 's' : ''} detected
          &mdash; try &ldquo;Expose Contradiction&rdquo; below.
        </div>
      )}

      {hasLedger && (
        <div className="ar-claim-ledger">
          <div className="ar-claim-ledger-title">Claim verdicts (fact-checked, not opinion)</div>
          {['elena', 'marcus'].map((agent) => (
            <div key={agent}>
              {Object.entries(ledger[agent]).map(([verdict, count]) => (
                <div className="ar-claim-ledger-row" key={`${agent}-${verdict}`}>
                  <span className={agent === 'elena' ? 'elena-text' : 'marcus-text'}>{agent}</span>
                  <span>{VERDICT_LABELS[verdict] || verdict}: {count}</span>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}

      {state.winner && (
        <div className="ar-winner-banner">
          🏆 Winner: <b>{state.winner === 'elena' ? 'Elena' : state.winner === 'marcus' ? 'Marcus' : state.winner}</b>
          {typeof state.winning_margin === 'number' && (
            <span> &nbsp;(margin {state.winning_margin.toFixed(1)})</span>
          )}
          {state.confidence && (
            <div>
              <span className={`ar-confidence-badge${state.confidence === 'TOO_CLOSE_TO_CALL' ? ' too-close' : ''}`}>
                {state.confidence === 'TOO_CLOSE_TO_CALL' ? 'Too close to call' : `${state.confidence.toLowerCase()} confidence`}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
