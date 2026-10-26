import { createFileRoute, Link } from "@tanstack/react-router";
import {
  motion,
  useMotionTemplate,
  useMotionValue,
  useMotionValueEvent,
  useTransform,
  type MotionValue,
} from "motion/react";
import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type RefObject,
} from "react";
import { ArrowLeft, ArrowRight, Check, Loader2 } from "lucide-react";

import { Logo } from "@/components/logo";
import { LogoSplit } from "@/components/logo-split";
import { Marquee } from "@/components/marquee";
import { Starfield } from "@/components/starfield";
import { useSmoothScroll } from "@/components/smooth-scroll";

export const Route = createFileRoute("/waitlist")({
  head: () => ({
    meta: [
      { title: "Join the Lexinit waitlist" },
      {
        name: "description",
        content:
          "Lexinit turns anything you want to learn into a structured course. Join the waitlist for early access.",
      },
      { property: "og:title", content: "Join the Lexinit waitlist" },
      {
        property: "og:description",
        content: "Early access to your AI-powered personalized learning space.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Waitlist,
});

const STORAGE_KEY = "lexinit:waitlist-joined";

const EASE = [0.22, 1, 0.36, 1] as const;

const ACCENT = "#78cfe9";

const SUBJECTS = [
  "Organic chemistry",
  "System design",
  "Linear algebra",
  "Machine learning",
  "Microeconomics",
  "Anatomy",
  "Constitutional law",
  "Thermodynamics",
  "Data structures",
  "Art history",
];

const CAPABILITIES = [
  "Study materials",
  "Adaptive assessments",
  "Flashcards",
  "Spaced review",
  "Learning path",
  "Progress insights",
  "Video lessons",
  "Source grounded",
];

/**
 * A long, scroll-driven page: pinned scenes, scrubbed type, and marquees over
 * a persistent starfield with books and pencils tumbling through it.
 *
 * Locked to its own dark palette rather than the theme tokens -- the backdrop
 * only reads against deep space, so it must not flip with the site-wide
 * light/dark toggle.
 */
function Waitlist() {
  useSmoothScroll();

  return (
    <div className="relative bg-[#04070f] text-white antialiased">
      <div className="pointer-events-none fixed inset-0 z-0">
        <Starfield />
        {/* Pools darkness where the type sits while leaving the edges of the
            frame lively. */}
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgba(4,7,15,0.82)_0%,rgba(4,7,15,0.5)_38%,rgba(4,7,15,0)_74%)]" />
      </div>

      <div className="relative z-10">
        <Nav />
        <HeroScene />
        <Marquee items={SUBJECTS} />
        <StatementScene />
        <SourcesScene />
        <StepsScene />
        <Marquee items={CAPABILITIES} reverse duration={44} />
        <JoinScene />
        <Footer />
      </div>
    </div>
  );
}

function Nav() {
  return (
    <header className="fixed inset-x-0 top-0 z-50">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6 lg:px-10">
        <Link to="/" className="flex items-center gap-2 text-white">
          <Logo className="h-7 w-7" />
          <span className="font-display text-lg tracking-tight">Lexinit</span>
        </Link>
        <Link
          to="/"
          className="group inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-4 py-2 text-xs text-white/70 backdrop-blur-md transition hover:border-white/30 hover:text-white"
        >
          <ArrowLeft className="h-3.5 w-3.5 transition group-hover:-translate-x-0.5" />
          Back to site
        </Link>
      </div>
    </header>
  );
}

/* -------------------------------------------------------------- scenes --- */

/**
 * How far a tall scene has travelled past the viewport: 0 when its top meets
 * the top of the screen, 1 when its bottom does.
 *
 * Polls the element's rect on every frame rather than listening for scroll.
 * That is deliberate: Lenis swallows native scroll events (a listener on
 * window or document never fires while it is active), so anything driven by
 * them -- including motion's own useScroll({ target }) -- stays frozen on its
 * first frame. Reading the rect per frame is correct no matter what moves the
 * page: Lenis, a plain wheel, an anchor jump, or a restored scroll position.
 */
function useSceneProgress(ref: RefObject<HTMLElement | null>) {
  const progress = useMotionValue(0);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    let frame = 0;
    let last = -1;

    const tick = () => {
      frame = requestAnimationFrame(tick);

      const span = el.offsetHeight - window.innerHeight;
      const next =
        span <= 0
          ? 0
          : Math.min(1, Math.max(0, -el.getBoundingClientRect().top / span));

      // Only push when it actually moves, so idle frames cost nothing
      // downstream.
      if (next !== last) {
        last = next;
        progress.set(next);
      }
    };

    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [ref, progress]);

  return progress;
}

/* ---------------------------------------------------------------- hero --- */

function HeroScene() {
  const ref = useRef<HTMLElement>(null);
  const scrollYProgress = useSceneProgress(ref);

  // Each band leaves at its own rate, so the hero reads as layers falling
  // away rather than one block sliding off.
  const eyebrowY = useTransform(scrollYProgress, [0, 1], [0, 140]);
  const titleY = useTransform(scrollYProgress, [0, 1], [0, 320]);
  const tailY = useTransform(scrollYProgress, [0, 1], [0, 460]);
  const fade = useTransform(scrollYProgress, [0, 0.62], [1, 0]);
  const blurPx = useTransform(scrollYProgress, [0, 0.7], [0, 14]);
  const blur = useMotionTemplate`blur(${blurPx}px)`;
  const scale = useTransform(scrollYProgress, [0, 1], [1, 0.9]);

  return (
    <section ref={ref} className="relative h-[200vh]">
      <div className="sticky top-0 flex h-[100svh] flex-col items-center justify-center px-6 text-center lg:px-10">
        <motion.div
          style={{ y: eyebrowY }}
          initial={{ opacity: 0, scale: 0.86 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 1.2, ease: EASE }}
          className="mb-6 text-white"
        >
          <LogoSplit
            progress={scrollYProgress}
            className="h-[clamp(5rem,11vw,8.5rem)] w-auto"
          />
        </motion.div>

        <motion.p
          style={{ y: eyebrowY, opacity: fade }}
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.9, ease: EASE, delay: 0.1 }}
          className="text-[11px] uppercase tracking-[0.32em] text-white/45"
        >
          Early access · Lexinit Beta
        </motion.p>

        <motion.h1
          style={{ y: titleY, opacity: fade, filter: blur, scale }}
          initial={{ opacity: 0, filter: "blur(16px)", y: 30 }}
          animate={{ opacity: 1, filter: "blur(0px)", y: 0 }}
          transition={{ duration: 1.3, ease: EASE, delay: 0.25 }}
          className="mt-8 max-w-4xl font-display text-[clamp(2.4rem,7vw,5.2rem)] font-normal leading-[1.02] tracking-tight text-balance"
        >
          Turn anything into a course
          <br />
          you&rsquo;ll <span className="italic text-[#78cfe9]">
            actually
          </span>{" "}
          finish.
        </motion.h1>

        <motion.div
          style={{ y: tailY, opacity: fade }}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 1, ease: EASE, delay: 0.95 }}
          className="mt-8 flex flex-col items-center gap-7"
        >
          <p className="max-w-md text-sm leading-relaxed text-white/55">
            Bring a topic, a syllabus, a PDF, or a playlist. Lexinit builds the
            course around it. We&rsquo;re opening to a first group of learners.
          </p>
          <a
            href="#join"
            className="group inline-flex items-center gap-2 rounded-full bg-white px-6 py-3 text-sm font-medium text-[#04070f] transition hover:bg-white/90"
          >
            Join the waitlist
            <ArrowRight className="h-4 w-4 transition group-hover:translate-x-0.5" />
          </a>
        </motion.div>

        <motion.div
          style={{ opacity: fade }}
          className="absolute inset-x-0 bottom-8 flex justify-center"
        >
          <motion.span
            animate={{ y: [0, 9, 0] }}
            transition={{ duration: 2.1, repeat: Infinity, ease: "easeInOut" }}
            className="text-[10px] uppercase tracking-[0.3em] text-white/30"
          >
            Scroll
          </motion.span>
        </motion.div>
      </div>
    </section>
  );
}

