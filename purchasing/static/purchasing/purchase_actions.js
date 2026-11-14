(() => {
    const errorDialog = document.getElementById('purchase-error-dialog');
    if (!errorDialog) return;
    const message = document.getElementById('purchase-error-message');
    const title = document.getElementById('purchase-error-title');

    let printFrame = null;
    document.querySelectorAll('[data-print-order]').forEach(link => {
        link.addEventListener('click', event => {
            event.preventDefault();
            if (link.getAttribute('aria-busy') === 'true') return;
            link.setAttribute('aria-busy', 'true');
            if (printFrame) printFrame.remove();
            const frame = document.createElement('iframe');
            printFrame = frame;
            frame.title = 'Impression du bon de commande';
            frame.setAttribute('aria-hidden', 'true');
            frame.tabIndex = -1;
            frame.style.cssText = 'position:fixed;left:-10000px;top:0;width:1100px;height:800px;border:0';
            frame.addEventListener('load', async () => {
                try {
                    if (!frame.contentDocument.getElementById('order-print-document')) throw new Error('Document inaccessible');
                    await frame.contentDocument.fonts.ready;
                    frame.contentWindow.addEventListener('afterprint', () => frame.remove(), {once: true});
                    frame.contentWindow.focus();
                    frame.contentWindow.print();
                } catch (_) {
                    title.textContent = 'Impression impossible';
                    message.textContent = 'Le bon de commande n’a pas pu être chargé. Rechargez la demande puis réessayez.';
                    errorDialog.showModal();
                    frame.remove();
                } finally { link.removeAttribute('aria-busy'); }
            }, {once: true});
            frame.src = link.href;
            document.body.appendChild(frame);
        });
    });
    const inFlight = new WeakSet();
    const send = async (form, button, decision) => {
        if (inFlight.has(form)) return;
        inFlight.add(form);
        button.disabled = true;
        const body = new FormData(form);
        if (decision) body.set('decision', decision);
        try {
            const response = await fetch(form.action, {
                method: 'POST', body, headers: {Accept: 'application/json'}, credentials: 'same-origin'
            });
            if (response.redirected) { window.location.assign(response.url); return; }
            const data = await response.json();
            if (response.ok && data.redirect) { window.location.assign(data.redirect); return; }
            title.textContent = decision ? 'Validation impossible' : 'Soumission impossible';
            message.textContent = (data.errors || ['Action impossible. Rechargez la demande avant de réessayer.']).join(String.fromCharCode(10));
            errorDialog.showModal();
        } catch (_) {
            title.textContent = 'Action non confirmée';
            message.textContent = 'Rechargez la demande pour vérifier son état avant de réessayer.';
            errorDialog.showModal();
        } finally { button.disabled = false; inFlight.delete(form); }
    };
    document.querySelectorAll('[data-purchase-submit]').forEach(form => {
        form.addEventListener('submit', event => {
            event.preventDefault();
            send(form, event.submitter || form.querySelector('button[type="submit"]'));
        });
    });
    const dialog = document.getElementById('purchase-decision-dialog');
    const reason = document.getElementById('purchase-decision-reason');
    let pending = null;
    const labels = {approve: 'Valider', approve_all: 'Valider tout le circuit', correct: 'Retourner pour correction', reject: 'Rejeter'};
    document.querySelectorAll('[data-purchase-decision]').forEach(form => {
        form.addEventListener('submit', event => {
            event.preventDefault();
            const button = event.submitter;
            if (!button || !labels[button.value] || inFlight.has(form)) return;
            pending = {form, button, decision: button.value};
            const approving = ['approve', 'approve_all'].includes(button.value);
            document.getElementById('purchase-decision-title').textContent = labels[button.value];
            document.getElementById('purchase-decision-description').textContent = button.value === 'approve_all'
                ? 'Toutes les validations restantes de toutes les lignes seront approuvées en votre nom. Confirmer ?'
                : button.value === 'approve' ? 'Confirmer la validation de cette ligne ?'
                : button.value === 'correct' ? 'Toute la demande sera retournée pour correction. Indiquez le motif.'
                : 'Toute la demande sera rejetée définitivement. Indiquez le motif.';
            document.getElementById('purchase-decision-reason-label').hidden = approving;
            reason.required = !approving;
            reason.value = '';
            reason.setCustomValidity('');
            dialog.showModal();
            (approving ? document.getElementById('purchase-decision-confirm-button') : reason).focus();
        });
    });
    reason.addEventListener('input', () => reason.setCustomValidity(''));
    document.getElementById('purchase-decision-close').addEventListener('click', () => dialog.close());
    dialog.addEventListener('close', () => { pending = null; });
    document.getElementById('purchase-decision-confirm').addEventListener('submit', event => {
        event.preventDefault();
        if (!pending) return;
        if (reason.required && !reason.value.trim()) {
            reason.setCustomValidity('Veuillez renseigner un motif.'); reason.reportValidity(); return;
        }
        const {form, button, decision} = pending;
        form.elements.reason.value = reason.required ? reason.value.trim() : '';
        dialog.close();
        send(form, button, decision);
    });
})();
