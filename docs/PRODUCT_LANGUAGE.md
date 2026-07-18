# Lexinit product language

Use these names in every user-facing screen, message, document export, and API error.
Internal database fields and API paths may continue to use legacy identifiers such as `session_id`.

## Product structure

- **Learning Dashboard**: the signed-in home where learners create and resume courses.
- **Course** / **Courses**: the saved learning experience for one topic. Never call it a session, study kit, or workspace in product copy.
- **Learning Path**: the ordered structure inside a course.
- **Course overview**: the main Learning Path screen.
- **Module** / **Modules**: a section within the Learning Path.
- **Progress**: scores, mastery, weak areas, and recommended next steps. Do not label this area Insights or Progress Dashboard.

## Course content

Use these exact navigation labels and capitalization:

- **Study Materials**
- **Video Lectures**
- **Flashcards**
- **Assessments**
- **Additional Resources**

Use **Lecture Guide** for the transcript-grounded summary and questions attached to a Video Lecture.

## Adaptive learning

- **Recommended next steps**: personalized recommendations shown on the Learning Dashboard.
- **Focused course**: a new course created from weak areas identified by an Assessment.

## Writing rules

- Use content-type names consistently; do not shorten Study Materials to Notes or Video Lectures to Videos in navigation.
- Use singular terms only for a single item, such as one Video Lecture or one Assessment.
- Keep implementation terms such as backend, worker, checkpoint, generation run, repair step, and session ID out of user-facing messages.
- Prefer plain actions: **Create course**, **Resume course**, **Continue course creation**, and **Course created**.
