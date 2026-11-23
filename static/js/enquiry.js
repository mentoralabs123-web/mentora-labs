/* Mentora Labs — business enquiry form (Task 4B).
   Progressive enhancement only: the form posts normally without this script and the
   server validates everything again. This adds inline messages, a character counter
   and the "Sending…" state that stops double submission. */
(function () {
  'use strict';

  var form = document.getElementById('enquiryForm');
  if (!form) return;

  var submitBtn = document.getElementById('enquirySubmit');
  var statusEl = document.getElementById('enquiryStatus');
  var f = function (id) { return document.getElementById(id); };
  var minDesc = parseInt(form.getAttribute('data-min-description'), 10) || 10;
  var maxDesc = parseInt(form.getAttribute('data-max-description'), 10) || 2000;
  var sending = false;
  var idleLabel = submitBtn ? submitBtn.textContent : 'Send enquiry';

  var EMAIL_RE = /^[^@\s,;<>()\[\]\\"]+@[^@\s,;<>()\[\]\\"]+\.[^@\s,;<>()\[\]\\"]{2,}$/;
  var PHONE_RE = /^\+?[0-9][0-9\s().\-]*$/;

  /* ---------- helpers ---------- */
  function errorEl(input, create) {
    var id = input.id + '-error';
    var el = f(id);
    if (!el && create) {
      el = document.createElement('p');
      el.className = 'field__error';
      el.id = id;
      var holder = input.closest('.field');
      var foot = holder && holder.querySelector('.field__foot');
      if (foot) foot.insertBefore(el, foot.firstChild); else holder.appendChild(el);
    }
    return el;
  }
  function describe(input, id, on) {
    var ids = (input.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean);
    var i = ids.indexOf(id);
    if (on && i < 0) ids.push(id);
    if (!on && i >= 0) ids.splice(i, 1);
    if (ids.length) input.setAttribute('aria-describedby', ids.join(' ')); else input.removeAttribute('aria-describedby');
  }
  function setError(input, msg) {
    var holder = input.closest('.field');
    var el = errorEl(input, true);
    el.textContent = msg;
    if (holder) holder.classList.add('has-error');
    input.setAttribute('aria-invalid', 'true');
    describe(input, el.id, true);
  }
  function clearError(input) {
    var holder = input.closest('.field');
    var el = errorEl(input, false);
    if (el) { el.remove(); describe(input, input.id + '-error', false); }
    if (holder) holder.classList.remove('has-error');
    input.removeAttribute('aria-invalid');
  }
  function contactGroup() { return form.querySelector('.field-group'); }
  function setContactError(msg) {
    var group = contactGroup();
    var el = f('contact-error');
    if (!el) {
      el = document.createElement('p');
      el.className = 'field__error';
      el.id = 'contact-error';
      var hint = f('contact-hint');
      group.insertBefore(el, hint ? hint.nextSibling : null);
    }
    el.textContent = msg;
    group.classList.add('has-error');
    [f('email'), f('phone')].forEach(function (i) { i.setAttribute('aria-invalid', 'true'); describe(i, 'contact-error', true); });
  }
  function clearContactError() {
    var el = f('contact-error');
    if (el) el.remove();
    [f('email'), f('phone')].forEach(function (i) { describe(i, 'contact-error', false); });
    if (!f('email-error') && !f('phone-error')) {
      contactGroup().classList.remove('has-error');
      [f('email'), f('phone')].forEach(function (i) { i.removeAttribute('aria-invalid'); });
    }
  }
  function val(id) { return f(id).value.replace(/\s+/g, ' ').trim(); }

  /* ---------- per-field checks (mirror the server rules) ---------- */
  var checks = {
    name: function () {
      var v = val('name');
      if (!v) return 'Please enter your name.';
      if (v.length < 2) return 'Your name should be at least 2 characters.';
      return '';
    },
    email: function () {
      var v = val('email');
      if (v && !EMAIL_RE.test(v)) return 'Please enter a valid email address, for example name@example.com.';
      return '';
    },
    phone: function () {
      var v = val('phone');
      if (!v) return '';
      var digits = v.replace(/\D/g, '').length;
      if (!PHONE_RE.test(v) || digits < 7 || digits > 15) return 'Please enter a valid phone number. Include the country code if it is outside India.';
      return '';
    },
    service: function () { return f('service').value ? '' : 'Please choose the service you are interested in.'; },
    project_description: function () {
      var v = f('project_description').value.trim();
      if (!v) return 'Please describe what you need.';
      if (v.length < minDesc) return 'Please add a little more detail (at least ' + minDesc + ' characters).';
      return '';
    }
  };

  function checkField(id) {
    var input = f(id), msg = checks[id]();
    if (msg) setError(input, msg); else clearError(input);
    return msg;
  }
  function checkContact() {
    if (!val('email') && !val('phone')) { setContactError('Please give us an email address or a phone number so we can reach you.'); return false; }
    clearContactError();
    return true;
  }

  /* ---------- live feedback: validate on leaving a field, clear as the visitor fixes it ---------- */
  Object.keys(checks).forEach(function (id) {
    var input = f(id);
    input.addEventListener('blur', function () {
      if (id === 'email' || id === 'phone') { checkField(id); if (val('email') || val('phone')) clearContactError(); return; }
      if (id === 'project_description' && !input.value) return; // do not nag an untouched field
      checkField(id);
    });
    var evt = input.tagName === 'SELECT' ? 'change' : 'input';
    input.addEventListener(evt, function () {
      if (input.closest('.field').classList.contains('has-error')) {
        if (!checks[id]()) clearError(input);
      }
      if ((id === 'email' || id === 'phone') && (val('email') || val('phone'))) clearContactError();
    });
  });

  /* ---------- character counter ---------- */
  var desc = f('project_description'), counter = f('descCount');
  function updateCount() { if (counter) counter.textContent = desc.value.length + ' / ' + maxDesc; }
  desc.addEventListener('input', updateCount);
  updateCount();

  /* ---------- submit ---------- */
  function setSending(on) {
    sending = on;
    submitBtn.disabled = on;
    submitBtn.setAttribute('aria-disabled', String(on));
    submitBtn.textContent = on ? 'Sending…' : idleLabel;
    statusEl.textContent = on ? 'Sending your enquiry…' : '';
    statusEl.className = 'form-status';
  }

  form.addEventListener('submit', function (e) {
    if (sending) { e.preventDefault(); return; }
    var first = null;
    ['name', 'service', 'project_description'].forEach(function (id) { if (checkField(id) && !first) first = f(id); });
    var emailMsg = checkField('email'), phoneMsg = checkField('phone');
    var contactOk = checkContact();
    if (!first) first = emailMsg ? f('email') : phoneMsg ? f('phone') : (!contactOk ? f('email') : null);
    /* keep DOM order for focus */
    var order = ['name', 'email', 'phone', 'service', 'project_description'];
    var firstId = order.filter(function (id) { return f(id).getAttribute('aria-invalid') === 'true'; })[0];
    if (firstId) {
      e.preventDefault();
      statusEl.textContent = 'Please check the highlighted fields.';
      statusEl.className = 'form-status is-error';
      f(firstId).focus();
      return;
    }
    setSending(true);
  });

  /* Coming back with the browser's Back button must not leave the button stuck on "Sending…" */
  window.addEventListener('pageshow', function (e) { if (e.persisted) setSending(false); });

  /* Server-side errors: bring the summary into view for keyboard and screen-reader users */
  var summary = f('formErrors');
  if (summary) { summary.focus(); summary.scrollIntoView({ block: 'center' }); }
})();
