(() => {
  const form = document.getElementById('allocation-search');
  if (!form || !window.fetch || !window.AbortController) return;
  const input = form.querySelector('input[name="q"]');
  const field = form.elements.field;
  const results = document.getElementById('allocation-results');
  const status = document.getElementById('allocation-search-status');
  const progress = document.getElementById('allocation-search-progress');
  let timer;
  let currentRequest;
  let dirty = results.querySelector('#budget-allocations')?.dataset.unsaved === 'true';

  function stop() {
    clearTimeout(timer);
    if (currentRequest) currentRequest.abort();
    progress.hidden = true;
    results.removeAttribute('aria-busy');
  }

  function warnUnsaved() {
    status.textContent = 'Enregistrez vos modifications avant de rechercher ou de changer de page.';
  }

  function markDirty(event) {
    if (!event.target.closest('#budget-allocations')) return;
    dirty = true;
    if (currentRequest && !currentRequest.signal.aborted) {
      stop();
      warnUnsaved();
    }
  }
  results.addEventListener('input', markDirty);
  results.addEventListener('change', markDirty);

  async function load(url) {
    stop();
    if (dirty) {
      warnUnsaved();
      return;
    }
    const request = new AbortController();
    currentRequest = request;
    status.textContent = 'Chargement des allocations…';
    progress.hidden = false;
    results.setAttribute('aria-busy', 'true');
    try {
      const response = await fetch(url, {signal: request.signal,
        headers: {'X-Requested-With': 'XMLHttpRequest'}, cache: 'no-store'});
      if (currentRequest !== request || request.signal.aborted || dirty) return;
      if (response.redirected) {
        window.location.assign(response.url);
        return;
      }
      if (!response.ok) throw new Error('Search unavailable');
      const markup = await response.text();
      if (currentRequest !== request || request.signal.aborted || dirty) return;
      results.innerHTML = markup;
      dirty = false;
      input.value = url.searchParams.get('q') || '';
      field.value = url.searchParams.get('field') || '';
      input.placeholder = field.selectedOptions[0].textContent;
      document.dispatchEvent(new Event('budget-allocations:updated'));
      window.history.replaceState(null, '', url.pathname + url.search);
      const exportLink = document.getElementById('allocation-export');
      if (exportLink) {
        const exportUrl = new URL(url);
        exportUrl.searchParams.set('export', 'xlsx');
        exportUrl.searchParams.delete('page');
        exportLink.href = exportUrl.href;
      }
      status.textContent = 'Allocations et totaux actualisés.';
    } catch (error) {
      if (currentRequest === request && error.name !== 'AbortError') {
        status.textContent = 'La recherche n’a pas pu être actualisée. Appuyez sur Entrée pour réessayer.';
      }
    } finally {
      if (currentRequest === request) {
        results.removeAttribute('aria-busy');
        progress.hidden = true;
        currentRequest = null;
      }
    }
  }

  function search() {
    const url = new URL(form.action, window.location.href);
    for (const [key, value] of new FormData(form)) {
      if (value.trim()) url.searchParams.set(key, value.trim());
    }
    load(url);
  }
  function queueSearch() {
    stop();
    timer = setTimeout(search, 200);
  }
  input.addEventListener('input', event => {
    if (!event.isComposing) queueSearch();
  });
  input.addEventListener('compositionend', queueSearch);
  field.addEventListener('change', () => {
    input.placeholder = field.selectedOptions[0].textContent;
    search();
  });
  form.addEventListener('submit', event => {
    event.preventDefault();
    search();
  });
  results.addEventListener('click', event => {
    const link = event.target.closest('a[data-allocation-page]');
    if (!link || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    load(new URL(link.href));
  });
  results.addEventListener('submit', event => {
    const jump = event.target.closest('form[data-allocation-page-jump]');
    if (!jump) return;
    event.preventDefault();
    if (!jump.reportValidity()) return;
    const url = new URL(jump.action, window.location.href);
    new FormData(jump).forEach((value, key) => url.searchParams.set(key, value));
    load(url);
  });
})();
