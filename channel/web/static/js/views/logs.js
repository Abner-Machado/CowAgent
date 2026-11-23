/* Live log stream.
   Split out of console.js. These are classic scripts sharing one global
   scope; see channel/web/README.md before changing the load order. */

// =====================================================================
// Logs View
// =====================================================================
let logEventSource = null;

function logLevelClass(line) {
    if (/\[CRITICAL\]/.test(line)) return 'log-line-critical';
    if (/\[ERROR\]/.test(line))    return 'log-line-error';
    if (/\[WARNING\]/.test(line))  return 'log-line-warning';
    if (/\[INFO\]/.test(line))     return 'log-line-info';
    if (/\[DEBUG\]/.test(line))    return 'log-line-debug';
    return '';
}

function getHiddenLevels() {
    const hidden = new Set();
    document.querySelectorAll('.log-filter-cb').forEach(function(cb) {
        if (!cb.checked) hidden.add('log-line-' + cb.dataset.level);
    });
    return hidden;
}

function applyLogFilter() {
    const hidden = getHiddenLevels();
    document.querySelectorAll('#log-output .log-line').forEach(function(span) {
        const level = span.classList[1] || '';
        span.style.display = hidden.has(level) ? 'none' : '';
    });
}

function appendLogLines(output, text) {
    const hidden = getHiddenLevels();
    let lastLevelClass = '';
    const lines = text.split('\n');
    lines.forEach(function(line, i) {
        if (i === lines.length - 1 && line === '') return;
        const span = document.createElement('span');
        const levelClass = logLevelClass(line) || lastLevelClass;
        if (logLevelClass(line)) lastLevelClass = levelClass;
        span.className = 'log-line ' + levelClass;
        span.textContent = line + '\n';
        if (hidden.has(levelClass)) span.style.display = 'none';
        output.appendChild(span);
    });
}

document.addEventListener('change', function(e) {
    if (e.target.classList.contains('log-filter-cb')) applyLogFilter();
});

function startLogStream() {
    if (logEventSource) return;
    const output = document.getElementById('log-output');
    output.innerHTML = '';

    logEventSource = new EventSource('/api/logs');
    logEventSource.onmessage = function(e) {
        let item;
        try { item = JSON.parse(e.data); } catch (_) { return; }

        if (item.type === 'init') {
            output.innerHTML = '';
            appendLogLines(output, item.content || '');
            output.scrollTop = output.scrollHeight;
        } else if (item.type === 'line') {
            appendLogLines(output, item.content);
            output.scrollTop = output.scrollHeight;
        } else if (item.type === 'error') {
            output.textContent = item.message || 'Error loading logs';
        }
    };
    logEventSource.onerror = function() {
        logEventSource.close();
        logEventSource = null;
    };
}

function stopLogStream() {
    if (logEventSource) {
        logEventSource.close();
        logEventSource = null;
    }
}

