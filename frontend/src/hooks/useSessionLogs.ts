import { useCallback, useEffect, useMemo, useState } from 'react'
import type { SessionDetail, SessionSummary } from '../types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

function buildApiUrl(path: string): string {
  if (!API_BASE_URL) {
    return path
  }
  return `${API_BASE_URL.replace(/\/$/, '')}${path}`
}

interface SessionLogsState {
  sessions: SessionSummary[]
  selectedSessionId: string | null
  selectedSession: SessionDetail | null
  loadingSessions: boolean
  loadingDetail: boolean
  error: string | null
}

const initialState: SessionLogsState = {
  sessions: [],
  selectedSessionId: null,
  selectedSession: null,
  loadingSessions: false,
  loadingDetail: false,
  error: null,
}

export function useSessionLogs() {
  const [state, setState] = useState<SessionLogsState>(initialState)

  const fetchSessions = useCallback(async () => {
    setState((prev) => ({ ...prev, loadingSessions: true, error: null }))
    try {
      const response = await fetch(buildApiUrl('/api/sessions'))
      if (!response.ok) {
        const detail = await response.text()
        throw new Error(`API ${response.status}: ${detail}`)
      }

      const payload = (await response.json()) as { sessions: SessionSummary[] }
      setState((prev) => {
        const selectedSessionId = prev.selectedSessionId ?? payload.sessions[0]?.session_id ?? null
        return {
          ...prev,
          sessions: payload.sessions,
          selectedSessionId,
          loadingSessions: false,
        }
      })
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to fetch sessions'
      setState((prev) => ({ ...prev, loadingSessions: false, error: message }))
    }
  }, [])

  const fetchSessionDetail = useCallback(async (sessionId: string) => {
    setState((prev) => ({ ...prev, loadingDetail: true, error: null }))
    try {
      const response = await fetch(buildApiUrl(`/api/sessions/${sessionId}`))
      if (!response.ok) {
        const detail = await response.text()
        throw new Error(`API ${response.status}: ${detail}`)
      }

      const payload = (await response.json()) as SessionDetail
      setState((prev) => ({
        ...prev,
        selectedSession: payload,
        selectedSessionId: sessionId,
        loadingDetail: false,
      }))
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to fetch session details'
      setState((prev) => ({ ...prev, loadingDetail: false, error: message }))
    }
  }, [])

  const refresh = useCallback(async () => {
    await fetchSessions()
  }, [fetchSessions])

  const selectSession = useCallback(
    async (sessionId: string) => {
      await fetchSessionDetail(sessionId)
    },
    [fetchSessionDetail],
  )

  useEffect(() => {
    void fetchSessions()
  }, [fetchSessions])

  useEffect(() => {
    if (!state.selectedSessionId) {
      return
    }
    void fetchSessionDetail(state.selectedSessionId)
  }, [fetchSessionDetail, state.selectedSessionId])

  useEffect(() => {
    const timer = window.setInterval(() => {
      void fetchSessions()
      if (state.selectedSessionId) {
        void fetchSessionDetail(state.selectedSessionId)
      }
    }, 10000)

    return () => {
      window.clearInterval(timer)
    }
  }, [fetchSessionDetail, fetchSessions, state.selectedSessionId])

  const activeSessions = useMemo(
    () => state.sessions.filter((session) => ['in_progress', 'dialing', 'ready_for_browser_talk'].includes(session.status)),
    [state.sessions],
  )

  return {
    apiBaseUrl: API_BASE_URL || 'Vite proxy (/api)',
    ...state,
    activeSessions,
    refresh,
    selectSession,
  }
}
