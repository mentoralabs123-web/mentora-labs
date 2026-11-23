/* Mentora Labs — Projects page: category filter + search + details dialog.
   Reads project data from the JSON block rendered by the template, so the
   dialog never duplicates text that lives in Python/the database. */
(function () {
  'use strict';

  var $ = function (sel, ctx) { return (ctx || document).querySelector(sel); };
  var $$ = function (sel, ctx) { return Array.prototype.slice.call((ctx || document).querySelectorAll(sel)); };

  var grid = $('#projectGrid');
  if (!grid) return;

  /* ---------- State ---------- */
  var cards = $$('.pcard', grid);
  var filterBtns = $$('[data-cat]');
  var searchInput = $('#projectSearch');
  var countEl = $('#filterCount');
  var emptyEl = $('#projectEmpty');
  var noticeEl = $('#pathNotice');
  var total = cards.length;
  var state = { cat: 'all', q: '', group: null };

  /* ---------- Filtering ---------- */
  function normalise(s) { return String(s || '').toLowerCase().replace(/\s+/g, ' ').trim(); }

  function apply() {
    var terms = normalise(state.q).split(' ').filter(Boolean);
    var shown = 0;
    cards.forEach(function (card) {
      var cats = (card.getAttribute('data-cats') || '').split(' ');
      var okCat = state.cat === 'all' || cats.indexOf(state.cat) !== -1;
      var okGroup = !state.group || card.getAttribute('data-group') === state.group;
      var hay = card.getAttribute('data-search') || '';
      var okQuery = terms.every(function (t) { return hay.indexOf(t) !== -1; });
      var match = okCat && okGroup && okQuery;
      if (match && card.hidden) {
        card.hidden = false;
        card.classList.remove('is-entering');
        void card.offsetWidth; /* restart the short fade-in */
        card.classList.add('is-entering');
      } else if (!match) {
        card.hidden = true;
        card.classList.remove('is-entering');
      }
      if (match) shown++;
    });
    filterBtns.forEach(function (b) {
      b.setAttribute('aria-pressed', String(b.getAttribute('data-cat') === state.cat));
    });
    countEl.textContent = 'Showing ' + shown + ' of ' + total + (total === 1 ? ' project' : ' projects');
    emptyEl.hidden = shown !== 0;
    grid.hidden = shown === 0;
  }

  filterBtns.forEach(function (btn) {
    btn.addEventListener('click', function () {
      state.cat = btn.getAttribute('data-cat');
      apply();
    });
  });
  if (searchInput) {
    searchInput.addEventListener('input', function () { state.q = searchInput.value; apply(); });
    searchInput.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && searchInput.value) { searchInput.value = ''; state.q = ''; apply(); }
    });
  }

  function clearAll() {
    state.cat = 'all'; state.q = ''; state.group = null;
    if (searchInput) searchInput.value = '';
    showNotice(null);
    apply();
  }
  var clearBtn = $('#clearFilters');
  if (clearBtn) clearBtn.addEventListener('click', function () { clearAll(); if (searchInput) searchInput.focus(); });

  /* Legacy links from Home / About / Learning use ?path=<learning group>.
     Keep them working: filter by that group and say so, with a way back. */
  function showNotice(title) {
    if (!noticeEl) return;
    noticeEl.textContent = '';
    if (!title) { noticeEl.hidden = true; return; }
    noticeEl.appendChild(document.createTextNode('Showing the ' + title + ' learning path. '));
    var b = document.createElement('button');
    b.type = 'button'; b.className = 'text-btn'; b.textContent = 'Show all projects';
    b.addEventListener('click', clearAll);
    noticeEl.appendChild(b);
    noticeEl.hidden = false;
  }
  (function readPathParam() {
    var wanted = new URLSearchParams(window.location.search).get('path');
    if (!wanted || !noticeEl) return;
    var groups = [];
    try { groups = JSON.parse(noticeEl.getAttribute('data-groups') || '[]'); } catch (e) { /* ignore */ }
    var match = groups.filter(function (g) { return g.key === wanted; })[0];
    if (match) { state.group = match.key; showNotice(match.title); }
  })();

  /* ---------- Details dialog ---------- */
  var data = {};
  try {
    JSON.parse($('#projectData').textContent).forEach(function (p) { data[p.key] = p; });
  } catch (e) { /* details just won't open without data */ }

  var dlg = $('#projectDialog');
  var elVisual = $('#pdVisual');
  var elTitle = $('#pdTitle');
  var elCats = $('#pdCats');
  var elContent = $('#pdContent');
  var enquireBtn = $('#pdEnquire');
  var lastTrigger = null;
  var currentKey = null;

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  function section(heading, child) {
    var s = el('section', 'pd__section');
    s.appendChild(el('h3', null, heading));
    s.appendChild(child);
    return s;
  }
  function textBlock(value) {
    var wrap = el('div', 'pd__text');
    (Array.isArray(value) ? value : [value]).forEach(function (para) { wrap.appendChild(el('p', null, para)); });
    return wrap;
  }
  function listBlock(items, cls) {
    var ul = el('ul', cls);
    items.forEach(function (i) { ul.appendChild(el('li', cls === 'chips' ? 'chip' : null, i)); });
    return ul;
  }

  function fill(key) {
    var p = data[key];
    if (!p) return false;
    currentKey = key;
    elTitle.textContent = p.title;

    elCats.textContent = '';
    p.categories.forEach(function (c) { elCats.appendChild(el('li', null, c.label)); });

    /* visual: reuse the card's own image/artwork so nothing is duplicated */
    elVisual.textContent = '';
    var src = $('.pcard[data-key="' + key + '"] .pcard__visual');
    if (src) {
      var clone = src.cloneNode(true);
      clone.className = 'pcard__visual pd__art';
      var svg = clone.querySelector('svg');
      if (svg) svg.setAttribute('preserveAspectRatio', 'xMidYMid meet'); /* show the whole artwork, uncropped */
      elVisual.appendChild(clone);
    }

    elContent.textContent = '';
    /* Only sections the project data supports are rendered */
    elContent.appendChild(section('Overview', textBlock(p.overview || p.desc)));
    if (p.problem) elContent.appendChild(section('Problem addressed', textBlock(p.problem)));
    if (p.objective) elContent.appendChild(section('Project objective', textBlock(p.objective)));
    if (p.implementation) elContent.appendChild(section('Implementation', textBlock(p.implementation)));
    if (p.domain) elContent.appendChild(section('Domain', textBlock(p.domain)));
    if (p.chips && p.chips.length) elContent.appendChild(section('Technologies used', listBlock(p.chips, 'chips')));
    if (p.images && p.images.length) {
      var gal = el('div', 'pd__gallery');
      p.images.forEach(function (u) {
        var img = document.createElement('img');
        img.src = u; img.alt = p.title + ' screenshot'; img.loading = 'lazy';
        gal.appendChild(img);
      });
      elContent.appendChild(section('Screenshots', gal));
    }
    if (p.link) {
      var a = el('a', 'link-arrow', 'Visit project');
      a.href = p.link; a.target = '_blank'; a.rel = 'noopener noreferrer';
      elContent.appendChild(section('Project link', a));
    }
    return true;
  }

  function openDetails(key, trigger) {
    if (!dlg || !fill(key)) return;
    lastTrigger = trigger || null;
    if (typeof dlg.showModal === 'function') { if (!dlg.open) dlg.showModal(); }
    else dlg.setAttribute('open', '');
    dlg.scrollTop = 0;
    try { history.replaceState(null, '', '#project-' + key); } catch (e) { /* ignore */ }
  }
  function closeDetails() {
    if (!dlg) return;
    if (typeof dlg.close === 'function') { if (dlg.open) dlg.close(); } else dlg.removeAttribute('open');
  }
  if (dlg) {
    dlg.addEventListener('close', function () {
      try { history.replaceState(null, '', window.location.pathname + window.location.search); } catch (e) { /* ignore */ }
      if (lastTrigger && document.contains(lastTrigger) && !lastTrigger.closest('[hidden]')) lastTrigger.focus();
      lastTrigger = null;
    });
    dlg.addEventListener('click', function (e) { if (e.target === dlg) closeDetails(); }); /* backdrop */
    $('#pdClose').addEventListener('click', closeDetails);
    $('#pdDone').addEventListener('click', closeDetails);
    enquireBtn.addEventListener('click', function () {
      var title = currentKey && data[currentKey] ? data[currentKey].title : '';
      lastTrigger = null; /* the enquiry dialog takes over focus */
      closeDetails();
      if (window.openOrderForm) window.openOrderForm(title);
    });
  }
  grid.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-details]');
    if (btn) openDetails(btn.getAttribute('data-details'), btn);
  });

  /* Deep link: /projects#project-nids opens that project */
  function openFromHash() {
    var m = /^#project-(.+)$/.exec(window.location.hash);
    if (m && data[m[1]]) openDetails(m[1], null);
  }
  window.addEventListener('hashchange', function () { if (!dlg.open) openFromHash(); });

  apply();
  openFromHash();
})();
