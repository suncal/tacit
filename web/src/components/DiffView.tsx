import type { Preview } from '../lib/api'
import { Badge } from './ui'
import { SYSTEM_LABEL } from '../lib/format'

/** What will change if this runs — rendered like a PR, because that's what it is. */
export function ChangePreview({ preview, tool, args }: { preview?: Preview; tool: string; args?: Record<string, unknown> }) {
  const p = preview || {}
  const body = p.text || (args && ((args.body as string) || (args.text as string) || (args.content as string))) || ''
  return (
    <div className="rounded-lg border line overflow-hidden">
      <div className="flex items-center gap-2 px-3 py-2 surface-2 text-[12.5px]">
        <Badge tone="neutral">{SYSTEM_LABEL[p.system || ''] || p.system || tool.split('_')[0]}</Badge>
        <span className="font-medium">{p.summary || tool}</span>
        {p.irreversible ? <Badge tone="bad">irreversible</Badge> : <Badge tone="ok">reversible</Badge>}
        <span className="mono muted ml-auto">{tool}</span>
      </div>
      {p.diff ? (
        <div className="diff p-3 scroll-x"><pre>{p.diff.split('\n').map((l, i) => <div key={i} className={l.startsWith('+') && !l.startsWith('+++') ? 'add' : l.startsWith('-') && !l.startsWith('---') ? 'del' : l.startsWith('@@') ? 'hunk' : ''}>{l || ' '}</div>)}</pre></div>
      ) : body ? (
        <div className="p-3 text-[13.5px] whitespace-pre-wrap leading-relaxed">{body}</div>
      ) : args ? (
        <pre className="mono p-3 whitespace-pre-wrap muted">{JSON.stringify(args, null, 1)}</pre>
      ) : null}
    </div>
  )
}
