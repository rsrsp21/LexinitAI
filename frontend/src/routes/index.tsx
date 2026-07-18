import { createFileRoute } from "@tanstack/react-router";
import { motion } from "motion/react";
import { useState } from "react";
import {
  BookOpen,
  BrainCircuit,
  Check,
  ListChecks,
  PlayCircle,
  LineChart,
  ArrowRight,
  FileScan,
  Instagram,
  Linkedin,
} from "lucide-react";

import { AuthDialog, type AuthMode } from "@/components/auth-dialog";
import { Logo } from "@/components/logo";
import { ThemeToggle } from "@/components/theme-toggle";
import heroImage from "@/assets/hero.jpg";
import founderImage from "@/assets/sri-ram-sai-pavan-relangi.jpg";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Lexinit - AI-powered personalized learning space" },
      {
        name: "description",
        content:
          "Lexinit is an AI-powered personalized learning space for any topic.",
      },
      {
        property: "og:title",
        content: "Lexinit - AI-powered personalized learning space",
      },
      {
        property: "og:description",
        content: "A personalized learning space for any topic.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Landing,
});

type AuthOpenHandler = (mode: AuthMode) => void;

function Landing() {
  const [authOpen, setAuthOpen] = useState(false);
  const [authMode, setAuthMode] = useState<AuthMode>("signin");

  const openAuth: AuthOpenHandler = (mode) => {
    setAuthMode(mode);
    setAuthOpen(true);
  };

  return (
    <div className="min-h-screen bg-background text-foreground">
      <Nav onAuthOpen={openAuth} />
      <Hero onAuthOpen={openAuth} />
      {/* <LogoStrip /> */}
      <Kit />
      <About />
      <Workflow />
      {/* <Impact /> */}
      <Leadership />
      <Pricing onAuthOpen={openAuth} />
      <CTA onAuthOpen={openAuth} />
      <Footer />
      <AuthDialog open={authOpen} mode={authMode} onOpenChange={setAuthOpen} />
    </div>
  );
}

function Nav({ onAuthOpen }: { onAuthOpen: AuthOpenHandler }) {
  const links = [
    ["Features", "#product"],
    ["About", "#about"],
    ["Workflow", "#workflow"],
    ["Leadership", "#leadership"],
    ["Pricing", "#pricing"],
  ];
  return (
    <header className="sticky top-0 z-50 border-b border-border/60 bg-background/80 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6 lg:px-10">
        <a href="#" className="flex items-center gap-2">
          <Logo className="h-8 w-8 text-foreground" />
          <span className="font-display text-xl tracking-tight">Lexinit</span>
        </a>
        <nav className="hidden items-center gap-8 md:flex">
          {links.map(([label, href]) => (
            <a
              key={label}
              href={href}
              className="text-sm text-muted-foreground transition hover:text-foreground"
            >
              {label}
            </a>
          ))}
        </nav>
        <div className="flex items-center gap-2">
          <ThemeToggle />
          <button
            type="button"
            onClick={() => onAuthOpen("signin")}
            className="inline-flex text-sm text-muted-foreground transition hover:text-foreground"
          >
            Sign in
          </button>
        </div>
      </div>
    </header>
  );
}

