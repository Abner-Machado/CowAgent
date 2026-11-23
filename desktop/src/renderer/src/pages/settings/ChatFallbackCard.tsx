import React, { useEffect, useMemo, useState } from 'react'
import { ChevronDown, ChevronUp, Loader2, Plus, ShieldAlert, Trash2 } from 'lucide-react'
import { t } from '../../i18n'
import type { ChatFallbackCapabilityState, ChatFallbackLink, ModelsData } from '../../types'
import { Field, Dropdown, TextInput, Toggle, Modal, Btn, type DropdownOption } from './primitives'
import { resolveModels, providerLabel } from './modelsHelpers'

// Backup chat models. Unlike the other capabilities this one is opt-in and
// rarely touched, so it does NOT get its own top-level card: it lives behind a
// small button on the main model card (see ChatFallbackButton) and is edited
// in a modal. It sits idle until the primary model fails a turn for good.
//
// The backups form an ordered chain rather than a single model: link 1 is
// tried first and, if it also fails, link 2 takes over, and so on. The chain
// is unbounded — however many links the user adds is how many backups a turn
// gets — so the modal renders one editable row per link with up/down/remove
// controls instead of a single provider + model picker.

export interface ChatFallbackSavePayload {
  enabled: boolean
  chain: ChatFallbackLink[]
}

export interface ChatFallbackButtonProps {
  state: ChatFallbackCapabilityState | undefined
  data: ModelsData | null
  busy?: boolean
  status?: string
  onSave: (payload: ChatFallbackSavePayload) => void
}

// The small entry point on the main model card header: a shield button that
// opens the modal, plus a subtle badge while the fallback is enabled so an
// active fallback is discoverable at a glance.
export const ChatFallbackButton: React.FC<ChatFallbackButtonProps> = ({ state, data, busy, status, onSave }) => {
  const [open, setOpen] = useState(false)

  // A single entry point that also reflects state: accent-colored + "on" label
  // when the fallback is enabled, muted + "configure" label when off.
  const on = !!state?.enabled
  return (
    <>
      <button
        type="button"
        title={t('models_chat_fallback_button_tip')}
        onClick={() => setOpen(true)}
        className={
          'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-btn text-xs cursor-pointer transition-colors ' +
          (on
            ? 'text-accent bg-accent-soft hover:bg-accent-soft/70'
            : 'text-content-tertiary hover:text-accent hover:bg-accent-soft/60')
        }
      >
        <ShieldAlert size={12} />
        {on ? t('models_chat_fallback_badge_on') : t('models_chat_fallback_button')}
      </button>
      <ChatFallbackModal
        open={open}
        state={state}
        data={data}
        busy={busy}
        status={status}
        onClose={() => setOpen(false)}
        onSave={onSave}
      />
    </>
  )
}

interface ChatFallbackModalProps extends ChatFallbackButtonProps {
  open: boolean
  onClose: () => void
}

// One editable chain link. Split out so each row keeps its own custom-model
// input state without the parent tracking a map of them.
interface LinkEditorProps {
  index: number
  link: ChatFallbackLink
  total: number
  data: ModelsData | null
  state: ChatFallbackCapabilityState | undefined
  onChange: (next: ChatFallbackLink) => void
  onMove: (delta: number) => void
  onRemove: () => void
}

const LinkEditor: React.FC<LinkEditorProps> = ({
  index, link, total, data, state, onChange, onMove, onRemove,
}) => {
  const isCustomProvider = link.provider.startsWith('custom:')
  const [showCustom, setShowCustom] = useState(false)

  const isConfigured = (id: string): boolean => {
    const p = data?.providers?.find((x) => x.id === id)
    if (!p) return true
    return p.configured || (p.is_custom && !!p.custom_name)
  }

  const providerOptions: DropdownOption[] = useMemo(() => {
    const opts = (state?.providers || [])
      .filter((id) => isConfigured(id) || id === link.provider)
      .map((id) => ({ value: id, label: providerLabel(data, id) }))
    return [{ value: '', label: t('models_select_provider') }, ...opts]
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state?.providers, data, link.provider])

  const modelOptions: DropdownOption[] = useMemo(() => {
    const list = resolveModels(data, link.provider, state?.provider_models).map((o) => ({
      value: o.value,
      label: o.value,
      hint: o.hint,
    }))
    if (link.model && !showCustom && !list.some((o) => o.value === link.model)) {
      list.unshift({ value: link.model, label: link.model, hint: undefined })
    }
    return list
  }, [data, state?.provider_models, link.provider, link.model, showCustom])

  const handleProvider = (id: string) => {
    setShowCustom(false)
    if (id.startsWith('custom:')) {
      onChange({ provider: id, model: '' })
      return
    }
    onChange({ provider: id, model: resolveModels(data, id, state?.provider_models)[0]?.value || '' })
  }

  return (
    <div className="rounded-lg border border-border p-2.5 space-y-2">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-content-tertiary">
          {`${t('models_chat_fallback_link')} ${index + 1}`}
        </span>
        <div className="flex items-center gap-0.5">
          <button
            type="button"
            title={t('models_chat_fallback_move_up')}
            onClick={() => onMove(-1)}
            disabled={index === 0}
            className="p-1 rounded text-content-tertiary hover:text-content-primary hover:bg-hover
                       cursor-pointer transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
          >
            <ChevronUp size={13} />
          </button>
          <button
            type="button"
            title={t('models_chat_fallback_move_down')}
            onClick={() => onMove(1)}
            disabled={index === total - 1}
            className="p-1 rounded text-content-tertiary hover:text-content-primary hover:bg-hover
                       cursor-pointer transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
          >
            <ChevronDown size={13} />
          </button>
          <button
            type="button"
            title={t('models_chat_fallback_remove')}
            onClick={onRemove}
            className="p-1 rounded text-content-tertiary hover:text-danger hover:bg-danger/10
                       cursor-pointer transition-colors"
          >
            <Trash2 size={13} />
          </button>
        </div>
      </div>

      <Dropdown
        value={link.provider}
        options={providerOptions}
        placeholder={t('models_select_provider')}
        onChange={handleProvider}
      />
      {!!link.provider && !isConfigured(link.provider) && (
        <p className="text-xs text-danger">{t('config_provider_unconfigured_hint')}</p>
      )}

      {isCustomProvider ? (
        <TextInput
          className="font-mono"
          value={link.model}
          onChange={(e) => onChange({ ...link, model: e.target.value })}
          placeholder={t('config_custom_model_hint')}
        />
      ) : (
        <Dropdown
          value={link.model}
          options={modelOptions}
          placeholder={t('models_select_model')}
          onChange={(m) => onChange({ ...link, model: m })}
          disabled={!link.provider}
        />
      )}
      {!!showCustom && !isCustomProvider && (
        <TextInput
          className="font-mono"
          value={link.model}
          onChange={(e) => onChange({ ...link, model: e.target.value })}
          placeholder={t('config_custom_model_hint')}
        />
      )}
    </div>
  )
}

