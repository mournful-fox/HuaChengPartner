// Подключается к программе Хуа Чена на этом же компьютере (ws://127.0.0.1:47321).
// Умеет только две вещи: показать список вкладок и закрыть выбранные.
const URL = "ws://127.0.0.1:47321";
let ws = null;

function connect() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
  try { ws = new WebSocket(URL); } catch (e) { return; }
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
  ws.onclose = () => { ws = null; };
  ws.onerror = () => {};
}

// держим связь живой: пинг каждые 20 с, а будильник раз в 30 с переподключает, если программа перезапускалась
setInterval(() => { if (ws && ws.readyState === WebSocket.OPEN) ws.send('{"ping":1}'); else connect(); }, 20000);
chrome.alarms.create("hua-keepalive", { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener(connect);
chrome.runtime.onStartup.addListener(connect);
chrome.runtime.onInstalled.addListener(connect);
connect();
