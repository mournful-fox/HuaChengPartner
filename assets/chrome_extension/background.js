// Подключается к персонажам на этом же компьютере: у каждого свой порт
// (47321 — Хуа Чен, 47322 — Вэй Усянь, 47323 — Лань Чжань).
// Умеет: показать список вкладок, закрыть выбранные, сообщить, какой сайт открылся.
const PORTS = [47321, 47322, 47323];
const sockets = {};

function connect(port) {
  const cur = sockets[port];
  if (cur && (cur.readyState === WebSocket.OPEN || cur.readyState === WebSocket.CONNECTING)) return;
  let ws;
  try { ws = new WebSocket("ws://127.0.0.1:" + port); } catch (e) { return; }
  sockets[port] = ws;
  ws.onmessage = async (ev) => {
    let m;
    try { m = JSON.parse(ev.data); } catch (e) { return; }
    try {
      if (m.cmd === "list") {
        const tabs = await chrome.tabs.query({});
        ws.send(JSON.stringify({ id: m.id, tabs: tabs.map(t => ({
          id: t.id, title: t.title, url: t.url, lastAccessed: t.lastAccessed,
          pinned: t.pinned, audible: t.audible, active: t.active })) }));
      } else if (m.cmd === "close" && Array.isArray(m.ids)) {
        await chrome.tabs.remove(m.ids);
        ws.send(JSON.stringify({ id: m.id, ok: true }));
      }
    } catch (e) {
      ws.send(JSON.stringify({ id: m.id, error: String(e) }));
    }
  };
  ws.onclose = () => { if (sockets[port] === ws) delete sockets[port]; };
  ws.onerror = () => {};
}

function connectAll() { PORTS.forEach(connect); }
function each(fn) { Object.values(sockets).forEach(ws => { if (ws.readyState === WebSocket.OPEN) fn(ws); }); }

setInterval(() => { each(ws => ws.send('{"ping":1}')); connectAll(); }, 20000);
chrome.alarms.create("hua-keepalive", { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener(connectAll);
chrome.runtime.onStartup.addListener(connectAll);
chrome.runtime.onInstalled.addListener(connectAll);
connectAll();

chrome.tabs.onUpdated.addListener((tabId, info) => {
  if (info.url) each(ws => ws.send(JSON.stringify({ event: "tab", tabId, url: info.url })));
});
