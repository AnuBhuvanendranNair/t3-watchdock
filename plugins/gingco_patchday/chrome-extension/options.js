const $ = id => document.getElementById(id);
chrome.storage.local.get(['names', 'askTime', 'wd'], c => {
  $('names').value = ((c.names && c.names.length) ? c.names : ['Siva', 'Anu BN']).join(', ');
  $('askTime').checked = c.askTime !== false;
  $('wd').value = c.wd || 'http://127.0.0.1:8787';
});
$('save').onclick = async () => {
  const names = $('names').value.split(',').map(x => x.trim()).filter(Boolean);
  const wd = ($('wd').value.trim() || 'http://127.0.0.1:8787').replace(/\/+$/, '');
  let u; try { u = new URL(wd); } catch (e) { return flash('Ungültige T3-Watchdock-Adresse.'); }
  // Zugriff auf T3 Watchdock für "Alle ausführen" (Klick auf das Symbol braucht ihn nicht)
  const ok = await chrome.permissions.request({ origins: [u.protocol + '//' + u.hostname + '/*'] }).catch(() => false);
  chrome.storage.local.set({ names, askTime: $('askTime').checked, wd }, () =>
    flash(ok ? 'Gespeichert.' : 'Gespeichert – ohne Zugriff auf T3 Watchdock funktioniert „Alle ausführen“ nicht.'));
};

// ---------- CSV Export / Import (Spalten: Typ;Website/Wert;UID;OpenProject-Link) ----------
// Zeilen "Zuordnung" aus Version 1.x werden ignoriert: die Links stehen jetzt in T3 Watchdock.
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
  let skipped = 0;
  for (const [typ = '', v = ''] of rows.slice(1)) {
    const t = typ.trim().toLowerCase();
    if (t === 'ausführung') $('names').value = v.trim();
    else if (t === 'uhrzeit abfragen') $('askTime').checked = /^(ja|true|1|x)$/i.test(v.trim());
    else if (t === 't3 watchdock') $('wd').value = v.trim();
    else if (t === 'zuordnung') skipped++;
  }
  flash('Importiert – bitte „Speichern“ klicken.' + (skipped ? ' ' + skipped + ' Zuordnung(en) ignoriert: OpenProject-Links in T3 Watchdock eintragen.' : ''));
};
