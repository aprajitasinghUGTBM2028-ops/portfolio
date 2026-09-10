/* IRAAYA — waitlist behaviour */
(function () {
  var root = document.documentElement;

  /* ---- theme toggle ---- */
  var themeBtn = document.getElementById('themeBtn');
  try {
    var saved = localStorage.getItem('iraaya-theme');
    if (saved) root.setAttribute('data-theme', saved);
  } catch (e) {}
  themeBtn.addEventListener('click', function () {
    var cur = root.getAttribute('data-theme');
    var isDark = cur ? cur === 'dark'
                     : window.matchMedia('(prefers-color-scheme:dark)').matches;
    var next = isDark ? 'light' : 'dark';
    root.setAttribute('data-theme', next);
    try { localStorage.setItem('iraaya-theme', next); } catch (e) {}
  });

  /* ---- click the tag to swing it again ---- */
  var pend = document.getElementById('pendulum');
  function reSwing(delay) {
    pend.style.animation = 'none';
    void pend.offsetWidth;
    pend.style.animation =
      'swing 3s ' + (delay || 0) + 's cubic-bezier(.36,0,.2,1) both, ' +
      'sway 8s ' + ((delay || 0) + 3) + 's ease-in-out infinite';
  }
  pend.addEventListener('click', function () { reSwing(0); });

  /* ---- form ---- */
  var form = document.getElementById('form');
  var email = document.getElementById('email');
  var care = document.getElementById('caretags');
  var done = document.getElementById('done');
  var doneMsg = document.getElementById('doneMsg');
  var valid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  var careHTML = care.innerHTML;

  function showDone(msg) {
    if (msg) doneMsg.textContent = msg;
    form.style.display = 'none';
    care.style.display = 'none';
    done.classList.add('show');
    reSwing(0);
  }

  /* returning visitor */
  try {
    if (localStorage.getItem('iraaya-joined')) {
      showDone("You're already on the list — hang tight, we'll be in touch.");
    }
  } catch (e) {}

  form.addEventListener('submit', function (ev) {
    var v = email.value.trim();
    if (!valid.test(v)) {
      ev.preventDefault();
      care.innerHTML = '<span class="err">That email looks a little off — mind checking it?</span>';
      email.focus();
      return;
    }

    // If Formspree isn't wired up yet, don't do a broken POST — just celebrate locally.
    var wired = form.action.indexOf('YOUR_FORM_ID') === -1;
    if (!wired) {
      ev.preventDefault();
      try { localStorage.setItem('iraaya-joined', v); } catch (e) {}
      showDone();
      return;
    }

    // Formspree AJAX submit (works on GitHub Pages) — stays on the page.
    ev.preventDefault();
    var btn = form.querySelector('button');
    var label = btn.innerHTML;
    btn.disabled = true;
    btn.textContent = 'Joining…';
    fetch(form.action, {
      method: 'POST',
      body: new FormData(form),
      headers: { Accept: 'application/json' }
    }).then(function (r) {
      if (r.ok) {
        try { localStorage.setItem('iraaya-joined', v); } catch (e) {}
        showDone();
      } else {
        throw new Error('bad response');
      }
    }).catch(function () {
      btn.disabled = false;
      btn.innerHTML = label;
      care.innerHTML = '<span class="err">Something hiccuped — try again in a sec?</span>';
    });
  });
})();
