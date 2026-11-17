// "Alle ausführen": alle Zuordnungen aus den Einstellungen nacheinander – aus T3 Watchdock lesen, OpenProject öffnen, writeOP mit Bestätigung je Schritt.
const $ = id => document.getElementById(id);
const exec = (tabId, func, args = [], world = 'ISOLATED') =>
  chrome.scripting.executeScript({ target: { tabId }, func, args, world }).then(r => r[0] && r[0].result).catch(e => ({ error: e.message }));
const base = u => (u || '').split(/[?#]/)[0].replace(/\/+$/, '');
const hostOf = u => { try { return new URL(u).host; } catch (e) { return ''; } };
const sleep = ms => new Promise(r => setTimeout(r, ms));
let stop = false;
$('stop').onclick = () => { stop = true; $('stop').disabled = true; $('stop').textContent = 'Stoppt nach aktueller Website…'; };

const open = openWait;
// Nach Klick auf "Speichern": warten, bis die Bearbeitungsseite verlassen wurde (max. 30 s)
const saved = async (tabId, edit) => {
  for (let i = 0; i < 60; i++) {
    await sleep(500);
    const t = await chrome.tabs.get(tabId).catch(() => null);
    if (!t) return false;
    if (t.status === 'complete' && base(t.url) !== edit) return true;
  }
  return false;
};

(async () => {
  const cfg = await getCfg();
  const fail = t => { $('txt').textContent = t; $('stop').hidden = true; };
  let wdUrl; try { wdUrl = new URL(cfg.wd); } catch (e) { return fail('T3-Watchdock-URL in den Einstellungen ungültig.'); }
  if (!(await chrome.permissions.contains({ origins: [wdOrigin(cfg.wd)] })))
    return fail('Kein Zugriff auf ' + cfg.wd + ' – bitte in den Einstellungen „Speichern“ klicken und den Zugriff erlauben.');
  const map = cfg.map.filter(m => m.id && m.op);
  const n = map.length;
  if (!n) return fail('Keine Zuordnungen in den Einstellungen.');
  const me = await chrome.tabs.getCurrent();
  const work = await chrome.tabs.create({ url: 'about:blank', windowId: me.windowId, active: false });
  const wdHome = cfg.wd + '/';
  const rows = map.map((m, i) => {
    const tr = $('list').insertRow();
    tr.insertCell().textContent = i + 1;
    tr.insertCell().textContent = m.name || m.id;
    const st = tr.insertCell(); st.textContent = 'wartet';
    return st;
  });
  const set = (i, text, cls = '') => { rows[i].textContent = text; rows[i].className = cls; };

  const who = prompt('Alle ausführen (' + n + ' Websites)\n\nAusführung: Wer führt aus?\nMehrere Namen mit Komma trennen.\nLeer lassen = aus Einstellungen: ' + cfg.names.join(', '), '');
  if (who === null) { chrome.tabs.remove(work.id); return fail('Abgebrochen.'); }
  const names = who.split(',').map(x => x.trim()).filter(Boolean);
  const c = { names: names.length ? names : cfg.names, askTime: cfg.askTime };

  const cnt = {};
  let i = 0;
  for (; i < n && !stop; i++) {
    const m = map[i], step = '[' + (i + 1) + '/' + n + '] ';
    $('txt').textContent = step + (m.name || m.id);
    $('bar').max = n; $('bar').value = i;
    chrome.action.setBadgeText({ text: (i + 1) + '/' + n });
    set(i, 'läuft…', 'run');
    const res = await (async () => {
      if (hostOf(await open(work.id, wdHome)) !== wdUrl.host) return ['Fehler: T3 Watchdock nicht erreichbar', 'err'];
      const d = await exec(work.id, readWD, [m.id], 'MAIN');   // liest die Website vorher neu (t3monitor)
      if (!d || d.error) return ['Fehler: ' + ((d && d.error) || 'T3 Watchdock nicht lesbar'), 'err'];
      const edit = opEditUrl(m.op);
      if (base(await open(work.id, edit)) !== edit) return ['Fehler: OpenProject nicht angemeldet oder Seite nicht gefunden', 'err', 1];
      await chrome.tabs.update(work.id, { active: true });
      const r = await exec(work.id, writeOP, [d, c, { step }], 'MAIN');
      if (r === 'saved') return (await saved(work.id, edit)) ? ['Gespeichert ✓', 'ok']
        : ['Speichern nicht bestätigt – bitte im Arbeits-Tab prüfen', 'err', 1];
      if (r === 'nothing') return ['Nichts Neues (heute schon eingetragen)', 'ok'];
      if (r === 'cancel') return ['Übersprungen', ''];
      if (r === 'manual') return ['Inhalt eingefügt, bitte im Arbeits-Tab selbst speichern', 'err', 1];
      return ['Fehler: ' + ((r && r.error) || 'Arbeits-Tab geschlossen oder Skriptfehler'), 'err', 1];
    })();
    set(i, res[0], res[1]);
    cnt[res[1] || 'skip'] = (cnt[res[1] || 'skip'] || 0) + 1;
    if (res[2]) { // Arbeits-Tab geschlossen oder evtl. ungespeicherter Inhalt -> Tab nicht verlassen, Lauf stoppen
      const t = await chrome.tabs.get(work.id).catch(() => null);
      if (!t || base(t.url) === opEditUrl(m.op)) { stop = true; i++; break; }
    }
  }
  rows.forEach((st, k) => { if (st.textContent === 'wartet') set(k, 'nicht ausgeführt'); });
  $('bar').value = i;
  chrome.action.setBadgeText({ text: '' });
  $('txt').textContent = (stop ? 'Gestoppt' : 'Fertig') + ': ' + (cnt.ok || 0) + ' OK, ' + (cnt.skip || 0) + ' übersprungen, ' + (cnt.err || 0) + ' Fehler.';
  $('stop').hidden = true;
  chrome.tabs.update(me.id, { active: true });
})();
