import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'

export type LiveEvent = { seq: number; kind: string; ts: number; actor?: string; target?: string; ok?: boolean; detail?: Record<string, unknown> }

/** Human phrasing for the things the server broadcasts. Anything unmapped simply isn't shown. */
export const SAY: Record<string, (e: LiveEvent) => string> = {
  'tool.ask': e => `${e.target} needs approval`,
  'approval.approved': e => `${e.target} approved`,
  'approval.denied': e => `${e.target} refused`,
  'draft.created': e => `Drafted for ${e.target}`,
  'draft.scored': e => `${e.target} graded ${e.detail?.hit ? '— matched' : '— missed'}`,
  'draft.escalated': e => `${e.target} escalated to a human`,
  'lesson.asked': e => `${e.target} asked for a rule`,
  'lesson.answered': e => `${e.target} learned a rule`,
  'playbook.stage': e => `${e.target} → ${e.detail?.to}`,
  'playbooks.mine': e => `Mined ${e.detail?.found ?? 0} jobs`,
  'agent.action': e => `${e.target} acted`,
  'agent.reworked': e => `${e.target} needed a human`,
  'run.done': () => `Run finished`,
  'run.error': () => `Run failed`,
  'cover.start': e => `Covering for ${e.target}`,
  'cover.end': e => `Cover ended for ${e.target}`,
  'backtest.run': () => `Backtest finished`,
  'pilot.report': () => `Report regenerated`,
}

const ALERT = new Set(['tool.ask', 'draft.escalated', 'agent.reworked', 'lesson.asked', 'run.error'])

/** One EventSource for the whole console. Refetches what changed and keeps a short activity tail. */
export function useLive(onAlert?: (text: string, kind: string) => void) {
  const qc = useQueryClient()
  const [connected, setConnected] = useState(false)
  const [feed, setFeed] = useState<LiveEvent[]>([])
  const timer = useRef<number | null>(null)
  const alert = useRef(onAlert)
  alert.current = onAlert

  useEffect(() => {
    const es = new EventSource('/api/v1/stream', { withCredentials: true })
    es.onopen = () => setConnected(true)
    es.onerror = () => setConnected(false)
    const handle = (raw: MessageEvent) => {
      let e: LiveEvent
      try { e = JSON.parse(raw.data) } catch { return }
      if (!e.kind || e.kind === 'hello') return
      setFeed(f => [e, ...f].slice(0, 40))
      if (ALERT.has(e.kind) && alert.current) alert.current(SAY[e.kind]?.(e) || e.kind, e.kind)
      // one coalesced refetch per burst — the server is the source of truth, the cache just follows
      if (timer.current) window.clearTimeout(timer.current)
      timer.current = window.setTimeout(() => qc.invalidateQueries(), 350)
    }
    Object.keys(SAY).forEach(k => es.addEventListener(k, handle as EventListener))
    es.onmessage = handle
    return () => { es.close(); if (timer.current) window.clearTimeout(timer.current) }
  }, [qc])

  return { connected, feed }
}
