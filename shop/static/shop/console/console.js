/* Console helpers: the light / dark / device switch in the side bar, and the touch handler that makes :active
   show on iPhone Safari (handoff rule 13). Plain script, no dependencies. */
(function () {
  'use strict';
  document.addEventListener('touchstart', function () {}, { passive: true });

  var KEY = 'tts-theme';
  var root = document.documentElement;
  var button = document.getElementById('c-theme');
  var label = document.getElementById('c-theme-label');

  function stored() {
    try {
      var t = localStorage.getItem(KEY);
      return t === 'light' || t === 'dark' ? t : 'device';
    } catch (e) { return 'device'; }
  }
  function show(mode) {
    if (label) label.textContent = 'Theme: ' + mode;
    if (button) button.setAttribute('aria-label', 'Color theme: ' + mode + '. Press to change.');
  }
  function apply(mode) {
    if (mode === 'device') root.removeAttribute('data-theme'); else root.setAttribute('data-theme', mode);
    try {
      if (mode === 'device') localStorage.removeItem(KEY); else localStorage.setItem(KEY, mode);
    } catch (e) { /* private window: the choice just lasts until the page closes */ }
    show(mode);
  }

  show(stored());
  if (button) {
    button.addEventListener('click', function () {
      var next = { device: 'light', light: 'dark', dark: 'device' }[stored()];
      apply(next);
    });
  }
})();

/* Alpine components used by the console pages. Registered before Alpine starts (this file loads first). */
document.addEventListener('alpine:init', function () {
  /* The quick-create form: a Front slot and a Back slot that take a dropped or chosen file, show it, and know when
     several fronts are chosen (a batch: one listing each, so no back and no title). Works without script too:
     each slot is a plain file input laid over its label. */
  Alpine.data('cDrop', function () {
    return {
      over: { front: false, back: false },
      names: { front: '', back: '' },
      preview: { front: '', back: '' },
      count: { front: 0, back: 0 },
      get batch() { return this.count.front > 1; },
      get hasFiles() { return this.count.front + this.count.back > 0; },
      changed: function (side) {
        var files = this.$refs[side].files;
        if (this.preview[side]) URL.revokeObjectURL(this.preview[side]);
        this.count[side] = files.length;
        this.names[side] = files.length > 1 ? files.length + ' files chosen' : (files[0] ? files[0].name : '');
        this.preview[side] = files.length === 1 && files[0].type.indexOf('image/') === 0 ? URL.createObjectURL(files[0]) : '';
        if (this.batch && this.count.back) this.clear('back');
      },
      drop: function (side, event) {
        this.over[side] = false;
        var files = event.dataTransfer && event.dataTransfer.files;
        if (!files || !files.length || (side === 'back' && this.batch)) return;
        this.$refs[side].files = side === 'back' ? this.single(files) : files;
        this.changed(side);
      },
      single: function (files) {
        var box = new DataTransfer();
        box.items.add(files[0]);
        return box.files;
      },
      clear: function (side) {
        this.$refs[side].value = '';
        this.changed(side);
      }
    };
  });
});

/* A link to a folded section (#artwork, #imagery ...) opens it, so redirects after an action land on what changed. */
(function () {
  function openTarget() {
    var el = location.hash.length > 1 ? document.getElementById(decodeURIComponent(location.hash.slice(1))) : null;
    if (!el) return;
    var box = el.tagName === 'DETAILS' ? el : el.closest('details');
    if (box) box.open = true;
  }
  window.addEventListener('hashchange', openTarget);
  document.addEventListener('DOMContentLoaded', openTarget);
})();
