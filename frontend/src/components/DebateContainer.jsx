import StartDebate from './StartDebate.jsx'
import DebateView from './DebateView.jsx'
import './DebateContainer.css'

export default function DebateContainer({
  activeState,
  loadingActive,
  submitting,
  busy,
  error,
  onStart,
  onModerate,
}) {
  return (
    <main className="ar-main">
      {!activeState && !loadingActive ? (
        <StartDebate onStart={onStart} submitting={submitting} />
      ) : (
        <DebateView
          state={activeState}
          loading={loadingActive}
          busy={busy}
          error={error}
          onModerate={onModerate}
        />
      )}
    </main>
  )
}
