const scrollingTimers = new WeakMap<HTMLElement, number>();

/**
 * Initializes a capture-phase global scroll listener that dynamically adds
 * the 'is-scrolling' class to chat and code scrollable containers only while
 * the user is actively scrolling, and removes it smoothly after scrolling stops.
 */
export function setupGlobalAutoScrollHide(): void {
  if (typeof window === 'undefined') return;

  const onScroll = (e: Event) => {
    const target = e.target;
    if (!(target instanceof HTMLElement)) return;

    let scrollEl: HTMLElement | null = null;
    if (target.classList.contains('scroll-auto-hide')) {
      scrollEl = target;
    } else if (target.tagName === 'PRE') {
      scrollEl = target;
    } else {
      scrollEl = target.closest('.scroll-auto-hide');
    }

    if (!scrollEl) return;

    scrollEl.classList.add('is-scrolling');

    const existing = scrollingTimers.get(scrollEl);
    if (existing !== undefined) {
      window.clearTimeout(existing);
    }

    const timerId = window.setTimeout(() => {
      scrollEl?.classList.remove('is-scrolling');
      if (scrollEl) {
        scrollingTimers.delete(scrollEl);
      }
    }, 800);

    scrollingTimers.set(scrollEl, timerId);
  };

  window.addEventListener('scroll', onScroll, { capture: true, passive: true });
}