function Hero({ onAuthOpen }: { onAuthOpen: AuthOpenHandler }) {
  return (
    <section className="relative overflow-hidden border-b border-border">
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute -left-40 top-20 h-[520px] w-[520px] rounded-full bg-accent/15 blur-[120px]" />
        <div className="absolute right-[-10%] top-[-10%] h-[480px] w-[480px] rounded-full bg-primary/10 blur-[120px]" />
        <div
          className="absolute inset-0 opacity-[0.05]"
          style={{
            backgroundImage:
              "linear-gradient(var(--color-foreground) 1px, transparent 1px), linear-gradient(90deg, var(--color-foreground) 1px, transparent 1px)",
            backgroundSize: "56px 56px",
            maskImage:
              "radial-gradient(ellipse at center, black 40%, transparent 75%)",
          }}
        />
      </div>

      <div className="relative mx-auto max-w-6xl px-6 pb-16 pt-10 text-center lg:px-10 lg:pb-20 lg:pt-14">
        <motion.h1
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1], delay: 0.05 }}
          className="mx-auto max-w-4xl font-display text-[clamp(2.4rem,5vw,4.8rem)] font-medium leading-[1] tracking-tight text-balance"
        >
          Learn anything.
          <br />
          <span className="italic text-accent">Actually</span> finish it.
        </motion.h1>

        <motion.p
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1], delay: 0.15 }}
          className="mx-auto mt-4 max-w-2xl text-sm leading-6 text-muted-foreground text-balance sm:text-base"
        >
          Lexinit is your AI-powered personalized learning space.
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.28 }}
          className="mt-6 flex flex-wrap items-center justify-center gap-3"
        >
          <button
            type="button"
            onClick={() => onAuthOpen("signup")}
            className="group inline-flex items-center gap-2 rounded-full bg-primary px-6 py-3 text-sm font-medium text-primary-foreground transition hover:opacity-90"
          >
            Start free
            <ArrowRight className="h-4 w-4 transition group-hover:translate-x-0.5" />
          </button>
          <a
            href="#workflow"
            className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-5 py-3 text-sm font-medium text-foreground transition hover:bg-muted"
          >
            <PlayCircle className="h-4 w-4" />
            See workflow
          </a>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.4 }}
          className="relative mx-auto mt-10 max-w-4xl"
        >
          <div className="overflow-hidden rounded-2xl border border-border bg-card shadow-[var(--shadow-elegant)]">
            <div className="flex items-center gap-2 border-b border-border bg-muted/60 px-4 py-2.5">
              <span className="h-2.5 w-2.5 rounded-full bg-destructive/60" />
              <span className="h-2.5 w-2.5 rounded-full bg-accent/70" />
              <span className="h-2.5 w-2.5 rounded-full bg-emerald-500/60" />
              <span className="ml-3 text-xs text-muted-foreground">
                lexinit.app / new course
              </span>
            </div>
            <div className="grid gap-0 sm:grid-cols-[220px_minmax(0,1fr)]">
              <div className="hidden border-r border-border p-5 sm:block">
                {["Study Materials", "Flashcards", "Assessments"].map(
                  (s, i) => (
                    <div
                      key={s}
                      className={`mt-2 rounded-lg px-3 py-2 text-sm ${
                        i === 0
                          ? "bg-accent/10 font-medium"
                          : "text-muted-foreground"
                      }`}
                    >
                      {s}
                    </div>
                  ),
                )}
              </div>
              <div className="p-6 text-left">
                <div className="font-display text-2xl leading-tight tracking-tight sm:text-3xl">
                  Your personalized course
                </div>
                <div className="mt-5 grid gap-3 sm:grid-cols-3">
                  {[
                    { k: "6", l: "Modules" },
                    { k: "10", l: "Flashcards" },
                    { k: "3", l: "Assessments" },
                  ].map((x) => (
                    <div
                      key={x.l}
                      className="rounded-lg border border-border bg-background p-3"
                    >
                      <div className="font-display text-2xl text-foreground">
                        {x.k}
                      </div>
                      <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
                        {x.l}
                      </div>
                    </div>
                  ))}
                </div>
                <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-muted">
                  <div className="h-full w-[38%] bg-accent" />
                </div>
                <div className="mt-2 text-xs text-muted-foreground">
                  Progress updates as you practice
                </div>
              </div>
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
}

