import asyncio
import os
from datetime import date, datetime, timezone

from dotenv import load_dotenv
from telegram import Bot

from database.db import get_pending_assignments, get_telegram_id, mark_assignment_reminded
from services.agents import reminder_agent

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise Exception("BOT_TOKEN missing in .env")

bot = Bot(token=BOT_TOKEN)


async def send_reminder(telegram_id, message):
    try:
        await bot.send_message(chat_id=telegram_id, text=message)
    except Exception as e:
        print(e)


def reminder_urgency(deadline):
    try:
        due = datetime.fromisoformat(deadline).date()
    except ValueError:
        return "normal"

    days_left = (due - date.today()).days

    if days_left <= 0:
        return "urgent"

    if days_left == 1:
        return "high"

    return "normal"


def should_send_reminder(deadline, reminder_count, last_reminded_at):
    try:
        due = datetime.fromisoformat(deadline).date()
        days_left = (due - date.today()).days
    except ValueError:
        days_left = 2

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    if last_reminded_at:
        try:
            last = datetime.fromisoformat(last_reminded_at)
            hours_since = (now - last).total_seconds() / 3600
        except ValueError:
            hours_since = 999
    else:
        hours_since = 999

    if days_left <= 0:
        return hours_since >= 6

    if days_left == 1:
        return hours_since >= 12

    return reminder_count == 0 or hours_since >= 24


async def assignment_reminders():
    assignments = get_pending_assignments()

    for assignment in assignments:
        assignment_id = assignment[0]
        student = assignment[1]
        task = assignment[2]
        deadline = assignment[3]
        reminder_count = assignment[5] or 0
        last_reminded_at = assignment[6]

        if not should_send_reminder(deadline, reminder_count, last_reminded_at):
            continue

        telegram_id = get_telegram_id(student)

        if telegram_id:
            # ReminderAgent crafts the nudge with the right urgency.
            message = reminder_agent.message(
                student,
                task,
                deadline,
                reminder_urgency(deadline),
            )

            await send_reminder(telegram_id, message)
            mark_assignment_reminded(assignment_id)


async def reminder_loop():
    while True:
        await assignment_reminders()
        await asyncio.sleep(3600)
