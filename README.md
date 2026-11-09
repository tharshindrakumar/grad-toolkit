# grad-toolkit

A small command-line tool I built to run my 2027 graduate job search and protect my actuarial exemption marks.

Grad applications for actuarial and pricing roles open and close on different dates across 50+ employers, and exemptions depend on hitting a 65 average. This tool answers four questions from a few CSV files:

| Command | Question it answers |
| --- | --- |
| `toolkit due` | Which programs are open that I haven't applied to, and which open in the next two weeks? |
| `toolkit funnel` | At which stage am I losing applications: screening, tests, video interview or final round? |
| `toolkit followups` | Who should I contact this week, and whose firm just opened its program so I can ask for a referral? |
| `toolkit marks` | What average do I need on my remaining assessments to get each exemption? |
| `toolkit merge scan.csv` | Add newly found programs to my tracker and update their dates, without touching anything I've applied to |

No dependencies beyond Python 3.9+.

## Quick start

```bash
pip install -e .
toolkit --data-dir sample_data --today 2027-03-10 marks
```

```
Exemptions (target 65 average, at least 55 in each course):
  Exemption                Courses                     Status    Detail
  -----------------------  --------------------------  --------  --------------------------------
  Actuarial Control Cycle  ACTL4001, ACTL4002          possible  need 61.9 average on what's left
  Data Science Principles  ACTL4305                    possible  need 62.0 average on what's left
  CS2 (example mapping)    CS2_COURSE_A, CS2_COURSE_B  possible  need 70.8 average on what's left
```

To use it for real, create your own data folder. It's git-ignored, so your applications, contacts and marks never reach GitHub:

```bash
toolkit init        # creates data/ with empty CSVs
toolkit due
```

## Data files

| File | Columns |
| --- | --- |
| `applications.csv` | employer, role, route, stage, outcome, open_date, close_date, applied_date, notes |
| `contacts.csv` | name, employer, role, last_contact, referral_asked, notes |
| `courses.csv` | course, assessment, weight, mark (leave mark blank until it's released) |
| `exemptions.csv` | exemption, course (one row per course the exemption averages over) |

- **stage:** `not_applied`, `applied`, `tests`, `video_interview`, `final` or `offer`, meaning the furthest stage reached
- **outcome:** `pending`, `rejected`, `offer` or `withdrawn`
- **Dates:** `YYYY-MM-DD`
- **Weights** for each course must add up to 100

## Feeding in a weekly scan

A scheduled job searches employers' career pages each week and writes what it finds to a scan file with the columns `employer, role, route, open_date, close_date, notes`. Then:

```bash
toolkit merge data/scan.csv --dry-run   # preview
toolkit merge data/scan.csv
```

- **New** employer and role pairs are added as `not_applied`.
- **Programs you haven't applied to** get their open and close dates updated.
- **Anything you've applied to** is never changed.
- Employer and role are matched ignoring case, so use the same names the tracker already uses. Running the same scan twice changes nothing.

## How the numbers work

**Funnel.** The pass rate at a stage counts only applications that were decided there. Pending applications haven't passed or failed yet, and withdrawals say nothing about your chances, so neither is counted.

**Exemption targets.** An exemption is averaged over its courses, with each course weighted equally, and needs at least the minimum in every course. The tool finds the single average you'd need on every assessment you haven't sat, across all the courses in the group. Defaults are a 65 average with 55 in each course. Change them with `--target` and `--minimum`.

The sample `exemptions.csv` maps the Actuarial Control Cycle to ACTL4001 and ACTL4002, and Data Science Principles to ACTL4305. The CS2 mapping is a placeholder. Confirm the current course mapping and thresholds for your cohort with UNSW's School of Risk and Actuarial Studies before relying on them.

## Tests

```bash
pip install -e ".[dev]"
pytest
```
