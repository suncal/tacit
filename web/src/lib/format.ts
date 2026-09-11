export const ago = (t?: number | null) => {
  if (!t) return '—'
  const d = Date.now() / 1000 - t
  if (d < 45) return 'just now'
  if (d < 3600) return `${Math.floor(d / 60)}m ago`
  if (d < 86400) return `${Math.floor(d / 3600)}h ago`
  if (d < 86400 * 14) return `${Math.floor(d / 86400)}d ago`
  return new Date(t * 1000).toLocaleDateString()
}
export const when = (t?: number | null) => (t ? new Date(t * 1000).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : '—')
export const pct = (x?: number | null, digits = 0) => (x === null || x === undefined ? '—' : `${(x * 100).toFixed(digits)}%`)
export const dur = (s: number) => (s < 60 ? `${Math.round(s)}s` : s < 3600 ? `${Math.round(s / 60)}m` : `${(s / 3600).toFixed(1)}h`)
export const STAGE_LABEL: Record<string, string> = { candidate: 'Candidate', shadow: 'Shadow', propose: 'Propose', auto: 'Auto', retired: 'Retired' }
export const STAGE_HELP: Record<string, string> = {
  candidate: 'Mined from history. Not watching yet.',
  shadow: 'Drafts silently and grades itself against what the owner really does.',
  propose: 'Drafts go to the Inbox; a human approves each one.',
  auto: 'Acts on its own. Every action is reversible and audited.',
  retired: 'Switched off.',
}
export const SYSTEM_LABEL: Record<string, string> = { slack: 'Slack', github: 'GitHub', linear: 'Linear', email: 'Email', webhook: 'Webhook', files: 'Files', memory: 'Memory', tasks: 'Tasks', notes: 'Notes', shell: 'Shell', automations: 'Automations' }
