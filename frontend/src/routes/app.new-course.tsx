import { createFileRoute } from "@tanstack/react-router";

import { NewCoursePage, type NewCourseSearch } from "@/routes/app.index";

export const Route = createFileRoute("/app/new-course")({
  validateSearch: (search: Record<string, unknown>) => {
    const result: NewCourseSearch = {};
    if (typeof search.topic === "string") result.topic = search.topic;
    if (typeof search.assessment_submission_id === "string") {
      result.assessment_submission_id = search.assessment_submission_id;
    }
    if (typeof search.adaptive_from_session === "string") {
      result.adaptive_from_session = search.adaptive_from_session;
    }
    if (typeof search.adaptive_from_topic === "string") {
      result.adaptive_from_topic = search.adaptive_from_topic;
    }
    return result;
  },
  head: () => ({
    meta: [
      { title: "Create a course - Lexinit" },
      {
        name: "description",
        content: "Create a personalized Lexinit course.",
      },
    ],
  }),
  component: NewCourseRoute,
});

function NewCourseRoute() {
  return <NewCoursePage search={Route.useSearch()} />;
}
