// Hover-only parallax: any element with .parallax-hover drifts toward the
// cursor while the mouse is over it, and eases back to center on leave.
(() => {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  const intensity = 14;

  document.querySelectorAll('.parallax-hover').forEach((el) => {
    let tx = 0, ty = 0, cx = 0, cy = 0;

    el.addEventListener('mousemove', (e) => {
      const r = el.getBoundingClientRect();
      const nx = (e.clientX - (r.left + r.width / 2)) / (r.width / 2);
      const ny = (e.clientY - (r.top + r.height / 2)) / (r.height / 2);
      tx = nx * intensity;
      ty = ny * intensity;
    });

    el.addEventListener('mouseleave', () => { tx = 0; ty = 0; });

    function tick() {
      cx += (tx - cx) * 0.12;
      cy += (ty - cy) * 0.12;
      el.style.transform = `translate3d(${cx.toFixed(2)}px, ${cy.toFixed(2)}px, 0)`;
      requestAnimationFrame(tick);
    }
    tick();
  });
})();

// Cursor-following tooltip on the see-it-unfold pill.
(() => {
  const tip = document.getElementById('hoverTip');
  const pill = document.querySelector('.see-it-pill');
  if (!tip || !pill) return;
  const offsetX = 18, offsetY = 22;
  pill.addEventListener('mouseenter', () => tip.classList.add('is-visible'));
  pill.addEventListener('mouseleave', () => tip.classList.remove('is-visible'));
  pill.addEventListener('mousemove', (e) => {
    tip.style.transform = `translate3d(${e.clientX + offsetX}px, ${e.clientY + offsetY}px, 0)`;
  });
})();

// Click the pill to open the unfold GIF in a lightbox.
(() => {
  const pill = document.querySelector('.see-it-pill');
  const box = document.getElementById('unfoldLightbox');
  const media = document.getElementById('lightboxMedia');
  const closeBtn = document.getElementById('lightboxClose');
  const tip = document.getElementById('hoverTip');
  if (!pill || !box || !media || !closeBtn) return;

  const open = () => {
    // Re-set src each time so the GIF restarts from frame 0.
    media.src = 'images/unfold.gif?t=' + Date.now();
    box.classList.add('is-open');
    box.setAttribute('aria-hidden', 'false');
    if (tip) tip.classList.remove('is-visible');
  };
  const close = () => {
    box.classList.remove('is-open');
    box.setAttribute('aria-hidden', 'true');
    media.src = '';
  };

  pill.addEventListener('click', (e) => { e.preventDefault(); open(); });
  closeBtn.addEventListener('click', close);
  box.addEventListener('click', (e) => { if (e.target === box) close(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') close(); });
})();
