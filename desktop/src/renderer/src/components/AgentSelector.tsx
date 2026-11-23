import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Check, Plus, X } from 'lucide-react'
import { t } from '../i18n'
import ComposerChip from './ComposerChip'
import AgentAvatar from './AgentAvatar'
import { useAgentStore, enabledDefaultFirst } from '../store/agentStore'
import { useSessionSettingsStore, selectSharedConversation } from '../store/sessionSettingsStore'

interface AgentSelectorProps {
  sessionId: string
}

/**
 * The composer chip that shows who the conversation talks to, and lets the
 * user change that. Only rendered in multi-Agent mode (ChatInput gates it).
 *
 * Mirrors the web console's composer identity menu:
 *  - Switch the current Agent. A conversation is stored with its owner, so on
 *    an empty chat this simply re-owns it; once there are messages, switching
 *    starts a clean conversation owned by the chosen Agent (rewriting the owner
 *    of an existing history is not possible — the history lives in the first
 *    owner's store). The switch list is hidden once the chat is a group: the
 *    sensible actions there are adding and removing members.
 *  - Add teammates to the current conversation (a group chat). Members share
 *    the context and can be addressed with a leading @name; the owner keeps
 *    receiving everything else and may hand turns to them.
 *  - Create a new Agent, so the team feature is discoverable from the composer.
 */
const AgentSelector: React.FC<AgentSelectorProps> = ({ sessionId }) => {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const agents = useAgentStore((s) => s.agents)
  const activeAgentId = useAgentStore((s) => s.activeAgentId)
  const defaultAgentId = useAgentStore((s) => s.defaultAgentId)
  const shared = useSessionSettingsStore(selectSharedConversation)
  const team = useSessionSettingsStore((s) => (s.sessionId === sessionId ? s.cfg?.team : undefined))
  const addMember = useSessionSettingsStore((s) => s.addMember)
  const removeMember = useSessionSettingsStore((s) => s.removeMember)

  const roster = enabledDefaultFirst(agents, defaultAgentId)
  const active = agents.find((a) => a.id === activeAgentId) || roster[0] || null
  const members = (team?.members || []).filter((m) => m.id !== activeAgentId)
  const memberIds = new Set(members.map((m) => m.id))
  const invitable = roster.filter((a) => a.id !== activeAgentId && !memberIds.has(a.id))

  const tip = `${t('composer_agent_tip')}${active?.name ? ` · ${active.name}` : ''}${
    members.length ? ` +${members.length}` : ''
  }`

  return (
    <ComposerChip
      icon={
        <span className="relative inline-flex">
          <AgentAvatar agent={active} size={18} />
          {members.length > 0 && (
            <span className="absolute -right-1.5 -bottom-1 min-w-[13px] h-[13px] px-0.5 rounded-full bg-accent text-white text-[9px] font-semibold leading-[13px] text-center ring-2 ring-surface">
              {members.length + 1}
            </span>
          )}
        </span>
      }
      label={active?.name || t('agents_title')}
      tip={tip}
      open={open}
      onToggle={() => setOpen((v) => !v)}
      onClose={() => setOpen(false)}
      align="end"
      menuClassName="w-64"
      labelHidden
    >
      {/* A solo chat only shows who it is talking to right now — the current
          Agent, and just that one. Switching to a different Agent (which would
          silently start a fresh conversation) was more confusing than useful,
          so the roster is gone; the invite section below is how others join. */}
      {!shared && active && (
        <>
          <div className="px-2 py-1.5 text-[11px] font-medium text-content-tertiary uppercase tracking-wide">
            {t('composer_current_agent')}
          </div>
          <div className="w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-[13px] bg-accent-soft text-accent font-medium">
            <AgentAvatar agent={active} size={20} />
            <span className="flex-1 min-w-0 text-left truncate">{active.name || active.id}</span>
            <Check size={13} className="flex-shrink-0" />
          </div>
        </>
      )}

      {/* Everyone in the conversation, host first. The host is the main Agent
          (owner): it leads the row list, carries a "main Agent" badge and has
          no remove control — it can't be dropped from its own conversation. The
          teammates below it are removable (hover swaps the ✓ for a red ×). */}
      {shared && (
        <>
          <div className="px-2 py-1.5 text-[11px] font-medium text-content-tertiary uppercase tracking-wide">
            {t('team_members')}
          </div>
          {active && (
            <div className="w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-[13px] text-content-secondary">
              <AgentAvatar agent={active} size={20} />
              <span className="flex-1 min-w-0 text-left truncate">{active.name || active.id}</span>
              <span className="px-1.5 py-0.5 rounded-full text-[10px] bg-accent-soft text-accent flex-shrink-0">
                {t('composer_agent_owner')}
              </span>
            </div>
          )}
          {members.map((m) => (
            <button
              key={m.id}
              type="button"
              title={t('team_remove')}
              onClick={() => void removeMember(sessionId, m.id)}
              className="w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-[13px] text-content-secondary cursor-pointer transition-colors hover:bg-danger-soft hover:text-danger group"
            >
              <AgentAvatar agent={m} size={20} />
              <span className="flex-1 min-w-0 text-left truncate">{m.name || m.id}</span>
              <Check size={13} className="flex-shrink-0 text-content-tertiary group-hover:hidden" />
              <X size={13} className="flex-shrink-0 hidden group-hover:block" />
            </button>
          ))}
        </>
      )}

      {/* Agents that can still be pulled into the conversation. In a solo chat
          this section is what turns it into a group; in a group it lists the
          remaining invitable teammates. */}
      {invitable.length > 0 && (
        <>
          <div className="my-1 h-px bg-default" />
          <div className="px-2 py-1.5 text-[11px] font-medium text-content-tertiary uppercase tracking-wide">
            {t('team_invite')}
          </div>
          {invitable.map((a) => (
            <button
              key={a.id}
              type="button"
              onClick={() => void addMember(sessionId, a.id)}
              className="w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-[13px] text-content-secondary hover:bg-surface-2 cursor-pointer transition-colors"
            >
              <AgentAvatar agent={a} size={20} />
              <span className="flex-1 min-w-0 text-left truncate">{a.name || a.id}</span>
              <Plus size={13} className="flex-shrink-0 text-content-tertiary" />
            </button>
          ))}
        </>
      )}

      <div className="my-1 h-px bg-default" />
      <button
        type="button"
        onClick={() => {
          setOpen(false)
          navigate('/agents?create=1')
        }}
        className="w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-[13px] text-content-secondary hover:bg-surface-2 cursor-pointer transition-colors"
      >
        <span className="w-5 h-5 rounded-full border border-dashed border-strong text-content-tertiary flex items-center justify-center flex-shrink-0">
          <Plus size={11} />
        </span>
        <span className="flex-1 min-w-0 text-left truncate">{t('agents_create')}</span>
      </button>
    </ComposerChip>
  )
}

export default AgentSelector
