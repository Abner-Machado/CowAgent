import React, { useEffect, useMemo, useRef, useState } from 'react'
import { ChevronDown, Check } from 'lucide-react'
import { t } from '../i18n'
import type { AgentProfile } from '../types'
import AgentAvatar from './AgentAvatar'

/**
 * The Agent binding for one channel instance, as a single multi-select
 * dropdown — mirroring the web console's channel team picker. The first picked
 * Agent is the owner (it receives inbound messages and may delegate); the rest
 * are teammates it can hand off to via @mention.
 *
 * Selection is an ordered list: `value[0]` is the owner. Picking a new Agent
 * appends it; removing the owner promotes the next one. An empty selection
 * means "follow the default Agent", shown muted in the trigger.
 *
 * The whole control is only meaningful in multi-Agent mode; the Channels page
 * decides whether to render it, so here we simply assume a real roster.
 */

interface ChannelTeamSelectProps {
  agents: AgentProfile[]
  defaultAgentId: string
  // Owner first, then members. Persisted by the parent via onChange.
  value: string[]
  onChange: (next: string[]) => void
  disabled?: boolean
}

const MAX_FACES = 3

const ChannelTeamSelect: React.FC<ChannelTeamSelectProps> = ({
  agents,
  defaultAgentId,
  value,
  onChange,
  disabled,
}) => {
  const [open, setOpen] = useState(false)
  // Flip the menu upward when the trigger is too close to the window bottom.
  const [dropUp, setDropUp] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [open])

  // max-h-64 = 16rem = 256px, plus a small gap.
  const MENU_MAX = 264
  const openMenu = () => {
    if (disabled) return
    if (!open && ref.current) {
      const rect = ref.current.getBoundingClientRect()
      const below = window.innerHeight - rect.bottom
      setDropUp(below < MENU_MAX && rect.top > below)
    }
    setOpen((v) => !v)
  }

  // Only enabled Agents are pickable; drop any stale ids the roster no longer
  // has so a deleted teammate doesn't linger in the trigger.
  const enabled = useMemo(() => agents.filter((a) => a.enabled), [agents])
  const byId = useMemo(() => new Map(enabled.map((a) => [a.id, a])), [enabled])
  const picked = useMemo(() => value.filter((id) => byId.has(id)), [value, byId])
  const defaultAgent = agents.find((a) => a.id === defaultAgentId) || null

  const toggle = (id: string) => {
    if (picked.includes(id)) {
      onChange(picked.filter((x) => x !== id))
    } else {
      onChange([...picked, id])
    }
  }

  // Trigger content: up to MAX_FACES overlapping avatars + a "+N" pill, then the
  // owner's name. When nothing is picked, show the default Agent muted.
  const faces = picked.slice(0, MAX_FACES)
  const extra = picked.length - faces.length
  const ownerName = picked.length ? byId.get(picked[0])?.name || picked[0] : defaultAgent?.name || ''

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        disabled={disabled}
        onClick={openMenu}
        className={`w-full flex items-center gap-2 h-9 px-3 rounded-btn border bg-inset text-sm transition-colors ${
          disabled
            ? 'border-default text-content-tertiary cursor-not-allowed opacity-70'
            : open
              ? 'border-accent ring-2 ring-accent/15 cursor-pointer'
              : 'border-strong hover:border-content-tertiary cursor-pointer'
        }`}
      >
        {picked.length > 0 ? (
          <span className="flex items-center flex-shrink-0" style={{ paddingLeft: 2 }}>
            {faces.map((id, i) => (
              <span key={id} style={{ marginLeft: i === 0 ? 0 : -6, zIndex: MAX_FACES - i }} className="ring-2 ring-surface rounded-full inline-flex">
                <AgentAvatar agent={byId.get(id)} size={20} />
              </span>
            ))}
            {extra > 0 && (
              <span className="ml-1 inline-flex items-center h-[18px] px-1.5 rounded-full bg-inset-2 text-content-tertiary text-[10px] font-semibold">
                +{extra}
              </span>
            )}
          </span>
        ) : (
          defaultAgent && <AgentAvatar agent={defaultAgent} size={20} className="opacity-60" />
        )}
        <span className={`truncate flex-1 text-left ${picked.length ? 'text-content' : 'text-content-tertiary'}`}>
          {ownerName || t('channel_team_none')}
        </span>
        <ChevronDown size={14} className={`flex-shrink-0 text-content-tertiary transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div
          className={`absolute left-0 right-0 z-50 max-h-64 overflow-y-auto rounded-btn border border-default bg-elevated shadow-lg p-1 ${
            dropUp ? 'bottom-[calc(100%+4px)]' : 'top-[calc(100%+4px)]'
          }`}
        >
          {enabled.length === 0 ? (
            <div className="px-3 py-2 text-sm text-content-tertiary text-center">{t('channel_team_no_candidates')}</div>
          ) : (
            enabled.map((a) => {
              const on = picked.includes(a.id)
              const isOwner = picked[0] === a.id
              return (
                <button
                  key={a.id}
                  type="button"
                  onClick={() => toggle(a.id)}
                  className={`w-full flex items-center gap-2.5 px-2.5 py-1.5 rounded-md text-[13px] cursor-pointer transition-colors ${
                    on ? 'text-content font-medium' : 'text-content-secondary hover:bg-inset'
                  }`}
                >
                  <AgentAvatar agent={a} size={20} />
                  <span className="truncate flex-1 text-left">{a.name || a.id}</span>
                  {isOwner && (
                    <span className="px-1.5 py-0.5 rounded-full text-[10px] bg-amber-500/10 text-amber-600 flex-shrink-0">
                      {t('channel_team_default')}
                    </span>
                  )}
                  {on && <Check size={14} className="flex-shrink-0 text-accent" />}
                </button>
              )
            })
          )}
        </div>
      )}
    </div>
  )
}

export default ChannelTeamSelect
