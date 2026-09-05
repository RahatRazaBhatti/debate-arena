import './Sidebar.css'

export default function Sidebar({
  debates,
  loading,
  activeId,
  onSelect,
  onNewDebate,
  isOpen,
  onClose,
}) {
  return (
    <>
      {isOpen && <div className="ar-sidebar-scrim" onClick={onClose} />}
      <aside className={`ar-sidebar ${isOpen ? 'open' : ''}`}>
        <button className="btn btn-primary ar-new-debate" onClick={onNewDebate}>
          <span>✎</span> New Debate
        </button>

        <div className="ar-sidebar-heading">Recent Debates</div>

        <div className="ar-sidebar-list">
          {loading && <div className="ar-sidebar-empty">Loading…</div>}

          {!loading && debates.length === 0 && (
            <div className="ar-sidebar-empty">
              No debates yet.
              <br />
              Start one to see it here. ✨
            </div>
          )}

          {!loading &&
            debates.map((d) => (
              <button
                key={d.id}
                className={`ar-sidebar-item ${d.id === activeId ? 'active' : ''}`}
                onClick={() => onSelect(d.id)}
              >
                <div className="ar-sidebar-item-top">
                  <span className="ar-sidebar-item-topic">{d.topic || 'Untitled debate'}</span>
                  {d.final_summary ? (
                    <span className="ar-pill done">done</span>
                  ) : (
                    <span className="ar-pill live">live</span>
                  )}
                </div>
                <div className="ar-sidebar-item-meta">
                  <span>Turn {d.turn_count ?? 0}</span>
                  {d.winner && <span className="ar-winner-tag">🏆 {d.winner}</span>}
                </div>
              </button>
            ))}
        </div>

        <div className="ar-sidebar-footer">
          <a href="https://github.com" target="_blank" rel="noreferrer">
            Documentation
          </a>
        </div>
      </aside>
    </>
  )
}
