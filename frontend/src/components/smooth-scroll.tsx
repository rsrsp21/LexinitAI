import Lenis from "lenis";
import { useEffect } from "react";

/**
 * Glides the page under Lenis, which is what gives scroll-driven scenes their
 * weight -- native wheel scrolling lands in hard steps and makes pinned
 * sections read as jumpy.
 *
 * Lenis drives the real window scroll position, so anything reading scroll
 * (motion's useScroll, the canvas backdrops) keeps working untouched.
 *
 * Mount once per page. Does nothing when the visitor prefers reduced motion.
 */
export function useSmoothScroll() {
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    const lenis = new Lenis({
      duration: 1.15,
      // Exponential ease-out: quick to respond, long settle.
      easing: (t: number) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
      smoothWheel: true,
      touchMultiplier: 1.6,
    });

    let frame = requestAnimationFrame(function raf(time: number) {
      lenis.raf(time);
      frame = requestAnimationFrame(raf);
    });

    // In-page anchors must go through Lenis or they fight the animation.
    const onClick = (event: MouseEvent) => {
      const link = (event.target as HTMLElement | null)?.closest?.(
        'a[href^="#"]',
      ) as HTMLAnchorElement | null;
      if (!link) return;
      const id = link.getAttribute("href");
      if (!id || id === "#") return;
      const el = document.querySelector(id);
      if (!el) return;
      event.preventDefault();
      lenis.scrollTo(el as HTMLElement, { offset: -40 });
    };
    document.addEventListener("click", onClick);

    return () => {
      cancelAnimationFrame(frame);
      document.removeEventListener("click", onClick);
      lenis.destroy();
    };
  }, []);
}
