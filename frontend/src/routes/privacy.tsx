import { createFileRoute, Link } from "@tanstack/react-router";
import type { ReactNode } from "react";

import { ThemeToggle } from "@/components/theme-toggle";
import { Logo } from "@/components/logo";

export const Route = createFileRoute("/privacy")({
  head: () => ({
    meta: [
      { title: "Privacy Policy | Lexinit" },
      {
        name: "description",
        content: "Lexinit AI Privacy Policy.",
      },
    ],
  }),
  component: Privacy,
});

const apiServices = [
  {
    service: "Gemini API (Google)",
    purpose:
      "Generate Study Materials, Flashcards, Assessments, and adaptive Learning Paths",
  },
  {
    service: "Cloud Vision API (Google)",
    purpose:
      "Extract text and concepts from uploaded educational images or documents",
  },
  {
    service: "YouTube Data API",
    purpose:
      "Recommend and embed public educational videos using YouTube URLs only",
  },
];

const collected = [
  "Account and profile details you provide, such as name, email address, learning profile, and optional school, organization, role, or experience information",
  "Password hashes, never plain-text passwords",
  "Topic, course module, difficulty, uploaded educational files, and prompt inputs you submit for content generation",
  "Generated courses, Study Materials, Flashcards, Assessments, Learning Paths, Video Lecture links, and Additional Resource links",
  "Assessment answers, completion activity, and progress signals used to show your learning progress and next steps",
  "Basic session and technical activity needed for login, security, debugging, performance, and product reliability",
];

const notCollected = [
  "YouTube login information or private YouTube account metadata",
  "Google account credentials",
  "Payment details for plans that are not yet active",
  "Third-party advertising identifiers",
];

const storageUses = [
  "Maintain your signed-in session",
  "Improve session continuity",
  "Reduce repeated API calls with cached generated content",
  "Remember interface preferences such as theme",
];

const usage = [
  "Generate personalized Study Materials using AI APIs",
  "Display relevant video lectures and web resources",
  "Save courses to your account",
  "Monitor performance, prevent abuse, and debug technical issues",
];

const internalAccess = [
  "Authorized personnel may access account, session, and technical data when reasonably needed to provide support, secure the service, or investigate a reliability issue",
];

const externalSharing = [
  "Lexinit does not sell personal data",
  "Topic-related inputs and uploaded educational content may be sent to Google Gemini or Google Cloud Vision to create learning content",
  "Public YouTube video information and transcripts may be retrieved to find, display, and support suitable video lectures",
  "Lexinit does not use or integrate third-party advertising trackers",
];

const retention = [
  "Keeps account details, courses, progress, and uploaded sources while your account remains active or until they are deleted or you request deletion",
  "Keeps limited operational records and backups for a reasonable period where needed for security, fraud prevention, recovery, or legal obligations",
  "May remove or anonymize information when it is no longer needed for these purposes",
];

const security = [
  "Encrypted communications where HTTPS is used",
  "Secured API key handling through environment configuration",
  "Password hashing instead of storing plain-text passwords",
  "Limited internal access to production data",
];

