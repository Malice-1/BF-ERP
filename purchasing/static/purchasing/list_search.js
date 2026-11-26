(() => {
    document.querySelectorAll('form[data-list-search]').forEach(form => {
        const input = form.elements.q;
        const field = form.elements.field || form.elements.search_column;
        const admin = form.hasAttribute('data-admin-search');
        let results = document.querySelector(form.dataset.listSearch);
        if (!input || !results) return;
        if (field) input.placeholder = field.selectedOptions[0].textContent.trim();
        const status = document.createElement('p');
        status.className = 'table-search-status';
        status.setAttribute('role', 'status');
        results.before(status);
        let timer;
        let pending;
        let dirty = false;

        function markDirty(event) {
            if (admin && results.contains(event.target)) {
                pending?.abort();
                results.removeAttribute('aria-busy');
                if (!event.target.matches('.action-select, #action-toggle') && !event.target.closest('.actions')) {
                    dirty = true;
                }
            }
        }

        if (admin) {
            results.parentElement.addEventListener('input', markDirty);
            results.parentElement.addEventListener('change', markDirty);
        }

        function updateAdmin(doc, updated) {
            results.replaceWith(updated);
            results = updated;
            const checkboxes = results.querySelectorAll('tr input.action-select');
            if (checkboxes.length && window.Actions) window.Actions(checkboxes);
            for (const selector of ['#admin-search-count', '.xfull.toplinks', '#changelist-filter']) {
                const before = document.querySelector(selector);
                const after = doc.querySelector(selector);
                if (!before || !after) continue;
                if (selector === '#changelist-filter') {
                    const links = [...after.querySelectorAll('a')];
                    const previous = [...before.querySelectorAll('a')];
                    if (previous.length === links.length) {
                        previous.forEach((link, index) => {
                            link.setAttribute('href', links[index].getAttribute('href'));
                            link.textContent = links[index].textContent;
                        });
                        continue;
                    }
                }
                before.replaceWith(after);
            }
        }

        async function refresh() {
            if (dirty || (admin && results.querySelector('.action-select:checked, .actions select[name="action"] option:checked:not([value=""])'))) {
                status.textContent = 'Enregistrez vos modifications ou terminez l’action en cours avant de rechercher.';
                return;
            }
            const controller = new AbortController();
            pending = controller;
            const url = new URL(form.action);
            url.search = '';
            for (const [key, value] of new FormData(form)) {
                if (value.trim()) url.searchParams.append(key, value.trim());
            }
            results.setAttribute('aria-busy', 'true');
            try {
                const response = await fetch(url, {signal: controller.signal, cache: 'no-store'});
                if (controller.signal.aborted) return;
                if (response.redirected || response.status === 403) {
                    window.location.assign(response.url);
                    return;
                }
                if (!response.ok) throw new Error();
                const doc = new DOMParser().parseFromString(await response.text(), 'text/html');
                if (controller.signal.aborted) return;
                const updated = doc.querySelector(form.dataset.listSearch);
                if (!updated) {
                    window.location.assign(url);
                    return;
                }
                if (admin) updateAdmin(doc, updated);
                else results.replaceChildren(...updated.childNodes);
                for (const link of document.querySelectorAll('a[data-list-search-link][id]')) {
                    const replacement = doc.getElementById(link.id);
                    if (replacement) link.setAttribute('href', replacement.getAttribute('href'));
                }
                window.history.replaceState(null, '', url);
                status.textContent = 'Résultats actualisés.';
            } catch (error) {
                if (!controller.signal.aborted) status.textContent = 'La recherche a échoué. Appuyez sur Entrée pour réessayer.';
            } finally {
                if (pending === controller) results.removeAttribute('aria-busy');
            }
        }

        function queue(delay) {
            clearTimeout(timer);
            pending?.abort();
            timer = setTimeout(refresh, delay);
        }

        input.addEventListener('input', event => {
            if (!event.isComposing) queue(200);
        });
        input.addEventListener('compositionend', () => queue(200));
        form.addEventListener('change', event => {
            if (event.target === input) return;
            if (event.target === field) input.placeholder = field.selectedOptions[0].textContent.trim();
            queue(0);
        });
        form.addEventListener('submit', event => {
            event.preventDefault();
            queue(0);
        });
    });
})();
