import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  CheckCircle2,
  Circle,
  Download,
  FileText,
  LoaderCircle,
  Play,
  Square,
  X,
} from "lucide-react";
import { renderToString } from "katex";

import { MarkdownContent } from "@/components/markdown-content";
import { SessionBackButton } from "@/components/session-back-button";
import { useSession } from "@/hooks/use-session";
import { materialChapters, sessionTitle } from "@/lib/session-utils";
import {
  apiErrorMessage,
  getCourse,
  getSourcePage,
  setCourseActivity,
  type SourceCitation,
} from "@/lib/api";
import { preloadCoursePage } from "@/lib/route-prefetch";

export const Route = createFileRoute("/app/session/$id/materials")({
  beforeLoad: ({ context, params }) =>
    preloadCoursePage(context.queryClient, params.id, { session: true }),
  validateSearch: (search: Record<string, unknown>) => ({
    module: typeof search.module === "string" ? search.module : undefined,
  }),
  head: () => ({ meta: [{ title: "Study Materials - Lexinit" }] }),
  component: Materials,
});

function Materials() {
  const { id } = Route.useParams();
  const { module } = Route.useSearch();
  const { data, isLoading, isError, error } = useSession(id);
  const queryClient = useQueryClient();
  const course = useQuery({
    queryKey: ["course", id],
    queryFn: () => getCourse(id),
    staleTime: 5_000,
  });
  const session = data?.session;
  const chapters = useMemo(() => {
    const all = materialChapters(session);
    return module ? all.filter((chapter) => chapter.moduleId === module) : all;
  }, [module, session]);
  const [active, setActive] = useState("");
  const [isReading, setIsReading] = useState(false);
  const [completionBusy, setCompletionBusy] = useState(false);
  const [completionError, setCompletionError] = useState("");
  const [citationPreview, setCitationPreview] = useState<{
    citation: SourceCitation;
    text: string;
  } | null>(null);
  const contentRef = useRef<HTMLDivElement | null>(null);
  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);

  useEffect(() => {
    if (
      chapters.length > 0 &&
      !chapters.some((chapter) => chapter.key === active)
    ) {
      setActive(chapters[0].key);
    }
  }, [active, chapters]);

  const chapter = chapters.find((item) => item.key === active) ?? chapters[0];
  const activeModuleId = module || chapter?.moduleId;
  const moduleTitle = session?.curriculum?.modules.find(
    (item) => item.module_id === activeModuleId,
  )?.title;
  const materialActivity = course.data?.modules
    .find((item) => item.module_id === activeModuleId)
    ?.activities.find((activity) => activity.type === "material");
  const materialCompleted = materialActivity?.status === "completed";

  const selectChapter = (key: string) => {
    setActive(key);
    stopReading();
  };

  useEffect(() => {
    return () => {
      if ("speechSynthesis" in window) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  useEffect(() => {
    if ("speechSynthesis" in window) {
      window.speechSynthesis.cancel();
      setIsReading(false);
    }
    contentRef.current?.scrollTo({ top: 0 });
  }, [chapter?.key]);

  const readAloud = () => {
    if (!chapter?.body || !("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(
      markdownToSpeechText(chapter.body),
    );
    utterance.lang = "en-IN";
    const voice = preferredSpeechVoice();
    if (voice) utterance.voice = voice;
    utterance.rate = 0.94;
    utterance.pitch = 1.03;
    utterance.onend = () => setIsReading(false);
    utterance.onerror = () => setIsReading(false);
    utteranceRef.current = utterance;
    setIsReading(true);
    window.speechSynthesis.speak(utterance);
  };

  const stopReading = () => {
    if (!("speechSynthesis" in window)) return;
    utteranceRef.current = null;
    window.speechSynthesis.cancel();
    setIsReading(false);
  };

  const downloadChapter = () => {
    if (!chapter) return;
    openPrintableStudyMaterial({
      topic: sessionTitle(session),
      sectionTitle: chapter.title,
      body: chapter.body,
    });
  };

  const openCitation = async (citation: SourceCitation) => {
    const page = await getSourcePage(citation.source_id, citation.page_number);
    setCitationPreview({ citation, text: page.text });
  };

  const toggleCompleted = async () => {
    if (!materialActivity) return;
    setCompletionBusy(true);
    setCompletionError("");
    try {
      const updated = await setCourseActivity(
        id,
        materialActivity.activity_id,
        materialCompleted ? "todo" : "completed",
      );
      queryClient.setQueryData(["course", id], updated);
      await queryClient.invalidateQueries({ queryKey: ["courses"] });
    } catch (cause) {
      setCompletionError(
        apiErrorMessage(cause, "Could not update Study Materials progress."),
      );
    } finally {
      setCompletionBusy(false);
    }
  };

  return (
    <div>
      <article className="flex h-[calc(100svh-190px)] min-h-[440px] flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-sm lg:h-[calc(100vh-148px)] lg:min-h-[560px]">
        <header className="shrink-0 border-b border-border p-5 sm:p-6">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex min-w-0 items-center gap-3">
              <SessionBackButton sessionId={id} />
              <FileText className="h-8 w-8 shrink-0 text-accent" />
              <h1 className="min-w-0 font-display text-3xl leading-[1.05] tracking-tight sm:text-4xl">
                {isLoading ? "Loading Study Materials" : "Study Materials"}
              </h1>
            </div>

            <div className="flex shrink-0 flex-wrap gap-3">
              {isReading ? (
                <button
                  onClick={stopReading}
                  className="inline-flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-2.5 text-sm font-medium text-destructive transition hover:border-destructive/50"
                >
                  <Square className="h-4 w-4" /> Stop reading
                </button>
              ) : (
                <button
                  onClick={readAloud}
                  disabled={!chapter?.body}
                  className="inline-flex items-center gap-2 rounded-lg border border-border bg-card px-4 py-2.5 text-sm font-medium transition hover:border-accent/50 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <Play className="h-4 w-4 text-accent" /> Read aloud
                </button>
              )}
              <button
                onClick={downloadChapter}
                disabled={!chapter?.body}
                className="inline-flex items-center gap-2 rounded-lg border border-border bg-card px-4 py-2.5 text-sm font-medium transition hover:border-accent/50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Download className="h-4 w-4 text-accent" /> Export PDF
              </button>
            </div>
          </div>

          <div className="mt-4 min-w-0">
            {isError ? (
              <p className="mt-3 text-sm text-destructive">{error.message}</p>
            ) : (
              <div className="mt-3 flex flex-wrap gap-2 text-sm text-muted-foreground">
                <span className="rounded-full border border-border bg-background/40 px-3 py-1.5">
                  <span className="font-medium text-foreground">Topic:</span>{" "}
                  {sessionTitle(session)}
                </span>
                <span className="rounded-full border border-accent/25 bg-accent/10 px-3 py-1.5 text-accent">
                  <span className="font-medium">Module:</span>{" "}
                  {moduleTitle || "All modules"}
                </span>
                {chapters.length > 1 && (
                  <label className="inline-flex items-center gap-2 rounded-full border border-border bg-background/40 px-3 py-1.5">
                    <span className="font-medium text-foreground">
                      Choose material:
                    </span>
                    <select
                      value={active}
                      onChange={(event) => selectChapter(event.target.value)}
                      className="max-w-56 bg-transparent text-sm text-foreground outline-none"
                    >
                      {chapters.map((item) => (
                        <option key={item.key} value={item.key}>
                          {item.title}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
              </div>
            )}
          </div>
        </header>

        <section
          ref={contentRef}
          className="app-scrollbar min-h-0 flex-1 overflow-y-auto bg-background/50 p-5 sm:p-7"
        >
          <div className="mx-auto max-w-4xl rounded-xl border border-border bg-card/80 p-5 sm:p-7">
            {(session?.source_citations?.length ?? 0) > 0 && (
              <div className="mb-6 rounded-2xl border border-accent/25 bg-accent/8 p-4">
                <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                  <FileText className="h-4 w-4 text-accent" /> Source-grounded
                  material
                </div>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">
                  Open a citation to verify the relevant source page.
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {uniqueCitations(session?.source_citations ?? []).map(
                    (citation) => (
                      <button
                        key={`${citation.chunk_id}:${citation.page_number}`}
                        type="button"
                        onClick={() => void openCitation(citation)}
                        className="rounded-full border border-accent/25 bg-card px-3 py-1.5 text-xs font-medium text-foreground transition hover:border-accent/50 hover:text-accent"
                      >
                        {citation.source_name} · page {citation.page_number}
                      </button>
                    ),
                  )}
                </div>
              </div>
            )}

            {citationPreview && (
              <div className="mb-6 rounded-2xl border border-border bg-background/70 p-4">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-sm font-semibold text-foreground">
                    {citationPreview.citation.source_name} · page{" "}
                    {citationPreview.citation.page_number}
                  </div>
                  <button
                    type="button"
                    onClick={() => setCitationPreview(null)}
                    aria-label="Close citation preview"
                    className="grid h-8 w-8 place-items-center rounded-full text-muted-foreground hover:bg-muted"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
                <div className="app-scrollbar mt-3 max-h-64 overflow-y-auto whitespace-pre-wrap text-sm leading-6 text-muted-foreground">
                  {citationPreview.text}
                </div>
              </div>
            )}
            <MarkdownContent
              content={
                chapter?.body ||
                "This course does not have study materials yet."
              }
            />
            {materialActivity && (
              <div className="mt-8 border-t border-border pt-6">
                <button
                  type="button"
                  onClick={() => void toggleCompleted()}
                  disabled={completionBusy}
                  className={`inline-flex min-h-11 items-center gap-2 rounded-full px-5 text-sm font-semibold transition disabled:cursor-wait disabled:opacity-60 ${materialCompleted ? "border border-accent/35 bg-accent/10 text-accent hover:bg-accent/15" : "bg-primary text-primary-foreground hover:opacity-90"}`}
                >
                  {completionBusy ? (
                    <LoaderCircle className="h-4 w-4 animate-spin" />
                  ) : materialCompleted ? (
                    <CheckCircle2 className="h-4 w-4" />
                  ) : (
                    <Circle className="h-4 w-4" />
                  )}
                  {materialCompleted
                    ? "Completed — mark as incomplete"
                    : "Mark as completed"}
                </button>
                {completionError && (
                  <p className="mt-3 text-sm text-destructive" role="alert">
                    {completionError}
                  </p>
                )}
              </div>
            )}
          </div>
        </section>
      </article>
    </div>
  );
}

function uniqueCitations(citations: SourceCitation[]) {
  const seen = new Set<string>();
  return citations.filter((citation) => {
    const key = `${citation.source_id}:${citation.page_number}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function markdownToSpeechText(markdown: string) {
  return markdown
    .replace(/```[\s\S]*?```/g, " code block omitted. ")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/^>\s?/gm, "")
    .replace(/^\s*[-*]\s+/gm, "")
    .replace(/^\s*\d+[).]\s+/gm, "")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\*([^*]+)\*/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/[_~#]/g, "")
    .replace(/\n{2,}/g, ". ")
    .replace(/\s+/g, " ")
    .trim();
}

function preferredSpeechVoice() {
  if (!("speechSynthesis" in window)) return null;

  const voices = window.speechSynthesis.getVoices();
  const englishVoices = voices.filter((voice) =>
    voice.lang.toLowerCase().startsWith("en"),
  );
  const indianVoices = englishVoices.filter(
    (voice) => voice.lang.toLowerCase() === "en-in",
  );
  const indianHints = [
    "neerja",
    "heera",
    "aditi",
    "raveena",
    "ravi",
    "prabhat",
    "india",
    "indian",
  ];
  const femaleHints = [
    "female",
    "neerja",
    "heera",
    "aditi",
    "raveena",
    "zira",
    "samantha",
    "victoria",
    "karen",
    "susan",
    "aria",
    "jenny",
    "natasha",
    "sonia",
  ];

  return (
    indianVoices.find((voice) =>
      femaleHints.some((hint) => voice.name.toLowerCase().includes(hint)),
    ) ??
    indianVoices[0] ??
    englishVoices.find((voice) =>
      indianHints.some((hint) => voice.name.toLowerCase().includes(hint)),
    ) ??
    englishVoices.find((voice) =>
      femaleHints.some((hint) => voice.name.toLowerCase().includes(hint)),
    ) ??
    englishVoices.find((voice) => voice.default) ??
    englishVoices[0] ??
    voices[0] ??
    null
  );
}

function openPrintableStudyMaterial({
  topic,
  sectionTitle,
  body,
}: {
  topic: string;
  sectionTitle: string;
  body: string;
}) {
  const printWindow = window.open("", "_blank", "width=980,height=720");
  if (!printWindow) return;

  const title = `${topic} - ${sectionTitle}`;
  const html = `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>${escapeHtml(title)}</title>
  <style>
    @page {
      size: A4;
      margin: 18mm 16mm;
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      background: #f7f7f5;
      color: #111827;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.62;
    }

    .page {
      max-width: 860px;
      margin: 32px auto;
      background: #ffffff;
      border: 1px solid #d9e0e7;
      border-radius: 24px;
      overflow: hidden;
      box-shadow: 0 24px 80px rgba(15, 23, 42, 0.12);
    }

    .brand {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 20px;
      padding: 28px 34px;
      background: #071014;
      color: #ffffff;
    }

    .brand-left {
      display: flex;
      align-items: center;
      gap: 14px;
    }

    .logo {
      width: 42px;
      height: 42px;
      display: block;
    }

    .brand-name {
      font-size: 24px;
      font-weight: 700;
      letter-spacing: -0.04em;
    }

    .brand-subtitle {
      color: rgba(255, 255, 255, 0.68);
      font-size: 12px;
      letter-spacing: 0.14em;
      text-transform: uppercase;
    }

    .meta {
      padding: 34px 38px 24px;
      border-bottom: 1px solid #e5eaf0;
      background:
        radial-gradient(circle at 100% 0%, rgba(10, 132, 155, 0.12), transparent 34%),
        linear-gradient(180deg, #ffffff, #fbfcfd);
    }

    .eyebrow {
      color: #0a849b;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.18em;
      text-transform: uppercase;
    }

    h1 {
      margin: 10px 0 16px;
      max-width: 760px;
      color: #0b1117;
      font-size: 42px;
      line-height: 1.04;
      letter-spacing: -0.055em;
    }

    .chips {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }

    .chip {
      border: 1px solid #d9e0e7;
      border-radius: 999px;
      padding: 7px 12px;
      background: rgba(255, 255, 255, 0.84);
      color: #4b5563;
      font-size: 13px;
    }

    .chip strong {
      color: #111827;
    }

    .content {
      padding: 34px 38px 42px;
      font-size: 15px;
      color: #2f3845;
    }

    .content h2,
    .content h3,
    .content h4 {
      break-after: avoid;
      color: #101820;
      letter-spacing: -0.035em;
      line-height: 1.14;
    }

    .content h2 {
      margin: 34px 0 12px;
      padding-top: 8px;
      font-size: 26px;
      border-top: 1px solid #e5eaf0;
    }

    .content h3 {
      margin: 28px 0 10px;
      font-size: 21px;
    }

    .content h4 {
      margin: 22px 0 8px;
      font-size: 17px;
    }

    .content p {
      margin: 0 0 15px;
    }

    .content ul,
    .content ol {
      margin: 0 0 18px;
      padding-left: 24px;
    }

    .content li {
      margin: 7px 0;
      padding-left: 4px;
    }

    .content strong {
      color: #0f172a;
      font-weight: 750;
    }

    .content code {
      border-radius: 7px;
      background: #eef3f7;
      color: #101820;
      padding: 2px 6px;
      font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
      font-size: 0.92em;
    }

    .math-inline {
      display: inline-flex;
      align-items: center;
      color: #0f172a;
      font-size: 1.02em;
      vertical-align: baseline;
    }

    .math-block {
      break-inside: avoid;
      overflow-x: auto;
      margin: 18px 0;
      border: 1px solid #d9e0e7;
      border-radius: 14px;
      background: #f7fafc;
      padding: 14px 16px;
      color: #0f172a;
      text-align: center;
      font-size: 17px;
    }

    math {
      font-family: "Cambria Math", "STIX Two Math", "Times New Roman", serif;
    }

    .content pre {
      break-inside: avoid;
      overflow: auto;
      margin: 18px 0;
      border: 1px solid #d9e0e7;
      border-radius: 14px;
      background: #101820;
      color: #e8eef5;
      padding: 16px;
      font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
      font-size: 12px;
      line-height: 1.55;
    }

    .content pre code {
      background: transparent;
      color: inherit;
      padding: 0;
    }

    .content blockquote {
      margin: 18px 0;
      border-left: 3px solid #0a849b;
      border-radius: 0 12px 12px 0;
      background: #f3f8fa;
      padding: 12px 16px;
      color: #536070;
    }

    .footer {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      padding: 18px 38px 24px;
      border-top: 1px solid #e5eaf0;
      color: #6b7280;
      font-size: 12px;
    }

    @media print {
      body {
        background: #ffffff;
      }

      .page {
        margin: 0;
        max-width: none;
        border: 0;
        border-radius: 0;
        box-shadow: none;
      }

      .brand,
      .meta,
      .content,
      .footer {
        print-color-adjust: exact;
        -webkit-print-color-adjust: exact;
      }

      .content h2:first-child {
        margin-top: 0;
        border-top: 0;
      }
    }
  </style>
</head>
<body>
  <main class="page">
    <header class="brand">
      <div class="brand-left">
        <img class="logo" src="${window.location.origin}/logo-light.svg" alt="Lexinit" />
        <div>
          <div class="brand-name">Lexinit</div>
          <div class="brand-subtitle">AI-powered personalized learning</div>
        </div>
      </div>
      <div class="brand-subtitle">Study material</div>
    </header>

    <section class="meta">
      <div class="eyebrow">Study Materials</div>
      <h1>${escapeHtml(sectionTitle)}</h1>
      <div class="chips">
        <span class="chip"><strong>Topic:</strong> ${escapeHtml(topic)}</span>
        <span class="chip"><strong>Section:</strong> ${escapeHtml(sectionTitle)}</span>
      </div>
    </section>

    <article class="content">
      ${markdownToPrintableHtml(body)}
    </article>

    <footer class="footer">
      <span>Generated by Lexinit</span>
      <span>${escapeHtml(new Date().toLocaleDateString())}</span>
    </footer>
  </main>
  <script>
    window.addEventListener("load", () => {
      setTimeout(() => window.print(), 250);
    });
  </script>
</body>
</html>`;

  printWindow.document.open();
  printWindow.document.write(html);
  printWindow.document.close();
}

function markdownToPrintableHtml(markdown: string) {
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  const html: string[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    const trimmed = line.trim();

    if (!trimmed) {
      index += 1;
      continue;
    }

    if (trimmed.startsWith("```")) {
      const code: string[] = [];
      index += 1;
      while (index < lines.length && !lines[index].trim().startsWith("```")) {
        code.push(lines[index]);
        index += 1;
      }
      html.push(`<pre><code>${escapeHtml(code.join("\n"))}</code></pre>`);
      index += 1;
      continue;
    }

    if (trimmed.startsWith("$$")) {
      const math: string[] = [];
      const firstLine = trimmed.replace(/^\$\$\s*/, "");
      if (firstLine && !firstLine.endsWith("$$")) math.push(firstLine);
      if (firstLine.endsWith("$$")) {
        math.push(firstLine.replace(/\s*\$\$$/, ""));
        html.push(
          `<div class="math-block">${renderPrintableMath(math.join("\n"), true)}</div>`,
        );
        index += 1;
        continue;
      }
      index += 1;
      while (index < lines.length && !lines[index].trim().endsWith("$$")) {
        math.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) {
        math.push(lines[index].trim().replace(/\s*\$\$$/, ""));
        index += 1;
      }
      html.push(
        `<div class="math-block">${renderPrintableMath(math.join("\n"), true)}</div>`,
      );
      continue;
    }

    const heading = trimmed.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      const level = Math.min(Math.max(heading[1].length + 1, 2), 4);
      html.push(`<h${level}>${renderPrintableInline(heading[2])}</h${level}>`);
      index += 1;
      continue;
    }

    const quote = trimmed.match(/^>\s?(.+)$/);
    if (quote) {
      const quotes = [quote[1]];
      index += 1;
      while (index < lines.length) {
        const next = lines[index].trim().match(/^>\s?(.+)$/);
        if (!next) break;
        quotes.push(next[1]);
        index += 1;
      }
      html.push(
        `<blockquote>${renderPrintableInline(quotes.join(" "))}</blockquote>`,
      );
      continue;
    }

    const unordered = trimmed.match(/^[-*]\s+(.+)$/);
    const ordered = trimmed.match(/^\d+[).]\s+(.+)$/);
    if (unordered || ordered) {
      const orderedList = Boolean(ordered);
      const items: string[] = [];
      while (index < lines.length) {
        const item = lines[index]
          .trim()
          .match(orderedList ? /^\d+[).]\s+(.+)$/ : /^[-*]\s+(.+)$/);
        if (!item) break;
        items.push(`<li>${renderPrintableInline(item[1])}</li>`);
        index += 1;
      }
      html.push(
        `<${orderedList ? "ol" : "ul"}>${items.join("")}</${orderedList ? "ol" : "ul"}>`,
      );
      continue;
    }

    const paragraph = [trimmed];
    index += 1;
    while (index < lines.length) {
      const next = lines[index].trim();
      if (
        !next ||
        /^(#{1,4})\s+/.test(next) ||
        /^[-*]\s+/.test(next) ||
        /^\d+[).]\s+/.test(next) ||
        /^>\s?/.test(next) ||
        next.startsWith("```")
      ) {
        break;
      }
      paragraph.push(next);
      index += 1;
    }
    html.push(`<p>${renderPrintableInline(paragraph.join(" "))}</p>`);
  }

  return html.join("\n");
}

function renderPrintableInline(text: string) {
  const parts = text
    .split(
      /(\$\$[^$]+\$\$|\$[^$\n]+\$|\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\))/g,
    )
    .filter(Boolean);
  return parts
    .map((part) => {
      if (
        (part.startsWith("$$") && part.endsWith("$$")) ||
        (part.startsWith("$") && part.endsWith("$"))
      ) {
        const delimiterLength = part.startsWith("$$") ? 2 : 1;
        return `<span class="math-inline">${renderPrintableMath(part.slice(delimiterLength, -delimiterLength), false)}</span>`;
      }
      if (part.startsWith("**") && part.endsWith("**")) {
        return `<strong>${escapeHtml(part.slice(2, -2))}</strong>`;
      }
      if (part.startsWith("`") && part.endsWith("`")) {
        return `<code>${escapeHtml(part.slice(1, -1))}</code>`;
      }
      const link = part.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
      if (link) {
        return `<a href="${escapeHtml(link[2])}">${escapeHtml(link[1])}</a>`;
      }
      return escapeHtml(part);
    })
    .join("");
}

function renderPrintableMath(expression: string, displayMode: boolean) {
  try {
    return renderToString(expression, {
      displayMode,
      output: "mathml",
      throwOnError: false,
      strict: false,
    });
  } catch {
    return escapeHtml(expression);
  }
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
