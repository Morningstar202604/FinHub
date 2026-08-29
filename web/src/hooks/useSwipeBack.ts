import { useEffect, useRef, type RefObject } from 'react';

interface UseSwipeBackOptions {
  edgeWidth?: number;
  threshold?: number;
  enabled?: boolean;
}

/**
 * Detects edge-swipe-right gesture for "back" navigation on mobile.
 * Only fires when touch starts within `edgeWidth` px of the left edge
 * and the swipe is predominantly horizontal (dx > dy * 1.5).
 */
export function useSwipeBack(
  ref: RefObject<HTMLElement | null>,
  onSwipeBack: () => void,
  options: UseSwipeBackOptions = {},
) {
  const { edgeWidth = 24, threshold = 80, enabled = true } = options;
  const touchRef = useRef<{ x: number; y: number; fromEdge: boolean } | null>(null);

  useEffect(() => {
    if (!enabled) return;
    const el = ref.current;
    if (!el) return;

    const onTouchStart = (e: TouchEvent) => {
      const touch = e.touches[0];
      const rect = el.getBoundingClientRect();
      touchRef.current = {
        x: touch.clientX,
        y: touch.clientY,
        fromEdge: touch.clientX - rect.left <= edgeWidth,
      };
    };

    const onTouchEnd = (e: TouchEvent) => {
      const start = touchRef.current;
      touchRef.current = null;
      if (!start?.fromEdge) return;

      const touch = e.changedTouches[0];
      const dx = touch.clientX - start.x;
      const dy = Math.abs(touch.clientY - start.y);

      if (dx > threshold && dx > dy * 1.5) {
        onSwipeBack();
      }
    };

    el.addEventListener('touchstart', onTouchStart, { passive: true });
    el.addEventListener('touchend', onTouchEnd, { passive: true });
    return () => {
      el.removeEventListener('touchstart', onTouchStart);
      el.removeEventListener('touchend', onTouchEnd);
    };
  }, [ref, onSwipeBack, edgeWidth, threshold, enabled]);
}
