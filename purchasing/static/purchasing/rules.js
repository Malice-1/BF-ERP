(() => {
  const form = document.getElementById('rule-editor');
  const catalog = JSON.parse(document.getElementById('condition-catalog').textContent);
  const rows = document.getElementById('condition-rows');
  const operators = {eq:'est égal à', ne:'est différent de', gte:'est supérieur ou égal à',gt:'est supérieur à',lte:'est inférieur ou égal à',lt:'est inférieur à'};
  const target = form.querySelector('#id_target');
  const always = form.querySelector('#id_unconditional');
  function sentence() {
    form.querySelectorAll('[data-target]').forEach(node => node.hidden = node.dataset.target !== target.value);
    const conditions = [...rows.querySelectorAll('.condition-row')].filter(row => !row.querySelector('[name$="-DELETE"]').checked).map(row => {
      const field = row.querySelector('[name$="-field"]');
      const op = row.querySelector('[name$="-op"]');
      const value = row.querySelector('[name$="-value"]');
      if (!field.value || !value.value) return '';
      return `${catalog[field.value].label} ${operators[op.value]} ${value.tagName === 'SELECT' ? value.selectedOptions[0].textContent : value.value}`;
    }).filter(Boolean);
    const joiner = document.getElementById('id_junction').value === 'all' ? ' ET ' : ' OU ';
    const detail = {role:'id_role',user:'id_named_user'}[target.value];
    const choice = detail ? document.getElementById(detail) : null;
    const who = target.selectedOptions[0].textContent + (choice?.value ? ` « ${choice.selectedOptions[0].textContent} »` : '');
    document.getElementById('rule-sentence').textContent = `${always.checked ? 'Pour toutes les lignes' : 'Si ' + (conditions.join(joiner) || '…')}, alors faire valider par ${who.toLocaleLowerCase('fr')}, à l’ordre ${document.getElementById('id_level').value || '1'}.`;
  }
  function updateField(row) {
    const field = catalog[row.querySelector('[name$="-field"]').value];
    const old = row.querySelector('[name$="-value"]');
    const input = document.createElement(field?.kind === 'reference' ? 'select' : 'input');
    input.name = old.name; input.id = old.id;
    if (field?.kind === 'reference') {
      input.add(new Option('Choisir une valeur', ''));
      field.choices.forEach(([id,label]) => input.add(new Option(label,id)));
    } else { input.type='number'; input.min='0'; input.step='any'; }
    old.replaceWith(input);
    const op = row.querySelector('[name$="-op"]');
    const previous = op.value;
    op.replaceChildren();
    Object.entries(operators).filter(([key]) => field?.kind !== 'reference' || ['eq','ne'].includes(key)).forEach(([key,label])=>op.add(new Option(label,key)));
    op.value = [...op.options].some(option=>option.value===previous) ? previous : 'eq';
    sentence();
  }
  rows.addEventListener('change', event => {
    if (event.target.name?.endsWith('-field')) updateField(event.target.closest('.condition-row'));
    sentence();
  });
  document.getElementById('add-condition').addEventListener('click', () => {
    const total = document.getElementById('id_conditions-TOTAL_FORMS');
    if (+total.value >= 50) return;
    const template = document.getElementById('empty-condition').innerHTML.replaceAll('__prefix__',total.value);
    rows.insertAdjacentHTML('beforeend',template); total.value=+total.value+1;
    rows.lastElementChild.querySelector('select').focus();
  });
  form.addEventListener('input', sentence);
  form.addEventListener('change', sentence);
  sentence();
})();
