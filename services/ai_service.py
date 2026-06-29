import json
import os
import re
from datetime import datetime, timedelta

from dotenv import load_dotenv
from groq import Groq

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    print("WARNING: GROQ_API_KEY missing")
    client = None
else:
    client = Groq(api_key=GROQ_API_KEY)


def _chat(messages, fallback, temperature=0.3):
    if client is None:
        return fallback

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            temperature=temperature,
            messages=messages,
        )

        return response.choices[0].message.content

    except Exception as e:
        print("GROQ ERROR:", str(e))
        return fallback


def _chat_json(system_prompt, user_prompt, fallback):
    if client is None:
        return fallback

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            temperature=0.1,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )

        return json.loads(response.choices[0].message.content)

    except Exception as e:
        print("AI JSON ERROR:", str(e))
        return fallback


def _deadline_from_text(text):
    lowered = text.lower()
    today = datetime.now().date()

    if "today" in lowered:
        return today.isoformat()

    if "tomorrow" in lowered:
        return (today + timedelta(days=1)).isoformat()

    match = re.search(r"due\s+in\s+(\d+)\s+day", lowered)
    if match:
        return (today + timedelta(days=int(match.group(1)))).isoformat()

    match = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if match:
        return match.group(1)

    return (today + timedelta(days=1)).isoformat()


def ask_ai(message, student=None):
    fallback = (
        "I can help with homework, progress updates, assignment reminders, "
        "and simple study explanations. Please try again with a little more detail."
    )

    prompt = f"""
Student:
{student or "unknown"}

Question:
{message}

Rules:
- Give a short beginner-friendly answer.
- Use an educational and motivating tone.
- Maximum 120 words.
"""

    return _chat(
        [
            {
                "role": "system",
                "content": "You are a helpful classroom tutor.",
            },
            {"role": "user", "content": prompt},
        ],
        fallback,
    )


def _fallback_assignment(text):
    words = text.replace(",", " ").split()
    student = None

    for index, word in enumerate(words):
        if word.lower() in ["assign", "give", "set"] and index + 1 < len(words):
            student = words[index + 1].strip("@").capitalize()
            break

    if not student and words:
        ignored = {
            "assign",
            "give",
            "set",
            "homework",
            "assignment",
            "due",
            "in",
            "days",
            "day",
            "today",
            "tomorrow",
            "a",
            "an",
            "the",
        }

        for word in words:
            if word.lower() not in ignored and not word.isdigit():
                student = word.strip("@").capitalize()
                break

    return {
        "student": student,
        "task": text,
        "deadline": _deadline_from_text(text),
    }


def detect_assignment(text):
    fallback = _fallback_assignment(text)

    result = _chat_json(
        """
You extract assignment instructions for a classroom bot.
Return JSON with keys: student, task, deadline.
deadline must be ISO date YYYY-MM-DD when possible.
If the message is not an assignment, include error.
""",
        text,
        fallback,
    )

    # The LLM does not know today's date, so it mishandles relative deadlines
    # ("due in 3 days", "today", "tomorrow") and can emit bogus dates like
    # 1970-01-04. Prefer the deterministic parser whenever the text uses a
    # relative phrase, and fall back to it for missing/invalid/past dates.
    lowered = text.lower()
    relative = (
        "today" in lowered
        or "tomorrow" in lowered
        or re.search(r"due\s+in\s+\d+\s+day", lowered)
    )

    deadline = result.get("deadline")
    valid_iso = bool(deadline) and bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(deadline)))
    not_past = valid_iso and str(deadline) >= datetime.now().date().isoformat()

    if relative or not valid_iso or not not_past:
        result["deadline"] = _deadline_from_text(text)

    return result


