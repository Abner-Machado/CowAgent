/* Task-completion notifications and their permission prompts.
   Split out of console.js. These are classic scripts sharing one global
   scope; see channel/web/README.md before changing the load order. */

// =====================================================================
// Task completion notification (client-side preference)
// =====================================================================
const TASK_NOTIFY_KEY = 'cow_task_notify';
const TASK_NOTIFY_SOUND_KEY = 'cow_task_notify_sound';
let taskNotifyEnabled = localStorage.getItem(TASK_NOTIFY_KEY) !== '0';
let taskNotifySound = localStorage.getItem(TASK_NOTIFY_SOUND_KEY) !== '0';
let notifyAudioCtx = null;
let unreadCount = 0;
const baseDocTitle = document.title;

// Unlock audio on the first user gesture; browsers block autoplay otherwise.
document.addEventListener('pointerdown', function() {
    if (window.AudioContext) notifyAudioCtx = notifyAudioCtx || new AudioContext();
    if (notifyAudioCtx && notifyAudioCtx.state === 'suspended') {
        notifyAudioCtx.resume().catch(function() {});
    }
}, { once: true });

function playNotifyBeep() {
    if (!taskNotifySound) return;
    try {
        if (!notifyAudioCtx) {
            const Ctx = window.AudioContext || window.webkitAudioContext;
            if (!Ctx) return;
            notifyAudioCtx = new Ctx();
        }
        if (notifyAudioCtx.state === 'suspended') {
            notifyAudioCtx.resume().catch(function() {});
        }
        // Two short sine tones (A5 → D6); no audio asset needed.
        const t0 = notifyAudioCtx.currentTime;
        [880, 1174.66].forEach(function(freq, i) {
            const at = t0 + i * 0.09;
            const osc = notifyAudioCtx.createOscillator();
            const gain = notifyAudioCtx.createGain();
            osc.type = 'sine';
            osc.frequency.value = freq;
            gain.gain.setValueAtTime(0.001, at);
            gain.gain.exponentialRampToValueAtTime(0.12, at + 0.01);
            gain.gain.exponentialRampToValueAtTime(0.001, at + 0.09);
            osc.connect(gain).connect(notifyAudioCtx.destination);
            osc.start(at);
            osc.stop(at + 0.1);
        });
    } catch (_) {
        // Autoplay still blocked or AudioContext unavailable; stay silent.
    }
}

function firstLineSnippet(text) {
    return (text || '').split('\n')[0].trim().slice(0, 80);
}

function sessionTitleOf(sid) {
    const el = document.querySelector(`.session-item[data-session-id="${sid}"] .session-title`);
    return el ? el.textContent.trim() : '';
}

function popNotification(title, body, sid, agentId) {
    if (typeof Notification === 'undefined' || Notification.permission !== 'granted') return;
    try {
        const n = new Notification(title, { body: body || title });
        n.onclick = function() {
            window.focus();
            // The browser decides which tab a notification click activates, and
            // it may not be the one that popped it. So ask ALL tabs to open this
            // session (broadcastOpenSession) — whichever tab ends up foregrounded
            // is then already on the right conversation. Also covers the case
            // where this tab was on another view (e.g. scheduler config).
            if (sid) broadcastOpenSession(sid, agentId);
            n.close();
        };
    } catch (_) {
        // Notification API unavailable; beep + title badge still applied.
    }
}

function showTaskNotification(title, body, sid, agentId) {
    if (!taskNotifyEnabled) return;
    // Only notify when the window is not focused. If the user is actively
    // watching the tab, the reply is already on screen — a notification/beep
    // would just be noise (especially for short tasks).
    if (document.hasFocus()) return;
    playNotifyBeep();
    if (document.hidden) {
        unreadCount += 1;
        document.title = `(${unreadCount}) ${baseDocTitle}`;
    }
    if (typeof Notification === 'undefined') return;
    // First time we actually need to notify (window is in the background):
    // request permission now, then show this notification once granted. This
    // is more contextual than prompting on page load.
    if (Notification.permission === 'default') {
        Notification.requestPermission()
            .then(function(perm) {
                if (perm === 'granted') popNotification(title, body, sid, agentId);
                else refreshNotifyBlockedHint();
            })
            .catch(function() {});
        return;
    }
    if (Notification.permission === 'denied') {
        // Can't notify; surface the hint in settings so the user knows why.
        refreshNotifyBlockedHint();
        return;
    }
    popNotification(title, body, sid, agentId);
}

