import json
import os


def env_int(name, default):
    value = os.getenv(name, "").strip()
    if not value:
        return default
    return int(value)


PUSHOVER_APP_TOKEN = os.getenv("PUSHOVER_APP_TOKEN", "")
PUSHOVER_USER_KEY = os.getenv("PUSHOVER_USER_KEY", "")
PUSHOVER_PRIORITY = env_int("PUSHOVER_PRIORITY", 0)
PUSHOVER_URL_TITLE = "Book this table"
GIST_ID = os.getenv("GIST_ID", "")
GIST_TOKEN = os.getenv("GIST_TOKEN", "")
RENOTIFY_MINUTES = env_int("RENOTIFY_MINUTES", 180)

ENABLE_EMAIL = os.getenv("ENABLE_EMAIL", "false").lower() in {"1", "true", "yes"}
EMAIL_USERNAME = os.getenv("EMAIL_USERNAME", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
EMAIL_SMTP_SERVER = os.getenv("EMAIL_SMTP_SERVER", "smtp.gmail.com")
EMAIL_SMTP_PORT = env_int("EMAIL_SMTP_PORT", 587)
EMAIL_TO = os.getenv("EMAIL_TO", "")

RETRY_AFTER = env_int("RETRY_AFTER", 120)

RESTAURANTS = [
    {
        "name": "Manhatta",
        "venue": "manhatta",
        "reservation_url": "https://www.sevenrooms.com/explore/manhatta/reservations/create/search/",
        "num_people": 2,
        "main_time": "19:00",
        "times_needed": ["19:00:00", "19:30:00"],
        "days_ahead": 14,
        "enable_lunch": False,
        "enable_dinner": True,
    },
    {
        "name": "Or'esh",
        "venue": "450wbroadway",
        "reservation_url": "https://www.sevenrooms.com/explore/450wbroadway/reservations/create/search/",
        "num_people": 2,
        "main_time": "19:00",
        "times_needed": ["19:00:00", "19:30:00"],
        "days_ahead": 14,
        "enable_lunch": False,
        "enable_dinner": True,
    },
    {
        "name": "The Corner Store",
        "venue": "thecornerstore",
        "reservation_url": "https://fp.sevenrooms.com/explore/thecornerstore/reservations/create/search/",
        "num_people": 2,
        "main_time": "19:00",
        "times_needed": ["19:00:00", "19:30:00"],
        "days_ahead": 14,
        "enable_lunch": False,
        "enable_dinner": True,
    },
    {
        "name": "The Eighty Six",
        "venue": "theeightysix",
        "reservation_url": "https://fp.sevenrooms.com/explore/theeightysix/reservations/create/search/",
        "num_people": 2,
        "main_time": "19:00",
        "times_needed": ["19:00:00", "19:30:00"],
        "days_ahead": 14,
        "enable_lunch": False,
        "enable_dinner": True,
    },
]