def route_intent(text, role):
    lowered = text.lower().strip()
    fallback = {"intent": "chat", "confidence": 0.5}

    if role == "teacher":
        if lowered.startswith(("assign ", "give ", "set ")) or " due " in lowered:
            fallback = {"intent": "assignment", "confidence": 0.8}
        elif "feedback" in lowered or "review" in lowered:
            fallback = {"intent": "feedback", "confidence": 0.7}
        elif "status" in lowered or "summary" in lowered or "progress" in lowered:
            fallback = {"intent": "status_summary", "confidence": 0.7}
    else:
        if any(word in lowered for word in ["completed", "complete", "done", "submit", "finished"]):
            fallback = {"intent": "completion", "confidence": 0.8}
        elif any(word in lowered for word in ["stuck", "started", "paragraph", "progress", "working"]):
            fallback = {"intent": "progress", "confidence": 0.8}

    return _chat_json(
        """
Classify a classroom Telegram message.
Return JSON keys: intent, confidence.
Allowed teacher intents: assignment, feedback, status_summary, chat.
Allowed student intents: progress, completion, chat.
""",
        f"role={role}\nmessage={text}",
        fallback,
    )


def interpret_student_progress(text):
    lowered = text.lower()
    status = "In Progress"

    if any(word in lowered for word in ["completed", "complete", "finished", "submitted", "done"]):
        status = "Submitted"
    elif "stuck" in lowered or "help" in lowered:
        status = "Needs Help"

    fallback = {"status": status, "summary": text}

    return _chat_json(
        """
Interpret a student's assignment progress update.
Return JSON keys: status and summary.
status should be one of In Progress, Needs Help, Submitted.
""",
        text,
        fallback,
    )


def generate_reminder_message(student, task, deadline, urgency="normal"):
    fallback = (
        f"Hi {student}, quick reminder about your assignment: {task}. "
        f"It is due on {deadline}. Reply with your progress, or say completed when done."
    )

    return _chat(
        [
            {
                "role": "system",
                "content": "Write friendly, concise Telegram reminders for students.",
            },
            {
                "role": "user",
                "content": (
                    f"Student: {student}\nTask: {task}\nDeadline: {deadline}\n"
                    f"Urgency: {urgency}\nMax 70 words."
                ),
            },
        ],
        fallback,
        temperature=0.4,
    )


def summarize_status(assignments, progress_updates):
    fallback_lines = []

    for row in assignments:
        last_progress = row[7] if len(row) > 7 and row[7] else "none"
        fallback_lines.append(f"{row[1]}: {row[2]} | {row[4]} | last update: {last_progress}")

    fallback = "\n".join(fallback_lines) or "No active assignment updates yet."

    return _chat(
        [
            {
                "role": "system",
                "content": "Summarize classroom assignment status for a teacher in clear bullets.",
            },
            {
                "role": "user",
                "content": f"Assignments: {assignments}\nProgress updates: {progress_updates}",
            },
        ],
        fallback,
    )


def analyze_student(student, marks):
    if not marks:
        return "No marks available."

    total = 0
    count = 0
    summary = ""

    for subject, score in marks:
        total += score
        count += 1
        summary += f"{subject}: {score}\n"

    avg = total / count

    if avg >= 80:
        performance = "Excellent performance."
    elif avg >= 60:
        performance = "Good performance."
    else:
        performance = "Needs improvement."

    return f"Marks Summary\n{summary}\nAverage: {avg:.1f}\n{performance}"


def generate_homework_feedback(student, assignment, submission_text):
    fallback = (
        "Strengths: submitted clearly.\n"
        "Weak Areas: add more detail where possible.\n"
        "Improvement Tips: revise once for clarity and examples."
    )

    prompt = f"""
Student:
{student}

Assignment:
{assignment}

Submission:
{submission_text}

Provide strengths, weak areas, grammar suggestions, and improvement tips.
"""

    return _chat(
        [
            {
                "role": "system",
                "content": "You are an encouraging educational evaluator.",
            },
            {"role": "user", "content": prompt},
        ],
        fallback,
    )
