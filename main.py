import csv
import datetime
import json
import logging
import os
import smtplib
import time
from zoneinfo import ZoneInfo

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
NYC = ZoneInfo("America/New_York")
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
    "slot_key",
    "lead_days",
    "lead_hours",
    "weekday_slot",
    "weekday_seen",
    "hour_slot",
    "run_id",
    "source",
]


def current_time_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def run_once_enabled():
    return os.getenv("RUN_ONCE", "").lower() in {"1", "true", "yes"}


def github_run_url():
    run_id = os.getenv("GITHUB_RUN_ID", "")
    server = os.getenv("GITHUB_SERVER_URL", "https://github.com")
    repository = os.getenv("GITHUB_REPOSITORY", "")
    if run_id and repository:
        return f"{server}/{repository}/actions/runs/{run_id}"
    return ""


def gist_headers():
    if not (config.GIST_ID and config.GIST_TOKEN):
        return None
    return {
        "Authorization": f"token {config.GIST_TOKEN}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "SevenSeatsState/1.0",
    }


def supabase_enabled():
    return bool(
        getattr(config, "SUPABASE_URL", "").strip()
        and getattr(config, "SUPABASE_SERVICE_ROLE_KEY", "").strip()
    )


def supabase_headers(prefer=None):
    if not supabase_enabled():
        return None
    headers = {
        "apikey": config.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {config.SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def supabase_rest_url(path):
    return f"{config.SUPABASE_URL.rstrip('/')}/rest/v1/{path.lstrip('/')}"


def supabase_insert(table, payload, returning=False):
    if not supabase_enabled():
        return None
    response = requests.post(
        supabase_rest_url(table),
        headers=supabase_headers("return=representation" if returning else "return=minimal"),
        json=payload,
        timeout=20,
    )
    response.raise_for_status()
    if returning:
        return response.json()
    return None


def supabase_update(table, filters, payload):
    if not supabase_enabled():
        return
    query = "&".join(f"{key}=eq.{value}" for key, value in filters.items())
    response = requests.patch(
        f"{supabase_rest_url(table)}?{query}",
        headers=supabase_headers("return=minimal"),
        json=payload,
        timeout=20,
    )
    response.raise_for_status()


def load_seen_state():
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
        csv.writer(file_obj).writerow([row.get(column, "") for column in CSV_HEADER])


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


def parse_slot_datetime(slot_time_iso):
    try:
        naive = datetime.datetime.strptime(slot_time_iso, "%Y-%m-%d %H:%M:%S")
        return naive.replace(tzinfo=NYC)
    except ValueError:
        return None


def format_slot_datetime(slot_time_iso):
    slot_dt = parse_slot_datetime(slot_time_iso)
    if slot_dt is None:
        return slot_time_iso, slot_time_iso
    return slot_dt.strftime("%-I:%M %p"), slot_dt.strftime("%a, %b %-d")


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
        return False

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
        return True
    except Exception:
        logger.error("Failed to send Pushover message.", exc_info=True)
        return False


def send_email(subject, message):
    if not config.ENABLE_EMAIL:
        return False

    if not config.EMAIL_USERNAME or not config.EMAIL_PASSWORD:
        logger.error("Email username or password not provided. Skipping.")
        return False

    try:
        server = smtplib.SMTP(config.EMAIL_SMTP_SERVER, config.EMAIL_SMTP_PORT)
        server.ehlo()
        server.starttls()
        server.login(config.EMAIL_USERNAME, config.EMAIL_PASSWORD)
        email_message = f"Subject: {subject}\n\n{message}"
        server.sendmail(config.EMAIL_USERNAME, config.EMAIL_TO, email_message)
        server.close()
        logger.info("Email sent.")
        return True
    except Exception:
        logger.error("Failed to send email.", exc_info=True)
        return False


def check_availability(restaurant, date_needed, stats):
    converted_date = datetime.datetime.strptime(date_needed, "%Y-%m-%d").strftime(
        "%m-%d-%Y"
    )
    stats["api_calls_made"] += 1
    try:
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
    except Exception:
        stats["api_calls_failed"] += 1
        raise

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
    if "dates_needed" in restaurant:
        return restaurant["dates_needed"]
    days_ahead = int(restaurant.get("days_ahead", 1))
    today = datetime.datetime.now(NYC).date()
    return [
        (today + datetime.timedelta(days=offset)).strftime("%Y-%m-%d")
        for offset in range(days_ahead)
    ]


def build_log_row(restaurant, slot, action, reason, run_id, seen_at):
    slot_dt = parse_slot_datetime(slot["time_iso"])
    seen_local = seen_at.astimezone(NYC)
    lead_hours = ""
    lead_days = ""
    weekday_slot = ""
    hour_slot = ""
    if slot_dt is not None:
        delta_seconds = (slot_dt - seen_local).total_seconds()
        lead_hours = round(delta_seconds / 3600, 1)
        lead_days = (slot_dt.date() - seen_local.date()).days
        weekday_slot = slot_dt.strftime("%a")
        hour_slot = slot_dt.hour

    return {
        "seen_at_iso": seen_at.isoformat(timespec="seconds"),
        "slot_at_iso": slot_dt.isoformat(timespec="seconds") if slot_dt else slot["time_iso"],
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
        "slot_key": notification_key(restaurant, slot),
        "lead_days": lead_days,
        "lead_hours": lead_hours,
        "weekday_slot": weekday_slot,
        "weekday_seen": seen_local.strftime("%a"),
        "hour_slot": hour_slot,
        "run_id": run_id,
        "source": "sevenrooms",
    }


def should_notify(seen_state, key, now_ts):
    """
    Cross-run dedupe:
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
        cooldown_minutes = int((now_ts - last_notified) / 60)
        return True, f"COOLDOWN_{cooldown_minutes}MIN"
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
    pushover_sent = send_pushover(title, message, reservation_url)
    email_sent = send_email(title, message)
    return pushover_sent or email_sent


def config_snapshot(restaurants):
    return {
        "renotify_minutes": getattr(config, "RENOTIFY_MINUTES", 180),
        "restaurants": [
            {
                "name": restaurant["name"],
                "venue": restaurant["venue"],
                "num_people": restaurant["num_people"],
                "main_time": restaurant["main_time"],
                "times_needed": restaurant["times_needed"],
                "days_ahead": restaurant.get("days_ahead"),
                "dates_needed": restaurant.get("dates_needed"),
                "enable_lunch": restaurant.get("enable_lunch", True),
                "enable_dinner": restaurant.get("enable_dinner", True),
            }
            for restaurant in restaurants
        ],
    }


def start_run_record(restaurants):
    if not supabase_enabled():
        logger.info("No Supabase credentials configured. Database logging disabled.")
        return None

    payload = {
        "status": "running",
        "source": "sevenrooms",
        "restaurants_checked": len(restaurants),
        "config": config_snapshot(restaurants),
        "github_run_id": os.getenv("GITHUB_RUN_ID", ""),
        "github_run_url": github_run_url(),
    }
    try:
        rows = supabase_insert("watcher_runs", payload, returning=True) or []
        if rows:
            run_id = rows[0]["id"]
            logger.info(f"Started Supabase watcher run {run_id}.")
            return run_id
    except Exception:
        logger.error("Failed to create Supabase run record.", exc_info=True)
    return None


def finish_run_record(run_id, stats, status="success", error_message=""):
    if not run_id or not supabase_enabled():
        return
    payload = {
        "completed_at": current_time_utc().isoformat(timespec="seconds"),
        "status": status,
        "error_message": error_message or None,
        "matches_seen": stats["matches_seen"],
        "notifications_sent": stats["notifications_sent"],
        "suppressed": stats["suppressed"],
        "dates_checked": stats["dates_checked"],
        "api_calls_made": stats["api_calls_made"],
        "api_calls_failed": stats["api_calls_failed"],
    }
    try:
        supabase_update("watcher_runs", {"id": run_id}, payload)
    except Exception:
        logger.error("Failed to finalize Supabase run record.", exc_info=True)


def persist_supabase_rows(rows):
    if not rows or not supabase_enabled():
        return
    try:
        supabase_insert("availability_logs", rows, returning=False)
        logger.info(f"Inserted {len(rows)} availability rows into Supabase.")
    except Exception:
        logger.error("Failed to insert availability rows into Supabase.", exc_info=True)


def run_check():
    restaurants = getattr(config, "RESTAURANTS", [])
    if not restaurants:
        raise ValueError("No restaurants configured. Add entries to config.RESTAURANTS.")

    for restaurant in restaurants:
        validate_restaurant(restaurant)

    run_id = start_run_record(restaurants)
    seen_state = load_seen_state()
    present_this_run = set()
    now_ts = int(time.time())
    stats = {
        "matches_seen": 0,
        "notifications_sent": 0,
        "suppressed": 0,
        "dates_checked": 0,
        "api_calls_made": 0,
        "api_calls_failed": 0,
    }
    supabase_rows = []

    try:
        for restaurant in restaurants:
            concrete_dates = dates_to_check(restaurant)
            logger.info(
                f"Checking {restaurant['name']} ({restaurant['venue']}) for "
                f"{len(concrete_dates)} date(s)."
            )
            stats["dates_checked"] += len(concrete_dates)

            for date_needed in concrete_dates:
                available_slots = check_availability(restaurant, date_needed, stats)
                for slot in available_slots:
                    if not slot_matches(restaurant, date_needed, slot):
                        continue

                    key = notification_key(restaurant, slot)
                    present_this_run.add(key)
                    stats["matches_seen"] += 1

                    should_send, reason = should_notify(seen_state, key, now_ts)
                    action = "NOTIFIED" if should_send else "SUPPRESSED"
                    seen_at = current_time_utc()
                    row = build_log_row(restaurant, slot, action, reason, run_id, seen_at)
                    append_log_row(row)
                    supabase_rows.append(row)

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
        persist_supabase_rows(supabase_rows)
        finish_run_record(run_id, stats, status="success")
        logger.info(
            f"Run summary: matches_seen={stats['matches_seen']} "
            f"notifications_sent={stats['notifications_sent']} "
            f"suppressed={stats['suppressed']} "
            f"api_calls_made={stats['api_calls_made']}"
        )
    except Exception as exc:
        finish_run_record(run_id, stats, status="error", error_message=str(exc))
        raise


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
