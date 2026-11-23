import React, { useEffect, useLayoutEffect } from 'react'
import { AlertTriangle } from 'lucide-react'
import { useConfirmStore } from '../store/confirmStore'
import { useWorkspaceStore, type EditState } from '../store/workspaceStore'

/**
 * Plain text area editor for the preview panel.
 *
 * The text lives in the DOM rather than in React state so a keystroke doesn't
 * re-render the panel; only the dirty flag is mirrored into the store, and only
 * when it actually flips.
 */
const FileEditor: React.FC<{
  edit: EditState
  /** Owned by the panel so its Save button can read the current text. */
  textareaRef: React.RefObject<HTMLTextAreaElement>
}> = ({ edit, textareaRef: ref }) => {
  const setEditDirty = useWorkspaceStore((s) => s.setEditDirty)
  const stashEditText = useWorkspaceStore((s) => s.stashEditText)
  const saveEdit = useWorkspaceStore((s) => s.saveEdit)
  const cancelEdit = useWorkspaceStore((s) => s.cancelEdit)
  const pendingConfirm = useConfirmStore((s) => s.pending)

  // autoFocus covers the normal mount. This also hands focus back once a
  // dialog that took it (discard / overwrite) has closed, so typing resumes
  // without a click. Keyed on the dialog rather than running every render,
  // which would fight the user for focus on the header buttons.
  useLayoutEffect(() => {
    const el = ref.current
    if (!pendingConfirm && el && document.activeElement !== el) el.focus()
  }, [pendingConfirm])

  // Navigating off the chat route unmounts the panel; hand the work in progress
  // back to the store so returning restores it rather than losing it.
  useEffect(() => {
    const el = ref.current
    return () => {
      if (el) stashEditText(el.value)
    }
  }, [])

  const onChange = () => setEditDirty((ref.current?.value ?? '') !== edit.baseline)

  // A save in place moves the baseline. Re-derive from the text area rather
  // than trusting the store's `dirty: false`, in case the user kept typing
  // while the write was in flight.
  useEffect(() => {
    if (ref.current) setEditDirty(ref.current.value !== edit.baseline)
  }, [edit.baseline])

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
      // Save in place, the way an editor does. The Save button in the header
      // instead returns to the rendered preview.
      e.preventDefault()
      saveEdit(e.currentTarget.value, { keepEditing: true })
      return
    }
    if (e.key === 'Escape') {
      e.preventDefault()
      cancelEdit()
      return
    }
    if (e.key === 'Tab') {
      // Otherwise Tab moves focus out of the text area, which is never what
      // indenting a line of code is meant to do.
      e.preventDefault()
      const el = e.currentTarget
      const { selectionStart: start, selectionEnd: end } = el
      el.value = `${el.value.slice(0, start)}    ${el.value.slice(end)}`
      el.selectionStart = el.selectionEnd = start + 4
      onChange()
    }
  }

  return (
    <div className="h-full flex flex-col">
      {edit.error && (
        <div className="shrink-0 flex items-start gap-1.5 px-3 py-2 text-[12px] text-red-500 bg-red-500/10 border-b border-default">
          <AlertTriangle size={13} className="mt-0.5 shrink-0" />
          <span className="break-all">{edit.error}</span>
        </div>
      )}
      <textarea
        ref={ref}
        // Uncontrolled: React seeds the node and then leaves the text alone, so
        // typing never round-trips through a re-render.
        defaultValue={edit.loaded}
        autoFocus
        onChange={onChange}
        onKeyDown={onKeyDown}
        spellCheck={false}
        // whitespace-pre keeps long lines on one row so code doesn't reflow;
        // the text area scrolls horizontally instead.
        className="flex-1 min-h-0 w-full p-4 bg-transparent text-content font-mono text-[12.5px] leading-relaxed border-0 outline-none resize-none whitespace-pre overflow-auto"
        style={{ tabSize: 4 }}
      />
    </div>
  )
}

export default FileEditor
