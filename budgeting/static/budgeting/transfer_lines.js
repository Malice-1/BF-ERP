(() => {
  const form = document.getElementById('transfer-lines-form');
  if (!form) return;
  const rows = document.getElementById('transfer-lines');
  const total = form.querySelector('[name="lines-TOTAL_FORMS"]');
  const add = document.getElementById('add-transfer-line');
  const template = document.getElementById('transfer-empty-row');
  const destinationTotal = document.getElementById('transfer-destination-total');
  function updateAmount() {
    let cents = 0n;
    let valid = true;
    rows.querySelectorAll('[data-transfer-row]:not([hidden])').forEach(row => {
      const input = row.querySelector('[name$="-amount"]');
      if (input.validity.badInput) valid = false;
      const value = input.value.trim().replace(',', '.');
      if (!value) return;
      const match = /^(\d+)(?:\.(\d{1,2}))?$/.exec(value);
      if (!match) { valid = false; return; }
      cents += BigInt(match[1]) * 100n + BigInt((match[2] || '').padEnd(2, '0'));
    });
    const euros = (cents / 100n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    const fraction = (cents % 100n).toString().padStart(2, '0').replace(/0+$/, '');
    destinationTotal.value = valid ? euros + (fraction ? ',' + fraction : '') : '\u2014';
  }
  rows.addEventListener('input', updateAmount);
  add.addEventListener('click', () => {
    const index = Number(total.value);
    if (index >= 100) return;
    rows.insertAdjacentHTML('beforeend', template.innerHTML.replaceAll('__prefix__', String(index)));
    total.value = index + 1;
    add.disabled = index + 1 >= 100;
    rows.lastElementChild.querySelector('select').focus();
    updateAmount();
  });
  function retire(row) {
    row.hidden = true;
    row.querySelectorAll('input, select, textarea').forEach(field => {
      if (field.name.endsWith('-DELETE')) field.checked = true;
      else field.disabled = true;
    });
  }
  rows.querySelectorAll('[data-transfer-row][hidden]').forEach(retire);
  rows.addEventListener('click', event => {
    const button = event.target.closest('[data-remove-transfer]');
    if (button) {
      retire(button.closest('[data-transfer-row]'));
      updateAmount();
    }
  });
  updateAmount();
})();
