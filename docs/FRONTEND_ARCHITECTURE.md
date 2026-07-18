# Lexinit frontend architecture

## Stack

- React 19 and TypeScript
- Vite build tooling
- TanStack Router with generated, type-safe routes
- TanStack Query for server state and cache invalidation
- Tailwind CSS for responsive styling
- Motion for transitions and interaction animation
- Zod runtime validation for important API responses

## Structure

```text
src/main.tsx                 Application bootstrap
src/router.tsx               Router and QueryClient policy
src/routeTree.gen.ts         Generated route tree
src/routes/                  Page routes and route-level loading
src/components/              Shared product components
src/components/ui/           Only actively used UI primitives
src/hooks/                   Shared server-state hooks
src/lib/api.ts               API client, public types, runtime schemas
src/lib/session-utils.ts     Backward-compatible course normalization
src/lib/route-prefetch.ts    Intent-based course-page preloading
src/styles.css               Tokens, themes, motion, and global layout
```

## Route map

| Route | Screen |
| --- | --- |
| `/` | Product homepage and authentication entry |
| `/login` | Login redirect/entry |
| `/onboarding` | Required profile setup after registration |
| `/app` | Protected application shell |
| `/app/` | Learning dashboard and course list |
| `/app/new-course` | Focused course-creation screen |
| `/app/insights` | Overall and course-level Progress dashboard |
| `/app/reviews` | Scheduled review queue |
| `/app/profile` | Profile, badges, identity, and password management |
| `/app/session/:id/path` | Full Learning Path and module navigation |
| `/app/session/:id/materials` | Study Materials |
| `/app/session/:id/flashcards` | Flashcards |
| `/app/session/:id/assessments` | Assessments, results, and reattempts |
| `/app/session/:id/videos` | Video Lectures, progress, and Lecture Guide |
| `/app/session/:id/resources` | Additional Resources |

The `/app` route verifies authentication and redirects incomplete profiles to onboarding before rendering the application shell.

## State rules

- TanStack Query owns server data; routes and components do not maintain duplicate long-lived copies.
- Query keys are invalidated after mutations that affect courses, progress, mastery, recommendations, or profile data.
- Generation polling is isolated in `use-generation-run` and survives navigation.
- Search parameters carry module, Assessment type, submission, and reattempt context.
- `session-utils` normalizes old and new session shapes so existing courses remain usable.

## Course navigation

The application shell provides global Dashboard, New Course, Progress, Reviews, and Profile navigation. Inside a course, the Learning Path is the main index. The course sidebar highlights the active module and activity, exposes Additional Resources, and shows completion toward the course badge. Study Materials use their dedicated reading layout rather than the course sidebar.

## UI conventions

- Learner-facing names are consistent: Course, Learning Path, Module, Study Materials, Flashcards, Assessments, Video Lectures, Additional Resources, Progress.
- Pages use the same topic/module context and back-navigation treatment.
- Light and dark themes use semantic tokens rather than hard-coded white containers.
- Loading, empty, error, retry, and completed states are explicit.
- Animations respect reduced-motion preferences where applicable.
- Technical generation scores, model names, validation internals, and backend terminology are not shown to learners.
- Desktop and mobile layouts share the same information hierarchy.

## API boundary

`src/lib/api.ts` is the only general API client. It:

- sends credentials and CSRF headers
- normalizes API errors
- exposes typed request helpers
- validates important responses with Zod
- defines the public frontend contract for courses, generation, Assessments, progress, adaptive learning, sources, and Video Lectures

Correct Assessment answers are never inferred or stored before submission.

## Frontend verification

```powershell
npm install
npx tsc --noEmit
npm run lint
npm run build
```

`noUnusedLocals`, `noUnusedParameters`, and ESLint unused-variable checks are enabled so dead source does not silently accumulate again.
