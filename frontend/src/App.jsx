import { useCallback, useEffect, useState } from 'react'
import { ThemeProvider } from './context/ThemeContext.jsx'
import Header from './components/Header.jsx'
import Sidebar from './components/Sidebar.jsx'
import DebateContainer from './components/DebateContainer.jsx'
import { api } from './api/client.js'
import './App.css'

function AppContent() {
  const [debates, setDebates] = useState([])
  const [debatesLoading, setDebatesLoading] = useState(true)

  const [activeState, setActiveState] = useState(null)
  const [loadingActive, setLoadingActive] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const [sidebarOpen, setSidebarOpen] = useState(false)

  const refreshDebates = useCallback(async () => {
    try {
      const list = await api.listDebates()
      setDebates(Array.isArray(list) ? list : [])
    } catch (e) {
      // Non-fatal: history sidebar just stays empty
      console.error('Failed to load debate history', e)
    } finally {
      setDebatesLoading(false)
    }
  }, [])

  useEffect(() => {
    refreshDebates()
  }, [refreshDebates])

  const handleNewDebate = () => {
    setActiveState(null)
    setError('')
    setSidebarOpen(false)
  }

  const handleStart = async (topic) => {
    setSubmitting(true)
    setError('')
    try {
      const state = await api.createDebate(topic)
      setActiveState(state)
      refreshDebates()
    } catch (e) {
      setError(e.message)
    } finally {
      setSubmitting(false)
    }
  }

  const handleSelect = async (id) => {
    setSidebarOpen(false)
    setError('')
    setLoadingActive(true)
    setActiveState(null)
    try {
      // Try to resume as a live, moderatable debate first.
      const state = await api.resumeDebate(id)
      setActiveState(state)
    } catch (e) {
      // Already finished (or otherwise not resumable) -> load read-only view.
      try {
        const raw = await api.getDebateFull(id)
        setActiveState(raw)
      } catch (e2) {
        setError(e2.message)
      }
    } finally {
      setLoadingActive(false)
    }
  }

  const handleModerate = async (payload) => {
    if (!activeState?.debate_id) return
    setBusy(true)
    setError('')
    try {
      const result = await api.sendModerator(activeState.debate_id, payload)
      setActiveState(result)
      if (result.final_summary || result.exit_requested) {
        refreshDebates()
      }
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="ar-app">
      <Header onMenuClick={() => setSidebarOpen((o) => !o)} />
      <div className="ar-body">
        <Sidebar
          debates={debates}
          loading={debatesLoading}
          activeId={activeState?.debate_id}
          onSelect={handleSelect}
          onNewDebate={handleNewDebate}
          isOpen={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
        />
        <DebateContainer
          activeState={activeState}
          loadingActive={loadingActive}
          submitting={submitting}
          busy={busy}
          error={error}
          onStart={handleStart}
          onModerate={handleModerate}
        />
      </div>
    </div>
  )
}

export default function App() {
  return (
    <ThemeProvider>
      <AppContent />
    </ThemeProvider>
  )
}
