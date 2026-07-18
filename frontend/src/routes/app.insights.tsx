import { useQuery } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import {
  AlertCircle,
  ArrowRight,
  BarChart3,
  BookOpenCheck,
  BrainCircuit,
  CheckCircle2,
  Circle,
  Flame,
  LockKeyhole,
  RefreshCw,
  Target,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import { useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  apiErrorMessage,
  getCourse,
  getCourseAssessments,
  getCourses,
  getLearnerDashboard,
  type CourseProgress,
  type DashboardAssessment,
  type LearnerDashboard,
} from "@/lib/api";

export const Route = createFileRoute("/app/insights")({
  head: () => ({
    meta: [
      { title: "Progress - Lexinit" },
      {
        name: "description",
        content: "Your assessment scores, mastery, and learning progress.",
      },
    ],
  }),
  component: ProgressDashboard,
});

const BAND_LABELS = {
  weak: "Needs focus",
  developing: "Developing",
  proficient: "Proficient",
  mastered: "Mastered",
};

const BAND_COLORS = [
  "var(--destructive)",
  "var(--ember-glow)",
  "var(--accent)",
  "var(--primary)",
];

const TYPE_LABELS: Record<string, string> = {
  mcq: "Multiple choice",
  truefalse: "True or false",
  oneword: "One word",
};

function ProgressDashboard() {
  const [view, setView] = useState<"overall" | "course">("overall");
  const query = useQuery({
    queryKey: ["learner-dashboard"],
    queryFn: getLearnerDashboard,
    staleTime: 30_000,
  });

  const data = query.data;
  const hasLearningData =
    Boolean(data?.overview.assessments_completed) ||
    Boolean(data?.overview.concepts_tracked);

  return (
    <div className="space-y-6 pb-10">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="flex items-center gap-3 font-display text-4xl tracking-tight sm:text-5xl">
            <BarChart3 className="h-8 w-8 shrink-0 text-accent sm:h-9 sm:w-9" />
            Progress
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
            See what is sticking, where you are improving, and what deserves
            your attention next.
          </p>
        </div>
      </header>

      <div className="inline-grid w-full grid-cols-2 rounded-2xl border border-border bg-card p-1.5 sm:w-auto sm:min-w-[390px]">
        {(["overall", "course"] as const).map((item) => (
          <button
            key={item}
            type="button"
            onClick={() => setView(item)}
            className={`rounded-xl px-5 py-3 text-sm font-semibold transition ${view === item ? "bg-primary text-primary-foreground shadow-sm" : "text-muted-foreground hover:bg-muted hover:text-foreground"}`}
          >
            {item === "overall" ? "Overall progress" : "Course progress"}
          </button>
        ))}
      </div>

      {view === "overall" && query.isLoading && <DashboardSkeleton />}

      {view === "overall" && (query.isError || !data) && (
        <ProgressError error={query.error} onRetry={() => query.refetch()} />
      )}

      {view === "overall" && data && (
        <>
          <OverviewCards data={data} />
          {!hasLearningData ? (
            <EmptyDashboard />
          ) : (
            <>
              <div className="grid gap-6 xl:grid-cols-[minmax(0,1.65fr)_minmax(300px,0.75fr)]">
                <ScoreTrend data={data} />
                <MasteryDistribution data={data} />
              </div>
              <div className="grid gap-6 lg:grid-cols-2">
                <FocusConcepts data={data} />
                <RecentAssessments data={data} />
              </div>
            </>
          )}
        </>
      )}

      {view === "course" && <CourseProgressView />}
    </div>
  );
}

function ProgressError({
  error,
  onRetry,
}: {
  error: unknown;
  onRetry: () => void;
}) {
  return (
    <div className="rounded-[24px] border border-destructive/25 bg-destructive/5 p-6">
      <AlertCircle className="h-8 w-8 text-destructive" />
      <h2 className="mt-4 font-display text-3xl tracking-tight">
        Your progress could not be loaded
      </h2>
      <p className="mt-2 text-sm text-muted-foreground">
        {apiErrorMessage(error, "Please try again in a moment.")}
      </p>
      <button
        type="button"
        onClick={onRetry}
        className="mt-5 inline-flex h-10 items-center gap-2 rounded-full bg-primary px-4 text-sm font-semibold text-primary-foreground"
      >
        <RefreshCw className="h-4 w-4" /> Try again
      </button>
    </div>
  );
}

function CourseProgressView() {
  const [selectedCourseId, setSelectedCourseId] = useState("");
  const coursesQuery = useQuery({
    queryKey: ["courses"],
    queryFn: getCourses,
    staleTime: 15_000,
  });
  const courses = coursesQuery.data?.courses || [];
  const courseId = selectedCourseId || courses[0]?.session_id || "";
  const courseQuery = useQuery({
    queryKey: ["course", courseId],
    queryFn: () => getCourse(courseId),
    enabled: Boolean(courseId),
    staleTime: 15_000,
  });
  const assessmentsQuery = useQuery({
    queryKey: ["course-assessments", courseId],
    queryFn: () => getCourseAssessments(courseId),
    enabled: Boolean(courseId),
    staleTime: 15_000,
  });

  if (coursesQuery.isLoading) return <DashboardSkeleton />;
  if (coursesQuery.isError) {
    return (
      <ProgressError
        error={coursesQuery.error}
        onRetry={() => coursesQuery.refetch()}
      />
    );
  }
  if (!courses.length) {
    return (
      <section className="rounded-[24px] border border-border bg-card p-8 text-center shadow-sm">
        <h2 className="font-display text-3xl tracking-tight">No courses yet</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          Create a course to start tracking course progress.
        </p>
        <Link
          to="/app/new-course"
          className="mt-5 inline-flex h-11 items-center gap-2 rounded-full bg-primary px-5 text-sm font-semibold text-primary-foreground"
        >
          Create a course <ArrowRight className="h-4 w-4" />
        </Link>
      </section>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 rounded-[20px] border border-border bg-card p-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
            Viewing one course
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            Choose a course to keep its progress separate from your overall
            learning.
          </p>
        </div>
        <select
          value={courseId}
          onChange={(event) => setSelectedCourseId(event.target.value)}
          className="h-11 min-w-64 rounded-xl border border-border bg-background px-4 text-sm font-semibold outline-none focus:border-accent"
        >
          {courses.map((course) => (
            <option key={course.session_id} value={course.session_id}>
              {course.topic}
            </option>
          ))}
        </select>
      </div>

      {courseQuery.isLoading && <CourseSkeleton />}
      {courseQuery.isError && (
        <ProgressError
          error={courseQuery.error}
          onRetry={() => courseQuery.refetch()}
        />
      )}
      {courseQuery.data && (
        <CourseDetail
          course={courseQuery.data}
          assessments={assessmentsQuery.data?.assessments || []}
        />
      )}
    </div>
  );
}

function CourseDetail({
  course,
  assessments,
}: {
  course: CourseProgress;
  assessments: DashboardAssessment[];
}) {
  const averageScore = assessments.length
    ? Math.round(
        assessments.reduce((sum, item) => sum + item.percentage, 0) /
          assessments.length,
      )
    : null;
  return (
    <>
      <section className="overflow-hidden rounded-[26px] border border-border bg-primary p-6 text-primary-foreground shadow-sm sm:p-8">
        <div className="flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary-foreground/65">
              Course progress
            </p>
            <h2 className="mt-2 font-display text-3xl tracking-tight sm:text-4xl">
              {course.topic}
            </h2>
            <p className="mt-2 text-sm capitalize text-primary-foreground/70">
              {course.difficulty} difficulty · {course.completed_modules}/
              {course.total_modules} modules completed
            </p>
          </div>
          <div className="font-display text-5xl tracking-tight">
            {course.progress_percent}%
          </div>
        </div>
        <div className="mt-6 h-2.5 overflow-hidden rounded-full bg-primary-foreground/15">
          <div
            className="h-full rounded-full bg-accent transition-[width] duration-500"
            style={{ width: `${course.progress_percent}%` }}
          />
        </div>
      </section>

      <section className="grid gap-3 sm:grid-cols-3">
        <CourseMetric
          label="Modules"
          value={`${course.completed_modules}/${course.total_modules}`}
        />
        <CourseMetric
          label="Learning activities"
          value={`${course.completed_activities}/${course.total_activities}`}
        />
        <CourseMetric
          label="Assessment average"
          value={averageScore === null ? "Not started" : `${averageScore}%`}
        />
      </section>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.35fr)_minmax(300px,0.65fr)]">
        <section className="rounded-[22px] border border-border bg-card p-5 shadow-sm sm:p-6">
          <SectionHeading
            icon={BookOpenCheck}
            title="Module progress"
            detail="Completion and mastery for this course only"
          />
          <div className="mt-5 space-y-3">
            {course.modules.map((module, index) => (
              <article
                key={module.module_id}
                className="rounded-2xl border border-border bg-background/50 p-4"
              >
                <div className="flex items-start gap-3">
                  <span
                    className={`grid h-9 w-9 shrink-0 place-items-center rounded-full ${module.status === "completed" ? "bg-emerald-500/12 text-emerald-700 dark:text-emerald-300" : module.status === "locked" ? "bg-muted text-muted-foreground" : "bg-accent/10 text-accent"}`}
                  >
                    {module.status === "completed" ? (
                      <CheckCircle2 className="h-4 w-4" />
                    ) : module.status === "locked" ? (
                      <LockKeyhole className="h-4 w-4" />
                    ) : (
                      <Circle className="h-4 w-4" />
                    )}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <h3 className="font-semibold">
                        {index + 1}. {module.title}
                      </h3>
                      <span className="text-sm font-semibold text-accent">
                        {module.progress_percent}%
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {module.completed_activities}/{module.total_activities}{" "}
                      activities
                      {module.mastery_percent !== null
                        ? ` · ${module.mastery_percent}% mastery`
                        : ""}
                    </p>
                    <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-muted">
                      <div
                        className="h-full rounded-full bg-accent"
                        style={{ width: `${module.progress_percent}%` }}
                      />
                    </div>
                  </div>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className="rounded-[22px] border border-border bg-card p-5 shadow-sm sm:p-6">
          <SectionHeading
            icon={Target}
            title="Course assessments"
            detail={`${assessments.length} recent result${assessments.length === 1 ? "" : "s"}`}
          />
          {assessments.length ? (
            <div className="mt-4 divide-y divide-border">
              {assessments.map((assessment) => (
                <Link
                  key={assessment.submission_id}
                  to="/app/session/$id/assessments"
                  params={{ id: course.session_id }}
                  search={{
                    submission: assessment.submission_id,
                    module: undefined,
                    reattempt: undefined,
                    type:
                      assessment.assessment_type === "truefalse" ||
                      assessment.assessment_type === "oneword"
                        ? assessment.assessment_type
                        : "mcq",
                  }}
                  className="flex items-center gap-3 py-3.5 transition hover:text-accent"
                >
                  <span className="grid h-10 w-10 place-items-center rounded-full bg-accent/10 text-sm font-bold text-accent">
                    {Math.round(assessment.percentage)}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm font-semibold">
                      {TYPE_LABELS[assessment.assessment_type] || "Assessment"}
                    </span>
                    <span className="block text-xs text-muted-foreground">
                      {formatDate(assessment.created_at)}
                    </span>
                  </span>
                  <ArrowRight className="h-4 w-4" />
                </Link>
              ))}
            </div>
          ) : (
            <PanelEmpty text="Assessment results for this course will appear here." />
          )}
          <Link
            to="/app/session/$id/path"
            params={{ id: course.session_id }}
            className="mt-5 inline-flex h-10 items-center gap-2 rounded-full bg-primary px-4 text-sm font-semibold text-primary-foreground"
          >
            Open course <ArrowRight className="h-4 w-4" />
          </Link>
        </section>
      </div>
    </>
  );
}

function CourseMetric({ label, value }: { label: string; value: string }) {
  return (
    <article className="rounded-[20px] border border-border bg-card p-5 shadow-sm">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="mt-3 font-display text-3xl tracking-tight">{value}</p>
    </article>
  );
}

function CourseSkeleton() {
  return (
    <div className="space-y-5">
      <div className="h-52 animate-pulse rounded-[26px] bg-muted" />
      <div className="grid gap-3 sm:grid-cols-3">
        {[0, 1, 2].map((item) => (
          <div
            key={item}
            className="h-28 animate-pulse rounded-[20px] bg-muted"
          />
        ))}
      </div>
    </div>
  );
}

function OverviewCards({ data }: { data: LearnerDashboard }) {
  const improvement = data.overview.improvement_percentage_points;
  const metrics = [
    {
      label: "Overall accuracy",
      value: `${Math.round(data.overview.overall_accuracy)}%`,
      detail: `${data.overview.questions_answered} questions answered`,
      icon: Target,
    },
    {
      label: "Average mastery",
      value: `${Math.round(data.overview.average_mastery)}%`,
      detail: `${data.overview.concepts_tracked} concepts tracked`,
      icon: BrainCircuit,
    },
    {
      label: "Current streak",
      value: `${data.overview.current_streak} day${data.overview.current_streak === 1 ? "" : "s"}`,
      detail: `${data.overview.active_days_30} active days this month`,
      icon: Flame,
    },
    {
      label: "Recent improvement",
      value:
        improvement === null
          ? "Building"
          : `${improvement > 0 ? "+" : ""}${Math.round(improvement)} pts`,
      detail:
        improvement === null
          ? "Complete 4 assessments to compare"
          : improvement >= 0
            ? "Compared with earlier attempts"
            : "A good area to revisit",
      icon: improvement !== null && improvement < 0 ? TrendingDown : TrendingUp,
    },
  ];

  return (
    <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {metrics.map(({ label, value, detail, icon: Icon }) => (
        <article
          key={label}
          className="rounded-[20px] border border-border bg-card p-5 shadow-sm"
        >
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm font-medium text-muted-foreground">{label}</p>
            <span className="grid h-9 w-9 place-items-center rounded-full bg-accent/10 text-accent">
              <Icon className="h-4 w-4" />
            </span>
          </div>
          <p className="mt-5 font-display text-3xl tracking-tight">{value}</p>
          <p className="mt-1 text-xs text-muted-foreground">{detail}</p>
        </article>
      ))}
    </section>
  );
}

function ScoreTrend({ data }: { data: LearnerDashboard }) {
  const points = data.score_trend.map((item, index) => ({
    ...item,
    label: item.created_at
      ? new Intl.DateTimeFormat(undefined, {
          month: "short",
          day: "numeric",
        }).format(new Date(item.created_at))
      : `Attempt ${index + 1}`,
  }));

  return (
    <section className="rounded-[22px] border border-border bg-card p-5 shadow-sm sm:p-6">
      <SectionHeading
        icon={TrendingUp}
        title="Score trend"
        detail="Your latest assessment results"
      />
      {points.length === 0 ? (
        <PanelEmpty text="Your score history will appear after your first assessment." />
      ) : (
        <div className="mt-6 h-72 w-full" aria-label="Assessment score trend">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart
              data={points}
              margin={{ top: 8, right: 8, left: -22, bottom: 0 }}
            >
              <defs>
                <linearGradient id="score-fill" x1="0" y1="0" x2="0" y2="1">
                  <stop
                    offset="0%"
                    stopColor="var(--accent)"
                    stopOpacity={0.35}
                  />
                  <stop
                    offset="100%"
                    stopColor="var(--accent)"
                    stopOpacity={0.02}
                  />
                </linearGradient>
              </defs>
              <CartesianGrid
                stroke="var(--border)"
                strokeDasharray="3 5"
                vertical={false}
              />
              <XAxis
                dataKey="label"
                axisLine={false}
                tickLine={false}
                tick={{ fill: "var(--muted-foreground)", fontSize: 12 }}
              />
              <YAxis
                domain={[0, 100]}
                ticks={[0, 25, 50, 75, 100]}
                axisLine={false}
                tickLine={false}
                tick={{ fill: "var(--muted-foreground)", fontSize: 12 }}
              />
              <Tooltip
                formatter={(value) => [`${value}%`, "Score"]}
                labelFormatter={(_, payload) =>
                  payload[0]?.payload?.topic || "Assessment"
                }
                contentStyle={{
                  background: "var(--card)",
                  border: "1px solid var(--border)",
                  borderRadius: 12,
                  color: "var(--foreground)",
                }}
              />
              <Area
                type="monotone"
                dataKey="percentage"
                stroke="var(--accent)"
                strokeWidth={3}
                fill="url(#score-fill)"
                activeDot={{ r: 5, fill: "var(--accent)" }}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
      {data.assessment_types.length > 0 && (
        <div className="mt-5 grid gap-2 border-t border-border pt-4 sm:grid-cols-3">
          {data.assessment_types.map((item) => (
            <div
              key={item.assessment_type}
              className="rounded-xl bg-muted/70 px-3 py-2.5"
            >
              <div className="text-xs text-muted-foreground">
                {TYPE_LABELS[item.assessment_type] || item.assessment_type}
              </div>
              <div className="mt-1 font-semibold">
                {Math.round(item.accuracy)}% · {item.attempts} attempt
                {item.attempts === 1 ? "" : "s"}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function MasteryDistribution({ data }: { data: LearnerDashboard }) {
  const chartData = Object.entries(data.mastery_distribution).map(
    ([name, value]) => ({ name, value }),
  );
  const total = chartData.reduce((sum, item) => sum + item.value, 0);

  return (
    <section className="rounded-[22px] border border-border bg-card p-5 shadow-sm sm:p-6">
      <SectionHeading
        icon={BrainCircuit}
        title="Mastery map"
        detail={`${total} concept${total === 1 ? "" : "s"} measured`}
      />
      {total === 0 ? (
        <PanelEmpty text="Concept mastery will build as you answer questions." />
      ) : (
        <>
          <div className="relative mx-auto mt-3 h-48 max-w-xs">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={chartData}
                  dataKey="value"
                  nameKey="name"
                  innerRadius={58}
                  outerRadius={82}
                  paddingAngle={3}
                  stroke="transparent"
                >
                  {chartData.map((item, index) => (
                    <Cell key={item.name} fill={BAND_COLORS[index]} />
                  ))}
                </Pie>
                <Tooltip
                  formatter={(value, name) => [
                    value,
                    BAND_LABELS[name as keyof typeof BAND_LABELS],
                  ]}
                  contentStyle={{
                    background: "var(--card)",
                    border: "1px solid var(--border)",
                    borderRadius: 12,
                    color: "var(--foreground)",
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
            <div className="pointer-events-none absolute inset-0 grid place-items-center text-center">
              <div>
                <div className="font-display text-3xl">
                  {Math.round(data.overview.average_mastery)}%
                </div>
                <div className="text-xs text-muted-foreground">average</div>
              </div>
            </div>
          </div>
          <div className="mt-2 grid grid-cols-2 gap-2">
            {chartData.map((item, index) => (
              <div
                key={item.name}
                className="flex items-center justify-between rounded-xl bg-muted/65 px-3 py-2 text-xs"
              >
                <span className="flex items-center gap-2 text-muted-foreground">
                  <span
                    className="h-2.5 w-2.5 rounded-full"
                    style={{ background: BAND_COLORS[index] }}
                  />
                  {BAND_LABELS[item.name as keyof typeof BAND_LABELS]}
                </span>
                <strong>{item.value}</strong>
              </div>
            ))}
          </div>
        </>
      )}
    </section>
  );
}

function FocusConcepts({ data }: { data: LearnerDashboard }) {
  return (
    <section className="rounded-[22px] border border-border bg-card p-5 shadow-sm sm:p-6">
      <div className="flex items-start justify-between gap-4">
        <SectionHeading
          icon={Target}
          title="Focus next"
          detail="Concepts with the most room to grow"
        />
        {data.overview.due_reviews > 0 && (
          <Link
            to="/app/reviews"
            className="inline-flex shrink-0 items-center gap-1 text-xs font-semibold text-accent hover:underline"
          >
            {data.overview.due_reviews} due{" "}
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        )}
      </div>
      {data.focus_concepts.length === 0 ? (
        <PanelEmpty text="Take an assessment to discover which concepts need focus." />
      ) : (
        <div className="mt-5 space-y-4">
          {data.focus_concepts.map((concept) => {
            const percentage = Math.round(concept.mastery_probability * 100);
            return (
              <article key={concept.concept_id}>
                <div className="flex items-center justify-between gap-3 text-sm">
                  <div className="min-w-0">
                    <p className="truncate font-semibold">
                      {concept.concept_label}
                    </p>
                    <p className="mt-0.5 text-xs capitalize text-muted-foreground">
                      {BAND_LABELS[concept.band]} · {concept.difficulty_reached}{" "}
                      level · {concept.attempts} attempts
                    </p>
                  </div>
                  <span className="font-display text-xl">{percentage}%</span>
                </div>
                <div className="mt-2 h-2 overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full bg-accent transition-[width]"
                    style={{ width: `${percentage}%` }}
                  />
                </div>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}

function RecentAssessments({ data }: { data: LearnerDashboard }) {
  return (
    <section className="rounded-[22px] border border-border bg-card p-5 shadow-sm sm:p-6">
      <SectionHeading
        icon={BookOpenCheck}
        title="Recent assessments"
        detail={`${data.overview.assessments_completed} completed`}
      />
      {data.recent_assessments.length === 0 ? (
        <PanelEmpty text="Completed assessments will be saved here." />
      ) : (
        <div className="mt-4 divide-y divide-border">
          {data.recent_assessments.slice(0, 6).map((assessment) => (
            <article
              key={assessment.submission_id}
              className="flex items-center gap-3 py-3.5"
            >
              <span
                className={`grid h-11 w-11 shrink-0 place-items-center rounded-full text-sm font-bold ${assessment.percentage >= 70 ? "bg-accent/10 text-accent" : "bg-destructive/10 text-destructive"}`}
              >
                {Math.round(assessment.percentage)}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold">
                  {assessment.topic}
                </p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {TYPE_LABELS[assessment.assessment_type] ||
                    assessment.assessment_type}{" "}
                  · {assessment.score}/{assessment.total} ·{" "}
                  {formatDate(assessment.created_at)}
                </p>
              </div>
              {assessment.session_id && (
                <Link
                  to="/app/session/$id/assessments"
                  params={{ id: assessment.session_id }}
                  search={{
                    submission: assessment.submission_id,
                    module: undefined,
                    reattempt: undefined,
                    type:
                      assessment.assessment_type === "truefalse" ||
                      assessment.assessment_type === "oneword"
                        ? assessment.assessment_type
                        : "mcq",
                  }}
                  aria-label={`Open ${assessment.topic} assessments`}
                  className="grid h-9 w-9 shrink-0 place-items-center rounded-full text-muted-foreground transition hover:bg-muted hover:text-foreground"
                >
                  <ArrowRight className="h-4 w-4" />
                </Link>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function EmptyDashboard() {
  return (
    <section className="rounded-[24px] border border-border bg-card px-6 py-12 text-center shadow-sm">
      <span className="mx-auto grid h-14 w-14 place-items-center rounded-full bg-accent/10 text-accent">
        <BarChart3 className="h-7 w-7" />
      </span>
      <h2 className="mt-5 font-display text-3xl tracking-tight">
        Your progress will grow with you
      </h2>
      <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-muted-foreground">
        Complete an assessment and your score trend, mastery map, focus
        concepts, and personalized suggestions will start appearing here.
      </p>
      <Link
        to="/app/new-course"
        className="mt-6 inline-flex h-11 items-center gap-2 rounded-full bg-primary px-5 text-sm font-semibold text-primary-foreground"
      >
        Create a course <ArrowRight className="h-4 w-4" />
      </Link>
    </section>
  );
}

function DashboardSkeleton() {
  return (
    <div className="space-y-6" aria-label="Loading progress">
      <div className="h-24 max-w-xl animate-pulse rounded-2xl bg-muted" />
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[0, 1, 2, 3].map((item) => (
          <div
            key={item}
            className="h-36 animate-pulse rounded-[20px] bg-muted"
          />
        ))}
      </div>
      <div className="grid gap-6 xl:grid-cols-[1.65fr_0.75fr]">
        <div className="h-96 animate-pulse rounded-[22px] bg-muted" />
        <div className="h-96 animate-pulse rounded-[22px] bg-muted" />
      </div>
    </div>
  );
}

function SectionHeading({
  icon: Icon,
  title,
  detail,
}: {
  icon: typeof BarChart3;
  title: string;
  detail: string;
}) {
  return (
    <div>
      <div className="flex items-center gap-2 text-accent">
        <Icon className="h-4 w-4" />
        <h2 className="font-display text-2xl tracking-tight text-foreground">
          {title}
        </h2>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">{detail}</p>
    </div>
  );
}

function PanelEmpty({ text }: { text: string }) {
  return (
    <div className="mt-5 rounded-xl bg-muted/65 p-5 text-sm leading-6 text-muted-foreground">
      {text}
    </div>
  );
}

function formatDate(value: string | null) {
  if (!value) return "Recently";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Recently";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
  }).format(date);
}
