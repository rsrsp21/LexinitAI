import { motion } from "motion/react";

/**
 * Endless horizontal ticker. The row is rendered twice and translated by
 * exactly -50%, so the second copy lands where the first began and the loop
 * has no visible seam.
 */
export function Marquee({
  items,
  reverse = false,
  duration = 38,
  className = "",
}: {
  items: string[];
  reverse?: boolean;
  duration?: number;
  className?: string;
}) {
  const row = [...items, ...items];

  return (
    <div
      className={`relative overflow-hidden border-y border-white/10 py-5 ${className}`}
      // Feather the ends so strips slide out of view instead of being cut off.
      style={{
        maskImage:
          "linear-gradient(to right, transparent, black 8%, black 92%, transparent)",
        WebkitMaskImage:
          "linear-gradient(to right, transparent, black 8%, black 92%, transparent)",
      }}
      aria-hidden="true"
    >
      <motion.div
        className="flex w-max whitespace-nowrap will-change-transform"
        animate={{ x: reverse ? ["-50%", "0%"] : ["0%", "-50%"] }}
        transition={{ duration, ease: "linear", repeat: Infinity }}
      >
        {row.map((item, index) => (
          <span
            key={`${item}-${index}`}
            className="flex items-center gap-8 pr-8 text-[11px] uppercase tracking-[0.28em] text-white/40"
          >
            {item}
            <span className="text-[#4db8db]">/</span>
          </span>
        ))}
      </motion.div>
    </div>
  );
}
