# NRBC Report Dashboard

A Streamlit dashboard for daily birth registration and national ID
registration reports collected with a Google Form during field outreach.
It cleans the form responses, reconciles mistyped zone and center names
against a master list, and turns the result into live charts, reporting
completion tracking and Excel reports.

Nothing about a particular office is built in. Each activity ("phase") is
set up in the app with its own office name, dates, response sheet and
master list of zones and centers.

## Features

**Data quality**

- Resubmitted reports (same zone, center and date) are removed, keeping the
  latest submission.
- Rows with missing, negative or fractional counts are flagged.
- Dates outside the activity window are flagged, and day/month swaps from
  spreadsheet locale mix-ups are corrected automatically.
- Column matching tolerates renamed or reordered form headers. Columns that
  can't be matched confidently are confirmed once by an admin and remembered.

**Zone and center reconciliation**

- Submitted zone and center names are checked against the phase's master list.
- Unknown names get a best-guess suggestion (fuzzy matching, and noise such
  as "Primary School" stripped) for an admin to confirm.
- Rows that are not yet reconciled are excluded from the figures and counted
  in a warning, so totals are never silently wrong.

**Reporting**

- Birth and NID registration totals, by zone, by center, over time and by sex.
- District scope and zone, center and date filters.
- Reporting status: which centers reported on which days, and a completion
  report for every zone and center.
- Excel export with summary, cleaned data, per-zone and per-center sheets with
  charts, a trend sheet and a sheet of flagged rows.

**Phases and access**

- Admins create, edit and switch phases in the app.
- Viewers see the dashboard. Admins (PIN in the sidebar) manage phases, data
  sources, column mapping, name corrections and exports.

## Demo

`examples/demo/` holds a fictional phase: 33 centers in 6 zones across 2
districts, and 297 daily responses over 10 days. Every name and figure is made
up. The responses contain the problems the dashboard is built to catch:

| Planted problem                                                                             | Where it shows                          |
| ------------------------------------------------------------------------------------------- | --------------------------------------- |
| 6 corrected resubmissions                                                                   | Data Quality Review: duplicates removed |
| Mistyped center names ("Oakrige", "Eastwod P/S", "Silver Lake", "Brookside Primary School") | Center Assignment, with suggestions     |
| Mistyped zone names ("Greenfeild", "Palmgrove")                                             | Zone Assignment, with suggestions       |
| Missing, negative and fractional counts                                                     | Data Quality Review warnings            |
| Day and month swapped in 2 dates                                                            | Auto-corrected and listed               |
| 2 dates outside the activity window                                                         | Flagged and excluded                    |
| Renamed headers ("Centre Name", "Reporting Date", "Male NID")                               | Matched automatically                   |
| A center that never reported, and one that reports patchily                                 | Reporting Status and completion report  |

