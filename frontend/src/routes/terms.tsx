import { createFileRoute, Link } from "@tanstack/react-router";
import type { ReactNode } from "react";

import { ThemeToggle } from "@/components/theme-toggle";
import { Logo } from "@/components/logo";

export const Route = createFileRoute("/terms")({
  head: () => ({
    meta: [
      { title: "Terms of Service | Lexinit" },
      {
        name: "description",
        content: "Lexinit AI Terms of Service.",
      },
    ],
  }),
  component: Terms,
});

const apiServices = [
  {
    title: "Gemini API (Google)",
    uses: [
      "Generating Study Materials from topics and course modules",
      "Creating flashcards",
      "Designing multiple types of assessments",
      "Recommending learning paths",
    ],
    note: "Topic and source content needed to create learning content may be sent to Gemini. Do not include information you are not permitted to share.",
  },
  {
    title: "Google Cloud Vision API",
    uses: [
      "Extracting text and concepts from uploaded images or textbook snapshots",
      "Recognizing diagrams or handwritten content for study content generation",
    ],
  },
  {
    title: "YouTube Data API",
    uses: [
      "Displaying and embedding publicly available educational videos",
      "Storing video links, not personal YouTube data, to generate curated video-based learning blocks",
    ],
    note: "No personal YouTube data is accessed or stored.",
  },
];

const restrictions = [
  "Reverse-engineer or attempt to extract source data from Lexinit",
  "Present generated content as guaranteed professional, academic, medical, legal, or financial advice",
  "Interfere with or manipulate API behavior, queries, or content delivery",
  "Upload malicious files or attempt to exploit input systems",
];

const disclaimers = [
  "That generated material is always accurate or error-free",
  "That recommended resources or videos are fully aligned with your curriculum",
  "That API services used will remain available or stable",
];

const availability = [
  "Add, update, or discontinue features or API integrations at any time",
  "Limit access to services during maintenance or due to external provider outages",
];

const liability = [
  "The use of or reliance on generated content",
  "Delays or interruptions in service",
  "Errors in third-party data or APIs",
  "Misuse of the platform",
];

