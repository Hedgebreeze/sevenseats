# SevenRooms Availability Checker

This project polls the SevenRooms availability API and sends notifications when a matching, bookable reservation slot appears.

It now borrows a few of the strongest ideas from `stonewatch`:

- cross-run dedupe via GitHub Gist
- historical CSV logging of every matched sighting
- a lightweight static dashboard for reviewing what the watcher has seen over time

## What Changed

- Supports multiple restaurants in one run
- Supports per-restaurant lunch/dinner toggles
- Uses Pushover for notifications
- Deduplicates alerts across runs with a GitHub Gist
- Logs matched sightings to `availability_log.csv`
- Includes a static dashboard at `dashboard/index.html`

## Local Setup

1. Create a virtualenv and install dependencies:
   `python3 -m venv .venv`
   `.venv/bin/pip install -r requirements.txt`
2. Copy `config.example.py` to `config.py`
3. Add your Pushover credentials in `config.py`
4. Edit the `RESTAURANTS` list in `config.py`
5. Run:
   `.venv/bin/python main.py`

## GitHub Actions Setup

This repo now includes [`.github/workflows/check-reservations.yml`](/Users/jacob/git/sevenseats/.github/workflows/check-reservations.yml:1), which is designed for scheduled polling on GitHub Actions.

It uses `RUN_ONCE=true`, so each Actions job does a single polling pass and exits cleanly.

Current schedule in `America/New_York`:

- Every 5 minutes from 9:00 AM through 10:59 AM
- Every 15 minutes from 7:00 AM through 8:59 AM and from 11:00 AM through 11:59 PM
- Hourly from 12:00 AM through 6:59 AM

Set these repository secrets:

- `PUSHOVER_APP_TOKEN`
- `PUSHOVER_USER_KEY`
- `GIST_ID`
- `GIST_TOKEN`

Optional secrets:

- `PUSHOVER_PRIORITY`
- `PUSHOVER_URL_TITLE`
- `RENOTIFY_MINUTES`
- `ENABLE_EMAIL`
- `EMAIL_USERNAME`
- `EMAIL_PASSWORD`
- `EMAIL_SMTP_SERVER`
- `EMAIL_SMTP_PORT`
- `EMAIL_TO`

Restaurant config now lives publicly in `config.example.py`, which the workflow copies to `config.py` at runtime.

Pushover format now mimics Stonewatch:

- Title: `Reservation found at [restaurant]!!`
- Message: `Table for [party size] @ [time] on [date]`
- Second line: seating / slot description
- Clickthrough button text: `PUSHOVER_URL_TITLE`

GitHub Actions now supports timezone-aware schedules, so this workflow is configured directly in Eastern time rather than manually converting cron expressions to UTC.

## Gist Dedupe

For persistent dedupe across GitHub Actions runs, create a private GitHub Gist and add:

- `GIST_ID`: the gist id
- `GIST_TOKEN`: a GitHub token with `gist` scope

The watcher stores state in a JSON file inside that Gist so it can tell the difference between:

- a first sighting
- a slot that disappeared and reappeared
- a slot that is still around and should stay under cooldown

## Dashboard

Open [dashboard/index.html](/Users/jacob/git/sevenseats/dashboard/index.html:1) in a browser to inspect the committed `availability_log.csv`.

It supports:

- summary counts
- restaurant filtering
- notified vs suppressed views
- free-text searching
- manual CSV upload if you want to inspect an exported log file

## Config Shape

Each item in `RESTAURANTS` can define:

- `name`: Friendly label used in logs and notifications
- `venue`: SevenRooms venue slug
- `reservation_url`: Optional booking link to include in notifications
- `num_people`: Party size
- `main_time`: Primary query time in `HH:MM`
- `times_needed`: Acceptable slot times in `HH:MM:SS`
- `dates_needed`: Dates to watch in `YYYY-MM-DD`
- `enable_lunch`: Whether to consider `LUNCH` shifts
- `enable_dinner`: Whether to consider `DINNER` shifts
- `halo_size_interval`: Optional API override
- `num_days`: Optional API override
- `channel`: Optional API override

## Known Venue Slugs

- Manhatta: `manhatta`
- Or'esh: `450wbroadway`
- The Corner Store: `thecornerstore`
- The Eighty Six: `theeightysix`

## Notes

- Request-only slots are still ignored. The script only alerts on bookable slots with a non-null `access_persistent_id`.
- Without `GIST_ID` and `GIST_TOKEN`, deduplication falls back to the current process only.
- With Gist state enabled, duplicate notifications are suppressed across GitHub Actions runs based on `RENOTIFY_MINUTES`.
- The workflow uses GitHub Actions `concurrency` so a new scheduled run cancels any older in-progress checker run instead of stacking them.
