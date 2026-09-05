// Thin fetch wrapper around the real backend (see backend/server.py).
// In dev, Vite proxies /api -> http://localhost:8000 (see vite.config.js).

async function request(path, options = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })

  let body = null
  try {
    body = await res.json()
  } catch (e) {
    // no body
  }

  if (!res.ok) {
    const message = (body && body.detail) || `Request failed (${res.status})`
    throw new Error(message)
  }

  return body
}

export const api = {
  health: () => request('/api/health'),

  moderatorActions: () => request('/api/moderator-actions'),

  createDebate: (topic, maxTurns) =>
    request('/api/debates', {
      method: 'POST',
      body: JSON.stringify({ topic, max_turns: maxTurns ?? null }),
    }),

  listDebates: () => request('/api/debates'),

  getDebate: (id) => request(`/api/debates/${id}`),

  getDebateFull: (id) => request(`/api/debates/${id}/full`),

  resumeDebate: (id) => request(`/api/debates/${id}/resume`, { method: 'POST' }),

  sendModerator: (id, payload) =>
    request(`/api/debates/${id}/moderator`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
}