function notifyTaskFinished(sid, kind, text, agentId) {
    const label = t(kind === 'error' ? 'notify_task_error' : 'notify_task_done');
    const snippet = firstLineSnippet(text);
    showTaskNotification(sessionTitleOf(sid) || label, snippet ? `${label}: ${snippet}` : label, sid, agentId);
}

// The global runs poller is the single source of scheduler notifications (the
// /poll loop deliberately stays silent for scheduler pushes). A run can surface
// in overlapping poll windows AND — the important case — the SAME run is seen
// independently by EVERY open browser tab, each running its own poll loop. To
// pop exactly one notification per run across all tabs, the "already notified"
// set is persisted in localStorage (shared by all same-origin tabs) and the
// claiming tab broadcasts the id so peers drop it immediately (localStorage
// alone races when two ticks fire ~simultaneously in different tabs).
const _NOTIFIED_RUNS_KEY = 'cow_notified_run_ids';
const _NOTIFIED_RUNS_MAX = 500;
const _notifiedRunIds = new Set();   // in-memory mirror of the shared set

// Cross-tab channel: a tab that claims a run tells the others right away, and a
// notification click asks all tabs to open the target session (see
// broadcastOpenSession) — since the browser, not us, decides which tab a system
// notification click activates, every tab pre-navigates so whichever one comes
// to the foreground is already on the right conversation.
let _notifyBus = null;
try {
    if (typeof BroadcastChannel !== 'undefined') {
        _notifyBus = new BroadcastChannel('cow_scheduler_notify');
        _notifyBus.onmessage = (e) => {
            const data = e && e.data;
            if (!data) return;
            if (data.type === 'open-session' && data.sid) {
                // Another tab's notification was clicked. Open the session here
                // too so this tab is correct if the browser activates it. Guarded
                // to the chat view switch; no focus stealing (browser owns that).
                try { switchSession(data.sid, data.agentId || ''); } catch (_) {}
                return;
            }
            // Default (legacy) shape: a claimed run id.
            if (data.runId) _notifiedRunIds.add(data.runId);
        };
    }
} catch (_) { _notifyBus = null; }

// Tell every tab to open this session, then open it locally. Used on
// notification click so the tab the browser foregrounds is already correct.
function broadcastOpenSession(sid, agentId) {
    if (!sid) return;
    if (_notifyBus) {
        try { _notifyBus.postMessage({ type: 'open-session', sid, agentId: agentId || '' }); } catch (_) {}
    }
    try { switchSession(sid, agentId); } catch (_) {}
}

// Route a manual "run now" notification back to the tab the user clicked in.
// This tab records ownership in-memory (_manualRunOrigin); a shared localStorage
// marker (_MANUAL_ORIGIN_KEY) lets OTHER tabs know *some* tab owns it so they
// stay silent, without them mistakenly thinking they own it.
const _manualRunOrigin = {};          // task_id -> ts (this tab's own claims)
const _MANUAL_ORIGIN_KEY = 'cow_manual_run_origin';
const _MANUAL_ORIGIN_TTL = 120000;    // 2 min: long enough for the run to surface

function _claimManualRunOrigin(taskId) {
    const now = Date.now();
    _manualRunOrigin[taskId] = now;
    setTimeout(() => { delete _manualRunOrigin[taskId]; }, _MANUAL_ORIGIN_TTL);
    try {
        const raw = localStorage.getItem(_MANUAL_ORIGIN_KEY);
        const map = raw ? (JSON.parse(raw) || {}) : {};
        // Drop stale entries so the shared marker can't grow unbounded.
        for (const k of Object.keys(map)) {
            if (now - map[k] >= _MANUAL_ORIGIN_TTL) delete map[k];
        }
        map[taskId] = now;
        localStorage.setItem(_MANUAL_ORIGIN_KEY, JSON.stringify(map));
    } catch (_) {}
}

// True if any tab (this one or a peer, within the TTL) claimed a manual run for
// this task. Reads the shared marker written by _claimManualRunOrigin.
function _someTabOwnsManualRun(taskId) {
    if (_manualRunOrigin[taskId]) return true;
    try {
        const raw = localStorage.getItem(_MANUAL_ORIGIN_KEY);
        if (!raw) return false;
        const map = JSON.parse(raw) || {};
        const ts = map[taskId];
        return !!ts && (Date.now() - ts) < _MANUAL_ORIGIN_TTL;
    } catch (_) { return false; }
}

