import React, { useMemo } from 'react'
import type { AgentBadge } from '../types'
import { useAgentStore, selectMultiAgent } from '../store/agentStore'
import { useSessionSettingsStore, selectSharedConversation } from '../store/sessionSettingsStore'
import AgentAvatar from './AgentAvatar'

/**
 * Renders a plain-text message with `@name` turned into an Agent chip (avatar +
 * name), the way the web console does in group chats. Only active when the open
 * conversation is a group (more than one Agent); otherwise the text is shown
 * unchanged, so a solo chat and a single-Agent install look exactly as before.
 *
 * The roster is the conversation's own (owner + members). A leading `@teammate`
 * is how a turn is handed to another Agent, so making it read as a chip — not a
 * pasted id — is what makes the direction of a message obvious at a glance.
 */
const MENTION_BOUNDARY = /[\s，,：:、。.!?；;]/

const MentionText: React.FC<{ text: string; onAccent?: boolean }> = ({ text, onAccent }) => {
  const multiAgent = useAgentStore(selectMultiAgent)
  const agents = useAgentStore((s) => s.agents)
  const activeAgentId = useAgentStore((s) => s.activeAgentId)
  const shared = useSessionSettingsStore(selectSharedConversation)
  const team = useSessionSettingsStore((s) => s.cfg?.team)

  const roster = useMemo<AgentBadge[]>(() => {
    if (!multiAgent || !shared) return []
    const owner = agents.find((a) => a.id === activeAgentId)
    const list: AgentBadge[] = owner ? [{ id: owner.id, name: owner.name || owner.id, avatar: owner.avatar }] : []
    for (const m of team?.members || []) {
      if (!list.some((a) => a.id === m.id)) list.push(m)
    }
    return list
  }, [multiAgent, shared, agents, activeAgentId, team])

  const nodes = useMemo(() => {
    if (!roster.length || !text.includes('@')) return null
    // Longest label first so "@data analyst" wins over "@data".
    const byLabel = new Map<string, AgentBadge>()
    for (const a of roster) {
      for (const label of [a.name, a.id]) {
        if (label) byLabel.set(label.toLowerCase(), a)
      }
    }
    const labels = Array.from(byLabel.keys())
      .sort((a, b) => b.length - a.length)
      .map((l) => l.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
    const re = new RegExp(`@(${labels.join('|')})`, 'gi')

    const out: React.ReactNode[] = []
    let cursor = 0
    let m: RegExpExecArray | null
    let key = 0
    while ((m = re.exec(text))) {
      // Only treat it as a mention when it stands as a token (start/space
      // before, boundary/end after), so an email or `a@name` stays literal.
      const before = m.index === 0 ? '' : text[m.index - 1]
      const afterIdx = m.index + m[0].length
      const after = afterIdx >= text.length ? '' : text[afterIdx]
      const okBefore = before === '' || MENTION_BOUNDARY.test(before)
      const okAfter = after === '' || MENTION_BOUNDARY.test(after)
      const agent = byLabel.get(m[1].toLowerCase())
      if (!agent || !okBefore || !okAfter) continue
      if (m.index > cursor) out.push(text.slice(cursor, m.index))
      out.push(
        <span
          key={`m${key++}`}
          className={`inline-flex items-center gap-1 align-middle rounded-full pl-0.5 pr-1.5 py-px font-medium ${
            onAccent ? 'bg-white/25 text-inherit' : 'bg-accent-soft text-accent'
          }`}
        >
          <AgentAvatar agent={agent} size={16} />
          <span className="whitespace-nowrap">{agent.name || agent.id}</span>
        </span>
      )
      cursor = afterIdx
    }
    if (!out.length) return null
    if (cursor < text.length) out.push(text.slice(cursor))
    return out
  }, [roster, text, onAccent])

  if (!nodes) return <>{text}</>
  return <>{nodes}</>
}

export default MentionText
