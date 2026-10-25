/* No credentials in IndexedDB, localStorage, URLs, or the service worker cache. */
const $ = id => document.getElementById(id);
const database = new Promise((resolve, reject) => {
  const open = indexedDB.open('xi-pocket-v1', 1);
  open.onupgradeneeded = () => open.result.createObjectStore('state');
  open.onsuccess = () => resolve(open.result);
  open.onerror = () => reject(open.error);
});
async function saved(key) {
  const db = await database;
  return new Promise((resolve, reject) => {
    const tx = db.transaction('state'); const request = tx.objectStore('state').get(key);
    request.onsuccess = () => resolve(request.result); request.onerror = () => reject(request.error);
  });
}
async function save(key, value) {
  const db = await database;
  return new Promise((resolve, reject) => {
    const tx = db.transaction('state', 'readwrite'); tx.objectStore('state').put(value, key);
    tx.oncomplete = resolve; tx.onerror = () => reject(tx.error); tx.onabort = () => reject(tx.error);
  });
}
async function clearDevice() {
  const db = await database;
  return new Promise((resolve, reject) => {
    const tx = db.transaction('state', 'readwrite'); tx.objectStore('state').clear();
    tx.oncomplete = resolve; tx.onerror = () => reject(tx.error);
  });
}
async function api(path, body) {
  const response = await fetch(path, {method: body === undefined ? 'GET' : 'POST',
    headers: body === undefined ? {} : {'Content-Type': 'application/json'},
    body: body === undefined ? undefined : JSON.stringify(body), cache: 'no-store',
    signal: AbortSignal.timeout(12000)});
  if (!response.ok) { const error = new Error(response.status === 401 ? 'Sign in to reconnect.' : 'Request not accepted (' + response.status + ').'); error.status = response.status; throw error; }
  return response.json();
}
let session, events = [], queue = [], cursor = 0, busy = false, library = {};
let queueChanges = Promise.resolve();
function updateQueue(change) {
  const operation = queueChanges.then(async () => {
    const next = change(queue); await save('queue', next); queue = next;
  });
  queueChanges = operation.catch(() => {}); return operation;
}
function render() {
  $('room').hidden = !session; $('login').hidden = !!session;
  $('logout').hidden = !session; $('backup').hidden = session?.actor.role !== 'owner';
  $('library').hidden = session?.actor.role !== 'owner';
  $('identity').textContent = session ? session.actor.name + ' · Room' : 'Room';
  $('node').textContent = session ? 'Node ' + session.node_id : '';
  $('pending').textContent = queue.length ? queue.length + ' kept on this device · waiting for receipt' : 'Queue clear';
  const feed = $('feed'); feed.replaceChildren();
  for (const e of events) {
    const element = document.createElement('article'); element.className = 'message';
    const author = document.createElement('strong'); author.textContent = e.actor;
    const meta = document.createElement('div'); meta.className = 'meta'; meta.textContent = e.created_at + ' · ' + (e.attribution?.kind || 'source declared');
    const text = document.createElement('div'); text.className = 'text'; text.textContent = e.text;
    element.append(author, meta, text); feed.append(element);
  }
  for (const q of queue) {
    const element = document.createElement('article'); element.className = 'message queued';
    const label = document.createElement('strong'); label.textContent = 'Saved locally · delivery pending';
    const text = document.createElement('div'); text.className = 'text'; text.textContent = q.body.text;
    element.append(label, text); feed.append(element);
  }
}
async function flush() {
  while (queue.length) {
    const q = queue[0];
    if (q.node_id !== session.node_id || q.actor_id !== session.actor.id) throw new Error('Queued message belongs to another node or seat. It remains on this device.');
    const receipt = await api('/api/room', q.body);
    if (receipt.event.event_id !== q.body.event_id || receipt.event.text !== q.body.text) throw new Error('Receipt mismatch; message remains queued.');
    await updateQueue(items => items.filter(item => item.body.event_id !== q.body.event_id)); render();
  }
}
async function refresh() {
  if (busy) return; busy = true; $('room').setAttribute('aria-busy', 'true');
  try {
    const current = await api('/api/me');
    if (session && (session.node_id !== current.node_id || session.actor.id !== current.actor.id)) throw new Error('This address now belongs to another node or seat. Sign out to change seats. Your queue is preserved.');
    session = current; await save('session', session); await flush();
    let page;
    do {
      page = await api('/api/room?after=' + cursor);
      if (page.source_node !== session.node_id) throw new Error('Node identity changed.');
      const seen = new Set(events.map(e => e.event_id));
      for (const e of page.events) if (!seen.has(e.event_id)) { events.push(e); seen.add(e.event_id); }
      cursor = page.cursor;
      // Save event data and its cursor together, after a successful response.
      await save('room', {events, cursor});
    } while (page.has_more);
    $('connection').textContent = 'Connected · receipt verified'; $('notice').textContent = '';
  } catch (error) {
    $('connection').textContent = error.status === 401 ? 'Reconnect needed' : 'Offline · keeping your place';
    $('notice').textContent = error.message;
  } finally { busy = false; $('room').setAttribute('aria-busy', 'false'); render(); }
}
$('login-form').onsubmit = async event => {
  event.preventDefault();
  try {
    const current = await api('/api/login', {secret: $('secret').value.trim()}); $('secret').value = '';
    if (session && (current.node_id !== session.node_id || current.actor.id !== session.actor.id)) throw new Error('Sign out before changing seats; this device still has the previous seat’s data.');
    session = current; await save('session', session); await refresh();
  } catch (error) { $('notice').textContent = error.message; }
};
$('compose').onsubmit = async event => {
  event.preventDefault(); if (!session || !$('draft').value.trim()) return;
  try {
    const submittedText = $('draft').value;
    const body = {event_id: crypto.randomUUID(), text: submittedText};
    const queued = {node_id: session.node_id, actor_id: session.actor.id, body};
    await updateQueue(items => [...items, queued]); // Clear only after durable IndexedDB completion.
    // A person may already be typing the next message while IndexedDB commits.
    // Never clear a newer draft when the submitted message finishes enqueuing.
    if ($('draft').value === submittedText) { $('draft').value = ''; await save('draft', ''); }
    render(); await refresh();
  } catch (error) { $('notice').textContent = 'Draft retained: ' + error.message; }
};
$('draft').oninput = () => save('draft', $('draft').value).catch(e => { $('notice').textContent = 'Draft not saved: ' + e.message; });
$('refresh').onclick = refresh;
function renderLibrary() {
  const all = Object.entries(library).flatMap(([collection, data]) => data.records.map(record => ({collection, record})));
  $('library-state').textContent = all.length ? all.length + ' records cached on this device.' : 'Archive has not been cached on this device.';
  const query = $('library-search').value.toLocaleLowerCase();
  const matches = all.filter(({record}) => JSON.stringify(record).toLocaleLowerCase().includes(query)).slice(0, 30);
  const results = $('library-results'); results.replaceChildren();
  for (const {collection, record} of matches) {
    const detail = document.createElement('details'); detail.className = 'message';
    const label = document.createElement('summary'); label.textContent = collection + ' · ' + (record.title || record.name || record.id || 'Record');
    const body = document.createElement('pre'); body.className = 'text'; body.textContent = JSON.stringify(record, null, 2);
    detail.append(label, body); results.append(detail);
  }
}
$('library-search').oninput = renderLibrary;
$('cache-library').onclick = async () => {
  try {
    const listing = await api('/api/library'); const next = {};
    for (const item of listing.collections) {
      if (!item.available) throw new Error('Carried export missing: ' + item.name);
      next[item.name] = await api('/api/library/' + item.name);
    }
    await save('library', next); library = next; renderLibrary();
    $('notice').textContent = 'All five carried collections are cached for offline reading.';
  } catch (error) { $('notice').textContent = error.message; }
};
$('persist').onclick = async () => {
  const granted = await navigator.storage?.persist?.();
  $('notice').textContent = granted ? 'Persistent storage granted on this device.' : 'Browser did not grant persistent storage. Keep an independent backup.';
};
$('backup').onclick = async () => {
  try { const result = await api('/api/backup', {}); $('notice').textContent = 'Server backup saved: ' + result.filename; }
  catch (error) { $('notice').textContent = error.message; }
};
$('logout').onclick = async () => {
  if (queue.length && !confirm('This device has unsent messages. Signing out will clear them. Continue?')) return;
  try { await api('/api/logout', {}); }
  catch { $('notice').textContent = 'Reconnect before signing out so the server session can be closed.'; return; }
  await clearDevice(); session = undefined; events = []; queue = []; cursor = 0; library = {}; $('draft').value = ''; render(); renderLibrary();
};
window.addEventListener('online', refresh);
async function start() {
  session = await saved('session'); queue = await saved('queue') || [];
  const room = await saved('room'); events = room?.events || []; cursor = room?.cursor || 0;
  $('draft').value = await saved('draft') || ''; library = await saved('library') || {}; render(); renderLibrary();
  if ('serviceWorker' in navigator) {
    try { await navigator.serviceWorker.register('/sw.js'); await navigator.serviceWorker.ready; $('offline').textContent = 'app shell installed'; }
    catch { $('offline').textContent = 'unavailable on this browser or origin'; }
  }
  await refresh(); setInterval(refresh, 7000);
}
start().catch(error => { $('notice').textContent = 'Offline storage unavailable: ' + error.message; });
