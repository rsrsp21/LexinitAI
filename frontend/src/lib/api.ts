import { z } from "zod";

type RequestOptions = RequestInit & {
  form?: FormData;
  json?: unknown;
  timeoutMs?: number;
};

let csrfTokenPromise: Promise<string> | null = null;

type ApiErrorPayload = {
  success?: false;
  message?: string;
  error?:
    | string
    | {
        code?: string;
        request_id?: string;
        details?: unknown;
      };
};

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId?: string;
  readonly details?: unknown;

  constructor({
    message,
    status,
    code = "request_failed",
    requestId,
    details,
  }: {
    message: string;
    status: number;
    code?: string;
    requestId?: string;
    details?: unknown;
  }) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
    this.details = details;
  }
}

export function apiErrorMessage(error: unknown, fallback: string) {
  if (!(error instanceof Error)) return fallback;
  if (error instanceof ApiError && error.requestId) {
    return `${error.message} Request: ${error.requestId}`;
  }
  return error.message || fallback;
}

function clientRequestId() {
  if (
    typeof crypto !== "undefined" &&
    typeof crypto.randomUUID === "function"
  ) {
    return crypto.randomUUID();
  }
  return `web_${Date.now()}_${Math.random().toString(36).slice(2, 12)}`;
}

async function parseJson<T>(response: Response): Promise<T> {
  const data = (await response.json().catch(() => ({}))) as ApiErrorPayload;
  if (!response.ok) {
    const structuredError =
      typeof data.error === "object" && data.error ? data.error : undefined;
    const message =
      typeof data.message === "string"
        ? data.message
        : typeof data.error === "string"
          ? data.error
          : "Request failed.";
    throw new ApiError({
      message,
      status: response.status,
      code: structuredError?.code,
      requestId:
        structuredError?.request_id ||
        response.headers.get("X-Request-ID") ||
        undefined,
      details: structuredError?.details,
    });
  }
  return data as T;
}

export async function requestJson<T>(
  url: string,
  options: RequestOptions = {},
) {
  const { form, json, headers, timeoutMs = 30_000, ...init } = options;
  const requestId = clientRequestId();
  const method = (init.method || "GET").toUpperCase();
  const unsafe = !["GET", "HEAD", "OPTIONS"].includes(method);
  let csrfToken = unsafe ? await getCsrfToken() : undefined;

  const send = () => {
    const controller = init.signal ? null : new AbortController();
    const timeout = controller
      ? window.setTimeout(() => controller.abort(), timeoutMs)
      : undefined;
    return fetch(url, {
      credentials: "include",
      ...init,
      signal: init.signal ?? controller?.signal,
      headers: {
        ...(json !== undefined ? { "Content-Type": "application/json" } : {}),
        "X-Request-ID": requestId,
        ...(csrfToken ? { "X-CSRF-Token": csrfToken } : {}),
        ...headers,
      },
      body: form ?? (json !== undefined ? JSON.stringify(json) : init.body),
    })
      .catch((error: unknown) => {
        const timedOut =
          error instanceof DOMException && error.name === "AbortError";
        throw new ApiError({
          message: timedOut
            ? "This request took too long. Please try again."
            : "Could not connect. Check your connection and try again.",
          status: 0,
          code: timedOut ? "request_timeout" : "network_unavailable",
          requestId,
        });
      })
      .finally(() => {
        if (timeout !== undefined) window.clearTimeout(timeout);
      });
  };

  let response = await send();
  if (unsafe && response.status === 403) {
    const payload = (await response
      .clone()
      .json()
      .catch(() => null)) as ApiErrorPayload | null;
    const code =
      typeof payload?.error === "object" ? payload.error?.code : undefined;
    if (code === "csrf_token_invalid") {
      csrfTokenPromise = null;
      csrfToken = await getCsrfToken();
      response = await send();
    }
  }

  if (response.status === 401 && typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent("lexinit:authentication-required"));
  }

  return parseJson<T>(response);
}

async function getCsrfToken() {
  csrfTokenPromise ??= fetch("/api/v1/security/csrf", {
    credentials: "include",
    headers: { "X-Request-ID": clientRequestId() },
  }).then(async (response) => {
    if (!response.ok) throw new Error("Could not initialize request security.");
    const data = (await response.json()) as { csrf_token?: unknown };
    if (typeof data.csrf_token !== "string") {
      throw new Error("Could not initialize request security.");
    }
    return data.csrf_token;
  });
  return csrfTokenPromise;
}

export type ApiResult = {
  success?: boolean;
  message?: string;
  redirect_url?: string;
};

export type Difficulty = "easy" | "medium" | "hard";
export type MasteryBand = "weak" | "developing" | "proficient" | "mastered";
export type AdaptiveAction =
  | "prerequisite_remediation"
  | "misconception_correction"
  | "weak_topic_remediation"
  | "targeted_practice"
  | "application_practice"
  | "difficulty_progression"
  | "spaced_review";

export type Concept = {
  concept_id: string;
  name: string;
  prerequisite_ids: string[];
  difficulty: Difficulty;
};

export type LearningObjective = {
  objective_id: string;
  description: string;
  concept_ids: string[];
};