function _loadNotifiedRunIds() {
    try {
        const raw = localStorage.getItem(_NOTIFIED_RUNS_KEY);
        if (!raw) return [];
        const arr = JSON.parse(raw);
        return Array.isArray(arr) ? arr : [];
    } catch (_) { return []; }
}

function _persistNotifiedRunIds(ids) {
    try { localStorage.setItem(_NOTIFIED_RUNS_KEY, JSON.stringify(ids)); } catch (_) {}
}

function claimScheduledRunNotify(runId) {
    if (!runId) return true;         // no id -> can't dedupe, allow once

    // Fast path: this tab already saw it (own tick or a peer's broadcast).
    if (_notifiedRunIds.has(runId)) return false;

    // Re-read the shared set so a claim from another tab that happened between
    // our ticks is honoured even if its broadcast was missed.
    const shared = _loadNotifiedRunIds();
    for (const id of shared) _notifiedRunIds.add(id);
    if (_notifiedRunIds.has(runId)) return false;

    // Claim it: record locally, persist to the shared store, and tell peers.
    _notifiedRunIds.add(runId);
    shared.push(runId);
    // Bound growth; the poll only looks back a short window so trimmed ids
    // can never reappear.
    const trimmed = shared.length > _NOTIFIED_RUNS_MAX
        ? shared.slice(shared.length - _NOTIFIED_RUNS_MAX)
        : shared;
    _persistNotifiedRunIds(trimmed);
    if (_notifyBus) { try { _notifyBus.postMessage({ runId }); } catch (_) {} }
    return true;
}

// Force a scheduled-task notification regardless of window focus.
//
// showTaskNotification() suppresses itself when the window is focused, which is
// right for a normal reply the user is watching stream in. A scheduled task is
// different: it can fire into a session the user isn't currently viewing (or
// while they're looking at another app/tab), so if we don't notify they have no
// way to know it happened. This reuses the same popNotification() plumbing but
// skips the focus gate. Still honours the user's "Task Notifications" toggle.
function forceScheduledNotification(title, body, sid, agentId) {
    if (!taskNotifyEnabled) return;
    playNotifyBeep();
    if (document.hidden) {
        unreadCount += 1;
        document.title = `(${unreadCount}) ${baseDocTitle}`;
    }
    if (typeof Notification === 'undefined') return;
    if (Notification.permission === 'default') {
        Notification.requestPermission()
            .then(function(perm) {
                if (perm === 'granted') popNotification(title, body, sid, agentId);
                else refreshNotifyBlockedHint();
            })
            .catch(function() {});
        return;
    }
    if (Notification.permission === 'denied') {
        refreshNotifyBlockedHint();
        return;
    }
    popNotification(title, body, sid, agentId);
}

document.addEventListener('visibilitychange', function() {
    if (!document.hidden) {
        unreadCount = 0;
        document.title = baseDocTitle;
    }
});

// Request OS notification permission when notifications are enabled and the
// browser hasn't decided yet. Safe to call repeatedly.
function ensureNotifyPermission() {
    if (taskNotifyEnabled
        && typeof Notification !== 'undefined'
        && Notification.permission === 'default') {
        Notification.requestPermission().catch(function() {});
    }
}

// Show the "blocked by browser" hint only when notifications are enabled but
// the browser permission is denied (nothing the app can do about it in code).
function refreshNotifyBlockedHint() {
    const el = document.getElementById('cfg-task-notify-blocked');
    if (!el) return;
    const blocked = taskNotifyEnabled
        && typeof Notification !== 'undefined'
        && Notification.permission === 'denied';
    el.classList.toggle('hidden', !blocked);
}

function initTaskNotifyToggles() {
    const notifyEl = document.getElementById('cfg-task-notify');
    if (notifyEl) {
        notifyEl.checked = taskNotifyEnabled;
        notifyEl.addEventListener('change', function() {
            taskNotifyEnabled = notifyEl.checked;
            localStorage.setItem(TASK_NOTIFY_KEY, taskNotifyEnabled ? '1' : '0');
            ensureNotifyPermission();
            refreshNotifyBlockedHint();
        });
    }
    const soundEl = document.getElementById('cfg-task-notify-sound');
    if (soundEl) {
        soundEl.checked = taskNotifySound;
        soundEl.addEventListener('change', function() {
            taskNotifySound = soundEl.checked;
            localStorage.setItem(TASK_NOTIFY_SOUND_KEY, taskNotifySound ? '1' : '0');
        });
    }
    refreshNotifyBlockedHint();
}

document.addEventListener('DOMContentLoaded', initTaskNotifyToggles);

