// Cat desktop buddy — shared across landing, about, archive pages.
// Idle behaviors: walk along bottom (with a step-bob), peek from bottom corners,
// scratch the right edge. Hover: speech bubble. Click: chat panel with preset Q&A.

(() => {
  if (document.getElementById('cat-buddy')) return;
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  const SRC = {
    walk:    'images/cat-walk.png',
    peek:    'images/cat-peek.png',
    scratch: 'images/cat-scratch.png',
  };

  const QUESTIONS = [
    {
      q: "Who is Aprajita?",
      a: "A UX designer who blends storytelling with structure — building playful, intentional digital experiences. The About page has the longer story."
    },
    {
      q: "How can I contact you?",
      a: "Email: <a href='mailto:aprajita.singh_UGTBM2028@mastersunion.org'>aprajita.singh_UGTBM2028@mastersunion.org</a><br/>Or book a 30-min chat — click the vintage computer on the archive page!"
    },
    {
      q: "Show me your work",
      a: "Open the Archive page (Start button on the About page) — click any project card to read its case study."
    },
  ];

  // ─── DOM ────────────────────────────────────────────────────────────────
  const wrap = document.createElement('div');
  wrap.id = 'cat-buddy';
  wrap.className = 'cat-buddy';
  wrap.dataset.state = 'walk';
  wrap.dataset.facing = 'right';
  wrap.innerHTML = `
    <div class="cat-bubble" id="cat-bubble" aria-hidden="true">How can I help? 🐱</div>
    <img class="cat-img" id="cat-img" src="${SRC.walk}" alt="" draggable="false" />
  `;
  document.body.appendChild(wrap);

  const panel = document.createElement('div');
  panel.className = 'cat-chat';
  panel.id = 'cat-chat';
  panel.setAttribute('aria-hidden', 'true');
  panel.innerHTML = `
    <button class="cat-chat-close" id="cat-chat-close" aria-label="Close chat">&times;</button>
    <div class="cat-chat-head">Hi! What would you like to know?</div>
    <div class="cat-chat-body">
      ${QUESTIONS.map((it, i) => `<button class="cat-q" data-i="${i}">${it.q}</button>`).join('')}
    </div>
    <div class="cat-chat-answer" id="cat-chat-answer"></div>
  `;
  document.body.appendChild(panel);

  const img      = wrap.querySelector('#cat-img');
  const bubble   = wrap.querySelector('#cat-bubble');
  const closeBtn = panel.querySelector('#cat-chat-close');
  const answerEl = panel.querySelector('#cat-chat-answer');

  // ─── State ──────────────────────────────────────────────────────────────
  const CAT_W = 96, CAT_H = 96;

  let state = 'walk';
  let facing = 'right';
  let posX = 30;
  let translateY = 0;
  let rotateDeg = 0;
  let stateStartedAt = performance.now();
  let stateDuration = 0;
  let paused = false;
  let chatOpen = false;
  let scheduleId = null;
  let lastT = performance.now();

  function commit() {
    wrap.style.transform = `translate3d(${posX}px, ${translateY}px, 0) rotate(${rotateDeg}deg)`;
    wrap.dataset.facing = facing;
    wrap.dataset.state = state;
  }

  // ─── Behaviors ──────────────────────────────────────────────────────────
  function enterWalk(dir) {
    state = 'walk';
    facing = dir;
    img.src = SRC.walk;
    translateY = 0;
    rotateDeg = 0;
    stateDuration = rand(12000, 20000); // walk for 12-20s
    stateStartedAt = performance.now();
    commit();
    scheduleAfter(stateDuration, pickNext);
  }
  function enterPeek(side) {
    state = side === 'left' ? 'peek-left' : 'peek-right';
    facing = 'right';
    img.src = SRC.peek;
    const margin = 24;
    posX = side === 'left' ? margin : window.innerWidth - CAT_W - margin;
    translateY = CAT_H * 0.75; // starts mostly below the visible area
    rotateDeg = 0;
    stateDuration = 4800;
    stateStartedAt = performance.now();
    commit();
    scheduleAfter(stateDuration, pickNext);
  }
  function enterScratch() {
    state = 'scratch';
    facing = 'right';
    img.src = SRC.scratch;
    posX = window.innerWidth - CAT_W - 2; // hug the right edge
    translateY = 0;
    rotateDeg = 0;
    stateDuration = 5500;
    stateStartedAt = performance.now();
    commit();
    scheduleAfter(stateDuration, pickNext);
  }

  function pickNext() {
    if (paused) return;
    const r = Math.random();
    if (r < 0.5)       enterWalk(facing === 'right' ? 'left' : 'right');
    else if (r < 0.75) enterPeek('left');
    else               enterPeek('right');
  }

  function scheduleAfter(ms, fn) {
    clearTimeout(scheduleId);
    scheduleId = setTimeout(() => {
      if (!paused) fn();
      else scheduleAfter(800, fn); // retry shortly if paused
    }, ms);
  }

  function rand(a, b) { return a + Math.random() * (b - a); }

  // ─── Render loop ────────────────────────────────────────────────────────
  function loop(now) {
    const dt = Math.min(0.04, (now - lastT) / 1000);
    lastT = now;

    if (!paused) {
      const elapsed = now - stateStartedAt;

      if (state === 'walk') {
        // forward motion
        const speed = 60; // px/sec
        posX += speed * dt * (facing === 'right' ? 1 : -1);
        const minX = 6, maxX = window.innerWidth - CAT_W - 6;
        if (posX > maxX) { posX = maxX; facing = 'left'; }
        if (posX < minX) { posX = minX; facing = 'right'; }
        // step bob — fake walking gait via sine wave on Y and a tiny rotation
        const t = elapsed / 1000;
        const stepHz = 3.4;        // ~3.4 steps per second
        translateY = -Math.abs(Math.sin(t * Math.PI * stepHz)) * 4; // 0..-4px hops
        rotateDeg  = Math.sin(t * Math.PI * stepHz) * 3;            // ±3° sway
      }
      else if (state === 'peek-left' || state === 'peek-right') {
        const t = Math.min(1, elapsed / stateDuration);
        // 0→0.5: rise out from below.  0.5→1: drop back down.
        // yFactor is 1 (hidden) at start/end, 0 (peak) at midpoint.
        const yFactor = t < 0.5 ? (1 - t / 0.5) : ((t - 0.5) / 0.5);
        const hideOffset = CAT_H * 0.75;  // fully hidden below baseline
        const peakOffset = CAT_H * 0.45;  // peak: only the head/eyes show
        translateY = peakOffset + (hideOffset - peakOffset) * yFactor;
      }
      else if (state === 'scratch') {
        const t = Math.min(1, elapsed / stateDuration);
        const maxRise = Math.min(220, window.innerHeight * 0.30);
        const tSec = elapsed / 1000;

        let rise;
        let shakeX = 0;
        let wobble = 0;

        if (t < 0.30) {
          // climbing up phase
          rise = maxRise * (t / 0.30);
        } else if (t < 0.75) {
          // hanging + scratching phase — claws slip down then re-grip, body shakes
          const base = maxRise;
          // sawtooth slip: rise creeps down then jumps up sharply (claw re-grip)
          const slipPhase = ((tSec * 1.6) % 1); // 0..1 every ~0.6s
          const slipAmount = slipPhase * 18;    // slip up to 18px down
          rise = base - slipAmount;

          // horizontal claw vibration
          shakeX = Math.sin(tSec * 35) * 4;     // ±4px shake
          // body wobble
          wobble = Math.sin(tSec * 12) * 4;     // ±4°
        } else {
          // drop back to ground
          rise = maxRise * (1 - (t - 0.75) / 0.25);
        }

        translateY = -rise;
        posX = (window.innerWidth - CAT_W - 2) + shakeX;
        rotateDeg = wobble;
      }

      commit();
    }
    requestAnimationFrame(loop);
  }

  // ─── Hover / click ──────────────────────────────────────────────────────
  wrap.addEventListener('mouseenter', () => {
    paused = true;
    bubble.classList.add('show');
  });
  wrap.addEventListener('mouseleave', () => {
    bubble.classList.remove('show');
    if (!chatOpen) {
      paused = false;
      lastT = performance.now();
      stateStartedAt = performance.now();
    }
  });
  wrap.addEventListener('click', (e) => { e.stopPropagation(); openChat(); });
  closeBtn.addEventListener('click', (e) => { e.stopPropagation(); closeChat(); });

  panel.addEventListener('click', (e) => {
    const btn = e.target.closest('.cat-q');
    if (!btn) return;
    const i = parseInt(btn.dataset.i, 10);
    answerEl.innerHTML = QUESTIONS[i].a;
    answerEl.classList.add('show');
  });

  function openChat() {
    chatOpen = true;
    paused = true;
    bubble.classList.remove('show');
    panel.classList.add('open');
    panel.setAttribute('aria-hidden', 'false');
    answerEl.classList.remove('show');
    answerEl.innerHTML = '';
  }
  function closeChat() {
    chatOpen = false;
    panel.classList.remove('open');
    panel.setAttribute('aria-hidden', 'true');
    paused = false;
    lastT = performance.now();
    stateStartedAt = performance.now();
  }

  wrap.style.bottom = '12px';
  wrap.style.left   = '0';

  enterWalk('right');
  requestAnimationFrame(loop);
})();