function Privacy() {
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
            Privacy Policy
          </h1>
          <p className="mt-3 text-sm text-muted-foreground">
            Last updated: July 19, 2026
          </p>
          <p className="mt-5 max-w-3xl text-base leading-7 text-muted-foreground">
            At Lexinit AI ("Lexinit", "we", "our", or "us"), we value your
            privacy and are committed to protecting your personal data. This
            Privacy Policy describes how we collect, use, store, and protect
            information when you use our platform.
          </p>
          <p className="mt-3 max-w-3xl text-base leading-7 text-muted-foreground">
            By using Lexinit, you agree to the practices described in this
            policy and our Terms of Service.
          </p>
        </div>
      </section>

      <div className="mx-auto grid max-w-5xl gap-6 px-6 py-10">
        <PolicySection title="1. What Lexinit Does">
          <p>Lexinit is an AI-powered educational platform that generates:</p>
          <ul>
            <li>Study Materials</li>
            <li>Flashcards</li>
            <li>Personalized Assessments</li>
            <li>Learning Paths</li>
            <li>Video Lecture recommendations</li>
            <li>Web-based reference links</li>
          </ul>
          <p>
            We process user-submitted learning inputs only as needed to provide,
            secure, and improve the learning workspace.
          </p>
        </PolicySection>

        <PolicySection title="2. Use of External APIs">
          <p>
            Lexinit uses the following third-party services to provide learning
            content:
          </p>
          <div className="mt-5 overflow-hidden rounded-2xl border border-border">
            <div className="grid grid-cols-[0.9fr_1.5fr] border-b border-border bg-muted/50 px-4 py-3 text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">
              <span>API / Service</span>
              <span>Purpose</span>
            </div>
            {apiServices.map((item) => (
              <div
                key={item.service}
                className="grid grid-cols-[0.9fr_1.5fr] gap-4 border-b border-border px-4 py-4 last:border-b-0"
              >
                <div className="font-medium text-foreground">
                  {item.service}
                </div>
                <div>{item.purpose}</div>
              </div>
            ))}
          </div>
          <p>
            We do not access your Google or YouTube account credentials. Lexinit
            stores public video metadata, links, and—when available—transcript
            content needed for the learning experience.
          </p>
        </PolicySection>

        <PolicySection title="3. What We Collect">
          <p>
            Lexinit collects only what is needed to operate the learning
            workspace:
          </p>
          <ul>
            {collected.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          <p>
            Lexinit is designed to avoid unnecessary sensitive data collection.
            We do not collect:
          </p>
          <ul>
            {notCollected.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </PolicySection>

        <PolicySection title="4. Cookies and Local Storage">
          <p>We use essential cookies and local storage to:</p>
          <ul>
            {storageUses.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          <p>No third-party advertising cookies or trackers are used.</p>
        </PolicySection>

        <PolicySection title="5. How We Use and Share Data">
          <h3>Usage</h3>
          <ul>
            {usage.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>

          <h3>Internal Access</h3>
          <ul>
            {internalAccess.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>

          <h3>External Sharing</h3>
          <ul>
            {externalSharing.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          <p>
            We do not sell personal data or use third-party advertising
            trackers.
          </p>
        </PolicySection>

        <PolicySection title="6. Data Storage and Retention">
          <p>Lexinit:</p>
          <ul>
            {retention.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </PolicySection>

        <PolicySection title="7. Third-Party Terms and Privacy">
          <p>
            Some features rely on Google and YouTube. Their handling of data is
            governed by their own policies, including the{" "}
            <a
              className="font-medium text-foreground underline underline-offset-4"
              href="https://policies.google.com/privacy"
              target="_blank"
              rel="noreferrer"
            >
              Google Privacy Policy
            </a>{" "}
            and{" "}
            <a
              className="font-medium text-foreground underline underline-offset-4"
              href="https://www.youtube.com/t/terms"
              target="_blank"
              rel="noreferrer"
            >
              YouTube Terms of Service
            </a>
            .
          </p>
        </PolicySection>

        <PolicySection title="8. Children's Privacy">
          <p>
            If you are under the age at which you may independently consent to
            data processing where you live, use Lexinit only with a parent or
            legal guardian's involvement and consent. A parent or guardian may
            contact us to request review or deletion of a child's account.
          </p>
        </PolicySection>

        <PolicySection title="9. Security Measures">
          <p>We follow best practices for data protection, including:</p>
          <ul>
            {security.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </PolicySection>

        <PolicySection title="10. Your Rights">
          <p>You may:</p>
          <ul>
            <li>Request access to or correction of your account information</li>
            <li>Request deletion of your account or retained personal data</li>
            <li>Withdraw consent where processing relies on your consent</li>
          </ul>
          <p>
            To make any such request, contact us at{" "}
            <a
              className="font-medium text-foreground underline underline-offset-4"
              href="mailto:lexinit.inc@gmail.com"
            >
              lexinit.inc@gmail.com
            </a>
            .
          </p>
        </PolicySection>

        <PolicySection title="11. Policy Changes">
          <p>
            This Privacy Policy may be updated from time to time. Updates will
            be posted on this page with the revised effective date. Where a
            material change requires it, we will provide additional notice.
          </p>
        </PolicySection>

        <PolicySection title="12. Contact Us">
          <p>For questions about this Privacy Policy, contact:</p>
          <p>
            Lexinit AI
            <br />
            Email:{" "}
            <a
              className="font-medium text-foreground underline underline-offset-4"
              href="mailto:lexinit.inc@gmail.com"
            >
              lexinit.inc@gmail.com
            </a>
          </p>
        </PolicySection>
      </div>
    </main>
  );
}

function PolicySection({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-border bg-card p-6 shadow-sm">
      <h2 className="font-display text-2xl tracking-tight">{title}</h2>
      <div className="mt-4 space-y-4 text-sm leading-7 text-muted-foreground [&_h3]:font-display [&_h3]:text-lg [&_h3]:tracking-tight [&_h3]:text-foreground [&_ul]:ml-5 [&_ul]:list-disc [&_ul]:space-y-1">
        {children}
      </div>
    </section>
  );
}