export type CurriculumModule = {
  module_id: string;
  title: string;
  concepts: Concept[];
  learning_objectives: LearningObjective[];
  common_misconceptions: string[];
  difficulty: Difficulty;
  estimated_minutes: number;
};

export type Curriculum = {
  curriculum_id: string;
  canonical_topic: string;
  difficulty: Difficulty;
  prerequisites: string[];
  modules: CurriculumModule[];
  schema_version: number;
  prompt_version: string;
};

export type ArtifactLineage = {
  curriculum_id?: string;
  module_id?: string;
  concept_ids?: string[];
  objective_ids?: string[];
  difficulty?: Difficulty;
  generation_kind?: string;
  prompt_version?: string;
  source_assessment_submission_id?: string;
  source_adaptation_decision_id?: string;
  adaptive_action?: AdaptiveAction;
  target_concept_ids?: string[];
  target_objective_ids?: string[];
  source_ids?: string[];
  source_citations?: SourceCitation[];
  knowledge_pack_id?: string;
  knowledge_pack_version?: string;
  grounding_refs?: string[];
  validation_status?: string;
};

export type SourceCitation = {
  source_id: string;
  source_name: string;
  page_number: number;
  chunk_id: string;
  excerpt: string;
  score?: number;
};

export type LearningSource = {
  source_id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  status:
    "validating" | "uploading" | "extracting" | "indexing" | "ready" | "failed";
  page_count: number;
  readable_page_count: number;
  chunk_count: number;
  suggested_topic: string;
  error_code?: string | null;
  error_message?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type MasteryRecord = {
  concept_id: string;
  concept_label: string;
  mastery_probability: number;
  confidence: number;
  band: MasteryBand;
  attempts: number;
  correct_attempts: number;
  difficulty_reached: Difficulty;
  misconception_counts: Record<string, number>;
  last_practiced_at: string;
  next_review_at: string;
};

export type AdaptationDecision = {
  decision_id: string;
  concept_id: string;
  action: AdaptiveAction;
  target_difficulty: Difficulty;
  reason_codes: string[];
  source_submission_id: string;
  target_concept_ids?: string[];
  target_objective_ids?: string[];
  created_at: string;
};

export type AssessmentFeedback = {
  correct: boolean;
  correct_answer: number | boolean | string;
  explanation: string;
};

export type SubmitAssessmentResult = {
  success: boolean;
  score: number;
  total: number;
  feedback: AssessmentFeedback[];
  adaptive_topic: string;
  adaptive_error?: string;
  submission_id: string;
  source_session_id: string;
  source_topic: string;
  mastery_updates?: MasteryRecord[];
  adaptation_decisions?: AdaptationDecision[];
  attempt_id?: string | null;
};

export type AssessmentSubmissionQuestion = {
  question: string;
  selected_answer: number | boolean | string | null;
  selected_option?: string | null;
  options: string[];
  correct: boolean;
  correct_answer: number | boolean | string | null;
  explanation: string;
};

export type AssessmentSubmissionDetail = {
  submission_id: string;
  session_id: string;
  source_topic: string;
  assessment_type: AssessmentType;
  score: number;
  total: number;
  percentage: number;
  weak_topic: string;
  module_id?: string | null;
  attempt_id?: string | null;
  created_at?: string | null;
  questions: AssessmentSubmissionQuestion[];
};

export type AssessmentType = "mcq" | "truefalse" | "oneword";

export type AdaptiveQuestion = {
  question_id: string;
  question: string;
  options?: string[];
  difficulty: Difficulty;
  concept_ids: string[];
  objective_ids: string[];
  module_id?: string | null;
};

export type AssessmentAttempt = {
  attempt_id: string;
  session_id: string;
  source_topic: string;
  assessment_type: AssessmentType;
  status: "active" | "ready" | "submitting" | "completed" | "expired";
  target_count: number;
  answered_count: number;
  current_question?: AdaptiveQuestion | null;
  selection_reason: string;
  submission_token: string;
  public_result?: SubmitAssessmentResult | null;
  expires_at?: string | null;
};

export type ReviewRating = "again" | "hard" | "good" | "easy";

export type ReviewItem = {
  review_id: string;
  concept_id: string;
  concept_label: string;
  band: MasteryBand;
  mastery_probability: number;
  next_review_at: string;
  session_id?: string | null;
  artifact: {
    artifact_id?: string | null;
    kind: "flashcard" | "recall_prompt" | "self_explanation";
    prompt: string;
    answer?: string | null;
  };
};

export type NextRecommendation = {
  recommendation_id: string;
  decision_id?: string;
  concept_id: string;
  concept_label: string;
  action: AdaptiveAction;
  target_difficulty: Difficulty;
  reason_codes: string[];
  target_concept_ids: string[];
  target_objective_ids: string[];
  next_review_at: string;
  source_submission_id?: string;
  can_generate: boolean;
};

export type GenerationRunStatus =
  | "queued"
  | "running"
  | "repairing"
  | "saving"
  | "completed"
  | "cancelled"
  | "failed";

export type GenerationStage =
  | "queued"
  | "safety"
  | "cache"
  | "curriculum"
  | "knowledge"
  | "materials"
  | "practice"
  | "videos"
  | "learning_path"
  | "resources"
  | "saving"
  | "completed";

export type GenerationRunError = {
  code: string;
  message: string;
  retryable: boolean;
  step?: string | null;
};

export type GenerationRun = {
  id: string;
  status: GenerationRunStatus;
  stage: GenerationStage;
  progress: number;
  message: string;
  session_id?: string | null;
  error?: GenerationRunError | null;
  topic?: string;
  difficulty_level?: string;
  mode?: string;
  version?: number;
  attempt: number;
  max_attempts: number;
  completed_steps: string[];
  failed_steps: string[];
  can_cancel: boolean;
  can_retry: boolean;
  created_at?: string | null;
  updated_at?: string | null;
};

export type SubmitTopicResult = ApiResult & {
  session_id?: string;
  job_id?: string;
  version?: number;
  queued?: boolean;
  deduplicated?: boolean;
} & Partial<GenerationRun>;

export type StudyMaterial = ArtifactLineage & {
  subtopic?: string;
  title?: string;
  study_material?: string;
  content?: string;
  body?: string;
};

export type Flashcard = ArtifactLineage & {
  flashcard_id?: string;
  question?: string;
  answer?: string;
  q?: string;
  a?: string;
};

export type Mcq = ArtifactLineage & {
  question_id?: string;
  question?: string;
  q?: string;
  options?: string[];
  answer?: string | number;
  correct_answer?: string | number;
  explanation?: string;
};

export type TrueFalseQuestion = ArtifactLineage & {
  question_id?: string;
  question?: string;
  q?: string;
  answer?: boolean | string;
  explanation?: string;
};

export type OneWordQuestion = ArtifactLineage & {
  question_id?: string;
  question?: string;
  q?: string;
  answer?: string;
  explanation?: string;
};

export type CourseVideo = {
  video_id?: string;
  title?: string;
  subtopic?: string;
  link?: string;
  url?: string;
  watch_time?: string;
  duration?: string;
  channel?: string;
  author?: string;
  module_id?: string;
  module_title?: string;
  concept_ids?: string[];
  objective_ids?: string[];
  objective_labels?: string[];
  coverage_labels?: string[];
  recommendation_reason?: string;
};

export type VideoPlaybackState = "playing" | "paused" | "ended";

export type VideoCatalogItem = {
  video_id: string;
  title: string;
  url: string;
  channel: string;
  thumbnail_url?: string | null;
  duration_seconds: number;
  transcript_status:
    | "unknown"
    | "available"
    | "disabled"
    | "not_found"
    | "video_unavailable"
    | "unavailable";
  module_id?: string | null;
  module_title: string;
  concept_ids: string[];
  objective_ids: string[];
  objective_labels: string[];
  coverage_labels: string[];
  recommendation_reason: string;
  position_seconds: number;
  furthest_position_seconds: number;
  progress_percent: number;
  completed: boolean;
  summary_status: "not_requested" | "ready";
};

export type VideoStudyGuide = {
  guide_id: string;
  video_id: string;
  status: "ready" | "unavailable";
  transcript_status: VideoCatalogItem["transcript_status"];
  retryable: boolean;
  summary_points: string[];
  key_moments: Array<{ start_seconds: number; note: string }>;
  questions: Array<{ question_id: string; question: string }>;
};

export type VideoRetrievalResult = {
  event_id: string;
  video_id: string;
  score: number;
  total: number;
  feedback: Array<{
    correct: boolean;
    expected_answer: string;
    explanation: string;
  }>;
  mastery_updates: MasteryRecord[];
  adaptation_decisions: AdaptationDecision[];
};

export type LearningSession = {
  _id: string;
  topic?: string;
  original_topic?: string;
  normalized_topic?: string;
  difficulty_level?: string;
  generation_mode?: string;
  mode?: string;
  version?: number;
  regenerated_from?: string;
  generation_kind?: "adaptive" | string;
  adaptive_from_session?: string;
  adaptive_from_topic?: string;
  assessment_submission_id?: string;
  curriculum_id?: string;
  curriculum?: Curriculum;
  created_at?: string;
  subtopics?: string[];
  study_materials?: Array<StudyMaterial | string>;
  flashcards?: Flashcard[];
  mcqs?: Mcq[];
  mcq?: Mcq[];
  mcq_questions?: Mcq[];
  true_false?: TrueFalseQuestion[];
  truefalse?: TrueFalseQuestion[];
  true_false_questions?: TrueFalseQuestion[];
  oneword?: OneWordQuestion[];
  one_word?: OneWordQuestion[];
  oneword_questions?: OneWordQuestion[];
  one_word_questions?: OneWordQuestion[];
  course_content?: CourseVideo[];
  learningpath?: string | string[];
  additionalresources?: Array<
    | string
    | { title?: string; url?: string; link?: string; description?: string }
  >;
  score_submissions?: unknown;
  source_ids?: string[];
  source_lineage?: LearningSource[];
  source_citations?: SourceCitation[];
  grounding_version?: string;
};

export type PublicUser = {
  _id: string;
  name?: string;
  email?: string;
  profile_type?: ProfileType;
  institution_name?: string | null;
  grade_or_class?: string | null;
  organization_name?: string | null;
  professional_role?: string | null;
  work_experience_years?: number | null;
  profile_complete?: boolean;
  plan?: "free" | "plus" | "pro";
  rate_limit?: number;
  deep_rate_limit?: number;
};

export type ProfileType = "student" | "professional" | "independent";

export type ProfileUpdate = {
  name: string;
  profile_type: ProfileType;
  institution_name?: string | null;
  grade_or_class?: string | null;
  organization_name?: string | null;
  professional_role?: string | null;
  work_experience_years?: number | null;
};

export type ProfileUpdateResult = ApiResult & {
  user: PublicUser;
};

export type ChangePasswordInput = {
  current_password: string;
  new_password: string;
  confirm_password: string;
};

export type MeResponse = {
  authenticated: boolean;
  user: PublicUser;
};

export type SessionResponse = {
  user: Pick<PublicUser, "_id" | "name" | "email">;
  session: LearningSession;
  sessions: LearningSession[];
};

export type SessionsResponse = {
  sessions: LearningSession[];
};

export function getMe() {
  return requestJson<MeResponse>("/api/v1/me");
}

export function updateProfile(profile: ProfileUpdate) {
  return requestJson<ProfileUpdateResult>("/api/v1/me/profile", {
    method: "PATCH",
    json: profile,
  });
}

export function changePassword(passwords: ChangePasswordInput) {
  return requestJson<ApiResult>("/api/v1/account/password", {
    method: "POST",
    json: passwords,
  });
}

export function startPasswordChange() {
  return requestJson<ApiResult & { verification_code?: string }>(
    "/api/v1/account/password/start",
    { method: "POST" },
  );
}

export function verifyPasswordChange(code: string) {
  return requestJson<ApiResult>("/api/v1/account/password/verify", {
    method: "POST",
    json: { code },
  });
}

export function completePasswordChange(
  newPassword: string,
  confirmPassword: string,
) {
  return requestJson<ApiResult>("/api/v1/account/password/complete", {
    method: "POST",
    json: { new_password: newPassword, confirm_password: confirmPassword },
  });
}

export function getSession(sessionId: string) {
  return requestJson<SessionResponse>(`/api/v1/sessions/${sessionId}`);
}

export function getSessions(query = "") {
  const params = query.trim() ? `?q=${encodeURIComponent(query.trim())}` : "";
  return requestJson<SessionsResponse>(`/api/v1/sessions${params}`);
}

export type CourseActivityType =
  "material" | "video" | "flashcards" | "assessment";

export type CourseActivity = {
  activity_id: string;
  module_id: string;
  type: CourseActivityType;
  title: string;
  detail: string;
  item_count: number;
  route: "materials" | "videos" | "flashcards" | "assessments";
  status: "todo" | "completed";
  latest_submission_id?: string | null;
};

export type CourseModule = {
  module_id: string;
  title: string;
  description: string;
  estimated_minutes: number;
  status: "locked" | "active" | "completed";
  completed_activities: number;
  total_activities: number;
  progress_percent: number;
  mastery_percent: number | null;
  needs_review: boolean;
  activities: CourseActivity[];
};

export type CourseProgress = {
  session_id: string;
  topic: string;
  difficulty: string;
  status: "not_started" | "in_progress" | "completed";
  progress_percent: number;
  completed_activities: number;
  total_activities: number;
  completed_modules: number;
  total_modules: number;
  current_module_id: string | null;
  current_module_title: string | null;
  created_at?: string | null;
  modules: CourseModule[];
};

export function getCourse(sessionId: string) {
  return requestJson<CourseProgress>(`/api/v1/sessions/${sessionId}/course`);
}

export function getCourses() {
  return requestJson<{ courses: Array<Omit<CourseProgress, "modules">> }>(
    "/api/v1/courses",
  );
}

export function setCourseActivity(
  sessionId: string,
  activityId: string,
  status: "todo" | "completed",
) {
  return requestJson<CourseProgress>(
    `/api/v1/sessions/${sessionId}/course/activities/${encodeURIComponent(activityId)}`,
    { method: "PUT", json: { status } },
  );
}

export function unlockCourseModule(sessionId: string, moduleId: string) {
  return requestJson<CourseProgress>(
    `/api/v1/sessions/${sessionId}/course/modules/${encodeURIComponent(moduleId)}/unlock`,
    { method: "POST" },
  );
}

export function regenerateSession(
  sessionId: string,
  idempotencyKey = createIdempotencyKey("regeneration"),
) {
  return requestJson<SubmitTopicResult>(
    `/api/v1/sessions/${sessionId}/regenerate`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
    },
  );
}

