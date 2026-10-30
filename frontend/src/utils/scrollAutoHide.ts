import { useLayoutEffect, useState, type RefObject } from 'react';

const scrollingTimers = new WeakMap<HTMLElement, number>();

/**
 * Initializes a capture-phase global scroll listener that toggles 'is-scrolling'
 * on scrollable containers only while the user is actively scrolling.
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

/**
 * Measures the active scrollbar width of a scrollable element so right padding stays balanced.
 */
export function useScrollGutter(
  ref: RefObject<HTMLElement | null>,
  trigger?: unknown,
  initialValue: number = 0
): number {
  const [scrollGutter, setScrollGutter] = useState<number>(initialValue);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;

    const updateGutter = () => {
      const sw = Math.max(0, el.offsetWidth - el.clientWidth);
      setScrollGutter(sw);
    };

    updateGutter();
    const rafId = requestAnimationFrame(updateGutter);

    let resizeObserver: ResizeObserver | null = null;
    if (typeof ResizeObserver !== 'undefined') {
      resizeObserver = new ResizeObserver(updateGutter);
      resizeObserver.observe(el);
    }

    window.addEventListener('resize', updateGutter);

    return () => {
      cancelAnimationFrame(rafId);
      if (resizeObserver) resizeObserver.disconnect();
      window.removeEventListener('resize', updateGutter);
    };
  }, [ref, trigger]);

  return scrollGutter;
}
