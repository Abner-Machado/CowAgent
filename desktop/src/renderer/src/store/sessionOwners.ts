/**
 * Which Agent owns which conversation.
 *
 * A conversation is stored in exactly one Agent's workspace: its history,
 * settings and title all live there, and every request about it must name that
 * Agent or the backend answers from the default Agent's (empty) copy. The
 * backend tells us the owner of every persisted session (`session.agent`), but
 * a brand-new chat exists only on this client until its first message, so the
 * owner is remembered here — in localStorage, so a restart mid-draft (or before
 * the roster has loaded) still knows who the open conversation belongs to.
 *
 * Kept free of store imports so both the agent store and the session store can
 * consult it without a cycle. Single-Agent installs never write to it: an
 * unknown owner means "the default Agent", exactly the legacy behavior.
 */

const OWNERS_KEY = 'cow_session_owners'
const ACTIVE_SESSION_KEY = 'cow_session_id'
// Bound so a long-lived install can't grow the map without limit; the backend
// list re-supplies owners for anything that got evicted.
const MAX_ENTRIES = 400

let cache: Record<string, string> | null = null

function load(): Record<string, string> {
  if (cache) return cache
  try {
    const raw = localStorage.getItem(OWNERS_KEY)
    const parsed = raw ? (JSON.parse(raw) as unknown) : null
    cache = parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? (parsed as Record<string, string>) : {}
  } catch {
    cache = {}
  }
  return cache
}

function persist(map: Record<string, string>) {
  cache = map
  try {
    localStorage.setItem(OWNERS_KEY, JSON.stringify(map))
  } catch {
    /* storage full or unavailable; the in-memory copy still works */
  }
}

/** The owner Agent id of a session, or '' when unknown (= default Agent). */
export function ownerOf(sessionId: string): string {
  if (!sessionId) return ''
  return load()[sessionId] || ''
}

/** Record (or change) a session's owner. An empty id forgets the entry. */
export function setOwner(sessionId: string, agentId: string) {
  if (!sessionId) return
  const map = { ...load() }
  if (agentId) map[sessionId] = agentId
  else delete map[sessionId]
  const keys = Object.keys(map)
  if (keys.length > MAX_ENTRIES) {
    // Insertion order ≈ age; drop the oldest.
    for (const k of keys.slice(0, keys.length - MAX_ENTRIES)) delete map[k]
  }
  persist(map)
}

/** Merge owners reported by the backend's session list. */
export function rememberOwners(entries: Array<{ session_id: string; agent?: { id: string } | null }>) {
  let changed = false
  const map = { ...load() }
  for (const e of entries) {
    const id = e.agent?.id || ''
    if (id && map[e.session_id] !== id) {
      map[e.session_id] = id
      changed = true
    }
  }
  if (changed) persist(map)
}

export function forgetOwner(sessionId: string) {
  setOwner(sessionId, '')
}

/**
 * Drop every session owned by a now-deleted Agent.
 *
 * The Agent's conversations were removed with its workspace, so any entry
 * still mapping to its id is a ghost that would keep re-pinning requests at a
 * gone Agent. Returns true if anything was pruned.
 */
export function forgetAgentOwners(agentId: string): boolean {
  if (!agentId) return false
  const map = { ...load() }
  let changed = false
  for (const sessionId of Object.keys(map)) {
    if (map[sessionId] === agentId) {
      delete map[sessionId]
      changed = true
    }
  }
  if (changed) persist(map)
  return changed
}

/** The session id the client will open on launch (same key the session store uses). */
export function readActiveSessionId(): string {
  try {
    return localStorage.getItem(ACTIVE_SESSION_KEY) || ''
  } catch {
    return ''
  }
}
