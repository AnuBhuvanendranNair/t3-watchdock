// Läuft auf T3 Watchdock: Button "Patchday" des Plugins -> Ablauf wie Klick auf das Symbol.
// Standard-Adressen über manifest.json, andere T3-Watchdock-Adressen über die Einstellungen (syncBridge).
(() => {
  if (document.documentElement.dataset.patchday) return;   // schon aktiv (z. B. beide Wege) -> nicht doppelt starten
  if (document.title !== 'T3 Watchdock' || !document.querySelector('a.brand')) return;   // andere Seiten auf localhost: nichts tun
  document.documentElement.dataset.patchday = '1';
  window.addEventListener('message', e => {
    if (e.source !== window || e.origin !== location.origin || !e.data || e.data.type !== 'patchday:run') return;
    chrome.runtime.sendMessage({ type: 'run', project: String(e.data.project || '') });
  });
})();
