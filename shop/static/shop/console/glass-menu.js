/* The side menu's small helper. The menu works with no script at all (the arrow is the label of a checkbox);
   this only adds what a checkbox cannot do: Esc closes it, tapping a link in it closes it, it comes back closed after the browser's Back or Forward
   button, and a screen reader hears a button that is expanded or collapsed. Same text in the Design app, Home and Drive; keep it free of the
   three-character openers of template syntax, because Design and Home include it through the template engine. */
(function () {
  'use strict';
  var box = document.getElementById('g-side-open');
  if (!box) return;
  var search = document.getElementById('g-search-open');   // Home only: a panel that takes over the open menu

  function sync() {
    box.setAttribute('role', 'button');
    box.setAttribute('aria-expanded', box.checked ? 'true' : 'false');
  }
  function closeMenu() {
    if (search) search.checked = false;
    if (box.checked) box.checked = false;
    sync();
  }

  box.addEventListener('change', sync);

  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape' && e.key !== 'Esc') return;
    if (search && search.checked) { search.checked = false; return; }   // the panel first, then the menu on the next press
    if (box.checked) { closeMenu(); box.focus(); }
  });

  document.addEventListener('click', function (e) {
    var link = e.target && e.target.closest ? e.target.closest('#g-side a[href]') : null;
    if (link && box.checked) closeMenu();                // a link on the same page (or one that opens in a new tab) leaves the menu open otherwise
  });

  window.addEventListener('pageshow', function (e) {
    if (e.persisted) closeMenu();                        // Back and Forward restore the page as it was left: open
  });

  sync();
})();
