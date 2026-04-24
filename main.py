import csv
import datetime
import json
import logging
import os
import smtplib
import time

import requests

import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s SevenRooms Booking Checker - %(funcName)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("SevenRooms Booking Checker")

DEFAULT_CHANNEL = "SEVENROOMS_WIDGET"
LOG_FILE = "availability_log.csv"
STATE_FILENAME = "sevenrooms_seen.json"
STATE_TTL_DAYS = 14
CSV_HEADER = [
    "seen_at_iso",
    "slot_at_iso",
    "restaurant_name",
    "venue",
    "party_size",
    "shift_category",
    "shift_name",
    "public_time_slot_description",
    "reservation_url",
    "notification_action",
    "notification_reason",
    "source",
]


def current_time_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def run_once_enabled():
    return os.getenv("RUN_ONCE", "").lower() in {"1", "true", "yes"}


def gist_headers():
    if not (config.GIST_ID and config.GIST_TOKEN):
        return None
    return {
        "Authorization": f"token {config.GIST_TOKEN}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "SevenSeatsState/1.0",
    }


def load_seen_state():
    """
    Loads cross-run state from a GitHub Gist if configured.
    """
    if not (config.GIST_ID and config.GIST_TOKEN):
        logger.info("No GIST_ID/GIST_TOKEN configured. Using in-memory dedupe only.")
        return {}

    try:
        response = requests.get(
            f"https://api.github.com/gists/{config.GIST_ID}",
            headers=gist_headers(),
            timeout=20,
        )
        response.raise_for_status()
        files = response.json().get("files", {})
        content = files.get(STATE_FILENAME, {}).get("content", "{}")
        data = json.loads(content)

        cutoff = int(time.time()) - (STATE_TTL_DAYS * 24 * 3600)
        pruned = {}
        for key, value in data.items():
            if not isinstance(value, dict):
                continue
            last_seen = int(value.get("last_seen", 0))
            if last_seen >= cutoff:
                pruned[key] = value
        logger.info(f"Loaded {len(pruned)} state entries from Gist.")
        return pruned
    except Exception:
        logger.error("Failed to load Gist state.", exc_info=True)
        return {}


def save_seen_state(seen_state):
    """
    Persists cross-run state to a GitHub Gist if configured.
    """
    if not (config.GIST_ID and config.GIST_TOKEN):
        return

    try:
        payload = {
            "files": {
                STATE_FILENAME: {
                    "content": json.dumps(seen_state, separators=(",", ":"))
                }
            }
        }
        response = requests.patch(
            f"https://api.github.com/gists/{config.GIST_ID}",
            headers=gist_headers(),
            json=payload,
            timeout=20,
        )
        response.raise_for_status()
        logger.info("Saved state to Gist.")
    except Exception:
        logger.error("Failed to save Gist state.", exc_info=True)


def ensure_csv_header(path):
    if not os.path.exists(path):
        with open(path, "w", newline="") as file_obj:
            csv.writer(file_obj).writerow(CSV_HEADER)


def append_log_row(row):
    ensure_csv_header(LOG_FILE)
    with open(LOG_FILE, "a", newline="") as file_obj:
        csv.writer(file_obj).writerow([row[column] for column in CSV_HEADER])


def is_enabled_shift(shift_category, restaurant):
    if shift_category == "LUNCH":
        return restaurant.get("enable_lunch", True)
    if shift_category == "DINNER":
        return restaurant.get("enable_dinner", True)
    return True


def build_reservation_url(restaurant):
    return restaurant.get(
        "reservation_url",
        f"https://www.sevenrooms.com/explore/{restaurant['venue']}/reservations/create/search/",
    )


def format_slot_datetime(slot_time_iso):
    """
    Formats a slot timestamp into compact human-friendly date/time strings.
    """
    try:
        slot_dt = datetime.datetime.strptime(slot_time_iso, "%Y-%m-%d %H:%M:%S")
        return slot_dt.strftime("%-I:%M %p"), slot_dt.strftime("%a, %b %-d")
    except ValueError:
        return slot_time_iso, slot_time_iso


def generate_message(restaurant, slot):
    slot_description = slot.get("public_time_slot_description", "Unknown")
    time_label, date_label = format_slot_datetime(slot["time_iso"])
    return (
        f"Table for {restaurant['num_people']} @ {time_label} on {date_label}\n"
        f"{slot_description}"
    )


