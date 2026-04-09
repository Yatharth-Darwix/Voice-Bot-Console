import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { CallFormValues, EventKind, TimelineEvent } from '../types'

type StreamPayload = {
  token?: string
  phase?: string
  status?: string
  done?: boolean
  system_prompt?: string
  first_message?: string
  call_id?: string
  session_id?: string
  error?: string
}

interface LiveSessionMessage {
  at: string
  role: string
  text: string
  source: string
  event_type: string
}

interface SessionDetailPayload {
  status: string
  messages: LiveSessionMessage[]
  vapi_fetch_error?: string | null
}

interface PipelineState {
  running: boolean
  error: string | null
  systemPrompt: string
  firstMessage: string
  callId: string | null
  sessionId: string | null
  sessionStatus: string
  sessionFetchError: string | null
  liveMessages: LiveSessionMessage[]
  phase: string
  timeline: TimelineEvent[]
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''
const SESSION_POLL_INTERVAL_MS = 1000

function buildApiUrl(path: string): string {
  if (!API_BASE_URL) {
    return path
  }

  return `${API_BASE_URL.replace(/\/$/, '')}${path}`
}

const initialState: PipelineState = {
  running: false,
  error: null,
  systemPrompt: '',
  firstMessage: '',
  callId: null,
  sessionId: null,
  sessionStatus: 'idle',
  sessionFetchError: null,
  liveMessages: [],
  phase: 'idle',
  timeline: [],
}

export function useCallPipeline() {
  const [state, setState] = useState<PipelineState>(initialState)
  const abortRef = useRef<AbortController | null>(null)
  const nextEventIdRef = useRef(1)
  const seenSessionIdRef = useRef<string | null>(null)
  const seenPhasesRef = useRef<Set<string>>(new Set())

  const addEvent = useCallback((kind: EventKind, message: string) => {
    setState((prev) => ({
      ...prev,
      timeline: [
        ...prev.timeline,
        {
          id: nextEventIdRef.current++,
          at: new Date().toLocaleTimeString(),
          kind,
          message,
        },
      ],
    }))
  }, [])

  const ingestPayload = useCallback(
    (payload: StreamPayload) => {
      if (payload.error) {
        setState((prev) => ({
          ...prev,
          running: false,
          error: payload.error ?? 'Unknown error',
          phase: 'failed',
          sessionStatus: 'failed',
        }))
        addEvent('error', payload.error)
        return
      }

      if (payload.phase) {
        const readable = payload.status ? `${payload.phase}: ${payload.status}` : payload.phase
        setState((prev) => ({ ...prev, phase: readable }))
        if (!seenPhasesRef.current.has(readable)) {
          seenPhasesRef.current.add(readable)
          addEvent('info', `Pipeline ${readable}`)
        }
      }

      if (payload.session_id) {
        setState((prev) => ({ ...prev, sessionId: payload.session_id ?? null, sessionStatus: 'created' }))
        if (seenSessionIdRef.current !== payload.session_id) {
          seenSessionIdRef.current = payload.session_id
          addEvent('info', `Session created (${payload.session_id})`)
        }
      }

      if (payload.token) {
        setState((prev) => ({ ...prev, systemPrompt: `${prev.systemPrompt}${payload.token}` }))
      }

      if (payload.done) {
        setState((prev) => ({
          ...prev,
          phase: 'prompt_ready',
          systemPrompt: payload.system_prompt?.trim() || prev.systemPrompt,
          firstMessage: payload.first_message?.trim() || prev.firstMessage,
          sessionId: payload.session_id?.trim() || prev.sessionId,
          sessionStatus: prev.sessionStatus === 'created' ? 'prompt_ready' : prev.sessionStatus,
        }))
        addEvent('success', 'Prompt generation completed')
      }

      if (payload.call_id) {
        setState((prev) => ({
          ...prev,
          callId: payload.call_id ?? null,
          sessionId: payload.session_id ?? prev.sessionId,
          running: false,
          phase: 'dialing',
          sessionStatus: 'dialing',
        }))
        addEvent('success', `Vapi call created (${payload.call_id})`)
      }
    },
    [addEvent],
  )

  const cancel = useCallback(() => {
    if (!abortRef.current) {
      return
    }

    abortRef.current.abort()
    abortRef.current = null
    setState((prev) => ({ ...prev, running: false, phase: 'cancelled', sessionStatus: 'cancelled' }))
    addEvent('info', 'Request cancelled')
  }, [addEvent])

  const fetchSessionDetail = useCallback(async (sessionId: string) => {
    try {
      const response = await fetch(buildApiUrl(`/api/sessions/${sessionId}`))
      if (!response.ok) {
        return
      }

      const payload = (await response.json()) as SessionDetailPayload
      setState((prev) => ({
        ...prev,
        sessionStatus: payload.status || prev.sessionStatus,
        sessionFetchError: payload.vapi_fetch_error ?? null,
        liveMessages: payload.messages ?? prev.liveMessages,
      }))
    } catch {
      // Keep the phone flow running even if polling temporarily fails.
    }
  }, [])

  useEffect(() => {
    if (!state.sessionId) {
      return
    }
    if (['ended', 'failed', 'cancelled'].includes(state.sessionStatus)) {
      return
    }

    void fetchSessionDetail(state.sessionId)
    const timer = window.setInterval(() => {
      void fetchSessionDetail(state.sessionId as string)
    }, SESSION_POLL_INTERVAL_MS)

    return () => {
      window.clearInterval(timer)
    }
  }, [fetchSessionDetail, state.sessionId, state.sessionStatus])

  const start = useCallback(
    async (values: CallFormValues) => {
      if (abortRef.current) {
        abortRef.current.abort()
      }

      const controller = new AbortController()
      abortRef.current = controller
      nextEventIdRef.current = 1
      seenSessionIdRef.current = null
      seenPhasesRef.current = new Set()

      setState({
        running: true,
        error: null,
        systemPrompt: '',
        firstMessage: '',
        callId: null,
        sessionId: null,
        sessionStatus: 'idle',
        sessionFetchError: null,
        liveMessages: [],
        phase: 'connecting',
        timeline: [],
      })

      addEvent('info', 'Starting pipeline request')

      try {
        const response = await fetch(buildApiUrl('/api/initiate-call'), {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(values),
          signal: controller.signal,
        })

        if (!response.ok) {
          const detail = await response.text()
          throw new Error(`API ${response.status}: ${detail}`)
        }

        if (!response.body) {
          throw new Error('No response stream available')
        }

        const reader = response.body.getReader()
        const decoder = new TextDecoder('utf-8')
        let buffer = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) {
            break
          }

          buffer += decoder.decode(value, { stream: true })

          const events = buffer.split('\n\n')
          buffer = events.pop() ?? ''

          for (const eventChunk of events) {
            const lines = eventChunk
              .split('\n')
              .map((line) => line.trim())
              .filter((line) => line.startsWith('data:'))

            for (const line of lines) {
              const jsonPayload = line.slice(5).trim()
              if (!jsonPayload) {
                continue
              }

              try {
                const payload = JSON.parse(jsonPayload) as StreamPayload
                ingestPayload(payload)
              } catch {
                addEvent('error', `Malformed stream payload: ${jsonPayload.slice(0, 60)}`)
              }
            }
          }
        }

        setState((prev) => ({
          ...prev,
          running: false,
          phase: prev.callId ? prev.phase : 'completed',
        }))
      } catch (error) {
        if (error instanceof DOMException && error.name === 'AbortError') {
          return
        }

        const message = error instanceof Error ? error.message : 'Unknown request error'
        setState((prev) => ({ ...prev, running: false, error: message, phase: 'failed', sessionStatus: 'failed' }))
        addEvent('error', message)
      } finally {
        abortRef.current = null
      }
    },
    [addEvent, ingestPayload],
  )

  const canStart = useMemo(() => !state.running, [state.running])

  return {
    apiBaseUrl: API_BASE_URL || 'Vite proxy (/api)',
    ...state,
    canStart,
    start,
    cancel,
  }
}