/* ----------------------------------------------------------- statement --- */

/** One word of scrubbed type: dim until the scroll position reaches it. */
function ScrubWord({
  progress,
  start,
  end,
  children,
}: {
  progress: MotionValue<number>;
  start: number;
  end: number;
  children: string;
}) {
  const opacity = useTransform(progress, [start, end], [0.14, 1]);
  const y = useTransform(progress, [start, end], [16, 0]);
  // The trailing space is a real text node, not margin -- margin alone would
  // render correctly but leave the sentence as one run-on word to screen
  // readers and to anyone copying the text.
  return (
    <>
      <motion.span style={{ opacity, y }} className="inline-block">
        {children}
      </motion.span>{" "}
    </>
  );
}

function StatementScene() {
  const ref = useRef<HTMLElement>(null);
  const scrollYProgress = useSceneProgress(ref);

  const words =
    "Most courses are built for everyone. This one is built for you.".split(
      " ",
    );

  return (
    <section id="why" ref={ref} className="relative h-[240vh]">
      <div className="sticky top-0 flex h-[100svh] items-center justify-center px-6 lg:px-10">
        <h2 className="max-w-4xl font-display text-[clamp(1.9rem,5.2vw,4rem)] font-normal leading-[1.12] tracking-tight">
          {words.map((word, index) => {
            // Spread the reveal across the first three quarters of the scene
            // so the finished sentence holds on screen before it unpins.
            const start = (index / words.length) * 0.72;
            return (
              <ScrubWord
                key={`${word}-${index}`}
                progress={scrollYProgress}
                start={start}
                end={start + 0.14}
              >
                {word}
              </ScrubWord>
            );
          })}
        </h2>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------- sources --- */

const SOURCES = [
  {
    label: "A topic",
    body: "Name the thing you want to understand and start from nothing else.",
  },
  {
    label: "A PDF",
    body: "Lecture notes, a textbook chapter, a paper you have been avoiding.",
  },
  {
    label: "A syllabus",
    body: "Hand over the course outline you were already meant to follow.",
  },
  {
    label: "A playlist",
    body: "Point at YouTube and let the videos become a structured path.",
  },
];

function SourcesScene() {
  return (
    <section id="sources" className="relative px-6 py-32 lg:px-10 lg:py-44">
      <div className="mx-auto max-w-6xl">
        <Reveal>
          <p className="text-[11px] uppercase tracking-[0.32em] text-white/40">
            Start from anything
          </p>
        </Reveal>

        <div className="mt-12 grid gap-px overflow-hidden rounded-2xl border border-white/10 bg-white/10 sm:grid-cols-2 lg:grid-cols-4">
          {SOURCES.map((source, index) => (
            <Reveal
              key={source.label}
              delay={index * 0.07}
              className="group bg-[#060a15]/85 p-8 backdrop-blur-sm transition-colors hover:bg-[#0a1120]/90"
            >
              <span className="font-display text-xs tracking-[0.2em] text-[#4db8db]">
                {String(index + 1).padStart(2, "0")}
              </span>
              <h3 className="mt-5 font-display text-xl tracking-tight">
                {source.label}
              </h3>
              <p className="mt-3 text-sm leading-relaxed text-white/55">
                {source.body}
              </p>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

/* --------------------------------------------------------------- steps --- */

const STEPS = [
  {
    title: "Bring a source",
    body: "Drop in a topic, a document, a syllabus, or a playlist. Nothing needs formatting first.",
  },
  {
    title: "Get your course",
    body: "Lexinit builds modules, study material, and flashcards grounded in what you gave it.",
  },
  {
    title: "Practice adaptively",
    body: "Assessments shift with your mastery. Miss something and the next round targets that gap.",
  },
  {
    title: "See what stuck",
    body: "Spaced review and insights show what has settled and what is quietly slipping.",
  },
];

function StepsScene() {
  const ref = useRef<HTMLElement>(null);
  const scrollYProgress = useSceneProgress(ref);
  const [active, setActive] = useState(0);

  useMotionValueEvent(scrollYProgress, "change", (value) => {
    const index = Math.floor(value * STEPS.length);
    setActive(Math.min(STEPS.length - 1, Math.max(0, index)));
  });

  return (
    <section id="how" ref={ref} className="relative h-[330vh]">
      <div className="sticky top-0 flex h-[100svh] items-center px-6 lg:px-10">
        <div className="mx-auto grid w-full max-w-6xl gap-12 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1fr)] lg:gap-20">
          <div className="flex items-start gap-6">
            <div className="font-display text-[clamp(4rem,12vw,9rem)] leading-none tracking-tight text-white/90 tabular-nums">
              {String(active + 1).padStart(2, "0")}
            </div>
            <div className="pt-3 text-[11px] uppercase tracking-[0.28em] text-white/35">
              / {String(STEPS.length).padStart(2, "0")}
            </div>
          </div>

          <ul className="space-y-8">
            {STEPS.map((step, index) => {
              const on = index === active;
              return (
                <li key={step.title}>
                  <motion.div
                    animate={{ opacity: on ? 1 : 0.28, x: on ? 0 : -6 }}
                    transition={{ duration: 0.5, ease: EASE }}
                  >
                    <div className="flex items-baseline gap-4">
                      <span
                        className="h-px w-8 shrink-0 transition-colors"
                        style={{
                          backgroundColor: on ? ACCENT : "rgba(255,255,255,.3)",
                        }}
                      />
                      <h3 className="font-display text-[clamp(1.25rem,2.6vw,2rem)] tracking-tight">
                        {step.title}
                      </h3>
                    </div>
                    <p className="mt-3 max-w-md pl-12 text-sm leading-relaxed text-white/55">
                      {step.body}
                    </p>
                  </motion.div>
                </li>
              );
            })}
          </ul>
        </div>
      </div>
    </section>
  );
}

/* -------------------------------------------------------------- shared --- */

function Reveal({
  children,
  delay = 0,
  className = "",
}: {
  children: React.ReactNode;
  delay?: number;
  className?: string;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 26 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-80px" }}
      transition={{ duration: 0.8, ease: EASE, delay }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

/* ---------------------------------------------------------------- join --- */

function JoinScene() {
  return (
    <section
      id="join"
      className="relative scroll-mt-20 px-6 py-32 lg:px-10 lg:py-44"
    >
      <div className="mx-auto max-w-xl">
        <Reveal>
          <WaitlistForm />
        </Reveal>
      </div>
    </section>
  );
}

type Status = "idle" | "submitting" | "done";

function WaitlistForm() {
  const [status, setStatus] = useState<Status>("idle");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [goal, setGoal] = useState("");
  const [error, setError] = useState<string | null>(null);

  // Returning visitors should not be asked to sign up twice.
  useEffect(() => {
    try {
      if (localStorage.getItem(STORAGE_KEY)) setStatus("done");
    } catch {
      // Storage can throw in private mode; the form still works without it.
    }
  }, []);

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (status === "submitting") return;

    const trimmed = email.trim();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(trimmed)) {
      setError("Enter a valid email address.");
      return;
    }

    setError(null);
    setStatus("submitting");

    // TODO: replace with the real signup call, e.g.
    //   await fetch("/api/waitlist", {
    //     method: "POST",
    //     headers: { "Content-Type": "application/json" },
    //     body: JSON.stringify({ email: trimmed, name, goal }),
    //   });
    // Nothing leaves the browser until that lands.
    console.info("[waitlist] pending submission", {
      email: trimmed,
      name,
      goal,
    });
    await new Promise((resolve) => setTimeout(resolve, 900));

    try {
      localStorage.setItem(STORAGE_KEY, trimmed);
    } catch {
      // Non-fatal: we just lose the "already joined" memory on this device.
    }
    setStatus("done");
  };

  if (status === "done") {
    return (
      <div className="rounded-2xl border border-white/12 bg-white/[0.04] p-10 text-center backdrop-blur-xl">
        <motion.div
          initial={{ scale: 0.7, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ duration: 0.6, ease: EASE }}
          className="mx-auto flex h-12 w-12 items-center justify-center rounded-full border border-white/20 bg-white/10"
        >
          <Check className="h-5 w-5" />
        </motion.div>
        <h3 className="mt-6 font-display text-2xl tracking-tight">
          You are on the list
        </h3>
        <p className="mx-auto mt-3 max-w-sm text-sm leading-relaxed text-white/55">
          We will email you as soon as your spot opens up. No newsletter, no
          noise — just the invite.
        </p>
        <Link
          to="/"
          className="mt-8 inline-flex items-center gap-2 text-sm text-white/60 underline-offset-4 transition hover:text-white hover:underline"
        >
          Back to the site
        </Link>
      </div>
    );
  }

  const busy = status === "submitting";

  return (
    <form
      onSubmit={onSubmit}
      className="rounded-2xl border border-white/12 bg-white/[0.04] p-8 backdrop-blur-xl sm:p-10"
    >
      <h3 className="font-display text-2xl tracking-tight">
        Request an invite
      </h3>
      <p className="mt-2 text-sm text-white/50">
        Takes ten seconds. We only use this to send your invite.
      </p>

      <div className="mt-8 space-y-5">
        <Field label="Email" htmlFor="wl-email" required>
          <input
            id="wl-email"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="you@example.com"
            autoComplete="email"
            required
            aria-invalid={error ? true : undefined}
            aria-describedby={error ? "wl-email-error" : undefined}
            className="w-full rounded-lg border border-white/15 bg-white/5 px-4 py-3 text-sm text-white outline-none transition placeholder:text-white/30 focus:border-white/40 focus:bg-white/[0.07]"
          />
        </Field>

        <Field label="Name" htmlFor="wl-name" optional>
          <input
            id="wl-name"
            type="text"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="What should we call you?"
            autoComplete="name"
            className="w-full rounded-lg border border-white/15 bg-white/5 px-4 py-3 text-sm text-white outline-none transition placeholder:text-white/30 focus:border-white/40 focus:bg-white/[0.07]"
          />
        </Field>

        <Field label="What do you want to learn?" htmlFor="wl-goal" optional>
          <select
            id="wl-goal"
            value={goal}
            onChange={(event) => setGoal(event.target.value)}
            className="w-full appearance-none rounded-lg border border-white/15 bg-white/5 px-4 py-3 text-sm text-white outline-none transition focus:border-white/40 focus:bg-white/[0.07] [&>option]:bg-[#0b1020] [&>option]:text-white"
          >
            <option value="">Pick one</option>
            <option value="exam">Studying for an exam</option>
            <option value="career">Skilling up for work</option>
            <option value="curiosity">Learning for the fun of it</option>
            <option value="teaching">Teaching or training others</option>
          </select>
        </Field>
      </div>

      {error ? (
        <p
          id="wl-email-error"
          role="alert"
          className="mt-4 text-sm text-red-300"
        >
          {error}
        </p>
      ) : null}

      <button
        type="submit"
        disabled={busy}
        className="group mt-8 inline-flex w-full items-center justify-center gap-2 rounded-full bg-white px-6 py-3.5 text-sm font-medium text-[#04070f] transition hover:bg-white/90 disabled:opacity-60"
      >
        {busy ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" />
            Joining
          </>
        ) : (
          <>
            Join the waitlist
            <ArrowRight className="h-4 w-4 transition group-hover:translate-x-0.5" />
          </>
        )}
      </button>

      <p className="mt-4 text-center text-xs text-white/35">
        No spam. Unsubscribe any time.
      </p>
    </form>
  );
}

function Field({
  label,
  htmlFor,
  required,
  optional,
  children,
}: {
  label: string;
  htmlFor: string;
  required?: boolean;
  optional?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label
        htmlFor={htmlFor}
        className="mb-2 flex items-baseline gap-2 text-xs uppercase tracking-[0.18em] text-white/45"
      >
        {label}
        {required ? <span className="text-white/30">required</span> : null}
        {optional ? <span className="text-white/25">optional</span> : null}
      </label>
      {children}
    </div>
  );
}

function Footer() {
  return (
    <footer className="relative border-t border-white/10 bg-[#04070f]/80 backdrop-blur-sm">
      <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 px-6 py-10 text-xs text-white/40 sm:flex-row lg:px-10">
        <div className="flex items-center gap-2">
          <Logo className="h-5 w-5" />
          <span>© {new Date().getFullYear()} Lexinit</span>
        </div>
        <div className="flex items-center gap-6">
          <Link to="/privacy" className="transition hover:text-white">
            Privacy
          </Link>
          <Link to="/terms" className="transition hover:text-white">
            Terms
          </Link>
          <Link to="/" className="transition hover:text-white">
            Home
          </Link>
        </div>
      </div>
    </footer>
  );
}
