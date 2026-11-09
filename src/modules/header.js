import gsap from 'gsap';

export function initHeader(lenis) {
  const header = document.getElementById('site-header');
  const toggleBtn = document.getElementById('mobile-menu-toggle');
  const sheet = document.getElementById('mobile-menu-sheet');
  if (!header) return;

  let pinnedProcessActive = false;
  let lastScrollY = window.scrollY;

  window.addEventListener('medici:process-pin', (e) => {
    pinnedProcessActive = !!e.detail?.active;
    if (pinnedProcessActive) {
      header.classList.add('is-hidden');
    } else {
      header.classList.remove('is-hidden');
    }
  });

  const handleScroll = () => {
    const y = window.scrollY;
    if (pinnedProcessActive) {
      header.classList.add('is-hidden');
      return;
    }
    if (y > 120 && y > lastScrollY + 4) {
      header.classList.add('is-hidden');
    } else if (y < lastScrollY - 4 || y <= 80) {
      header.classList.remove('is-hidden');
    }
    lastScrollY = y;
  };

  if (lenis) {
    lenis.on('scroll', handleScroll);
  } else {
    window.addEventListener('scroll', handleScroll, { passive: true });
  }

  // Mobile Menu Sheet
  if (toggleBtn && sheet) {
    const links = sheet.querySelectorAll('.mobile-sheet__link');
    toggleBtn.addEventListener('click', () => {
      const expanded = toggleBtn.getAttribute('aria-expanded') === 'true';
      toggleBtn.setAttribute('aria-expanded', String(!expanded));
      if (expanded) {
        sheet.hidden = true;
      } else {
        sheet.hidden = false;
        gsap.fromTo(
          links,
          { y: 20, opacity: 0 },
          { y: 0, opacity: 1, stagger: 0.06, duration: 0.5, ease: 'medici' }
        );
      }
    });

    links.forEach((link) => {
      link.addEventListener('click', () => {
        toggleBtn.setAttribute('aria-expanded', 'false');
        sheet.hidden = true;
      });
    });
  }
}