def send_pushover(title, message, url):
    if not config.PUSHOVER_APP_TOKEN or not config.PUSHOVER_USER_KEY:
        logger.error("Pushover app token or user key not provided. Skipping.")
        return

    try:
        response = requests.post(
            "https://api.pushover.net/1/messages.json",
            data={
                "token": config.PUSHOVER_APP_TOKEN,
                "user": config.PUSHOVER_USER_KEY,
                "title": title,
                "message": message,
                "priority": getattr(config, "PUSHOVER_PRIORITY", 0),
                "url": url,
                "url_title": getattr(config, "PUSHOVER_URL_TITLE", "Open reservation"),
            },
            timeout=20,
        )
        response.raise_for_status()
        logger.info("Pushover message sent.")
    except Exception:
        logger.error("Failed to send Pushover message.", exc_info=True)


def send_email(subject, message):
    if not config.ENABLE_EMAIL:
        return

    if not config.EMAIL_USERNAME or not config.EMAIL_PASSWORD:
        logger.error("Email username or password not provided. Skipping.")
        return

    try:
        server = smtplib.SMTP(config.EMAIL_SMTP_SERVER, config.EMAIL_SMTP_PORT)
        server.ehlo()
        server.starttls()
        server.login(config.EMAIL_USERNAME, config.EMAIL_PASSWORD)
        email_message = f"Subject: {subject}\n\n{message}"
        server.sendmail(config.EMAIL_USERNAME, config.EMAIL_TO, email_message)
        server.close()
        logger.info("Email sent.")
    except Exception:
        logger.error("Failed to send email.", exc_info=True)