const generationRunSchema = z.object({
  id: z.string().regex(/^[a-f0-9]{32}$/),
  status: z.enum([
    "queued",
    "running",
    "repairing",
    "saving",
    "completed",
    "cancelled",
    "failed",
  ]),
  stage: z.enum([
    "queued",
    "safety",
    "cache",
    "curriculum",
    "knowledge",
    "materials",
    "practice",
    "videos",
    "learning_path",
    "resources",
    "saving",
    "completed",
  ]),
  progress: z.number().int().min(0).max(100),
  message: z.string(),
  session_id: z.string().nullable().optional(),
  error: z
    .object({
      code: z.string(),
      message: z.string(),
      retryable: z.boolean(),
      step: z.string().nullable().optional(),
    })
    .nullable()
    .optional(),
  topic: z.string().optional(),
  difficulty_level: z.string().optional(),
  mode: z.string().optional(),
  version: z.number().int().positive().optional(),
  attempt: z.number().int().positive(),
  max_attempts: z.number().int().positive(),
  completed_steps: z.array(z.string()),
  failed_steps: z.array(z.string()),
  can_cancel: z.boolean(),
  can_retry: z.boolean(),
  created_at: z.string().nullable().optional(),
  updated_at: z.string().nullable().optional(),
});

export function getGenerationRun(runId: string) {
  return requestJson<unknown>(`/api/v1/generation-runs/${runId}`).then((data) =>
    generationRunSchema.parse(data),
  );
}

