(() => {
  const dialog = document.getElementById('transfer-action-dialog');
  const confirmation = document.getElementById('transfer-action-confirm');
  const reason = document.getElementById('transfer-action-reason');
  const reasonLabel = document.getElementById('transfer-action-reason-label');
  const submit = document.getElementById('transfer-action-submit');
  let pending = null;
  const confirmed = new WeakSet();
  const labels = {approve: 'Valider', approve_all: 'Valider tout le circuit', approve_batch: 'Valider toutes les lignes', return_batch: 'Refuser', cancel_batch: 'Annuler définitivement', reject: 'Refuser', cancel: 'Annuler'};

  document.addEventListener('submit', event => {
    const form = event.target;
    if (!form.matches('form[data-transfer-decision]')) return;
    if (confirmed.delete(form)) return;
    const button = event.submitter;
    if (!button || !labels[button.value]) return;
    event.preventDefault();
    pending = {form, button};
    const action = button.value;
    const approving = ['approve', 'approve_all', 'approve_batch'].includes(action);
    document.getElementById('transfer-action-title').textContent = `${labels[action]} le transfert`;
    document.getElementById('transfer-action-description').textContent = action === 'return_batch'
      ? 'Toutes les lignes seront renvoyées au demandeur pour correction, y compris celles masquées par les filtres. Indiquez le motif du refus.'
      : action === 'cancel_batch'
      ? 'Toutes les lignes seront définitivement annulées, y compris celles masquées par les filtres. Elles ne pourront plus être resoumises. Indiquez le motif.'
      : action === 'approve_batch'
      ? 'Confirmer la validation de toutes les lignes du transfert, y compris celles masquées par les filtres ? Toutes leurs étapes restantes seront validées en votre nom.'
      : action === 'approve_all'
      ? 'Confirmer la validation de toutes les étapes restantes de cette transaction ? Chaque étape sera validée en votre nom.'
      : action === 'approve'
      ? 'Confirmer la validation de cette étape du transfert ?'
      : 'Indiquez le motif de votre décision.';
    reasonLabel.hidden = approving;
    reason.required = ['reject', 'return_batch', 'cancel_batch'].includes(action) || (action === 'cancel' && form.dataset.reasonRequired !== 'false');
    reason.value = form.elements.reason.value;
    reason.setCustomValidity('');
    submit.textContent = labels[action];
    dialog.showModal();
    (approving ? submit : reason).focus();
  });
  reason.addEventListener('input', () => reason.setCustomValidity(''));
  document.getElementById('transfer-action-close').addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', () => { pending = null; });
  confirmation.addEventListener('submit', event => {
    event.preventDefault();
    if (!pending) return;
    if (reason.required && !reason.value.trim()) {
      reason.setCustomValidity('Veuillez renseigner un motif.');
      reason.reportValidity();
      return;
    }
    const {form, button} = pending;
    form.elements.reason.value = ['approve', 'approve_all', 'approve_batch'].includes(button.value) ? '' : reason.value.trim();
    confirmed.add(form);
    dialog.close();
    form.requestSubmit(button);
  });
})();
