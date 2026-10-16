#!/usr/bin/env node
'use strict';
/**
 * DOM contract smoke tests. No server, browser installation, or network calls.
 * Run: node scripts/test_ui.cjs
 * Or: WORLDLINE_JSDOM_PATH=/absolute/path/to/node_modules/jsdom node scripts/test_ui.cjs
 * These tests verify DOM behavior, not rendered layout or native browser behavior.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM, VirtualConsole } = require(process.env.WORLDLINE_JSDOM_PATH || 'jsdom');
const root = path.resolve(__dirname, '..', 'dist');
const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
const app = fs.readFileSync(path.join(root, 'app.js'), 'utf8');
const dataset = JSON.parse(fs.readFileSync(path.join(root, 'data/demo.json'), 'utf8'));
const realDataset = JSON.parse(fs.readFileSync(path.join(root, 'data/gdelt_sample.json'), 'utf8'));
const settle = () => new Promise(resolve => setImmediate(resolve));
const response = data => ({ ok: true, status: 200, json: async () => data });
let passed = 0;

function createDOM(fetcher) {
  const errors = [];
  const virtualConsole = new VirtualConsole();
  virtualConsole.on('jsdomError', error => errors.push(error));
  const dom = new JSDOM(html, {
    url: 'https://worldline.example/', runScripts: 'outside-only', virtualConsole,
  });
  const window = dom.window;
  window.matchMedia = () => ({ matches: true });
  window.scrollTo = () => {};
  window.HTMLElement.prototype.scrollIntoView = () => {};
  // jsdom does not implement native modal behavior. Only open/close wiring is tested.
  window.HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  window.HTMLDialogElement.prototype.close = function () { this.open = false; };
  window.fetch = fetcher || (async url => response(url.includes('gdelt') ? realDataset : dataset));
  const intervals = new Map();
  let intervalId = 0;
  window.setInterval = callback => { intervals.set(++intervalId, callback); return intervalId; };
  window.clearInterval = id => intervals.delete(id);
  const document = window.document;
  const $ = id => document.getElementById(id);
  const click = selector => {
    const element = document.querySelector(selector);
    assert.ok(element, `Missing control: ${selector}`);
    element.click();
  };
  const change = (id, value, event = 'change') => {
    $(id).value = String(value);
    $(id).dispatchEvent(new window.Event(event, { bubbles: true }));
  };
  window.eval(app);
  return { dom, window, document, $, click, change, intervals, errors };
}

async function test(name, run) {
  await run();
  passed++;
  console.log(`PASS ${name}`);
}

(async () => {
  await test('loading is explicit; no content is fabricated while fetch is pending', async () => {
    let release;
    const ui = createDOM(() => new Promise(resolve => { release = resolve; }));
    try {
      assert.equal(ui.$('loading').hidden, false);
      assert.equal(ui.$('app').hidden, true);
      release(response(dataset));
      await settle();
      assert.equal(ui.$('loading').hidden, true);
      assert.equal(ui.$('app').hidden, false);
      assert.deepEqual(ui.errors, []);
    } finally { ui.dom.window.close(); }
  });

  await test('HTTP errors expose retry; retry loads real fixture', async () => {
    let attempts = 0;
    const ui = createDOM(async () => ++attempts === 1 ? { ok: false, status: 503 } : response(dataset));
    try {
      await settle();
      assert.equal(ui.$('load-error').hidden, false);
      assert.equal(ui.$('app').hidden, true);
      assert.match(ui.$('error-description').textContent, /503/);
      assert.match(ui.$('error-description').textContent, /No substitute data/);
      ui.click('#retry');
      await settle();
      assert.equal(attempts, 2);
      assert.equal(ui.$('load-error').hidden, true);
      assert.equal(ui.$('app').hidden, false);
      assert.deepEqual(ui.errors, []);
    } finally { ui.dom.window.close(); }
  });

  await test('actual metrics, dates, references, timeline, event tabs and replay controls', async () => {
    const ui = createDOM();
    try {
      await settle();
      const last = dataset.history.at(-1);
      assert.equal(ui.$('slider-date').textContent, last.date);
      assert.equal(ui.$('displacement').textContent, last.js_topic.toFixed(4));
      ui.change('reference', 'rolling');
      assert.equal(ui.$('displacement').textContent, last.rolling_js.toFixed(4));
      assert.equal(ui.document.querySelectorAll('#domain-bars .bar.reference').length, dataset.taxonomy.length);
      assert.match(ui.$('reference-detail').textContent, /excludes selected day/);
      assert.equal(ui.document.querySelectorAll('#forecast-uncertainty tbody tr').length, dataset.taxonomy.length);
      ui.click('[data-event-index]');
      assert.equal(ui.$('event-dialog').open, true);
      assert.match(ui.$('event-details').textContent, /SIMULATED EVIDENCE/);
      ui.click('#close-dialog');
      assert.equal(ui.$('event-dialog').open, false);
      ui.click('[data-tab="events"]');
      assert.equal(ui.$('events').hidden, false);
      assert.equal(ui.$('observatory').hidden, true);
      ui.change('event-date', 0);
      assert.equal(ui.$('slider-date').textContent, dataset.history[0].date);
      ui.change('event-filter', dataset.taxonomy[0].id);
      const expected = dataset.history[0].events.filter(event => event.domain === dataset.taxonomy[0].id).length;
      assert.equal(ui.document.querySelectorAll('#event-log .event-card').length, expected);
      ui.click('[data-tab="observatory"]');
      ui.click('[data-range="all"]');
      ui.$('chart').getBoundingClientRect = () => ({ left: 0, width: 1000 });
      ui.$('chart').dispatchEvent(new ui.window.MouseEvent('click', { clientX: 984, bubbles: true }));
      assert.equal(ui.$('slider-date').textContent, last.date);
      ui.click('[data-metric="surprise"]');
      assert.match(ui.$('chart-label').textContent, /DESCRIPTIVE RANK/);
      for (const range of ['7', '30', '90', 'all']) ui.click(`[data-range="${range}"]`);
      for (const index of [0, Math.floor(dataset.history.length / 2), dataset.history.length - 1]) {
        ui.change('date-slider', index, 'input');
        assert.equal(ui.$('slider-date').textContent, dataset.history[index].date);
        assert.doesNotMatch(ui.$('chart').innerHTML, /NaN|Infinity/);
      }
      ui.click('#play');
      assert.equal(ui.$('slider-date').textContent, dataset.history[0].date);
      assert.equal(ui.intervals.size, 1);
      [...ui.intervals.values()][0]();
      assert.equal(ui.$('slider-date').textContent, dataset.history[1].date);
      ui.click('#play');
      assert.equal(ui.intervals.size, 0);
      assert.deepEqual(ui.errors, []);
    } finally { ui.dom.window.close(); }
  });

  await test('null estimates stay unavailable and missing intervals do not invent values', async () => {
    const row = { ...dataset.history[0], events: [], topic_shares: null, reference_shares: null,
      rolling_reference_shares: null, js_topic: null, rolling_js: null, transport_cost: null,
      rolling_transport: null, surprise_percentile: null, forecast_shares: null,
      forecast_share_interval_80: null, coverage_warnings: null, coverage_ok: false };
    const fixture = { ...dataset, history: [row] };
    const ui = createDOM(async () => response(fixture));
    try {
      await settle();
      assert.equal(ui.$('app').hidden, false);
      assert.equal(ui.$('surprise').textContent, '—');
      assert.equal(ui.$('displacement').textContent, '—');
      assert.match(ui.$('forecast-uncertainty').textContent, /unavailable/);
      assert.ok([...ui.document.querySelectorAll('.domain-share')].every(el => el.textContent === '—'));
      ui.change('reference', 'rolling');
      assert.equal(ui.document.querySelectorAll('.bar.reference').length, 0);
      ui.click('[data-metric="surprise"]');
      assert.match(ui.$('chart').textContent, /Insufficient history/);
      assert.doesNotMatch(ui.$('chart').innerHTML, /NaN|Infinity/);
      assert.deepEqual(ui.errors, []);
    } finally { ui.dom.window.close(); }
  });

  await test('actual GDELT archive sample stays isolated and is searchable and paginated', async () => {
    const ui = createDOM();
    try {
      await settle();
      const priorScore = ui.$('displacement').textContent;
      ui.click('[data-tab="real-data"]');
      await settle();
      assert.equal(ui.$('real-content').hidden, false);
      assert.equal(ui.$('observatory').hidden, true);
      const events = realDataset.history.at(-1).events;
      assert.equal(ui.document.querySelectorAll('.real-record').length, Math.min(15, events.length));
      for (const link of ui.document.querySelectorAll('.real-record a, #real-archives a')) {
        assert.match(link.href, /^https?:\/\//);
        assert.equal(link.rel, 'noopener noreferrer');
      }
      if (events.length > 15) {
        ui.click('#real-next');
        assert.match(ui.$('real-page').textContent, /^2 \//);
        ui.click('#real-previous');
        assert.match(ui.$('real-page').textContent, /^1 \//);
      }
      ui.change('real-search', '__NO_MATCHING_ACTOR_983105__', 'input');
      assert.match(ui.$('real-records').textContent, /No records match/);
      ui.change('real-search', '', 'input');
      assert.equal(ui.$('displacement').textContent, priorScore);
      assert.match(ui.$('real-stats').textContent, /unavailable/);
      assert.deepEqual(ui.errors, []);
    } finally { ui.dom.window.close(); }
  });

  await test('unsafe publisher URLs and markup are inert; null real metadata is tolerated', async () => {
    const fixture = { mode: 'historical_sample', history: [{ date: '2025-01-01', events: [
      { id: 'unsafe', label: '<img src=x onerror="alert(1)">', source_url: 'javascript:alert(1)', credibility_flags: null, event_time_utc: null, available_at_utc: null },
      { id: 'safe', label: 'Actor → action', source_url: 'https://example.org/source', publisher: null },
    ] }], archives: [{ url: 'data:text/html,unsafe' }], methodology: null };
    const ui = createDOM(async url => response(url.includes('gdelt') ? fixture : dataset));
    try {
      await settle();
      ui.click('[data-tab="real-data"]');
      await settle();
      assert.equal(ui.$('real-content').hidden, false);
      assert.equal(ui.document.querySelectorAll('#real-records img').length, 0);
      assert.equal(ui.document.querySelectorAll('#real-records a').length, 1);
      assert.equal(ui.document.querySelector('#real-records a').href, 'https://example.org/source');
      assert.equal(ui.document.querySelectorAll('#real-archives a').length, 0);
      assert.match(ui.$('real-records').textContent, /Occurrence: Unknown/);
      assert.match(ui.$('real-records').textContent, /No usable publisher URL/);
      assert.deepEqual(ui.errors, []);
    } finally { ui.dom.window.close(); }
  });

  console.log(`\n${passed} DOM smoke tests passed. No browser or visual layout verification performed.`);
})().catch(error => { console.error(error); process.exitCode = 1; });