export function getActiveGenerationRuns() {
  return requestJson<unknown>("/api/v1/generation-runs/active").then((data) =>
    z.object({ runs: z.array(generationRunSchema) }).parse(data),
  );
}

export function cancelGenerationRun(runId: string) {
  return requestJson<unknown>(`/api/v1/generation-runs/${runId}/cancel`, {
    method: "POST",
  }).then((data) => generationRunSchema.passthrough().parse(data));
}

export function retryGenerationRun(runId: string) {
  return requestJson<unknown>(`/api/v1/generation-runs/${runId}/retry`, {
    method: "POST",
  }).then((data) => generationRunSchema.passthrough().parse(data));
}

export function createIdempotencyKey(prefix = "generation") {
  return `${prefix}:${clientRequestId()}`;
}

export function deleteSession(sessionId: string, confirmCode: string) {
  return requestJson<ApiResult>(`/api/v1/sessions/${sessionId}`, {
    method: "DELETE",
    json: { confirm_code: confirmCode },
  });
}

export function logout() {
  return requestJson<ApiResult>("/api/v1/logout", { method: "POST" }).finally(
    () => {
      csrfTokenPromise = null;
    },
  );
}

const learningSourceSchema = z.object({
  source_id: z.string().regex(/^[a-f0-9]{24}$/),
  filename: z.string().min(1),
  mime_type: z.string().min(1),
  size_bytes: z.number().int().nonnegative(),
  status: z.enum([
    "validating",
    "uploading",
    "extracting",
    "indexing",
    "ready",
    "failed",
  ]),
  page_count: z.number().int().nonnegative(),
  readable_page_count: z.number().int().nonnegative(),
  chunk_count: z.number().int().nonnegative(),
  suggested_topic: z.string(),
  error_code: z.string().nullable().optional(),
  error_message: z.string().nullable().optional(),
  created_at: z.string().nullable().optional(),
  updated_at: z.string().nullable().optional(),
});

