(() => {
  const form = document.getElementById('allocation-import-form');
  if (!form || !window.XMLHttpRequest || !window.FormData) return;
  const button = document.getElementById('allocation-import-submit');
  const progress = document.getElementById('allocation-import-progress');
  const bar = document.getElementById('allocation-import-bar');
  const status = document.getElementById('allocation-import-status');
  const result = document.getElementById('allocation-import-result');
  let busy = false;

  function showResult(success, messages) {
    result.replaceChildren();
    result.className = success ? 'allocation-import-success' : 'login-error';
    result.setAttribute('role', success ? 'status' : 'alert');
    messages.forEach(message => {
      const paragraph = document.createElement('p');
      paragraph.textContent = message;
      result.append(paragraph);
    });
    result.hidden = false;
    result.focus();
  }

  function processing() {
    bar.removeAttribute('value');
    status.textContent = 'Fichier transmis. Vérification et enregistrement des allocations en cours…';
  }

  form.addEventListener('submit', event => {
    event.preventDefault();
    if (busy) return;
    if (!form.reportValidity()) return;
    const data = new FormData(form);
    busy = true;
    button.disabled = true;
    button.textContent = 'Import en cours…';
    form.setAttribute('aria-busy', 'true');
    result.hidden = true;
    progress.hidden = false;
    bar.value = 0;
    status.textContent = 'Envoi du fichier…';

    const xhr = new XMLHttpRequest();
    xhr.open('POST', form.action);
    xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
    xhr.responseType = 'json';
    xhr.upload.addEventListener('progress', event => {
      if (!event.lengthComputable) return;
      bar.value = Math.round(event.loaded / event.total * 100);
      status.textContent = `Envoi du fichier : ${bar.value} %`;
      if (event.loaded === event.total) processing();
    });
    xhr.upload.addEventListener('load', processing);
    xhr.addEventListener('load', () => {
      const payload = xhr.response;
      if (xhr.status >= 200 && xhr.status < 300 && payload && payload.ok) {
        showResult(true, [payload.message]);
      } else if (payload && Array.isArray(payload.errors)) {
        showResult(false, ['Import impossible. Aucune modification enregistrée.', ...payload.errors]);
      } else if (xhr.status === 403 || xhr.responseURL.includes('/connexion/')) {
        showResult(false, ['Votre session ou vos droits ne permettent plus cet import. Reconnectez-vous et rechargez la page.']);
      } else {
        showResult(false, ['Le résultat de l’import n’a pas pu être confirmé. Vérifiez la version budgétaire avant de réessayer.']);
      }
    });
    xhr.addEventListener('error', () => showResult(false, [
      'La connexion a été interrompue. Vérifiez la version budgétaire avant de réessayer.'
    ]));
    xhr.addEventListener('loadend', () => {
      busy = false;
      button.disabled = false;
      button.textContent = 'Importer les allocations';
      form.removeAttribute('aria-busy');
      progress.hidden = true;
    });
    xhr.send(data);
  });
})();
