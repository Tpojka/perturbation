// Holds a persistent native-messaging port to the Perturbation host, which pushes the status of every
// watched agent whenever it changes. An open port also keeps this service worker alive; the alarm
// reconnects after a crash.
const HOST = 'com.tpojka.perturbation';
const RECONNECT_ALARM = 'reconnect';

// One lamp at a time: solid red = working, dotted amber = needs you, green ring = free, grey dashes = no host.
const ICONS = { busy: 'lamp-red', waiting: 'lamp-amber', ready: 'lamp-green', unknown: 'lamp-grey' };
const BADGE_BACKGROUND = '#202124';
const BADGE_TEXT = '#ffffff';

let port = null;
let last = null; // the latest status message, or null while disconnected
let detail = '';

function iconSet(name) {
  const set = {};
  for (const size of [16, 32, 48, 128]) set[size] = `icons/${name}-${size}.png`;
  return set;
}

function plural(n, word) {
  return `${n} ${word}${n === 1 ? '' : 's'}`;
}

function badgeText(n) {
  return n > 99 ? '99+' : String(n);
}

function headline(status) {
  if (!status.agents.some((a) => a.watched)) return 'Perturbation — no agents watched';
  if (status.overall === 'busy') return `Perturbation — ${plural(status.busy_sessions, 'session')} working`;
  if (status.overall === 'waiting') return `Perturbation — ${plural(status.waiting_sessions, 'session')} need${status.waiting_sessions === 1 ? 's' : ''} you`;
  return 'Perturbation — unperturbed';
}

function agentLine(agent) {
  if (!agent.watched) return `· ${agent.name} — not watched`;
  if (agent.state === 'busy') {
    const count = agent.total > 1 ? `${agent.busy} of ${plural(agent.total, 'session')}` : plural(agent.total, 'session');
    return `● ${agent.name} — working, ${count}`;
  }
  if (agent.state === 'waiting') return `◐ ${agent.name} — needs you`;
  return `○ ${agent.name} — ready`;
}

function render() {
  if (!last) {
    chrome.action.setIcon({ path: iconSet(ICONS.unknown) });
    chrome.action.setBadgeText({ text: '' });
    chrome.action.setTitle({ title: `Perturbation: native host not connected${detail ? `\n${detail}` : ''}` });
    return;
  }
  const watched = last.agents.some((a) => a.watched);
  const lamp = watched ? last.overall : 'unknown';
  chrome.action.setIcon({ path: iconSet(ICONS[lamp] || ICONS.unknown) });
  let badge = '';
  if (lamp === 'busy') badge = badgeText(last.busy_sessions);
  else if (lamp === 'waiting') badge = badgeText(last.waiting_sessions);
  chrome.action.setBadgeText({ text: badge });
  chrome.action.setBadgeBackgroundColor({ color: BADGE_BACKGROUND });
  if (chrome.action.setBadgeTextColor) chrome.action.setBadgeTextColor({ color: BADGE_TEXT });
  chrome.action.setTitle({ title: [headline(last), ...last.agents.map(agentLine)].join('\n') });
}

function broadcast() {
  // The popup, if open, re-renders. Nobody listening is the normal case, so the error is expected.
  chrome.runtime.sendMessage({ type: 'status', status: last, connected: port !== null }).catch(() => {});
}

function remember() {
  chrome.storage.session.set({ status: last }).catch?.(() => {});
}

function connect() {
  if (port) return;
  try {
    port = chrome.runtime.connectNative(HOST);
  } catch (e) {
    port = null;
    detail = String(e);
    render();
    broadcast();
    return;
  }
  port.onMessage.addListener((msg) => {
    if (!msg || msg.type !== 'status') return;
    last = msg;
    detail = '';
    render();
    remember();
    broadcast();
  });
  port.onDisconnect.addListener(() => {
    const err = chrome.runtime.lastError;
    port = null;
    last = null;
    detail = err ? err.message : 'Disconnected';
    render();
    remember();
    broadcast();
  });
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg) return;
  if (msg.type === 'get') {
    sendResponse({ status: last, connected: port !== null, detail });
  } else if (msg.type === 'reconnect') {
    connect();
    sendResponse({ connected: port !== null });
  } else if (msg.type === 'mute' || msg.type === 'order') {
    if (port) port.postMessage(msg);
    sendResponse({ ok: port !== null });
  }
});

chrome.alarms.create(RECONNECT_ALARM, { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === RECONNECT_ALARM) connect();
});
chrome.runtime.onStartup.addListener(connect);
chrome.runtime.onInstalled.addListener(connect);

connect();
