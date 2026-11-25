(() => {
    const form = document.getElementById('purchase-request-filter');
    const field = form.elements.field;
    const input = form.elements.q;
    const results = document.getElementById('purchase-request-results');
    const status = document.getElementById('purchase-request-filter-status');
    const exportLink = document.querySelector('#purchase-request-export a');
    let pending;
    let timer;

    async function refresh() {
        const controller = new AbortController();
        pending = controller;
        const url = new URL(form.action);
        if (field.value) url.searchParams.set('field', field.value);
        if (input.value.trim()) url.searchParams.set('q', input.value.trim());
        results.setAttribute('aria-busy', 'true');
        try {
            const response = await fetch(url, {
                headers: {'X-Requested-With': 'XMLHttpRequest'},
                signal: controller.signal,
                cache: 'no-store',
            });
            if (controller.signal.aborted) return;
            if (response.redirected || response.status === 403) {
                window.location.assign(response.url);
                return;
            }
            if (!response.ok) throw new Error('Recherche indisponible');
            if (response.headers.get('X-Purchase-Request-Results') !== '1') {
                window.location.assign(url);
                return;
            }
            const markup = await response.text();
            if (controller.signal.aborted) return;
            results.innerHTML = markup;
            const count = results.querySelectorAll('[data-purchase-request]').length;
            status.textContent = count === 1 ? '1 demande affichée.' : `${count} demandes affichées.`;
            window.history.replaceState(null, '', url);
            url.searchParams.set('export', 'xlsx');
            exportLink.href = url;
        } catch (error) {
            if (!controller.signal.aborted) status.textContent = 'La recherche a échoué. Appuyez sur Entrée pour réessayer.';
        } finally {
            if (pending === controller) results.removeAttribute('aria-busy');
        }
    }

    function queueRefresh(delay) {
        clearTimeout(timer);
        pending?.abort();
        timer = setTimeout(refresh, delay);
    }

    input.addEventListener('input', event => {
        if (!event.isComposing) queueRefresh(200);
    });
    input.addEventListener('compositionend', () => queueRefresh(200));
    field.addEventListener('change', () => {
        input.placeholder = field.selectedOptions[0].textContent;
        queueRefresh(0);
    });
    form.addEventListener('submit', event => {
        event.preventDefault();
        queueRefresh(0);
    });
})();
