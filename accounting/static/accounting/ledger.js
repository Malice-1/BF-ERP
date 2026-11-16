(() => {
  const form = document.getElementById('ledger-entry-form');
  if (!form) return;
  const lines = document.getElementById('ledger-lines');
  const count = form.querySelector('[name="lines-TOTAL_FORMS"]');
  // Integer cents for the display preview. Authoritative calculations use Decimal server-side.
  const cents = value => {
    const match = /^(\d+)(?:[.,](\d{1,2}))?$/.exec(value.trim());
    return match ? BigInt(match[1]) * 100n + BigInt((match[2] || '').padEnd(2, '0')) : 0n;
  };
  const euros = value => `${value / 100n},${String(value % 100n).padStart(2, '0')}`;
  const preview = () => {
    let debit = 0n, credit = 0n;
    for (const row of lines.querySelectorAll('.ledger-line')) {
      if (row.querySelector('[name$="-DELETE"]')?.checked) continue;
      debit += cents(row.querySelector('[name$="-debit"]')?.value || '0');
      credit += cents(row.querySelector('[name$="-credit"]')?.value || '0');
    }
    document.getElementById('ledger-preview').textContent = `Débit : ${euros(debit)} EUR — Crédit : ${euros(credit)} EUR — ${debit === credit && debit > 0n ? 'Équilibre' : 'À équilibrer'}`;
  };
  document.getElementById('ledger-add-line').addEventListener('click', () => {
    const index = Number(count.value);
    if (index >= 200) return;
    lines.insertAdjacentHTML('beforeend', document.getElementById('ledger-empty-line').innerHTML.replaceAll('__prefix__', String(index)));
    count.value = index + 1;
    preview();
  });
  form.addEventListener('input', preview);
  preview();
})();