function Terms() {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-50 border-b border-border/60 bg-background/85 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-5xl items-center justify-between px-6">
          <Link to="/" className="flex items-center gap-2">
            <Logo className="h-8 w-8 text-foreground" />
            <span className="font-display text-xl tracking-tight">Lexinit</span>
          </Link>
          <div className="flex items-center gap-3">
            <ThemeToggle />
            <Link
              to="/"
              className="rounded-full border border-border px-4 py-2 text-sm font-medium transition hover:bg-muted"
            >
              Home
            </Link>
          </div>
        </div>
      </header>

      <section className="border-b border-border">
        <div className="mx-auto max-w-5xl px-6 py-14">
          <p className="text-sm font-medium text-accent">
            Effective Date: July 19, 2026
          </p>
          <h1 className="mt-3 font-display text-4xl leading-tight tracking-tight sm:text-5xl">
            Terms of Service
          </h1>
          <p className="mt-3 text-sm text-muted-foreground">
            Last updated: July 19, 2026
          </p>
          <p className="mt-5 max-w-3xl text-base leading-7 text-muted-foreground">
            Welcome to Lexinit AI ("Lexinit", "we", "our", or "us"). By
            accessing or using our website, application, or any part of our
            services ("Platform"), you agree to comply with and be bound by
            these Terms of Service.
          </p>
          <p className="mt-3 max-w-3xl text-base leading-7 text-muted-foreground">
            If you do not agree with any of these terms, you should not use the
            platform.
          </p>
        </div>
      </section>

      <div className="mx-auto grid max-w-5xl gap-6 px-6 py-10">
        <TermSection title="1. Acceptance of Terms">
          <p>
            By using Lexinit AI, you confirm that you have read, understood, and
            agreed to:
          </p>
          <ul>
            <li>These Terms of Service</li>
            <li>Our Privacy Policy</li>
            <li>
              The terms and privacy policies of third-party services used by
              Lexinit, including the{" "}
              <a
                href="https://www.youtube.com/t/terms"
                target="_blank"
                rel="noreferrer"
              >
                YouTube Terms of Service
              </a>{" "}
              and{" "}
              <a
                href="https://policies.google.com/privacy"
                target="_blank"
                rel="noreferrer"
              >
                Google Privacy Policy
              </a>
              .
            </li>
          </ul>
        </TermSection>

        <TermSection title="2. Platform Overview">
          <p>Lexinit AI is an adaptive learning platform that provides:</p>
          <ul>
            <li>AI-generated Study Materials</li>
            <li>Flashcards</li>
            <li>Personalized Assessments</li>
            <li>Learning Paths</li>
            <li>Video Lecture recommendations</li>
            <li>Additional Resources</li>
          </ul>
          <p>
            Users interact with the platform by selecting topics, course
            modules, and difficulty levels. All content is generated or curated
            in real time using a combination of internal logic and third-party
            AI and API services.
          </p>
        </TermSection>

        <TermSection title="3. Third-Party API Services Used">
          <p>
            Lexinit relies on the following third-party APIs for content
            generation and enrichment:
          </p>
          <div className="mt-5 grid gap-4">
            {apiServices.map((service) => (
              <article
                key={service.title}
                className="rounded-2xl border border-border bg-card p-5"
              >
                <h3 className="font-display text-xl tracking-tight">
                  {service.title}
                </h3>
                <p className="mt-3 text-sm text-muted-foreground">Used for:</p>
                <ul>
                  {service.uses.map((use) => (
                    <li key={use}>{use}</li>
                  ))}
                </ul>
                {service.note && <p className="mt-3">{service.note}</p>}
              </article>
            ))}
          </div>
          <p>
            By using Lexinit, you acknowledge and agree to the terms of use and
            privacy policies associated with each of these APIs.
          </p>
        </TermSection>

        <TermSection title="4. User Restrictions">
          <p>You agree not to:</p>
          <ul>
            {restrictions.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          <p>
            You are responsible for ensuring you have the right to submit any
            topic, source file, image, or other learning material to Lexinit.
          </p>
        </TermSection>

        <TermSection title="5. Intellectual Property">
          <p>
            Lexinit retains rights in its platform, branding, and software. You
            retain the rights you hold in content you submit. Generated learning
            content may be used for your personal learning, subject to these
            Terms and any rights that may apply to source or third-party
            content.
          </p>
          <p>
            YouTube videos and external content fetched via API remain the
            intellectual property of their original owners and are used under
            API Terms of Use.
          </p>
        </TermSection>

        <TermSection title="6. Accuracy Disclaimer">
          <p>
            Lexinit AI provides educational assistance using generative AI and
            search-based systems. We do not guarantee:
          </p>
          <ul>
            {disclaimers.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          <p>
            Users should treat content as assistive, not authoritative, and
            verify with academic sources where needed.
          </p>
        </TermSection>

        <TermSection title="7. Service Availability and Modifications">
          <p>Lexinit reserves the right to:</p>
          <ul>
            {availability.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          <p>
            We are not liable for service interruptions caused by third-party
            APIs.
          </p>
        </TermSection>

        <TermSection title="8. Limitation of Liability">
          <p>
            To the fullest extent permitted by law, Lexinit AI shall not be
            liable for any damages resulting from:
          </p>
          <ul>
            {liability.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </TermSection>

        <TermSection title="9. Governing Law">
          <p>
            These terms shall be governed by the laws of India. Any disputes
            shall be subject to the jurisdiction of the courts in Kakinada,
            Andhra Pradesh.
          </p>
        </TermSection>

        <TermSection title="10. Minors">
          <p>
            If you are under the age at which you may independently consent to
            these Terms where you live, you may use Lexinit only with the
            involvement and consent of a parent or legal guardian.
          </p>
        </TermSection>

        <TermSection title="11. Changes to These Terms">
          <p>
            We may update these Terms of Service from time to time. Continued
            use of Lexinit constitutes acceptance of any such changes.
          </p>
        </TermSection>

        <TermSection title="12. Contact">
          <p>
            If you have any questions or concerns regarding these Terms, please
            contact us at{" "}
            <a
              className="font-medium text-foreground underline underline-offset-4"
              href="mailto:lexinit.inc@gmail.com"
            >
              lexinit.inc@gmail.com
            </a>
            .
          </p>
        </TermSection>
      </div>
    </main>
  );
}

function TermSection({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-border bg-card p-6 shadow-sm">
      <h2 className="font-display text-2xl tracking-tight">{title}</h2>
      <div className="mt-4 space-y-4 text-sm leading-7 text-muted-foreground [&_ul]:ml-5 [&_ul]:list-disc [&_ul]:space-y-1">
        {children}
      </div>
    </section>
  );
}