function Kit() {
  const items = [
    {
      icon: FileScan,
      title: "Learn from what you have",
      copy: "Start with text, PDFs, images, voice notes, or scanned sources and keep everything in one course.",
    },
    {
      icon: BookOpen,
      title: "Personalized without limits",
      copy: "Your profile can shape examples and explanations, while your chosen topic and level always stay in control.",
    },
    {
      icon: BrainCircuit,
      title: "Adaptive learning",
      copy: "Identify weak areas and reshape your next study path around what needs more practice.",
    },
    {
      icon: PlayCircle,
      title: "Video Lectures",
      copy: "Watch focused lectures with transcripts, lecture guides, and automatic next-lecture playback.",
    },
    {
      icon: ListChecks,
      title: "Assessments",
      copy: "MCQs, true/false and short-answer checks with instant, explained feedback.",
    },
    {
      icon: LineChart,
      title: "Progress",
      copy: "See scores, concept mastery, weak areas, and the next best step in one place.",
    },
  ];
  return (
    <section
      id="product"
      className="mx-auto max-w-7xl px-6 py-12 lg:px-10 lg:py-16"
    >
      <div className="max-w-3xl">
        <h2 className="font-display text-3xl leading-[1.05] tracking-tight text-balance sm:text-4xl">
          One topic becomes a complete course.
        </h2>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-muted-foreground text-balance">
          Every course brings together Study Materials, Video Lectures,
          Flashcards, Assessments, and personalized next steps.
        </p>
      </div>

      <div className="mt-7 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {items.map(({ icon: Icon, title, copy }) => (
          <div
            key={title}
            className="group flex gap-3 rounded-2xl border border-border bg-card p-4 transition hover:border-accent/40 hover:bg-background"
          >
            <div className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-secondary text-foreground transition group-hover:bg-primary group-hover:text-primary-foreground">
              <Icon className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <h3 className="font-display text-lg leading-tight tracking-tight">
                {title}
              </h3>
              <p className="mt-1.5 text-xs leading-5 text-muted-foreground">
                {copy}
              </p>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function About() {
  return (
    <section id="about" className="border-y border-border bg-card/35">
      <div className="mx-auto grid max-w-7xl gap-8 px-6 py-14 lg:grid-cols-[0.72fr_1.28fr] lg:px-10 lg:py-20">
        <div className="overflow-hidden rounded-2xl border border-border bg-background shadow-[var(--shadow-elegant)] lg:max-w-[430px]">
          <img
            src={heroImage}
            alt="Abstract learning workspace"
            className="h-[260px] w-full object-cover sm:h-[300px] lg:h-[320px]"
          />
        </div>
        <div className="flex flex-col justify-center">
          <h2 className="font-display text-3xl leading-[1.05] tracking-tight text-balance sm:text-4xl">
            Lexinit turns scattered learning into one guided course.
          </h2>
          <div className="mt-4 space-y-3 text-sm leading-6 text-muted-foreground">
            <p>
              Most learning tools split the work across Study Materials, Video
              Lectures, Flashcards, Assessments, and progress trackers. Lexinit
              keeps them together in one course.
            </p>
            <p>
              The goal is not to generate more content for its own sake. It is
              to reduce the time between curiosity and useful practice, then
              make the next study step obvious.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}

function Workflow() {
  const steps = [
    {
      k: "01",
      t: "Drop a topic",
      d: "Paste text, upload a PDF or image, or dictate. Any subject and any level are welcome.",
    },
    {
      k: "02",
      t: "Create your course",
      d: "Study Materials, Video Lectures, Flashcards, Assessments, and resources arrive in one connected course.",
    },
    {
      k: "03",
      t: "Practice, then adapt",
      d: "Answer, review, and self-test. Follow-up practice focuses on concepts that need more work.",
    },
    {
      k: "04",
      t: "Track your progress",
      d: "See scores, mastery, weak concepts, and what to study next.",
    },
  ];
  return (
    <section id="workflow" className="border-y border-border bg-card/35">
      <div className="mx-auto max-w-7xl px-6 py-14 lg:px-10 lg:py-20">
        <div className="max-w-2xl">
          <h2 className="font-display text-3xl leading-[1.05] tracking-tight text-balance sm:text-4xl">
            Designed for fast, focused study loops.
          </h2>
          <p className="mt-4 text-sm leading-6 text-muted-foreground text-balance">
            Start broad, learn the essentials, test yourself, then build a
            sharper follow-up path from what needs more work.
          </p>
        </div>
        <ol className="mt-10 grid gap-6 border-t border-border pt-6 sm:grid-cols-2 lg:grid-cols-4">
          {steps.map((s) => (
            <li key={s.k}>
              <span className="font-display text-2xl text-accent">{s.k}</span>
              <h3 className="mt-3 font-display text-lg">{s.t}</h3>
              <p className="mt-2 text-xs leading-5 text-muted-foreground">
                {s.d}
              </p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

function Leadership() {
  return (
    <section
      id="leadership"
      className="mx-auto max-w-7xl px-6 py-8 lg:px-10 lg:py-10"
    >
      <div className="grid gap-8 lg:grid-cols-[1fr_360px] lg:items-center">
        <div>
          <h2 className="font-display text-3xl leading-[1.05] tracking-tight text-balance sm:text-4xl">
            Built with a founder-led product instinct.
          </h2>
        </div>
        <div className="rounded-2xl border border-border bg-card p-6 shadow-sm">
          <img
            src={founderImage}
            alt="Sri Ram Sai Pavan Relangi"
            className="h-20 w-20 rounded-full object-cover object-center shadow-sm"
          />
          <h3 className="mt-5 font-display text-2xl tracking-tight">
            Sri Ram Sai Pavan Relangi
          </h3>
          <p className="mt-1 text-sm text-accent">Founder, CEO and Developer</p>
          <div className="mt-5 flex items-center gap-2">
            <a
              href="https://www.linkedin.com/in/sriramsaipavanrelangi"
              target="_blank"
              rel="noreferrer"
              aria-label="Sri Ram Sai Pavan Relangi on LinkedIn"
              className="grid h-9 w-9 place-items-center rounded-full border border-border text-muted-foreground transition hover:-translate-y-0.5 hover:border-accent hover:bg-accent/10 hover:text-accent"
            >
              <Linkedin className="h-4 w-4" />
            </a>
            <a
              href="https://x.com/sriram_relangi"
              target="_blank"
              rel="noreferrer"
              aria-label="Sri Ram Sai Pavan Relangi on X"
              className="grid h-9 w-9 place-items-center rounded-full border border-border font-display text-sm font-bold text-muted-foreground transition hover:-translate-y-0.5 hover:border-accent hover:bg-accent/10 hover:text-accent"
            >
              X
            </a>
            <a
              href="https://www.instagram.com/sram_217"
              target="_blank"
              rel="noreferrer"
              aria-label="Sri Ram Sai Pavan Relangi on Instagram"
              className="grid h-9 w-9 place-items-center rounded-full border border-border text-muted-foreground transition hover:-translate-y-0.5 hover:border-accent hover:bg-accent/10 hover:text-accent"
            >
              <Instagram className="h-4 w-4" />
            </a>
          </div>
        </div>
      </div>
    </section>
  );
}

function Pricing({ onAuthOpen }: { onAuthOpen: AuthOpenHandler }) {
  const plans = [
    {
      name: "Free",
      price: "₹0",
      description: "For trying the full learning loop.",
      action: "Get Started",
      available: true,
      features: [
        "Access to all learning content",
        "5 Quick generations per 24 hours",
        "Community support",
        "3 Deep Focus generations per 24 hours",
      ],
    },
    {
      name: "Pro",
      price: "₹49",
      description: "For learners who generate often.",
      action: "Coming soon",
      available: false,
      featured: true,
      features: [
        "Full access to all features",
        "Limited to 20 generations for 24 hours",
        "Priority support",
        "Deep focus mode with advanced AI",
      ],
    },
    {
      name: "Premium",
      price: "₹99",
      description: "For heavier study and exam prep.",
      action: "Coming soon",
      available: false,
      features: [
        "Access to all learning content",
        "Unlimited Generations",
        "Exclusive support",
        "Deep focus mode with advanced AI",
      ],
    },
  ];

  return (
    <section id="pricing" className="border-y border-border bg-card/35">
      <div className="mx-auto max-w-7xl px-6 py-14 lg:px-10 lg:py-20">
        <div>
          <h2 className="font-display text-3xl leading-[1.05] tracking-tight text-balance sm:text-4xl">
            Pricing that starts simple.
          </h2>
          <p className="mt-4 max-w-2xl text-sm leading-6 text-muted-foreground">
            Start free with 5 generations every 24 hours. Pro raises the limit
            to 20, and Premium removes the generation cap.
          </p>
        </div>

        <div className="mt-8 grid gap-5 lg:grid-cols-3">
          {plans.map((plan) => (
            <div
              key={plan.name}
              className={`rounded-2xl border bg-card p-5 shadow-sm transition ${
                plan.featured
                  ? "border-accent/60 shadow-[var(--shadow-glow)]"
                  : "border-border hover:border-accent/40"
              }`}
            >
              <h3 className="font-display text-2xl tracking-tight">
                {plan.name}
              </h3>
              <p className="mt-2 text-sm text-muted-foreground">
                {plan.description}
              </p>
              <div className="mt-6 flex items-end gap-1">
                <span className="font-display text-4xl tracking-tight">
                  {plan.price}
                </span>
                <span className="pb-1.5 text-xs text-muted-foreground">
                  / month
                </span>
              </div>
              <ul className="mt-5 space-y-2.5 text-sm">
                {plan.features.map((feature) => (
                  <li key={feature} className="flex items-start gap-3">
                    <Check className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
                    <span className="text-muted-foreground">{feature}</span>
                  </li>
                ))}
              </ul>
              <button
                type="button"
                disabled={!plan.available}
                onClick={() => plan.available && onAuthOpen("signup")}
                className={`mt-6 inline-flex w-full items-center justify-center rounded-full px-5 py-2.5 text-sm font-medium transition ${
                  plan.available
                    ? "bg-primary text-primary-foreground hover:opacity-90"
                    : "cursor-not-allowed border border-border text-muted-foreground"
                }`}
              >
                {plan.action}
              </button>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/*
function Impact() {
  const stats = [
    { k: "3.4×", d: "Faster prep time vs. self-directed study" },
    { k: "72%", d: "Of learners hit weekly mastery goal" },
    { k: "18 min", d: "Median time from topic → full kit" },
  ];
  return (
    <section id="impact" className="mx-auto max-w-7xl px-6 py-24 lg:px-10 lg:py-32">
      <div className="grid gap-12 lg:grid-cols-12 lg:items-end">
        <div className="lg:col-span-6">
          <p className="text-xs uppercase tracking-[0.22em] text-accent">Impact</p>
          <h2 className="mt-4 font-display text-5xl leading-[1.02] tracking-tight text-balance lg:text-6xl">
            Study that respects your{" "}
            <em className="text-accent">time</em>.
          </h2>
        </div>
        <figure className="lg:col-span-6">
          <blockquote className="font-display text-2xl leading-snug tracking-tight text-foreground lg:text-3xl">
            “I stopped bookmarking things I'd never revisit. Lexinit turned three
            scattered PDFs into a plan I actually finished — in an afternoon.”
          </blockquote>
          <figcaption className="mt-6 flex items-center gap-3 text-sm">
            <div className="grid h-10 w-10 place-items-center rounded-full bg-primary text-primary-foreground font-display">
              A
            </div>
            <div>
              <div className="font-medium">Amara Okafor</div>
              <div className="text-muted-foreground">PhD candidate, computational biology</div>
            </div>
          </figcaption>
        </figure>
      </div>

      <div className="mt-16 grid gap-px overflow-hidden rounded-2xl border border-border bg-border sm:grid-cols-3">
        {stats.map((s) => (
          <div key={s.k} className="bg-card p-10">
            <div className="font-display text-6xl tracking-tight">{s.k}</div>
            <p className="mt-3 text-sm text-muted-foreground">{s.d}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

*/
function CTA({ onAuthOpen }: { onAuthOpen: AuthOpenHandler }) {
  return (
    <section className="mx-auto max-w-7xl px-6 py-14 lg:px-10 lg:py-20">
      <div className="relative overflow-hidden rounded-2xl bg-[#1e222b] p-7 text-white lg:p-10">
        <div className="pointer-events-none absolute -bottom-24 -left-24 h-72 w-72 rounded-full bg-accent/30 blur-3xl" />
        <div className="pointer-events-none absolute -top-24 right-0 h-72 w-72 rounded-full bg-accent/20 blur-3xl" />
        <div className="relative grid gap-6 lg:grid-cols-[1fr_auto] lg:items-end">
          <div>
            <h2 className="font-display text-3xl leading-[1.05] tracking-tight text-balance sm:text-4xl">
              Bring the topic. We'll bring the plan.
            </h2>
            <p className="mt-3 max-w-xl text-sm leading-6 text-white/75">
              Create a focused course with a clear learning path and next step.
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => onAuthOpen("signup")}
              className="group inline-flex items-center gap-2 rounded-full bg-white px-5 py-2.5 text-sm font-semibold text-[#1e222b] shadow-sm transition hover:bg-white/90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
            >
              Start free
              <ArrowRight className="h-4 w-4 transition group-hover:translate-x-0.5" />
            </button>
            <button className="inline-flex items-center gap-2 rounded-full border border-white/70 bg-white/10 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-white/20 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white">
              Book a walkthrough
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}

function Footer() {
  const groups = [
    {
      title: "Product",
      links: [
        ["Features", "#product"],
        ["About", "#about"],
        ["Workflow", "#workflow"],
        ["Pricing", "#pricing"],
      ],
    },
    {
      title: "Company",
      links: [
        ["Leadership", "#leadership"],
        ["Contact", "mailto:lexinit.inc@gmail.com"],
        ["Privacy", "/privacy"],
        ["Terms", "/terms"],
      ],
    },
  ];

  return (
    <footer className="border-t border-border">
      <div className="mx-auto grid max-w-7xl gap-10 px-6 py-14 lg:grid-cols-[1fr_auto] lg:px-10">
        <div className="max-w-sm">
          <a href="#" className="flex items-center gap-2">
            <Logo className="h-8 w-8 text-foreground" />
            <span className="font-display text-xl tracking-tight">Lexinit</span>
          </a>
          <p className="mt-4 max-w-xs text-sm text-muted-foreground">
            The AI-powered personalized learning platform for serious learners.
          </p>
          <a
            href="mailto:lexinit.inc@gmail.com"
            className="mt-4 inline-flex text-sm text-foreground/80 transition hover:text-foreground"
          >
            lexinit.inc@gmail.com
          </a>
        </div>
        <div className="grid gap-10 sm:grid-cols-2 lg:min-w-[360px] lg:justify-end">
          {groups.map(({ title, links }) => (
            <div key={title} className="lg:text-right">
              <div className="text-xs uppercase tracking-[0.2em] text-muted-foreground">
                {title}
              </div>
              <ul className="mt-4 space-y-2 text-sm">
                {links.map(([label, href]) => (
                  <li key={label}>
                    <a
                      href={href}
                      className="text-foreground/80 transition hover:text-foreground"
                    >
                      {label}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>
      <div className="border-t border-border">
        <div className="mx-auto flex max-w-7xl flex-col items-start justify-between gap-2 px-6 py-6 text-xs text-muted-foreground sm:flex-row sm:items-center lg:px-10">
          <span>
            © {new Date().getFullYear()} Lexinit, Inc. All rights reserved.
          </span>
          <span>Crafted for focused minds.</span>
        </div>
      </div>
    </footer>
  );
}