Run it locally with the demo settings:

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
streamlit run app.py
```

The admin PIN for the demo is `2468`. Regenerate the data with
`python scripts/generate_demo_data.py`.

## Settings

Set these in `.streamlit/secrets.toml`, in the Secrets box on Streamlit
Community Cloud, or as environment variables. All are optional.

| Setting              | Effect                                                                                                                                 |
| -------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `ADMIN_PIN`          | Fixed admin PIN. It can't be changed in the app.                                                                                       |
| `DEMO_MODE`          | Locks phase and data-source settings. Name corrections and column mappings stay in the visitor's session.                              |
| `MONGODB_URI`        | Save to MongoDB Atlas instead of local files (see Storage). Ignored in `DEMO_MODE`.                                                    |
| `MONGODB_DB`         | Database name (default `nrbc_dashboard`).                                                                                              |
| `REPORTING_TIMEZONE` | IANA time zone for "today" defaults (default `Africa/Blantyre`).                                                                       |
| `[initial_phase]`    | The first phase, created when none exists: `office_name`, `title`, `start_date`, `end_date`, `response_sheet_url`, `master_sheet_url`. |

See `.streamlit/secrets.toml.example`.

## Run it

```bash
pip install -r requirements.txt
streamlit run app.py
```

Then open http://localhost:8501.

1. Log in as admin in the sidebar. The first-run PIN is `1234`. Change it
   straight away with "Change admin PIN".
2. Create a phase: office name, title, start and end dates, the response
   Google Sheet, and the master list.
3. Viewers now see the dashboard for the active phase.

## The response form

The app expects one row per center per day with these fields. Header names
don't have to match exactly:

| Field                          | Meaning                                 |
| ------------------------------ | --------------------------------------- |
| Timestamp                      | Submission time (added by Google Forms) |
| ZONE NAME                      | Zone the center belongs to              |
| CENTER NAME                    | Registration center                     |
| Date                           | Day being reported                      |
| Total Male Births Registered   | Count                                   |
| Total Female Births Registered | Count                                   |
| Total Males Processed          | NID registrations, male                 |
| Total Females Processed        | NID registrations, female               |

Link the response sheet shared as "Anyone with the link can view". The app
reads its CSV export, so no Google credentials are needed. A direct link to a
`.csv` file, or a `.csv` path inside the project folder, also works. An admin
can also upload an `.xlsx` export for their own session.

## The master list

Each phase needs a list of its zones and centers with three columns:
`District`, `Zone` and `Center` (`Centre` also works). Either link it as a
Google Sheet, shared the same way as the response sheet, or upload an Excel
or CSV file. See [`examples/master_list_template.csv`](examples/master_list_template.csv).

## Storage

What admins change is saved in one of two places:

| Saved item                               | Local files (default) | MongoDB (`MONGODB_URI` set)            |
| ---------------------------------------- | --------------------- | -------------------------------------- |
| Admin PIN hash, confirmed column mapping | `config.json`         | `settings` collection, `_id: "config"` |
| Phases, sheet links, name corrections    | `phases.json`         | `settings` collection, `_id: "phases"` |
| Uploaded master lists                    | `masters/`            | `files` collection                     |

Local files suit a host with a persistent disk. They are git-ignored and must
never be committed, because they hold sheet links and the PIN hash.

Hosts such as Streamlit Community Cloud wipe local files on restart, so a live
deployment there should set `MONGODB_URI`:

1. In MongoDB Atlas, create a database user and copy the `mongodb+srv://`
   connection string (Database, Connect, Drivers).
2. Under Network Access, allow the host's IP addresses. Streamlit Community
   Cloud has no fixed IP, so it needs `0.0.0.0/0` with a strong password.
3. Put `MONGODB_URI` in the host's secrets. Phases are then created in the app
   as usual, and survive restarts.

`DEMO_MODE` always uses local files and never connects to a database, even
when `MONGODB_URI` is set. The demo resets on restart and the `[initial_phase]`
setting brings its phase back.

## One codebase, demo and live

Deploy the same repo twice with different settings:

|                   | Public demo                              | Live                                             |
| ----------------- | ---------------------------------------- | ------------------------------------------------ |
| `DEMO_MODE`       | `true`                                   | not set                                          |
| `ADMIN_PIN`       | published demo PIN                       | private PIN, or not set (PIN managed in the app) |
| `[initial_phase]` | fictional sheets or `examples/demo` CSVs | optional                                         |
| `MONGODB_URI`     | not set                                  | set, unless the host keeps local files           |

Real sheet links, PINs and connection strings live only in the live host's
settings, never in the repo.

## Security note

The admin PIN keeps casual viewers from changing the data connection. It is
not real authentication: there are no user accounts or rate limiting. Use
proper authentication or SSO before exposing the app publicly.

## Development

```bash
pip install -e ".[dev]"
pytest
```

Code layout:

- `reporting/domain`: cleaning, column matching and master list rules (pure pandas)
- `reporting/application`: reporting use cases and metrics
- `reporting/infrastructure`: Google Sheets, phase storage, master lists and Excel
- `reporting/presentation`: Streamlit pages and the admin PIN gate

Set `REPORTING_TIMEZONE` (an IANA name, default `Africa/Blantyre`) so the
"today" defaults follow the office's local time.

## Copyright

© 2026 Harry Kanyumbu. All rights reserved.
