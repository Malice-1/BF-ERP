(() => {
  const form = document.getElementById('sales-order-form');
  if (!form) return;
  const total = form.querySelector('[name="lines-TOTAL_FORMS"]');
  const lines = document.getElementById('sales-lines');
  const catalogue = JSON.parse(document.getElementById('sales-training-data').textContent);
  const numeric = (row, name) => Number(row.querySelector(`[name$="-${name}"]`)?.value.replace(',', '.') || 0);
  const round = value => Math.round((value + Number.EPSILON) * 100) / 100;
  const preview = () => {
    let subtotal = 0;
    const taxes = new Map();
    for (const row of lines.querySelectorAll('.sales-line')) {
      const deleted = row.querySelector('[name$="-DELETE"]')?.checked;
      row.style.opacity = deleted ? '.5' : '1';
      if (deleted) continue;
      const base = round(numeric(row, 'quantity') * numeric(row, 'unit_price') - numeric(row, 'discount'));
      const rate = numeric(row, 'tax_rate');
      const code = row.querySelector('[name$="-tax_code"]')?.value;
      const key = `${code}/${rate}`;
      subtotal += base;
      const group = taxes.get(key) || {base: 0, rate};
      group.base += base;
      taxes.set(key, group);
      row.querySelector('.line-preview').textContent = `Estimation HT : ${base.toFixed(2)} EUR`;
    }
    const vat = [...taxes.values()].reduce((sum, group) => sum + round(group.base * group.rate / 100), 0);
    document.getElementById('sales-total-preview').textContent = `Estimation : HT ${subtotal.toFixed(2)} — TVA ${vat.toFixed(2)} — TTC ${(subtotal + vat).toFixed(2)} EUR`;
  };
  document.getElementById('sales-add-line').addEventListener('click', () => {
    const count = Number(total.value);
    if (count >= 100) return;
    lines.insertAdjacentHTML('beforeend', document.getElementById('sales-empty-line').innerHTML.replaceAll('__prefix__', String(count)));
    total.value = count + 1;
    preview();
  });
  form.addEventListener('input', preview);
  form.addEventListener('change', event => {
    if (event.target.name?.endsWith('-service')) {
      const training = catalogue.find(item => String(item.id) === event.target.value);
      if (training) {
        const row = event.target.closest('.sales-line');
        row.querySelector('[name$="-description"]').value = training.description;
        row.querySelector('[name$="-unit"]').value = training.unit;
        preview();
      }
    }
  });
  preview();
})();
