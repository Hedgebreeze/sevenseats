import json
import os

PUSHOVER_APP_TOKEN = os.getenv("PUSHOVER_APP_TOKEN", "")
PUSHOVER_USER_KEY = os.getenv("PUSHOVER_USER_KEY", "")
PUSHOVER_PRIORITY = int(os.getenv("PUSHOVER_PRIORITY", "0"))
PUSHOVER_URL_TITLE = "Book this table"
GIST_ID = os.getenv("GIST_ID", "")
GIST_TOKEN = os.getenv("GIST_TOKEN", "")
RENOTIFY_MINUTES = int(os.getenv("RENOTIFY_MINUTES", "180"))

ENABLE_EMAIL = os.getenv("ENABLE_EMAIL", "false").lower() in {"1", "true", "yes"}
EMAIL_USERNAME = os.getenv("EMAIL_USERNAME", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
EMAIL_SMTP_SERVER = os.getenv("EMAIL_SMTP_SERVER", "smtp.gmail.com")
EMAIL_SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT", "587"))
EMAIL_TO = os.getenv("EMAIL_TO", "")

RETRY_AFTER = int(os.getenv("RETRY_AFTER", "120"))

RESTAURANTS = [
    {
        "name": "Manhatta",
        "venue": "manhatta",
        "reservation_url": "https://www.sevenrooms.com/explore/manhatta/reservations/create/search/",
        "num_people": 2,
        "main_time": "19:00",
        "times_needed": ["19:00:00", "19:30:00"],
        "dates_needed": ["2026-04-25", "2026-04-26"],
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
        "dates_needed": ["2026-04-25"],
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
        "dates_needed": ["2026-04-25"],
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
        "dates_needed": ["2026-04-25"],
        "enable_lunch": False,
        "enable_dinner": True,
    },
]