def check_availability(restaurant, date_needed):
    converted_date = datetime.datetime.strptime(date_needed, "%Y-%m-%d").strftime(
        "%m-%d-%Y"
    )
    response = requests.get(
        "https://www.sevenrooms.com/api-yoa/availability/widget/range",
        params={
            "venue": restaurant["venue"],
            "time_slot": restaurant["main_time"],
            "party_size": restaurant["num_people"],
            "halo_size_interval": restaurant.get("halo_size_interval", 16),
            "start_date": converted_date,
            "num_days": restaurant.get("num_days", 1),
            "channel": restaurant.get("channel", DEFAULT_CHANNEL),
        },
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()

    try:
        availability = data["data"]["availability"].get(date_needed, [])
        if not availability:
            logger.info(
                f"{restaurant['name']}: no availability returned for {date_needed}."
            )
            return []

        slots = []
        for shift in availability:
            if not is_enabled_shift(shift.get("shift_category"), restaurant):
                continue
            for slot in shift.get("times", []):
                enriched_slot = dict(slot)
                enriched_slot["shift_category"] = shift.get("shift_category")
                enriched_slot["shift_name"] = shift.get("name")
                slots.append(enriched_slot)
        return slots
    except Exception:
        logger.error(
            f"{restaurant['name']}: failed to parse availability response.",
            exc_info=True,
        )
        return []


def slot_matches(restaurant, date_needed, slot):
    times_i_want = {
        f"{date_needed} {slot_time}" for slot_time in restaurant["times_needed"]
    }
    return (
        slot["time_iso"] in times_i_want
        and slot.get("access_persistent_id") is not None
    )


def notification_key(restaurant, slot):
    return (
        f"{restaurant['venue']}|{slot['time_iso']}|{restaurant['num_people']}|"
        f"{slot.get('shift_category', 'UNKNOWN')}|"
        f"{slot.get('public_time_slot_description', 'Unknown')}"
    )


def validate_restaurant(restaurant):
    required_fields = [
        "name",
        "venue",
        "num_people",
        "main_time",
        "times_needed",
    ]
    missing_fields = [field for field in required_fields if field not in restaurant]
    if missing_fields:
        raise ValueError(
            f"Restaurant config is missing required fields: {', '.join(missing_fields)}"
        )
    if "dates_needed" not in restaurant and "days_ahead" not in restaurant:
        raise ValueError(
            "Restaurant config must include either 'dates_needed' or 'days_ahead'."
        )


def dates_to_check(restaurant):
    """
    Returns the concrete dates to check for a restaurant.
    """
    if "dates_needed" in restaurant:
        return restaurant["dates_needed"]
    days_ahead = int(restaurant.get("days_ahead", 1))
    today = datetime.datetime.now().date()
    return [
        (today + datetime.timedelta(days=offset)).strftime("%Y-%m-%d")
        for offset in range(days_ahead)
    ]


def build_log_row(restaurant, slot, action, reason):
    return {
        "seen_at_iso": current_time_utc().isoformat(timespec="seconds"),
        "slot_at_iso": slot["time_iso"],
        "restaurant_name": restaurant["name"],
        "venue": restaurant["venue"],
        "party_size": restaurant["num_people"],
        "shift_category": slot.get("shift_category", "UNKNOWN"),
        "shift_name": slot.get("shift_name", ""),
        "public_time_slot_description": slot.get(
            "public_time_slot_description", "Unknown"
        ),
        "reservation_url": build_reservation_url(restaurant),
        "notification_action": action,
        "notification_reason": reason,
        "source": "sevenrooms",
    }


def should_notify(seen_state, key, now_ts):
    """
    Simple cross-run dedupe:
    - first sighting: notify
    - disappeared then reappeared: notify
    - otherwise notify after cooldown
    """
    record = seen_state.get(key, {})
    if not isinstance(record, dict):
        record = {}

    was_present = bool(record.get("present", False))
    last_notified = int(record.get("last_notified", 0))
    cooldown_seconds = int(getattr(config, "RENOTIFY_MINUTES", 180)) * 60

    if last_notified == 0:
        return True, "FIRST_SIGHTING"
    if not was_present:
        return True, "REAPPEARED"
    if now_ts - last_notified >= cooldown_seconds:
        return True, f"COOLDOWN_{int((now_ts - last_notified) / 60)}MIN"
    return False, f"COOLDOWN_{int((now_ts - last_notified) / 60)}MIN"


def mark_seen(seen_state, key, slot_present, notified, reason, now_ts):
    record = seen_state.get(key, {})
    if not isinstance(record, dict):
        record = {}
    record["present"] = slot_present
    record["last_seen"] = now_ts
    if notified:
        record["last_notified"] = now_ts
        record["last_reason"] = reason
    seen_state[key] = record


def notify_match(restaurant, slot):
    message = generate_message(restaurant, slot)
    title = f"Reservation found at {restaurant['name']}!!"
    reservation_url = build_reservation_url(restaurant)
    send_pushover(title, message, reservation_url)
    send_email(title, message)


def run_check():
    restaurants = getattr(config, "RESTAURANTS", [])
    if not restaurants:
        raise ValueError("No restaurants configured. Add entries to config.RESTAURANTS.")

    for restaurant in restaurants:
        validate_restaurant(restaurant)

    seen_state = load_seen_state()
    present_this_run = set()
    now_ts = int(time.time())
    stats = {
        "matches_seen": 0,
        "notifications_sent": 0,
        "suppressed": 0,
    }

    for restaurant in restaurants:
        logger.info(
            f"Checking {restaurant['name']} ({restaurant['venue']}) for "
            f"{len(dates_to_check(restaurant))} date(s)."
        )
        for date_needed in dates_to_check(restaurant):
            available_slots = check_availability(restaurant, date_needed)
            for slot in available_slots:
                if not slot_matches(restaurant, date_needed, slot):
                    continue

                key = notification_key(restaurant, slot)
                present_this_run.add(key)
                stats["matches_seen"] += 1

                should_send, reason = should_notify(seen_state, key, now_ts)
                action = "NOTIFIED" if should_send else "SUPPRESSED"
                append_log_row(build_log_row(restaurant, slot, action, reason))

                if should_send:
                    logger.info(
                        f"{restaurant['name']}: booking available: {slot['time_iso']} "
                        f"@ {slot.get('public_time_slot_description', 'Unknown')} "
                        f"[{slot.get('shift_category', 'UNKNOWN')}] ({reason})"
                    )
                    notify_match(restaurant, slot)
                    stats["notifications_sent"] += 1
                else:
                    logger.info(
                        f"{restaurant['name']}: suppressed duplicate notification for "
                        f"{slot['time_iso']} [{slot.get('shift_category', 'UNKNOWN')}] ({reason})"
                    )
                    stats["suppressed"] += 1

                mark_seen(seen_state, key, True, should_send, reason, now_ts)

    for key, record in list(seen_state.items()):
        if not isinstance(record, dict):
            continue
        if record.get("present", False) and key not in present_this_run:
            record["present"] = False

    save_seen_state(seen_state)
    logger.info(
        f"Run summary: matches_seen={stats['matches_seen']} "
        f"notifications_sent={stats['notifications_sent']} "
        f"suppressed={stats['suppressed']}"
    )


def main():
    runcount = 0
    while True:
        logger.info(f"Run count: {runcount}")
        runcount += 1
        run_check()
        if run_once_enabled():
            logger.info("RUN_ONCE enabled. Exiting after one polling pass.")
            return
        time.sleep(config.RETRY_AFTER)


if __name__ == "__main__":
    main()
