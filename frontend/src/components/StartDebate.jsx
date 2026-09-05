import { useState } from 'react'
import './StartDebate.css'

const SAMPLE_TOPICS = [
  'Should homework be banned in schools?',
  'Is AI more of a threat or opportunity for developers?',
  'Should social media platforms verify every user\u2019s identity?',
  'Is remote work better than in-office work?',
  'Should college education be free for everyone?',
]

export default function StartDebate({ onStart, submitting }) {
  const [topic, setTopic] = useState('')
  const [error, setError] = useState('')

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!topic.trim()) {
      setError('Give the agents something to argue about first.')
      return
    }
    setError('')
    onStart(topic.trim())
  }

  return (
    <div className="ar-start">
      <div className="ar-start-hero">
        <div className="ar-vs-badge">
          <div className="ar-vs-avatar elena">
            <span>E</span>
          </div>
          <div className="ar-vs-mark">VS</div>
          <div className="ar-vs-avatar marcus">
            <span>M</span>
          </div>
        </div>

        <h1>
          Pick a topic. <span className="gradient-text">Let them argue it out.</span>
        </h1>
        <p className="ar-start-lede">
          Elena and Marcus research, cite sources, catch each other in contradictions, and
          build a case &mdash; turn by turn, moderated by you.
        </p>
      </div>

      <form className="card ar-start-form" onSubmit={handleSubmit}>
        <label htmlFor="topic" className="ar-start-label">
          Debate topic
        </label>
        <input
          id="topic"
          className="input-field"
          placeholder="e.g. Should homework be banned in schools?"
          value={topic}
          onChange={(e) => {
            setTopic(e.target.value)
            if (error) setError('')
          }}
          disabled={submitting}
        />
        {error && <div className="ar-start-error">{error}</div>}

        <div className="ar-start-samples">
          {SAMPLE_TOPICS.map((t) => (
            <button
              type="button"
              key={t}
              className="ar-sample-chip"
              onClick={() => {
                setTopic(t)
                setError('')
              }}
              disabled={submitting}
            >
              {t}
            </button>
          ))}
        </div>

        <button type="submit" className="btn btn-primary ar-start-submit" disabled={submitting}>
          {submitting ? 'Opening the floor…' : 'Start the Debate'}
        </button>
      </form>

      <div className="ar-agent-cards">
        <div className="card ar-agent-card elena">
          <div className="ar-agent-avatar elena">E</div>
          <div>
            <h4>Elena</h4>
            <p>Evidence-first debater. Leans on retrieved data, statistics, and sources.</p>
          </div>
        </div>
        <div className="card ar-agent-card marcus">
          <div className="ar-agent-avatar marcus">M</div>
          <div>
            <h4>Marcus</h4>
            <p>Sharp rebuttal specialist. Hunts for the weakest point in the opposing case.</p>
          </div>
        </div>
      </div>
    </div>
  )
}
