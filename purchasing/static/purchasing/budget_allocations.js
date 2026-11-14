(() => {
  function initialize() {
  const form = document.getElementById('budget-allocations');
  if (!form || form.dataset.initialized) return;
  form.dataset.initialized = 'true';
  const referenceData = document.getElementById('allocation-reference-data');
  const references = referenceData ? JSON.parse(referenceData.textContent) : {};
  function expandReference(event) {
    const select = event.target.closest('select[data-allocation-reference]');
    if (!select || select.dataset.expanded) return;
    const options = references[select.dataset.allocationReference];
    if (!options) return;
    const current = select.value;
    const fragment = document.createDocumentFragment();
    options.forEach(([value, label]) => {
      const selected = String(value) === current;
      fragment.append(new Option(label, value, selected, selected));
    });
    select.replaceChildren(fragment);
    select.value = current;
    select.dataset.expanded = 'true';
  }
  form.addEventListener('focusin', expandReference);
  form.addEventListener('pointerdown', expandReference);
  const notice = document.getElementById('allocation-deletions');
  const status = document.getElementById('allocation-deletions-status');
  const undo = document.getElementById('allocation-deletions-undo');
  const selector = 'input[type="checkbox"][name$="-DELETE"]';
  const disabledStates = new WeakMap();

  function updateRow(checkbox) {
    const row = checkbox.closest('[data-allocation-row]');
    if (!row) return;
    if (checkbox.checked && !disabledStates.has(row)) {
      // Keep IDs and DELETE enabled so Django can confirm the deletion on save.
      // Disable only visible fields, avoiding hidden browser-validation errors.
      const controls = [...row.querySelectorAll('input:not([type="hidden"]), select, textarea')]
        .filter(control => control !== checkbox);
      disabledStates.set(row, controls.map(control => [control, control.disabled]));
      controls.forEach(control => { control.disabled = true; });
    } else if (!checkbox.checked && disabledStates.has(row)) {
      disabledStates.get(row).forEach(([control, disabled]) => { control.disabled = disabled; });
      disabledStates.delete(row);
    }
    row.hidden = checkbox.checked;
  }

  function refresh() {
    const checkboxes = [...form.querySelectorAll(selector)];
    checkboxes.forEach(updateRow);
    const count = checkboxes.filter(checkbox => checkbox.checked).length;
    notice.hidden = count === 0;
    status.textContent = count ? `${count} ligne${count > 1 ? 's' : ''} à supprimer. Enregistrez pour confirmer.` : '';
  }

  form.addEventListener('change', event => {
    if (event.target.matches(selector)) {
      refresh();
      if (event.target.checked) undo.focus();
    }
  });
  undo.addEventListener('click', () => {
    const checked = [...form.querySelectorAll(selector)].filter(checkbox => checkbox.checked);
    checked.forEach(checkbox => { checkbox.checked = false; });
    refresh();
    if (checked.length) checked[0].focus();
  });
  refresh();
  }
  document.addEventListener('budget-allocations:updated', initialize);
  initialize();
})();
