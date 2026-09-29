import datetime
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


# Load the public runtime config, never a developer's local credentials.
spec = importlib.util.spec_from_file_location(
    "config", Path(__file__).resolve().parents[1] / "config.example.py"
)
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)
sys.modules["config"] = config

import main


class LaRenommeeTests(unittest.TestCase):
    def setUp(self):
        self.restaurant = next(
            restaurant for restaurant in config.RESTAURANTS
            if restaurant["venue"] == "larenommee"
        )
        self.date = "2026-10-25"
        self.slot = {
            "type": "book",
            "time_iso": f"{self.date} 19:00:00",
            "access_persistent_id": "bookable-access",
            "public_time_slot_description": "Dining Room",
        }

    def test_live_response_shape_filters_requests_and_unwanted_times(self):
        request_only = dict(
            self.slot, type="request", access_persistent_id=None,
            time_iso=f"{self.date} 19:30:00",
        )
        later = dict(self.slot, time_iso=f"{self.date} 22:00:00")
        response_data = {
            "data": {"availability": {self.date: [
                {"name": "Dinner", "shift_category": "DINNER",
                 "times": [self.slot, request_only, later]},
                {"name": "Lunch", "shift_category": "LUNCH",
                 "times": [dict(self.slot)]},
            ]}}
        }
        stats = {"api_calls_made": 0, "api_calls_failed": 0}
        with patch.object(main.requests, "get") as get:
            get.return_value.json.return_value = response_data
            slots = main.check_availability(self.restaurant, self.date, stats)

        params = get.call_args.kwargs["params"]
        self.assertEqual(params["venue"], "larenommee")
        self.assertEqual(params["party_size"], 2)
        self.assertEqual(params["start_date"], "10-25-2026")
        self.assertEqual(params["num_days"], 1)
        self.assertEqual(stats, {"api_calls_made": 1, "api_calls_failed": 0})
        matches = [s for s in slots if main.slot_matches(self.restaurant, self.date, s)]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["shift_category"], "DINNER")
        self.assertFalse(main.slot_matches(self.restaurant, "2026-10-26", self.slot))

    def test_paris_log_uses_winter_offset_and_elapsed_hours_across_dst(self):
        seen_at = datetime.datetime(2026, 10, 24, 17, tzinfo=datetime.timezone.utc)
        row = main.build_log_row(
            self.restaurant, self.slot, "NOTIFIED", "FIRST_SIGHTING", None, seen_at
        )
        self.assertEqual(row["slot_at_iso"], "2026-10-25T19:00:00+01:00")
        self.assertEqual(row["lead_hours"], 25)
        self.assertEqual(row["lead_days"], 1)
        self.assertEqual(row["hour_slot"], 19)
        self.assertIn("party_size=2&date=2026-10-25", row["reservation_url"])

    def test_existing_venues_keep_new_york_timezone(self):
        restaurant = dict(self.restaurant)
        restaurant.pop("timezone")
        row = main.build_log_row(
            restaurant, self.slot, "SUPPRESSED", "COOLDOWN_1MIN", None,
            datetime.datetime(2026, 10, 25, 22, tzinfo=datetime.timezone.utc),
        )
        self.assertEqual(row["slot_at_iso"], "2026-10-25T19:00:00-04:00")
        self.assertEqual(row["lead_hours"], 1)

    def test_rolling_dates_use_venue_local_date(self):
        restaurant = dict(self.restaurant, days_ahead=2)
        restaurant.pop("dates_needed")
        instant = datetime.datetime(2026, 10, 24, 22, 30, tzinfo=datetime.timezone.utc)

        class FixedDatetime(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return instant.astimezone(tz)

        # Midnight has passed in Paris, while NYC is still on the previous day.
        with patch.object(main.datetime, "datetime", FixedDatetime):
            self.assertEqual(main.dates_to_check(restaurant), [self.date, "2026-10-26"])
            restaurant.pop("timezone")
            self.assertEqual(main.dates_to_check(restaurant), ["2026-10-24", self.date])

    def test_notification_keeps_paris_wall_time_and_booking_parameters(self):
        with patch.object(main, "send_pushover", return_value=True) as push, \
             patch.object(main, "send_email", return_value=False):
            self.assertTrue(main.notify_match(self.restaurant, self.slot))
        title, message, url = push.call_args.args
        self.assertIn("La Renommée", title)
        self.assertIn("Table for 2 @ 7:00 PM on Sun, Oct 25", message)
        self.assertEqual(url, self.restaurant["reservation_url"])


if __name__ == "__main__":
    unittest.main()
