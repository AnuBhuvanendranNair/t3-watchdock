// Läuft auf T3 Watchdock (registriert in den Einstellungen): Button "Patchday" des Plugins -> Ablauf wie Klick auf das Symbol.
document.documentElement.dataset.patchday = '1';
window.addEventListener('message', e => {
  if (e.source !== window || e.origin !== location.origin || !e.data || e.data.type !== 'patchday:run') return;
  chrome.runtime.sendMessage({ type: 'run', project: String(e.data.project || '') });
});
