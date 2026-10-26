import type {
  CourseVideo,
  Flashcard,
  LearningSession,
  Mcq,
  OneWordQuestion,
  TrueFalseQuestion,
} from "@/lib/api";

export function titleCase(value: string) {
  return value
    .split(/[\s_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function sessionTitle(session?: Pick<LearningSession, "topic"> | null) {
  return titleCase(session?.topic || "Untitled Session");
}

export function sessionLevel(
  session?: Pick<
    LearningSession,
    "difficulty_level" | "generation_mode" | "mode" | "version"
  > | null,
) {
  const level = titleCase(session?.difficulty_level || "Medium");
  const mode = session?.generation_mode || session?.mode;
  const modeLabel =
    mode === "Pro Reasoning" ? "Deep Focus" : mode ? "Quick" : "";
  const version =
    session?.version && session.version > 1 ? `v${session.version}` : "";
  return [level, modeLabel, version].filter(Boolean).join(" · ");
}

export function materialChapters(session?: LearningSession | null) {
  const materials = session?.study_materials ?? [];
  return materials.map((item, index) => {
    if (typeof item === "string") {
      return {
        key: `material-${index}`,
        title: session?.subtopics?.[index] || `Section ${index + 1}`,
        body: item,
        moduleId: session?.curriculum?.modules[index]?.module_id,
      };
    }

    return {
      key: item.subtopic || item.title || `material-${index}`,
      title:
        item.subtopic ||
        item.title ||
        session?.subtopics?.[index] ||
        `Section ${index + 1}`,
      body: item.study_material || item.content || item.body || "",
      moduleId:
        item.module_id || session?.curriculum?.modules[index]?.module_id,
    };
  });
}

export function flashcards(session?: LearningSession | null) {
  return (session?.flashcards ?? [])
    .map((card: Flashcard, index) => ({
      id: card.flashcard_id,
      question: card.question || card.q || "",
      answer: card.answer || card.a || "",
      moduleId:
        card.module_id ||
        session?.curriculum?.modules[
          index % Math.max(session.curriculum.modules.length, 1)
        ]?.module_id,
      conceptIds: card.concept_ids ?? [],
      objectiveIds: card.objective_ids ?? [],
      generationKind: card.generation_kind,
      difficulty: card.difficulty,
    }))
    .filter((card) => card.question || card.answer);
}

export function mcqs(session?: LearningSession | null) {
  const questions =
    session?.mcqs ?? session?.mcq ?? session?.mcq_questions ?? [];
  return questions
    .map((question: Mcq, index) => ({
      id: question.question_id,
      question: question.question || question.q || "",
      options: question.options ?? [],
      answer: normalizeMcqAnswer(question.answer ?? question.correct_answer),
      explanation: question.explanation || "",
      moduleId:
        question.module_id ||
        session?.curriculum?.modules[
          index % Math.max(session.curriculum.modules.length, 1)
        ]?.module_id,
      conceptIds: question.concept_ids ?? [],
      objectiveIds: question.objective_ids ?? [],
      generationKind: question.generation_kind,
      difficulty: question.difficulty,
    }))
    .filter((question) => question.question);
}

export function trueFalseQuestions(session?: LearningSession | null) {
  const questions =
    session?.true_false ??
    session?.truefalse ??
    session?.true_false_questions ??
    [];
  return questions
    .map((question: TrueFalseQuestion, index) => ({
      id: question.question_id,
      question: question.question || question.q || "",
      answer: normalizeBoolean(question.answer),
      explanation: question.explanation || "",
      moduleId:
        question.module_id ||
        session?.curriculum?.modules[
          index % Math.max(session.curriculum.modules.length, 1)
        ]?.module_id,
      conceptIds: question.concept_ids ?? [],
      objectiveIds: question.objective_ids ?? [],
      generationKind: question.generation_kind,
      difficulty: question.difficulty,
    }))
    .filter((question) => question.question);
}

export function oneWordQuestions(session?: LearningSession | null) {
  const questions =
    session?.oneword ??
    session?.one_word ??
    session?.oneword_questions ??
    session?.one_word_questions ??
    [];
  return questions
    .map((question: OneWordQuestion, index) => ({
      id: question.question_id,
      question: question.question || question.q || "",
      answer: question.answer || "",
      explanation: question.explanation || "",
      moduleId:
        question.module_id ||
        session?.curriculum?.modules[
          index % Math.max(session.curriculum.modules.length, 1)
        ]?.module_id,
      conceptIds: question.concept_ids ?? [],
      objectiveIds: question.objective_ids ?? [],
      generationKind: question.generation_kind,
      difficulty: question.difficulty,
    }))
    .filter((question) => question.question);
}

export function courseVideos(session?: LearningSession | null) {
  return (session?.course_content ?? [])
    .map((video: CourseVideo, index) => {
      const url = video.link || video.url || "#";
      return {
        title: video.title || video.subtopic || `Video ${index + 1}`,
        author:
          video.author || video.channel || domainFromUrl(url) || "Recommended",
        duration: video.watch_time || video.duration || "Open",
        tag: session?.subtopics?.[index] || "Lecture",
        url,
      };
    })
    .filter((video) => video.title);
}

export function resources(session?: LearningSession | null) {
  return (session?.additionalresources ?? [])
    .map((item, index) => {
      if (typeof item === "string") {
        return {
          title: domainFromUrl(item) || `Resource ${index + 1}`,
          by: item,
          url: item,
        };
      }
      const url = item.url || item.link || "#";
      return {
        title: item.title || domainFromUrl(url) || `Resource ${index + 1}`,
        by: item.description || url,
        url,
      };
    })
    .filter((item) => item.title);
}

export function learningSteps(session?: LearningSession | null) {
  const raw = session?.learningpath;
  const lines = Array.isArray(raw) ? raw : String(raw || "").split(/\n+/);
  const cleaned = lines
    .map((line) => line.replace(/^#+\s*/, "").trim())
    .filter(Boolean);

  if (cleaned.length === 0) {
    return (session?.subtopics ?? []).map((subtopic, index) => ({
      title: subtopic,
      detail:
        "Review the material, test recall, then move to the next concept.",
      state: index === 0 ? "active" : "todo",
      minutes: 12,
    }));
  }

  return cleaned.slice(0, 8).map((line, index) => {
    const normalized = line.replace(/^\d+[).\s-]*/, "");
    const [title, ...rest] = normalized.split(":");
    return {
      title: title.trim() || `Step ${index + 1}`,
      detail: rest.join(":").trim() || normalized,
      state: index === 0 ? "active" : index < 2 ? "done" : "todo",
      minutes: 10 + ((index + 1) % 3) * 5,
    };
  });
}

function normalizeMcqAnswer(answer: string | number | undefined) {
  if (typeof answer === "number") return answer;
  if (!answer) return -1;
  const trimmed = answer.trim().toLowerCase();
  if (/^\d+$/.test(trimmed)) return Number(trimmed);
  const letter = trimmed.charCodeAt(0) - 97;
  return letter >= 0 && letter <= 25 ? letter : -1;
}

function normalizeBoolean(value: boolean | string | undefined) {
  if (typeof value === "boolean") return value;
  return (
    String(value || "")
      .trim()
      .toLowerCase() === "true"
  );
}

function domainFromUrl(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}
