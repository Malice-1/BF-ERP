const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../purchasing/static/purchasing/theme.js'), 'utf8');

function page({saved = null, dark = false, blocked = false} = {}) {
  const events = {}, documentEvents = {}, attributes = {}, nodes = {}, clicks = {}, messages = [];
  const storage = new Map(saved ? [['bf-erp-theme', saved]] : []);
  const button = {
    setAttribute: (key, value) => attributes[key] = value,
    querySelector: selector => nodes[selector] ||= {},
    addEventListener: (type, handler) => clicks[type] = handler,
  };
  const media = {matches: dark, addEventListener: (type, handler) => events.system = handler};
  const document = {
    documentElement: {dataset: {}},
    querySelectorAll: selector => selector === 'iframe'
      ? [{contentWindow: {postMessage: (...args) => messages.push(args)}}] : [button],
    addEventListener: (type, handler) => documentEvents[type] = handler,
  };
  const window = {matchMedia: () => media, addEventListener: (type, handler) => events[type] = handler};
  window.parent = {};
  vm.runInNewContext(source, {
    window, document, location: {origin: 'http://localhost'},
    localStorage: {
      getItem: key => { if (blocked) throw Error('blocked'); return storage.get(key) || null; },
      setItem: (key, value) => { if (blocked) throw Error('blocked'); storage.set(key, value); },
    },
  });
  documentEvents.DOMContentLoaded();
  return {document, window, events, attributes, nodes, clicks, messages, storage,
    theme: () => document.documentElement.dataset.theme};
}

test('uses system preference until a manual choice is saved', () => {
  const p = page({dark: true});
  assert.equal(p.theme(), 'dark');
  p.events.system({matches: false});
  assert.equal(p.theme(), 'light');
  p.clicks.click();
  assert.equal(p.theme(), 'dark');
  assert.equal(p.storage.get('bf-erp-theme'), 'dark');
  p.events.system({matches: false});
  assert.equal(p.theme(), 'dark');
  assert.equal(page({saved: p.storage.get('bf-erp-theme')}).theme(), 'dark');
});
test('toggle updates accessible state and embedded budget immediately', () => {
  const p = page({saved: 'light'});
  p.clicks.click();
  assert.equal(p.attributes['aria-pressed'], 'true');
  assert.equal(p.attributes['aria-label'], 'Activer le mode clair');
  assert.equal(p.nodes['[data-theme-label]'].textContent, 'Mode clair');
  assert.equal(p.messages[0][0].theme, 'dark');
  p.clicks.click();
  assert.equal(p.theme(), 'light');
  assert.equal(p.attributes['aria-pressed'], 'false');
});
test('keeps working when browser storage is blocked', () => {
  const p = page({blocked: true});
  p.clicks.click();
  assert.equal(p.theme(), 'dark');
});
test('synchronizes tabs and accepts budget messages only from its same-origin parent', () => {
  const p = page();
  p.events.storage({key: 'bf-erp-theme', newValue: 'dark'});
  assert.equal(p.theme(), 'dark');
  const event = {origin: 'https://other.example', source: p.window.parent, data: {type: 'bf-erp-theme', theme: 'light'}};
  p.events.message(event);
  assert.equal(p.theme(), 'dark');
  p.events.message({...event, origin: 'http://localhost', source: {}});
  assert.equal(p.theme(), 'dark');
  p.events.message({...event, origin: 'http://localhost'});
  assert.equal(p.theme(), 'light');
});