export function getSources() {
  return requestJson<unknown>("/api/v1/sources").then((data) =>
    z
      .object({
        sources: z.array(learningSourceSchema),
        count: z.number().int(),
      })
      .parse(data),
  );
}

export function uploadLearningSource(file: File) {
  const form = new FormData();
  form.append("file", file);
  return requestJson<unknown>("/api/v1/sources", {
    method: "POST",
    form,
    timeoutMs: 120_000,
  }).then((data) =>
    z
      .object({ source: learningSourceSchema, deduplicated: z.boolean() })
      .parse(data),
  );
}

export function retryLearningSource(sourceId: string) {
  return requestJson<unknown>(`/api/v1/sources/${sourceId}/retry`, {
    method: "POST",
  }).then((data) => z.object({ source: learningSourceSchema }).parse(data));
}

export function deleteLearningSource(sourceId: string) {
  return requestJson<ApiResult>(`/api/v1/sources/${sourceId}`, {
    method: "DELETE",
  });
}

export function getSourcePage(sourceId: string, pageNumber: number) {
  return requestJson<unknown>(
    `/api/v1/sources/${sourceId}/pages/${pageNumber}`,
  ).then((data) =>
    z
      .object({
        source_id: z.string(),
        filename: z.string(),
        page_number: z.number().int().positive(),
        page_count: z.number().int().positive(),
        text: z.string(),
      })
      .parse(data),
  );
}

const masteryRecordSchema = z.object({
  concept_id: z.string().min(1),
  concept_label: z.string().min(1),
  mastery_probability: z.number().min(0).max(1),
  confidence: z.number().min(0).max(1),
  band: z.enum(["weak", "developing", "proficient", "mastered"]),
  attempts: z.number().int().nonnegative(),
  correct_attempts: z.number().int().nonnegative(),
  difficulty_reached: z.enum(["easy", "medium", "hard"]),
  misconception_counts: z.record(z.string(), z.number().int().nonnegative()),
  last_practiced_at: z.string(),
  next_review_at: z.string(),
});

const masteryResponseSchema = z.object({
  mastery: z.array(masteryRecordSchema),
});
const weakConceptsResponseSchema = z.object({
  weak_concepts: z.array(masteryRecordSchema),
});

