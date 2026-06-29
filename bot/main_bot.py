import asyncio
import os
import time

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from database.db import (
    add_progress_update,
    create_invite_code,
    get_assignment,
    get_student_teacher,
    get_submission,
    get_teacher_progress_updates,
    get_teacher_students,
    get_telegram_id,
    get_user_by_telegram_id,
    is_student_linked,
    link_student_to_teacher,
    login_user,
    register_user,
    update_submission_feedback,
    update_telegram_id,
)
from services.ai_service import generate_reminder_message
from services.agents import (
    router,
    teacher_agent,
    student_agent,
    summariser_agent,
)
from services.assignment_service import (
    create_assignment,
    fetch_latest_active_assignment,
    fetch_student_assignments,
    fetch_teacher_assignments,
)
from services.submission_service import create_submission

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
TELEGRAM_GROUP_INVITE_LINK = os.getenv("TELEGRAM_GROUP_INVITE_LINK", "")

if not BOT_TOKEN:
    raise Exception("BOT_TOKEN missing in .env")

teacher_sessions = {}
pending_feedback = {}


def _telegram_id(update):
    return str(update.effective_user.id)


def _username_from_update(update):
    user = get_user_by_telegram_id(_telegram_id(update))
    return user[2] if user else None


def _role_from_update(update):
    user = get_user_by_telegram_id(_telegram_id(update))
    return user[4] if user else None


def _display_name(update):
    user = update.effective_user
    return user.username or user.full_name or f"student_{user.id}"


def _group_invite_text():
    if not TELEGRAM_GROUP_INVITE_LINK:
        return ""

    return f"\n\nJoin the classroom Telegram group here:\n{TELEGRAM_GROUP_INVITE_LINK}"


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0].startswith("link_"):
        context.args = [context.args[0].replace("link_", "", 1)]
        await link_command(update, context)
        return

    await update.message.reply_text(
        "Classroom Companion\n\n"
        "Teacher:\n"
        "/registerteacher teacher01 pass123\n"
        "/loginteacher teacher01 pass123\n"
        "/onboard Riya\n"
        "Then send: Assign Riya a 500-word essay on photosynthesis, due in 3 days.\n\n"
        "Student:\n"
        "/link INVITE_CODE\n"
        "Then reply naturally: done 2 paragraphs, stuck on intro, completed, or upload a file/photo."
    )


