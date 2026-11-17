const $ = id => document.getElementById(id);
// Zuordnung: Projekt in T3 Watchdock (Name, Projekt-ID) -> OpenProject-Link (Patchday Protokoll)
const row = (m = {}) => {
  const tr = document.createElement('tr');
  tr.innerHTML = '<td><input class="name"></td><td><input class="id"></td><td><input class="op" type="url"></td><td><button class="del" title="Entfernen">✕</button></td>';
  tr.querySelector('.name').value = m.name || ''; tr.querySelector('.id').value = m.id || ''; tr.querySelector('.op').value = m.op || '';
  tr.querySelector('.del').onclick = () => tr.remove();
  $('map').appendChild(tr);
};
const readMap = () => [...$('map').rows].map(r => ({
  name: r.querySelector('.name').value.trim(), id: r.querySelector('.id').value.trim(), op: r.querySelector('.op').value.trim()
}));
const askAccess = wd => chrome.permissions.request({ origins: [wdOrigin(wd)] }).catch(() => false);
const wdValue = () => ($('wd').value.trim() || DEF_WD).replace(/\/+$/, '');

chrome.storage.local.get(['names', 'askTime', 'wd', 'map'], c => {
  $('names').value = ((c.names && c.names.length) ? c.names : DEF_NAMES).join(', ');
  $('askTime').checked = c.askTime !== false;
  $('wd').value = c.wd || DEF_WD;
  (c.map || []).forEach(row);
  if (!(c.map || []).length) row();
});
$('addRow').onclick = () => row();
$('save').onclick = async () => {
  const names = $('names').value.split(',').map(x => x.trim()).filter(Boolean);
  const wd = wdValue();
  try { new URL(wd); } catch (e) { return flash('Ungültige T3-Watchdock-Adresse.'); }
  // Zugriff auf T3 Watchdock für "Alle ausführen" und "Projekte laden" (Klick auf das Symbol braucht ihn nicht)
  const ok = await askAccess(wd);
  const map = readMap().filter(m => m.id && m.op);
  chrome.storage.local.set({ names, askTime: $('askTime').checked, wd, map }, () =>
    flash(ok ? 'Gespeichert.' : 'Gespeichert – ohne Zugriff auf T3 Watchdock funktionieren „Alle ausführen“ und „Projekte laden“ nicht.'));
};
// Projekte aus T3 Watchdock laden: fehlende Projekte als Zeilen ergänzen (vorhandene Links bleiben)
$('loadProjects').onclick = async () => {
  const wd = wdValue();
  try { new URL(wd); } catch (e) { return flash('Ungültige T3-Watchdock-Adresse.'); }
  if (!(await askAccess(wd))) return flash('Kein Zugriff auf ' + wd + '.');
  const tab = await chrome.tabs.create({ url: 'about:blank', active: false });
  let list;
  try {
    await openWait(tab.id, wd + '/');
    list = await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: listWD, world: 'MAIN' }).then(r => r[0] && r[0].result);
  } catch (e) { list = { error: e.message }; }
  chrome.tabs.remove(tab.id).catch(() => {});
  if (!Array.isArray(list)) return flash('Fehler: ' + ((list && list.error) || 'T3 Watchdock nicht lesbar'));
  const cur = readMap(), have = new Set(cur.map(m => m.id));
  $('map').innerHTML = '';
  cur.filter(m => m.id || m.op || m.name).forEach(row);
  const add = list.filter(p => !have.has(p.id));
  add.forEach(p => row({ id: p.id, name: p.name }));
  if (!$('map').rows.length) row();
  flash(add.length + ' Projekt(e) ergänzt – Links eintragen und „Speichern“ klicken.');
};

// ---------- CSV Export / Import (Spalten: Typ;Website/Wert;UID;OpenProject-Link) ----------
// Zuordnung: Website/Wert = Projektname, UID = Projekt-ID in T3 Watchdock. Zeilen aus 1.x mit T3Monitor-UID (Zahl) werden ignoriert.
const CSV_HEAD = ['Typ', 'Website/Wert', 'UID', 'OpenProject-Link'];
const csvCell = v => /[";\r\n]/.test(v = String(v ?? '')) ? '"' + v.replace(/"/g, '""') + '"' : v;
const csvParse = (txt, sep) => { // RFC 4180, Anführungszeichen und Zeilenumbrüche in Feldern erlaubt
  const out = []; let row = [], f = '', q = false;
  for (let i = 0; i < txt.length; i++) {
    const ch = txt[i];
    if (q) { if (ch === '"') { if (txt[i + 1] === '"') { f += '"'; i++; } else q = false; } else f += ch; }
    else if (ch === '"') q = true;
    else if (ch === sep) { row.push(f); f = ''; }
    else if (ch === '\n' || ch === '\r') { if (ch === '\r' && txt[i + 1] === '\n') i++; row.push(f); out.push(row); row = []; f = ''; }
    else f += ch;
  }
  if (f || row.length) { row.push(f); out.push(row); }
  return out.filter(r => r.some(c => c.trim()));
};
const flash = t => { $('msg').textContent = t; setTimeout(() => $('msg').textContent = '', 4000); };
$('exportCsv').onclick = () => {
  const rows = [CSV_HEAD, ['Ausführung', $('names').value.trim(), '', ''], ['Uhrzeit abfragen', $('askTime').checked ? 'ja' : 'nein', '', ''],
    ['T3 Watchdock', $('wd').value.trim(), '', '']];
  for (const m of readMap()) if (m.id || m.op) rows.push(['Zuordnung', m.name, m.id, m.op]);
  const blob = new Blob(['﻿' + rows.map(r => r.map(csvCell).join(';')).join('\r\n') + '\r\n'], { type: 'text/csv;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = 'patchday-einstellungen-' + new Date().toISOString().slice(0, 10) + '.csv';
  a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
};
$('importCsv').onclick = () => $('csvFile').click();
$('csvFile').onchange = async e => {
  const file = e.target.files[0]; e.target.value = '';
  if (!file) return;
  const txt = (await file.text()).replace(/^﻿/, '');
  const first = txt.split(/\r?\n/, 1)[0];
  const rows = csvParse(txt, (first.match(/;/g) || []).length >= (first.match(/,/g) || []).length ? ';' : ',');
  if (!rows.length || rows[0][0].trim() !== CSV_HEAD[0]) return flash('Ungültige CSV: Kopfzeile „' + CSV_HEAD.join(';') + '“ erwartet.');
  const map = []; let skipped = 0;
  for (const [typ = '', v = '', id = '', op = ''] of rows.slice(1)) {
    const t = typ.trim().toLowerCase();
    if (t === 'ausführung') $('names').value = v.trim();
    else if (t === 'uhrzeit abfragen') $('askTime').checked = /^(ja|true|1|x)$/i.test(v.trim());
    else if (t === 't3 watchdock') $('wd').value = v.trim();
    else if (t === 'zuordnung') { if (/^\d*$/.test(id.trim())) skipped++; else map.push({ name: v.trim(), id: id.trim(), op: op.trim() }); }
  }
  $('map').innerHTML = '';
  map.forEach(row); if (!map.length) row();
  flash(map.length + ' Zuordnung(en) importiert – bitte „Speichern“ klicken.' + (skipped ? ' ' + skipped + ' Zeile(n) aus 1.x ignoriert (T3Monitor-UID statt Projekt-ID).' : ''));
};