const dashboardAssessmentSchema = z.object({
  submission_id: z.string(),
  session_id: z.string(),
  topic: z.string(),
  assessment_type: z.string(),
  score: z.number().int().nonnegative(),
  total: z.number().int().nonnegative(),
  percentage: z.number().min(0).max(100),
  weak_topic: z.string(),
  created_at: z.string().nullable(),
});

export type DashboardAssessment = z.infer<typeof dashboardAssessmentSchema>;

const dashboardConceptSchema = masteryRecordSchema
  .omit({
    misconception_counts: true,
    last_practiced_at: true,
    next_review_at: true,
  })
  .extend({
    last_practiced_at: z.string().nullable(),
    next_review_at: z.string().nullable(),
  });

const learnerDashboardSchema = z.object({
  generated_at: z.string(),
  overview: z.object({
    overall_accuracy: z.number().min(0).max(100),
    average_mastery: z.number().min(0).max(100),
    assessments_completed: z.number().int().nonnegative(),
    questions_answered: z.number().int().nonnegative(),
    concepts_tracked: z.number().int().nonnegative(),
    due_reviews: z.number().int().nonnegative(),
    study_sessions: z.number().int().nonnegative(),
    videos_started: z.number().int().nonnegative(),
    videos_completed: z.number().int().nonnegative(),
    active_days_30: z.number().int().nonnegative(),
    current_streak: z.number().int().nonnegative(),
    improvement_percentage_points: z.number().nullable(),
  }),
  score_trend: z.array(dashboardAssessmentSchema),
  recent_assessments: z.array(dashboardAssessmentSchema),
  assessment_types: z.array(
    z.object({
      assessment_type: z.string(),
      attempts: z.number().int().nonnegative(),
      accuracy: z.number().min(0).max(100),
    }),
  ),
  mastery_distribution: z.object({
    weak: z.number().int().nonnegative(),
    developing: z.number().int().nonnegative(),
    proficient: z.number().int().nonnegative(),
    mastered: z.number().int().nonnegative(),
  }),
  focus_concepts: z.array(dashboardConceptSchema),
  strong_concepts: z.array(dashboardConceptSchema),
  top_misconceptions: z.array(
    z.object({ misconception: z.string(), count: z.number().int().positive() }),
  ),
  evidence_mix: z.record(z.string(), z.number().int().nonnegative()),
  recent_adaptations: z.array(
    z.object({
      decision_id: z.string(),
      concept_id: z.string(),
      concept_label: z.string(),
      action: z.string(),
      target_difficulty: z.string(),
      reason_codes: z.array(z.string()),
      created_at: z.string().nullable(),
    }),
  ),
});

export type LearnerDashboard = z.infer<typeof learnerDashboardSchema>;

export function getMastery(band?: MasteryBand, limit = 100) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (band) params.set("band", band);
  return requestJson<unknown>(`/api/v1/learners/me/mastery?${params}`).then(
    (data) => masteryResponseSchema.parse(data),
  );
}

export function getWeakConcepts(limit = 6) {
  return requestJson<unknown>(
    `/api/v1/learners/me/weak-concepts?limit=${limit}`,
  ).then((data) => weakConceptsResponseSchema.parse(data));
}

export function getLearnerDashboard() {
  return requestJson<unknown>("/api/v1/learners/me/dashboard").then((data) =>
    learnerDashboardSchema.parse(data),
  );
}

export function getCourseAssessments(sessionId: string) {
  return requestJson<unknown>(
    `/api/v1/sessions/${encodeURIComponent(sessionId)}/assessment-submissions`,
  ).then((data) =>
    z.object({ assessments: z.array(dashboardAssessmentSchema) }).parse(data),
  );
}

const difficultySchema = z.enum(["easy", "medium", "hard"]);
const adaptiveActionSchema = z.enum([
  "prerequisite_remediation",
  "misconception_correction",
  "weak_topic_remediation",
  "targeted_practice",
  "application_practice",
  "difficulty_progression",
  "spaced_review",
]);
const adaptiveQuestionSchema = z.object({
  question_id: z.string().min(8),
  question: z.string().min(1),
  options: z.array(z.string()).optional(),
  difficulty: difficultySchema,
  concept_ids: z.array(z.string()),
  objective_ids: z.array(z.string()),
  module_id: z.string().nullable().optional(),
});
const assessmentResultSchema = z
  .object({
    success: z.boolean(),
    score: z.number().int().nonnegative(),
    total: z.number().int().positive(),
    feedback: z.array(
      z.object({
        correct: z.boolean(),
        correct_answer: z.union([z.number(), z.boolean(), z.string()]),
        explanation: z.string(),
      }),
    ),
    adaptive_topic: z.string(),
    adaptive_error: z.string().optional(),
    submission_id: z.string(),
    source_session_id: z.string(),
    source_topic: z.string(),
    mastery_updates: z.array(masteryRecordSchema).optional(),
    adaptation_decisions: z
      .array(
        z.object({
          decision_id: z.string(),
          concept_id: z.string(),
          action: adaptiveActionSchema,
          target_difficulty: difficultySchema,
          reason_codes: z.array(z.string()),
          source_submission_id: z.string(),
          target_concept_ids: z.array(z.string()).optional(),
          target_objective_ids: z.array(z.string()).optional(),
          created_at: z.string(),
        }),
      )
      .optional(),
    attempt_id: z.string().nullable().optional(),
  })
  .passthrough();