async def register_teacher_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        await update.message.reply_text("Register teacher in private chat.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("Usage: /registerteacher teacher01 pass123")
        return

    teacher_id, password = context.args[0], context.args[1]
    success = register_user(teacher_id, teacher_id, password, "teacher")
    update_telegram_id(teacher_id, _telegram_id(update))
    teacher_sessions[_telegram_id(update)] = teacher_id

    await update.message.reply_text(
        "Teacher registered and logged in." if success else "Teacher already exists; Telegram linked and logged in."
    )


async def login_teacher_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        await update.message.reply_text("Login in private chat.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("Usage: /loginteacher teacher01 pass123")
        return

    teacher_id, password = context.args[0], context.args[1]
    result = login_user(teacher_id, password)

    if not result:
        await update.message.reply_text("Invalid login.")
        return

    update_telegram_id(teacher_id, _telegram_id(update))
    teacher_sessions[_telegram_id(update)] = teacher_id

    await update.message.reply_text("Login successful. You can now assign work in natural language.")


async def onboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    teacher = teacher_sessions.get(_telegram_id(update)) or _username_from_update(update)

    if not teacher or _role_from_update(update) != "teacher":
        await update.message.reply_text("Teacher login required.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /onboard Riya")
        return

    student = context.args[0].strip("@")
    code = create_invite_code(teacher, student)

    await update.message.reply_text(
        f"Invite created for {student}.\n"
        f"Ask the student to open this bot and send:\n/link {code}"
    )


async def link_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /link INVITE_CODE")
        return

    result = link_student_to_teacher(
        context.args[0],
        _telegram_id(update),
        _display_name(update)
    )

    if not result:
        await update.message.reply_text("Invalid invite code.")
        return

    await update.message.reply_text(
        f"Linked successfully. Your teacher is {result['teacher']}."
        f"{_group_invite_text()}"
    )

    teacher_telegram = get_telegram_id(result["teacher"])
    if teacher_telegram:
        await context.bot.send_message(
            chat_id=teacher_telegram,
            text=f"{result['student']} linked their Telegram account.",
        )


async def register_student_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /registerstudent Rahul")
        return

    student = context.args[0].strip("@")
    register_user(student, student, "", "student")
    update_telegram_id(student, _telegram_id(update))
    await update.message.reply_text(
        "Student Telegram connected. If your teacher gave you a code, send /link CODE too."
        f"{_group_invite_text()}"
    )


async def assign_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    teacher = teacher_sessions.get(_telegram_id(update)) or _username_from_update(update)

    if not teacher or _role_from_update(update) != "teacher":
        await update.message.reply_text("Teacher login required.")
        return

    if len(context.args) < 3:
        await update.message.reply_text("Usage: /assign Rahul Math 2026-06-15")
        return

    student = context.args[0].strip("@")
    task = " ".join(context.args[1:-1])
    deadline = context.args[-1]

    await create_and_send_assignment(update, context, teacher, student, task, deadline)


async def create_and_send_assignment(update, context, teacher, student, task, deadline):

    # A teacher can only assign work to a student who has registered (linked).
    if not is_student_linked(student, teacher):
        await update.message.reply_text(
            f"❌ {student} has not registered yet.\n"
            "Share your invite link from the web dashboard. Once they register, you can assign work."
        )
        return

    result = create_assignment(student, task, deadline, teacher)
    telegram_id = get_telegram_id(student)

    if telegram_id:
        await context.bot.send_message(
            chat_id=telegram_id,
            text=(
                f"New assignment from {teacher}\n\n"
                f"Assignment ID: {result['assignment_id']}\n"
                f"Task: {task}\n"
                f"Deadline: {deadline}\n\n"
                "Reply with progress anytime. When finished, say completed and send your text/file/photo."
            ),
        )

    await update.message.reply_text(
        f"Assignment created for {student}.\nTask: {task}\nDeadline: {deadline}"
    )


async def mywork_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    student = context.args[0].strip("@") if context.args else _username_from_update(update)

    if not student:
        await update.message.reply_text("Usage: /mywork Rahul")
        return

    assignments = fetch_student_assignments(student)

    if not assignments:
        await update.message.reply_text("No assignments found.")
        return

    lines = [f"Assignments for {student}"]
    for row in assignments:
        lines.append(f"#{row[0]} | {row[2]} | due {row[3]} | {row[4]}")

    await update.message.reply_text("\n".join(lines))


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    teacher = teacher_sessions.get(_telegram_id(update)) or _username_from_update(update)

    if not teacher or _role_from_update(update) != "teacher":
        await update.message.reply_text("Teacher login required.")
        return

    assignments = fetch_teacher_assignments(teacher)
    updates = get_teacher_progress_updates(teacher)
    await update.message.reply_text(summariser_agent.summarize(assignments, updates))


async def remind_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /remind Rahul")
        return

    student = context.args[0].strip("@")
    assignments = fetch_student_assignments(student)
    telegram_id = get_telegram_id(student)

    if not telegram_id:
        await update.message.reply_text("Student Telegram is not connected.")
        return

    sent = 0
    for row in assignments:
        if row[4] in ["Pending", "In Progress", "Needs Help"]:
            await context.bot.send_message(
                chat_id=telegram_id,
                text=generate_reminder_message(student, row[2], row[3], "manual"),
            )
            sent += 1

    await update.message.reply_text(f"Reminder sent for {sent} active assignment(s).")


async def handle_teacher_message(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    teacher = teacher_sessions.get(_telegram_id(update)) or _username_from_update(update)

    if pending_feedback.get(_telegram_id(update)):
        submission_id = pending_feedback.pop(_telegram_id(update))
        submission = get_submission(submission_id)
        update_submission_feedback(submission_id, text, "Reviewed")

        if submission:
            student = submission[2]
            student_telegram = get_telegram_id(student)
            if student_telegram:
                await context.bot.send_message(
                    chat_id=student_telegram,
                    text=f"Your teacher sent feedback:\n\n{text}",
                )

        await update.message.reply_text("Feedback saved and sent to the student.")
        return

    # RouterAgent decides what kind of teacher message this is.
    # Agent calls hit the LLM (blocking) -> run them off the event loop.
    routed = await asyncio.to_thread(router.route, text, "teacher")
    intent = routed.get("intent")

    if intent == "assignment":
        # TeacherAgent extracts the structured assignment.
        result = await asyncio.to_thread(teacher_agent.parse_assignment, text)
        student = result.get("student")
        task = result.get("task")
        deadline = result.get("deadline")

        if not student or not task:
            await update.message.reply_text("I could not identify the student/task. Try: Assign Riya an essay, due in 3 days.")
            return

        await create_and_send_assignment(update, context, teacher, student, task, deadline)
        return

    if intent == "status_summary":
        # SummariserAgent builds the teacher status update.
        assignments = fetch_teacher_assignments(teacher)
        updates = get_teacher_progress_updates(teacher)
        summary = await asyncio.to_thread(summariser_agent.summarize, assignments, updates)
        await update.message.reply_text(summary)
        return

    answer = await asyncio.to_thread(teacher_agent.answer, text, teacher)
    await update.message.reply_text(answer)


async def handle_student_message(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    student = _username_from_update(update)

    if not student:
        await update.message.reply_text("Please link your Telegram first with /link INVITE_CODE.")
        return

    assignment = fetch_latest_active_assignment(student)

    if not assignment:
        # No active work -> StudentAgent acts as a tutor (LLM, off-loop).
        answer = await asyncio.to_thread(student_agent.answer, text, student)
        await update.message.reply_text(answer)
        return

    # RouterAgent + StudentAgent interpret the progress message (LLM, off-loop).
    routed = await asyncio.to_thread(router.route, text, "student")
    progress = await asyncio.to_thread(student_agent.interpret_progress, text)
    status = progress.get("status", "In Progress")

    if (routed.get("intent") == "completion") or status == "Submitted":
        result = create_submission(assignment[0], student, "telegram-text", text)
        add_progress_update(assignment[0], student, text, "Submitted")
        await notify_teacher_of_submission(context, assignment, result["submission_id"], student, text)
        await update.message.reply_text("Marked complete and sent to your teacher. Nice work.")
        return

    add_progress_update(assignment[0], student, progress.get("summary", text), status)

    teacher = get_student_teacher(student) or assignment[5]
    teacher_telegram = get_telegram_id(teacher) if teacher else None

    if teacher_telegram:
        await context.bot.send_message(
            chat_id=teacher_telegram,
            text=f"Progress update from {student} on #{assignment[0]}:\n{progress.get('summary', text)}\nStatus: {status}",
        )

    await update.message.reply_text("Progress saved and shared with your teacher.")


async def notify_teacher_of_submission(context, assignment, submission_id, student, text):
    teacher = assignment[5] or get_student_teacher(student)
    teacher_telegram = get_telegram_id(teacher) if teacher else None

    if teacher_telegram:
        pending_feedback[str(teacher_telegram)] = submission_id
        await context.bot.send_message(
            chat_id=teacher_telegram,
            text=(
                f"{student} submitted assignment #{assignment[0]}.\n"
                f"Task: {assignment[2]}\n\n"
                f"Submission:\n{text}\n\n"
                "Reply with feedback and I will send it to the student."
            ),
        )


async def handle_attachment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    student = _username_from_update(update)

    if not student:
        await update.message.reply_text("Please link your Telegram first with /link INVITE_CODE.")
        return

    assignment = fetch_latest_active_assignment(student)

    if not assignment:
        await update.message.reply_text("I received the file, but you have no active assignment.")
        return

    os.makedirs("uploads/telegram", exist_ok=True)

    attachment = update.message.document or (update.message.photo[-1] if update.message.photo else None)
    telegram_file = await attachment.get_file()
    filename = getattr(attachment, "file_name", None) or f"photo_{int(time.time())}.jpg"
    file_path = os.path.join("uploads", "telegram", f"{int(time.time())}_{filename}")

    await telegram_file.download_to_drive(file_path)

    result = create_submission(assignment[0], student, file_path, update.message.caption or "")
    add_progress_update(assignment[0], student, update.message.caption or "Submitted a file/photo.", "Submitted")
    await notify_teacher_of_submission(context, assignment, result["submission_id"], student, file_path)

    await update.message.reply_text("Submission received and forwarded to your teacher.")


async def natural_language_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return

    text = update.message.text
    if text.startswith("/"):
        return

    role = _role_from_update(update)

    if role == "teacher":
        await handle_teacher_message(update, context, text)
        return

    if role == "student":
        await handle_student_message(update, context, text)
        return

    await update.message.reply_text("Please register/login as a teacher or link as a student first.")


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("registerteacher", register_teacher_command))
    app.add_handler(CommandHandler("loginteacher", login_teacher_command))
    app.add_handler(CommandHandler("registerstudent", register_student_command))
    app.add_handler(CommandHandler("onboard", onboard_command))
    app.add_handler(CommandHandler("link", link_command))
    app.add_handler(CommandHandler("assign", assign_command))
    app.add_handler(CommandHandler("mywork", mywork_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("remind", remind_command))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_attachment))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, natural_language_router))

    print("Bot started")
    app.run_polling()


if __name__ == "__main__":
    main()