const ChatFallbackModal: React.FC<ChatFallbackModalProps> = ({
  open,
  state,
  data,
  busy,
  status,
  onClose,
  onSave,
}) => {
  const [enabled, setEnabled] = useState(!!state?.enabled)
  const [chain, setChain] = useState<ChatFallbackLink[]>([])

  // Reset the form to the persisted state each time the modal is (re)opened so
  // a cancelled edit never leaks into the next open.
  useEffect(() => {
    if (!open) return
    setEnabled(!!state?.enabled)
    const persisted = (state?.chain || []).map((l) => ({
      provider: l.provider || '',
      model: l.model || '',
    }))
    // Older backends report a single backup model instead of a chain.
    if (persisted.length === 0 && (state?.current_provider || state?.current_model)) {
      persisted.push({ provider: state?.current_provider || '', model: state?.current_model || '' })
    }
    setChain(persisted)
  }, [open, state])

  const updateLink = (i: number, next: ChatFallbackLink) => {
    setChain((prev) => prev.map((l, idx) => (idx === i ? next : l)))
  }

  const addLink = () => {
    const firstProvider = (state?.providers || [])[0] || ''
    const firstModel = resolveModels(data, firstProvider, state?.provider_models)[0]?.value || ''
    setChain((prev) => [...prev, { provider: firstProvider, model: firstModel }])
  }

  const removeLink = (i: number) => {
    setChain((prev) => prev.filter((_, idx) => idx !== i))
  }

  const moveLink = (i: number, delta: number) => {
    const j = i + delta
    setChain((prev) => {
      if (j < 0 || j >= prev.length) return prev
      const next = prev.slice()
      const tmp = next[i]
      next[i] = next[j]
      next[j] = tmp
      return next
    })
  }

  // Enabling needs at least one complete link; the backend rejects an empty
  // chain for the same reason (a fallback with nothing to fall back to).
  const hasCompleteLink = chain.some((l) => !!l.provider && !!l.model)
  const incomplete = enabled && !hasCompleteLink

  return (
    <Modal
      open={open}
      title={t('models_cap_chat_fallback')}
      onClose={onClose}
      footer={
        <>
          <span className={`text-xs text-accent mr-auto transition-opacity ${status ? 'opacity-100' : 'opacity-0'}`}>
            {status}
          </span>
          <Btn variant="ghost" onClick={onClose}>
            {t('config_cancel')}
          </Btn>
          <Btn
            variant="primary"
            disabled={busy || incomplete}
            onClick={() => onSave({ enabled, chain })}
          >
            {busy ? <Loader2 size={14} className="animate-spin" /> : t('config_save')}
          </Btn>
        </>
      }
    >
      <p className="text-xs text-content-tertiary -mt-1">{t('models_cap_chat_fallback_sub')}</p>

      {/* Label on the left, switch flush to the right. */}
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm text-content-secondary">{t('models_chat_fallback_enable')}</span>
        <Toggle checked={enabled} onChange={setEnabled} />
      </div>

      {enabled && (
        <div className="space-y-2">
          <Field label={t('models_chat_fallback_chain_title')}>
            <p className="text-xs text-content-tertiary leading-relaxed">
              {t('models_chat_fallback_chain_desc')}
            </p>
          </Field>

          {chain.length === 0 ? (
            <p className="text-xs text-content-tertiary">{t('models_chat_fallback_chain_empty')}</p>
          ) : (
            <div className="space-y-2">
              {chain.map((link, i) => (
                <LinkEditor
                  key={`${i}-${link.provider}`}
                  index={i}
                  link={link}
                  total={chain.length}
                  data={data}
                  state={state}
                  onChange={(next) => updateLink(i, next)}
                  onMove={(delta) => moveLink(i, delta)}
                  onRemove={() => removeLink(i)}
                />
              ))}
            </div>
          )}

          <button
            type="button"
            onClick={addLink}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-btn text-xs
                       text-accent bg-accent-soft hover:bg-accent-soft/70 cursor-pointer transition-colors"
          >
            <Plus size={12} />
            {t('models_chat_fallback_chain_add')}
          </button>

          {incomplete && <p className="text-xs text-danger">{t('models_chat_fallback_incomplete')}</p>}
        </div>
      )}
    </Modal>
  )
}

export default ChatFallbackButton