const assessmentSubmissionDetailSchema = z.object({
  submission_id: z.string(),
  session_id: z.string(),
  source_topic: z.string(),
  assessment_type: z.enum(["mcq", "truefalse", "oneword"]),
  score: z.number().int().nonnegative(),
  total: z.number().int().nonnegative(),
  percentage: z.number().min(0).max(100),
  weak_topic: z.string(),
  module_id: z.string().nullable().optional(),
  attempt_id: z.string().nullable().optional(),
  created_at: z.string().nullable().optional(),
  questions: z.array(
    z.object({
      question: z.string(),
      selected_answer: z
        .union([z.number(), z.boolean(), z.string()])
        .nullable(),
      selected_option: z.string().nullable().optional(),
      options: z.array(z.string()),
      correct: z.boolean(),
      correct_answer: z.union([z.number(), z.boolean(), z.string()]).nullable(),
      explanation: z.string(),
    }),
  ),
});
const assessmentAttemptSchema = z.object({
  attempt_id: z.string(),
  session_id: z.string(),
  source_topic: z.string(),
  assessment_type: z.enum(["mcq", "truefalse", "oneword"]),
  status: z.enum(["active", "ready", "submitting", "completed", "expired"]),
  target_count: z.number().int().positive(),
  answered_count: z.number().int().nonnegative(),
  current_question: adaptiveQuestionSchema.nullable().optional(),
  selection_reason: z.string(),
  submission_token: z.string().min(32),
  public_result: assessmentResultSchema.nullable().optional(),
  expires_at: z.string().nullable().optional(),
});

export function startAssessmentAttempt(
  sessionId: string,
  assessmentType: AssessmentType,
  idempotencyKey: string,
  questionCount = 5,
  moduleId?: string,
) {
  return requestJson<unknown>(
    `/api/v1/sessions/${sessionId}/assessment-attempts`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      json: {
        assessment_type: assessmentType,
        question_count: questionCount,
        ...(moduleId ? { module_id: moduleId } : {}),
      },
    },
  ).then((data) => assessmentAttemptSchema.parse(data));
}

export function getAssessmentAttempt(attemptId: string) {
  return requestJson<unknown>(`/api/v1/assessment-attempts/${attemptId}`).then(
    (data) => assessmentAttemptSchema.parse(data),
  );
}

export function getAssessmentSubmission(submissionId: string) {
  return requestJson<unknown>(
    `/api/v1/assessment-submissions/${encodeURIComponent(submissionId)}`,
  ).then((data) => assessmentSubmissionDetailSchema.parse(data));
}

export function answerAssessmentAttempt(
  attemptId: string,
  questionId: string,
  answer: number | boolean | string,
  idempotencyKey: string,
) {
  return requestJson<unknown>(
    `/api/v1/assessment-attempts/${attemptId}/answers`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      json: { question_id: questionId, answer },
    },
  ).then((data) => assessmentAttemptSchema.parse(data));
}

export function finalizeAssessmentAttempt(
  attemptId: string,
  submissionToken: string,
  idempotencyKey: string,
) {
  return requestJson<unknown>(
    `/api/v1/assessment-attempts/${attemptId}/submit`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      json: { submission_token: submissionToken },
    },
  ).then((data) => assessmentResultSchema.parse(data));
}

const nextRecommendationSchema = z.object({
  recommendation_id: z.string(),
  decision_id: z.string().optional(),
  concept_id: z.string(),
  concept_label: z.string(),
  action: adaptiveActionSchema,
  target_difficulty: difficultySchema,
  reason_codes: z.array(z.string()),
  target_concept_ids: z.array(z.string()),
  target_objective_ids: z.array(z.string()),
  next_review_at: z.string(),
  source_submission_id: z.string().optional(),
  can_generate: z.boolean(),
});
const reviewItemSchema = z.object({
  review_id: z.string(),
  concept_id: z.string(),
  concept_label: z.string(),
  band: z.enum(["weak", "developing", "proficient", "mastered"]),
  mastery_probability: z.number().min(0).max(1),
  next_review_at: z.string(),
  session_id: z.string().nullable().optional(),
  artifact: z.object({
    artifact_id: z.string().nullable().optional(),
    kind: z.enum(["flashcard", "recall_prompt", "self_explanation"]),
    prompt: z.string(),
    answer: z.string().nullable().optional(),
  }),
});

export function getDueReviews(limit = 20) {
  return requestJson<unknown>(
    `/api/v1/learners/me/reviews?limit=${limit}`,
  ).then((data) =>
    z
      .object({
        reviews: z.array(reviewItemSchema),
        due_count: z.number().int().nonnegative(),
      })
      .parse(data),
  );
}

