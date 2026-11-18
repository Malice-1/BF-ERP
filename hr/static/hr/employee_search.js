(() => {
    const form = document.getElementById('employee-search');
    const input = form.elements.q;
    const filter = form.elements.status;
    const results = document.getElementById('employee-results');
    const status = document.getElementById('employee-search-status');
    let request;
    let timer;

    async function refresh() {
        const controller = new AbortController();
        request = controller;
        const url = new URL(form.action);
        if (input.value.trim()) url.searchParams.set('q', input.value.trim());
        if (filter.value) url.searchParams.set('status', filter.value);
        results.setAttribute('aria-busy', 'true');

        try {
            const response = await fetch(url, {
                headers: {'X-Requested-With': 'XMLHttpRequest'},
                signal: controller.signal,
                cache: 'no-store',
            });
            if (controller.signal.aborted) return;
            if (response.redirected) {
                window.location.assign(response.url);
                return;
            }
            if (!response.ok) throw new Error('Recherche indisponible');
            const markup = await response.text();
            if (controller.signal.aborted) return;
            results.innerHTML = markup;
            const count = Number(results.querySelector('[data-result-count]').dataset.resultCount);
            status.textContent = count === 1 ? '1 employé trouvé.' : `${count} employés trouvés.`;
            window.history.replaceState(null, '', url.pathname + url.search);
        } catch (error) {
            if (!controller.signal.aborted) {
                status.textContent = 'Recherche indisponible. Appuyez sur Entrée pour réessayer.';
            }
        } finally {
            if (request === controller) results.removeAttribute('aria-busy');
        }
    }

    function cancelRefresh() {
        clearTimeout(timer);
        if (request) request.abort();
    }

    input.addEventListener('input', () => {
        cancelRefresh();
        timer = setTimeout(refresh, 200);
    });
    filter.addEventListener('change', () => {
        cancelRefresh();
        refresh();
    });
})();
