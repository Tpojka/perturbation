// The popup never waits on the host: the service worker answers from its cached status at once, and
// re-renders whenever a fresh status arrives while the popup is open.
const $ = (id) => document.getElementById(id);

function plural(n, word) {
  return `${n} ${word}${n === 1 ? '' : 's'}`;
}

function describe(agent) {
  if (!agent.watched) return ['not watched', ''];
  if (agent.total === 0) return ['ready', 'no sessions'];
  if (agent.state === 'busy') return ['working', `${agent.busy} of ${plural(agent.total, 'session')}`];
  if (agent.state === 'waiting') return ['needs you', `${agent.waiting} of ${plural(agent.total, 'session')}`];
  return ['ready', plural(agent.total, 'session')];
}

function headline(status) {
  if (!status.agents.some((a) => a.watched)) return 'No agents watched';
  if (status.overall === 'busy') return `${plural(status.busy_sessions, 'session')} working`;
  if (status.overall === 'waiting') return `${plural(status.waiting_sessions, 'session')} need${status.waiting_sessions === 1 ? 's' : ''} you`;
  return 'Unperturbed';
}

function render({ status, connected, detail }) {
  const list = $('agents');
  list.textContent = '';
  if (!status) {
    $('overall').className = 'lamp unknown';
    $('headline').textContent = 'Native host not connected';
    $('connection').textContent = detail || 'Run the installer, then reconnect';
    $('reconnect').hidden = false;
    $('hint').hidden = true;
    $('version').textContent = '';
    return;
  }
  const watched = status.agents.some((a) => a.watched);
  $('overall').className = `lamp ${watched ? status.overall : 'unknown'}`;
  $('headline').textContent = headline(status);
  for (const agent of status.agents) {
    const [state, count] = describe(agent);
    const row = document.createElement('li');
    row.dataset.id = agent.id;
    row.draggable = true;
    row.className = agent.watched ? '' : 'unwatched';
    const lamp = document.createElement('span');
    lamp.className = `lamp ${agent.watched ? agent.state : 'unknown'}`;
    const label = document.createElement('div');
    const name = document.createElement('div');
    name.className = 'name';
    name.textContent = agent.name;
    const stateText = document.createElement('div');
    stateText.className = 'state';
    stateText.textContent = state;
    label.append(name, stateText);
    const countText = document.createElement('span');
    countText.className = 'count';
    countText.textContent = count;
    const mute = document.createElement('label');
    mute.className = 'mute';
    mute.title = agent.muted ? 'Notifications muted; click to unmute' : 'Notifications on; click to mute';
    const input = document.createElement('input');
    input.type = 'checkbox';
    input.checked = !agent.muted;
    input.disabled = !agent.watched;
    input.setAttribute('aria-label', `Notifications for ${agent.name}`);
    input.addEventListener('change', () => {
      chrome.runtime.sendMessage({ type: 'mute', id: agent.id, muted: !input.checked });
    });
    mute.append(input, document.createElement('span'));
    row.append(lamp, label, countText, mute);
    list.append(row);
  }
  $('connection').textContent = connected ? 'Native host connected' : 'Native host not connected';
  $('reconnect').hidden = connected;
  $('hint').hidden = false;
  $('version').textContent = `v${status.version}`;
  enableDragging(list);
}

function enableDragging(list) {
  let dragging = null;
  for (const row of list.children) {
    row.addEventListener('dragstart', (e) => {
      dragging = row;
      row.classList.add('dragging');
      e.dataTransfer.effectAllowed = 'move';
    });
    row.addEventListener('dragend', () => {
      row.classList.remove('dragging');
      for (const r of list.children) r.classList.remove('over');
    });
    row.addEventListener('dragover', (e) => {
      e.preventDefault();
      if (row !== dragging) row.classList.add('over');
    });
    row.addEventListener('dragleave', () => row.classList.remove('over'));
    row.addEventListener('drop', (e) => {
      e.preventDefault();
      if (!dragging || row === dragging) return;
      list.insertBefore(dragging, row);
      const ids = [...list.children].map((r) => r.dataset.id);
      chrome.runtime.sendMessage({ type: 'order', ids });
    });
  }
}

$('reconnect').addEventListener('click', () => {
  chrome.runtime.sendMessage({ type: 'reconnect' }, () => {
    chrome.runtime.sendMessage({ type: 'get' }, render);
  });
});

chrome.runtime.onMessage.addListener((msg) => {
  if (msg && msg.type === 'status') render(msg);
});

chrome.runtime.sendMessage({ type: 'get' }, (response) => {
  render(response || { status: null, connected: false, detail: '' });
});
