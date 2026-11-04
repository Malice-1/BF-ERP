/* Apply before paint; share the preference with tabs and budget iframes. */
(() => {
  const key = 'bf-erp-theme';
  const system = window.matchMedia('(prefers-color-scheme: dark)');
  let preference = null;
  try { preference = localStorage.getItem(key); } catch (_) { /* Storage can be disabled. */ }
  const valid = value => value === 'dark' || value === 'light';
  function apply(theme) {
    document.documentElement.dataset.theme = theme;
    document.querySelectorAll('[data-theme-toggle]').forEach(button => {
      const dark = theme === 'dark';
      button.setAttribute('aria-pressed', String(dark));
      button.setAttribute('aria-label', dark ? 'Activer le mode clair' : 'Activer le mode sombre');
      button.querySelector('[data-theme-label]').textContent = dark ? 'Mode clair' : 'Mode sombre';
      button.querySelector('[data-theme-icon]').textContent = dark ? '☀' : '☾';
    });
  }
  apply(valid(preference) ? preference : system.matches ? 'dark' : 'light');
  document.addEventListener('DOMContentLoaded', () => {
    apply(document.documentElement.dataset.theme);
    document.querySelectorAll('[data-theme-toggle]').forEach(button => {
      button.addEventListener('click', () => {
        preference = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
        try { localStorage.setItem(key, preference); } catch (_) { /* Keep the current choice in memory. */ }
        apply(preference);
        document.querySelectorAll('iframe').forEach(frame => {
          if (frame.contentWindow) frame.contentWindow.postMessage({type: key, theme: preference}, location.origin);
        });
      });
    });
  });
  window.addEventListener('storage', event => {
    if (event.key === key || event.key === null) {
      preference = event.newValue;
      apply(valid(preference) ? preference : system.matches ? 'dark' : 'light');
    }
  });
  window.addEventListener('message', event => {
    if (event.origin === location.origin && event.source === window.parent && event.data?.type === key && valid(event.data.theme)) apply(event.data.theme);
  });
  system.addEventListener('change', event => { if (!valid(preference)) apply(event.matches ? 'dark' : 'light'); });
})();
