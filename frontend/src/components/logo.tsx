/**
 * Lexinit brand mark: an open book with a pencil.
 *
 * Canonical artwork (see docs/DESIGN.md). Renders in `currentColor`, so it
 * automatically follows the theme: dark ink in light mode, light ink in dark
 * mode (set the color via `text-*` classes, normally `text-foreground`).
 * Background is transparent by design.
 *
 * Static asset copies for use outside the app (emails, socials, stores):
 * - frontend/public/logo-dark.svg  (ink mark, for light backgrounds)
 * - frontend/public/logo-light.svg (light mark, for dark backgrounds)
 * - frontend/public/favicon.svg (fixed black tile with the white mark)
 */
export function Logo({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 100 100"
      fill="none"
      stroke="currentColor"
      strokeWidth="5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className={className}
    >
      {/* Book cover */}
      <rect x="25" y="15" width="38" height="56" />
      {/* Book spine and pages */}
      <path d="M 25 15 H 13 V 71 Q 13 85 25 85 H 63" />
      {/* Pencil */}
      <path d="M 75 15 H 87 V 63 L 81 85 L 75 63 Z" />
    </svg>
  );
}
