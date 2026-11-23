import apiClient from '../api/client'
import { useSessionStore } from '../store/sessionStore'
import { useChatStore } from '../store/chatStore'
import { useUIStore } from '../store/uiStore'
import { useAgentStore } from '../store/agentStore'
import { useSessionSettingsStore } from '../store/sessionSettingsStore'

/**
 * Start a fresh conversation. One code path for every "new chat" entry point
 * (session list, composer, app menu, Agent switch), so they all behave alike.
 *
 * `ownerId` picks the Agent the conversation belongs to (multi-Agent mode);
 * omitted, it's the active Agent. `inheritProject` keeps the new chat in the
 * current session's workspace, which is what a plain "+" should do — but a
 * chat opened for a *different* Agent starts on that Agent's own root, like the
 * web console, since the project record belongs to the previous owner.
 */
export function startNewChat(opts?: { ownerId?: string; inheritProject?: boolean }): string {
  const inheritProject = opts?.inheritProject ?? true
  const sessions = useSessionStore.getState()
  const inherited = inheritProject ? sessions.currentProject() : null
  const id = sessions.newSession(opts?.ownerId)
  const chat = useChatStore.getState()
  chat.ensureSession(id)
  void chat.loadHistory(id, 1)
  // Show the fresh chat in the list immediately (under the inherited space),
  // and expand the session list so the user sees the new session.
  useSessionStore.getState().addOptimistic(id, inherited)
  useUIStore.getState().setSessionsCollapsed(false)
  if (inherited) apiClient.selectProject(id, inherited.path).catch(() => {})
  return id
}

/**
 * Open a new conversation as a group: `ownerId` owns it and `guestIds` are
 * invited before the first message, so the very first turn already goes to a
 * team. Returns the new session id.
 */
export async function startTeamChat(ownerId: string, guestIds: string[]): Promise<string> {
  useAgentStore.getState().setActive(ownerId)
  const id = startNewChat({ ownerId, inheritProject: false })
  const guests = Array.from(new Set(guestIds.filter((g) => g && g !== ownerId)))
  if (guests.length) {
    await useSessionSettingsStore.getState().apply(id, { members: guests })
  }
  return id
}
