/* Mentora Labs — site behaviour: sidebar, mobile drawer, enquiry dialog. (Projects page logic: projects.js.) */
(function () {
  'use strict';

  var root = document.documentElement;
  var $ = function (sel, ctx) { return (ctx || document).querySelector(sel); };
  var $$ = function (sel, ctx) { return Array.prototype.slice.call((ctx || document).querySelectorAll(sel)); };

  /* ---------- Sidebar: collapse (desktop/tablet) + drawer (mobile) ---------- */
  var STORE_KEY = 'ml-sidebar';
  var mobileMQ = window.matchMedia('(max-width: 767px)');
  var tabletMQ = window.matchMedia('(min-width: 768px) and (max-width: 1099px)');
  var page = $('#page');
  var sidebar = $('#sidebar');
  var toggleBtn = $('#sidebarToggle');
  var menuBtn = $('#menuButton');
  var closeBtn = $('#navClose');
  var scrim = $('#scrim');
  var navLinks = $$('.sidebar .nav-link');

  function readPref() { try { return localStorage.getItem(STORE_KEY) === 'collapsed'; } catch (e) { return false; } }
  function writePref(collapsed) { try { localStorage.setItem(STORE_KEY, collapsed ? 'collapsed' : 'expanded'); } catch (e) { /* storage unavailable */ } }

  var userCollapsed = readPref();

  function applyCollapse() {
    var collapsed = !mobileMQ.matches && (tabletMQ.matches || userCollapsed);
    root.classList.toggle('sb-collapsed', collapsed);
    if (toggleBtn) {
      toggleBtn.setAttribute('aria-expanded', String(!collapsed));
      toggleBtn.setAttribute('aria-label', collapsed ? 'Expand sidebar' : 'Collapse sidebar');
      var label = $('.sb-label', toggleBtn);
      if (label) label.textContent = collapsed ? 'Expand' : 'Collapse';
    }
    navLinks.forEach(function (a) {
      var text = $('.sb-label', a);
      if (collapsed && text) a.setAttribute('title', text.textContent.trim());
      else a.removeAttribute('title');
    });
  }

  function openNav() {
    root.classList.add('nav-open');
    if (menuBtn) menuBtn.setAttribute('aria-expanded', 'true');
    if (page) page.inert = true;
    if (closeBtn) closeBtn.focus();
  }
  function closeNav(restoreFocus) {
    if (!root.classList.contains('nav-open')) return;
    root.classList.remove('nav-open');
    if (menuBtn) menuBtn.setAttribute('aria-expanded', 'false');
    if (page) page.inert = false;
    if (restoreFocus && menuBtn) menuBtn.focus();
  }

  if (toggleBtn) toggleBtn.addEventListener('click', function () {
    userCollapsed = !root.classList.contains('sb-collapsed');
    writePref(userCollapsed);
    applyCollapse();
  });
  if (menuBtn) menuBtn.addEventListener('click', openNav);
  if (closeBtn) closeBtn.addEventListener('click', function () { closeNav(true); });
  if (scrim) scrim.addEventListener('click', function () { closeNav(true); });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { closeNav(true); return; }
    /* Keep Tab inside the drawer while it is open (the page behind is inert) */
    if (e.key === 'Tab' && root.classList.contains('nav-open') && sidebar) {
      var items = $$('a[href], button:not([disabled])', sidebar).filter(function (el) { return el.getClientRects().length > 0; });
      if (!items.length) return;
      var first = items[0], last = items[items.length - 1];
      if (!sidebar.contains(document.activeElement)) { e.preventDefault(); first.focus(); }
      else if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  });
  [mobileMQ, tabletMQ].forEach(function (mq) {
    var handler = function () { if (!mobileMQ.matches) closeNav(false); applyCollapse(); };
    if (mq.addEventListener) mq.addEventListener('change', handler); else mq.addListener(handler);
  });
  applyCollapse();

  /* ---------- Enquiry dialog ---------- */
  var dialog = $('#orderDialog');
  var form = $('#orderForm');
  var statusEl = $('#formStatus');
  var select = $('#trackSelect');
  var closeTimer = null;

  function setStatus(text, kind) {
    statusEl.textContent = text;
    statusEl.className = 'form-status' + (kind ? ' is-' + kind : '');
  }

  var messageEl = $('#orderMessage');
  var prefilled = '';

  window.openOrderForm = function (track, message) {
    if (!dialog) return;
    if (track && select) {
      for (var i = 0; i < select.options.length; i++) {
        if (select.options[i].value === track) { select.value = track; break; }
      }
    }
    /* Optional starter message from a CTA (data-order-message). Never overwrites what the visitor typed. */
    if (messageEl) {
      if (messageEl.value === prefilled) messageEl.value = '';
      prefilled = '';
      if (message && !messageEl.value) { messageEl.value = message; prefilled = message; }
    }
    setStatus('', '');
    if (typeof dialog.showModal === 'function') { if (!dialog.open) dialog.showModal(); }
    else dialog.setAttribute('open', '');
  };
  window.closeOrderForm = function () {
    if (!dialog) return;
    clearTimeout(closeTimer);
    if (typeof dialog.close === 'function') dialog.close(); else dialog.removeAttribute('open');
    setStatus('', '');
  };

  document.addEventListener('click', function (e) {
    var trigger = e.target.closest('[data-open-order]');
    if (trigger) {
      e.preventDefault();
      closeNav(false);
      window.openOrderForm(trigger.getAttribute('data-open-order') || '', trigger.getAttribute('data-order-message') || '');
    }
    if (e.target.closest('[data-close-order]')) window.closeOrderForm();
  });
  if (dialog) dialog.addEventListener('click', function (e) { if (e.target === dialog) window.closeOrderForm(); }); // backdrop click

  if (form) form.addEventListener('submit', function (e) {
    e.preventDefault();
    var submitBtn = $('button[type="submit"]', form);
    var payload = {};
    new FormData(form).forEach(function (value, key) { payload[key] = String(value).trim(); });

    setStatus('Sending…', '');
    submitBtn.disabled = true;
    fetch('/api/orders', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }).then(function (res) {
      if (!res.ok) throw new Error('Request failed');
      setStatus("Got it — we'll reach out soon!", 'ok');
      form.reset();
      prefilled = '';
      closeTimer = setTimeout(window.closeOrderForm, 1600);
    }).catch(function () {
      setStatus('Something went wrong. Please try WhatsApp or email instead.', 'error');
    }).then(function () { submitBtn.disabled = false; });
  });
})();
