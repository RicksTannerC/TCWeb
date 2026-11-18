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
