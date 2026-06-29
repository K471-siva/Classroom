"""
Cooperating AI agents for the Classroom Companion.

This module implements the agentic design described in the project brief.
Each agent owns one responsibility and uses the LLM primitives in
``services.ai_service`` as its "tools". The bot/dashboard talk to these
agents instead of calling the raw LLM helpers directly.

Agents
------
RouterAgent     -> classifies an incoming message (assignment / status /
                   progress / completion / chat).
TeacherAgent    -> handles teacher conversations: assignment creation and
                   feedback collection.
StudentAgent    -> handles student conversations: progress capture and
                   submission detection.
ReminderAgent   -> decides when/how to nudge a student about a deadline.
SummariserAgent -> produces the status summary a teacher receives.

The agents are intentionally framework-free (plain LLM-with-tools) so the
project has no heavy dependency, but the split mirrors what a LangGraph /
CrewAI design would look like.
"""

from services import ai_service


class RouterAgent:
    """Intent / Routing Agent — classifies the incoming message."""

    def route(self, text, role):
        return ai_service.route_intent(text, role)


class TeacherAgent:
    """Teacher Agent — assignment creation + feedback interpretation."""

    def parse_assignment(self, text):
        """Extract {student, task, deadline} from natural language."""
        return ai_service.detect_assignment(text)

    def answer(self, text, teacher=None):
        """Free-form teacher Q&A fallback."""
        return ai_service.ask_ai(text, teacher)


class StudentAgent:
    """Student Agent — progress capture and submission detection."""

    def interpret_progress(self, text):
        """Return {status, summary} for a student's progress message."""
        return ai_service.interpret_student_progress(text)

    def is_completion(self, text, routed=None):
        """Decide whether the message means the work is finished."""
        routed = routed or ai_service.route_intent(text, "student")
        progress = ai_service.interpret_student_progress(text)
        return (
            routed.get("intent") == "completion"
            or progress.get("status") == "Submitted"
        )

    def answer(self, text, student=None):
        """Free-form student tutoring fallback (no active assignment)."""
        return ai_service.ask_ai(text, student)


class ReminderAgent:
    """Reminder / Scheduler Agent — decides when and how to nudge."""

    def message(self, student, task, deadline, urgency="normal"):
        return ai_service.generate_reminder_message(student, task, deadline, urgency)


class SummariserAgent:
    """Summariser Agent — produces teacher-facing status updates."""

    def summarize(self, assignments, progress_updates):
        return ai_service.summarize_status(assignments, progress_updates)


# Shared singletons so callers can `from services.agents import router, ...`

router = RouterAgent()
teacher_agent = TeacherAgent()
student_agent = StudentAgent()
reminder_agent = ReminderAgent()
summariser_agent = SummariserAgent()
