import { motion, useTransform, type MotionValue } from "motion/react";

/**
 * The Lexinit mark, taken apart by scroll.
 *
 * The brand logo is a book and a pencil sharing one lockup (see logo.tsx).
 * Scrolling the hero plays that lockup apart as a single scrubbed timeline:
 * the two halves separate, the whole mark grows, the closed book crossfades
 * into an open one whose pages swing out from the spine, and the pencil
 * settles onto the right-hand page and writes three lines across it.
 *
 * Everything is driven by `progress` (0 to 1) rather than time, so the
 * animation runs forward and backward exactly with the scroll position. The
 * one exception is the pencil's small wobble, which loops on its own so the
 * writing keeps a bit of life even when the page is still.
 *
 * The viewBox is padded well past the artwork so nothing clips once the
 * halves have travelled and the mark has scaled up.
 */
export function LogoSplit({
  progress,
  className = "",
}: {
  progress: MotionValue<number>;
  className?: string;
}) {
  // The whole mark grows as it comes apart.
  const scale = useTransform(progress, [0, 0.85], [1, 1.5]);

  // Stage one: the closed logo separates, then hands over to the open book.
  const closedOpacity = useTransform(progress, [0.06, 0.3], [1, 0]);
  const closedBookX = useTransform(progress, [0, 0.3], [0, -20]);
  const closedBookRotate = useTransform(progress, [0, 0.3], [0, -12]);
  const closedPencilX = useTransform(progress, [0, 0.3], [0, 26]);
  const closedPencilRotate = useTransform(progress, [0, 0.3], [0, 24]);

  // Stage two: the open book fades in and its covers swing off the spine.
  const openOpacity = useTransform(progress, [0.24, 0.44], [0, 1]);
  const rightPage = useTransform(progress, [0.26, 0.66], [0.08, 1]);
  const leftPage = useTransform(progress, [0.3, 0.72], [0.08, 1]);

  // Stage three: the pencil crosses the page as the lines appear under it.
  const penX = useTransform(progress, [0.4, 1], [16, 34]);
  const penY = useTransform(progress, [0.4, 1], [-14, 26]);
  const penRotate = useTransform(progress, [0.3, 0.5], [24, 38]);
  const penOpacity = useTransform(progress, [0.24, 0.42], [0, 1]);

  const line1 = useTransform(progress, [0.58, 0.72], [1, 0]);
  const line2 = useTransform(progress, [0.68, 0.82], [1, 0]);
  const line3 = useTransform(progress, [0.78, 0.92], [1, 0]);

  // Rotating each half about its own centre is what makes them read as two
  // separate objects rather than one group being nudged.
  const ownCentre = {
    transformBox: "fill-box",
    transformOrigin: "center",
  } as const;

  // The pages hinge on the spine, so they pivot about it, not themselves.
  const spineHinge = {
    transformBox: "view-box",
    transformOrigin: "50px 55px",
  } as const;

  return (
    <motion.svg
      viewBox="-40 -18 180 146"
      fill="none"
      stroke="currentColor"
      strokeWidth="5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      style={{ scale }}
      className={className}
    >
      {/* -------- closed mark: the logo exactly as it is drawn elsewhere -- */}
      <motion.g style={{ opacity: closedOpacity }}>
        <motion.g
          style={{ x: closedBookX, rotate: closedBookRotate, ...ownCentre }}
        >
          <rect x="25" y="15" width="38" height="56" />
          <path d="M 25 15 H 13 V 71 Q 13 85 25 85 H 63" />
        </motion.g>
        <motion.g
          style={{ x: closedPencilX, rotate: closedPencilRotate, ...ownCentre }}
        >
          <path d="M 75 15 H 87 V 63 L 81 85 L 75 63 Z" />
        </motion.g>
      </motion.g>

      {/* ---------------- open book: two pages hinged on a centre spine -- */}
      <motion.g style={{ opacity: openOpacity }}>
        <motion.g style={{ scaleX: leftPage, ...spineHinge }}>
          <path d="M 50 26 H 12 V 84 H 50 Z" />
        </motion.g>
        <motion.g style={{ scaleX: rightPage, ...spineHinge }}>
          <path d="M 50 26 H 88 V 84 H 50 Z" />

          {/* Written lines, drawn on by scroll via a normalised dash. */}
          <motion.path
            d="M 58 44 H 80"
            strokeWidth="3"
            stroke="#78cfe9"
            pathLength={1}
            strokeDasharray={1}
            style={{ strokeDashoffset: line1 }}
          />
          <motion.path
            d="M 58 56 H 82"
            strokeWidth="3"
            stroke="#78cfe9"
            pathLength={1}
            strokeDasharray={1}
            style={{ strokeDashoffset: line2 }}
          />
          <motion.path
            d="M 58 68 H 73"
            strokeWidth="3"
            stroke="#78cfe9"
            pathLength={1}
            strokeDasharray={1}
            style={{ strokeDashoffset: line3 }}
          />
        </motion.g>

        {/* Spine last so it sits over both page edges. */}
        <path d="M 50 24 V 86" />
      </motion.g>

      {/* ------------------------------- pencil, poised over the page --- */}
      <motion.g
        style={{
          x: penX,
          y: penY,
          rotate: penRotate,
          opacity: penOpacity,
          ...ownCentre,
        }}
      >
        <motion.g
          animate={{ x: [0, 1.6, 0], y: [0, 1.1, 0] }}
          transition={{ duration: 0.5, repeat: Infinity, ease: "easeInOut" }}
        >
          <path d="M 75 15 H 87 V 63 L 81 85 L 75 63 Z" />
        </motion.g>
      </motion.g>
    </motion.svg>
  );
}
