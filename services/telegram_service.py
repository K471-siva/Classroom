import os

import requests

from dotenv import load_dotenv

from database.db import (
    get_classroom
)

# =========================
# LOAD ENV
# =========================

load_dotenv()

BOT_TOKEN = os.getenv(
    "BOT_TOKEN"
)

# =========================
# SEND GROUP MESSAGE
# =========================

def send_group_message(

    group_id,
    message

):

    try:

        url = (
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        )

        payload = {

            "chat_id": group_id,

            "text": message
        }

        requests.post(

            url,

            data=payload
        )

    except Exception as e:

        print(e)

def send_private_message(telegram_id, message):

    if not telegram_id:
        return False

    try:

        url = (
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        )

        payload = {
            "chat_id": telegram_id,
            "text": message
        }

        requests.post(
            url,
            data=payload,
            timeout=10
        )

        return True

    except Exception as e:

        print(e)

        return False
