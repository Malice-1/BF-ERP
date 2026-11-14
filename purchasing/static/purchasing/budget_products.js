(() => {
  const form = document.getElementById('budget-product-search');
  const input = form.querySelector('input[name="q"]');
  const results = document.getElementById('budget-product-results');
  const status = document.getElementById('budget-product-search-status');
  let timer;
  let currentRequest;

  async function search() {
    clearTimeout(timer);
    if (currentRequest) currentRequest.abort();
    const request = new AbortController();
    currentRequest = request;
    const url = new URL(form.action, window.location.href);
    if (input.value.trim()) url.searchParams.set('q', input.value.trim());
    results.setAttribute('aria-busy', 'true');
    try {
      const response = await fetch(url, {
        signal: request.signal,
        headers: {'X-Requested-With': 'XMLHttpRequest'},
        cache: 'no-store',
      });
      if (currentRequest !== request || request.signal.aborted) return;
      if (response.redirected) {
        window.location.assign(response.url);
        return;
      }
      if (!response.ok) throw new Error('Search unavailable');
      const markup = await response.text();
      if (currentRequest !== request || request.signal.aborted) return;
      results.innerHTML = markup;
      const count = results.querySelectorAll('[data-product]').length;
      status.textContent = `${count} produit${count > 1 ? 's' : ''} trouvé${count > 1 ? 's' : ''}.`;
      window.history.replaceState(null, '', url.pathname + url.search);
    } catch (error) {
      if (currentRequest === request && error.name !== 'AbortError') {
        status.textContent = 'La recherche n’a pas pu être actualisée. Appuyez sur Entrée pour réessayer.';
      }
    } finally {
      if (currentRequest === request) results.removeAttribute('aria-busy');
    }
  }

  input.addEventListener('input', () => {
    clearTimeout(timer);
    if (currentRequest) currentRequest.abort();
    timer = setTimeout(search, 200);
  });
  form.addEventListener('submit', event => {
    event.preventDefault();
    search();
  });
})();