export function recordReview(
  review: Pick<ReviewItem, "concept_id" | "session_id"> & {
    rating: ReviewRating;
    artifact_id?: string | null;
  },
  idempotencyKey: string,
) {
  return requestJson<unknown>("/api/v1/learners/me/reviews", {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    json: review,
  }).then((data) =>
    z
      .object({
        success: z.boolean(),
        event_id: z.string(),
        rating: z.enum(["again", "hard", "good", "easy"]),
        mastery: masteryRecordSchema,
        next_action: nextRecommendationSchema,
      })
      .parse(data),
  );
}

export function getNextRecommendation() {
  return requestJson<unknown>("/api/v1/learners/me/next-action").then((data) =>
    z
      .object({ recommendation: nextRecommendationSchema.nullable() })
      .parse(data),
  );
}

export function generateFromRecommendation(
  decisionId: string,
  idempotencyKey: string,
) {
  return requestJson<SubmitTopicResult>(
    `/api/v1/adaptation-decisions/${decisionId}/generate`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
    },
  );
}

const transcriptStatusSchema = z.enum([
  "unknown",
  "available",
  "disabled",
  "not_found",
  "video_unavailable",
  "unavailable",
]);
const videoCatalogItemSchema = z.object({
  video_id: z.string().length(11),
  title: z.string(),
  url: z.string(),
  channel: z.string(),
  thumbnail_url: z.string().nullable().optional(),
  duration_seconds: z.number().int().nonnegative(),
  transcript_status: transcriptStatusSchema,
  module_id: z.string().nullable().optional(),
  module_title: z.string(),
  concept_ids: z.array(z.string()),
  objective_ids: z.array(z.string()),
  objective_labels: z.array(z.string()),
  coverage_labels: z.array(z.string()).optional().default([]),
  recommendation_reason: z.string(),
  position_seconds: z.number().nonnegative(),
  furthest_position_seconds: z.number().nonnegative(),
  progress_percent: z.number().int().min(0).max(100),
  completed: z.boolean(),
  summary_status: z.enum(["not_requested", "ready"]),
});
const videoStudyGuideSchema = z.object({
  guide_id: z.string(),
  video_id: z.string().length(11),
  status: z.enum(["ready", "unavailable"]),
  transcript_status: transcriptStatusSchema,
  retryable: z.boolean().optional().default(false),
  summary_points: z.array(z.string()),
  key_moments: z.array(
    z.object({ start_seconds: z.number().nonnegative(), note: z.string() }),
  ),
  questions: z.array(
    z.object({ question_id: z.string(), question: z.string() }),
  ),
});
const videoRetrievalResultSchema = z.object({
  event_id: z.string(),
  video_id: z.string().length(11),
  score: z.number().int().nonnegative(),
  total: z.number().int().positive(),
  feedback: z.array(
    z.object({
      correct: z.boolean(),
      expected_answer: z.string(),
      explanation: z.string(),
    }),
  ),
  mastery_updates: z.array(masteryRecordSchema),
  adaptation_decisions: z.array(
    z.object({
      decision_id: z.string(),
      concept_id: z.string(),
      action: adaptiveActionSchema,
      target_difficulty: difficultySchema,
      reason_codes: z.array(z.string()),
      source_submission_id: z.string(),
      target_concept_ids: z.array(z.string()).optional(),
      target_objective_ids: z.array(z.string()).optional(),
      created_at: z.string(),
    }),
  ),
});

export function getVideoCatalog(
  sessionId: string,
  probeTranscripts = false,
  hydrateMetadata = false,
) {
  return requestJson<unknown>(
    `/api/v1/sessions/${sessionId}/videos?probe_transcripts=${probeTranscripts ? 1 : 0}&hydrate_metadata=${hydrateMetadata ? 1 : 0}`,
  ).then((data) =>
    z
      .object({
        session_id: z.string(),
        videos: z.array(videoCatalogItemSchema),
        count: z.number().int().nonnegative(),
      })
      .parse(data),
  );
}

export function saveVideoProgress(
  sessionId: string,
  videoId: string,
  progress: {
    position_seconds: number;
    duration_seconds: number;
    state: VideoPlaybackState;
  },
) {
  return requestJson<unknown>(
    `/api/v1/sessions/${sessionId}/videos/${videoId}/progress`,
    { method: "PUT", json: progress },
  ).then((data) =>
    z
      .object({
        video_id: z.string(),
        position_seconds: z.number(),
        furthest_position_seconds: z.number(),
        duration_seconds: z.number(),
        progress_percent: z.number().int(),
        completed: z.boolean(),
        updated_at: z.string(),
      })
      .parse(data),
  );
}

export function getVideoStudyGuide(sessionId: string, videoId: string) {
  return requestJson<unknown>(
    `/api/v1/sessions/${sessionId}/videos/${videoId}/study-guide`,
  ).then((data) => videoStudyGuideSchema.parse(data));
}

export function submitVideoRetrievalCheck(
  sessionId: string,
  videoId: string,
  guideId: string,
  answers: string[],
  idempotencyKey: string,
) {
  return requestJson<unknown>(
    `/api/v1/sessions/${sessionId}/videos/${videoId}/retrieval-check`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      json: { guide_id: guideId, answers },
    },
  ).then((data) => videoRetrievalResultSchema.parse(data));
}
