"""Command-line entry point: `toolkit <command>`."""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path

from . import marks, tracker

FILES = {
    "applications.csv": tracker.APPLICATION_FIELDS,
    "contacts.csv": tracker.CONTACT_FIELDS,
    "courses.csv": marks.COURSE_FIELDS,
    "exemptions.csv": marks.EXEMPTION_FIELDS,
}


def table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "  (none)"
    widths = [max(len(str(x)) for x in col) for col in zip(headers, *rows)]
    line = lambda cells: "  " + "  ".join(str(c).ljust(w) for c, w in zip(cells, widths)).rstrip()
    return "\n".join([line(headers), line(["-" * w for w in widths]), *map(line, rows)])


def fmt_date(d: date | None) -> str:
    return d.isoformat() if d else "-"


def fmt_pct(x: float | None) -> str:
    return "-" if x is None else f"{x:.1f}"


def fmt_need(x: float | None) -> str:
    if x is None:
        return "-"
    if x <= 0:
        return "secured"
    return f"{x:.1f}" if x <= 100 else f"{x:.1f} (out of reach)"


def cmd_init(args) -> None:
    args.data_dir.mkdir(parents=True, exist_ok=True)
    for name, fields in FILES.items():
        path = args.data_dir / name
        if path.exists():
            print(f"kept     {path} (already exists)")
            continue
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(fields)
        print(f"created  {path}")


def cmd_due(args) -> None:
    apps = tracker.load_applications(args.data_dir / "applications.csv")
    print(f"Open now, not applied (as of {args.today}):")
    rows = []
    for a in tracker.open_not_applied(apps, args.today):
        left = (a.close_date - args.today).days if a.close_date else None
        flag = "CLOSING SOON" if left is not None and left <= args.days else ""
        rows.append([a.employer, a.role, fmt_date(a.close_date), "-" if left is None else str(left), flag])
    print(table(["Employer", "Role", "Closes", "Days left", ""], rows))
    print(f"\nOpening in the next {args.days} days:")
    rows = [[a.employer, a.role, fmt_date(a.open_date), fmt_date(a.close_date)]
            for a in tracker.opening_soon(apps, args.today, args.days)]
    print(table(["Employer", "Role", "Opens", "Closes"], rows))


def cmd_merge(args) -> None:
    path = args.data_dir / "applications.csv"
    apps = tracker.load_applications(path)
    result = tracker.merge_scan(apps, tracker.load_applications(args.scan_file))
    print(f"Added ({len(result.added)}):")
    print(table(["Employer", "Role", "Opens", "Closes"],
                [[a.employer, a.role, fmt_date(a.open_date), fmt_date(a.close_date)] for a in result.added]))
    print(f"\nUpdated dates ({len(result.updated)}):")
    print(table(["Employer", "Role", "Change"], [[a.employer, a.role, c] for a, c in result.updated]))
    if result.skipped:
        print(f"\nLeft alone because you've already applied: {len(result.skipped)}")
    if args.dry_run:
        print("\nDry run: applications.csv not changed.")
    elif result.added or result.updated:
        tracker.save_applications(path, apps)
        print(f"\nSaved {path}.")


def cmd_funnel(args) -> None:
    apps = tracker.load_applications(args.data_dir / "applications.csv")
    rows = []
    for s in tracker.funnel(apps):
        rate = "-" if s.pass_rate is None else f"{s.pass_rate:.0%}"
        rows.append([f"{s.stage} -> {s.next_stage}", s.reached, s.passed, s.failed, s.pending, rate])
    print("Pass rate at each stage (pending and withdrawn applications don't count):")
    print(table(["Stage", "Reached", "Passed", "Rejected", "Pending", "Pass rate"], rows))


def cmd_followups(args) -> None:
    apps = tracker.load_applications(args.data_dir / "applications.csv")
    contacts = tracker.load_contacts(args.data_dir / "contacts.csv")
    print(f"Ask for a referral (their program opened in the last {args.opened_within} days):")
    rows = [[c.name, c.employer, fmt_date(c.last_contact)]
            for c in tracker.referral_prompts(contacts, apps, args.today, args.opened_within)]
    print(table(["Name", "Employer", "Last contact"], rows))
    print(f"\nNo contact in {args.stale_days}+ days:")
    rows = [[c.name, c.employer, fmt_date(c.last_contact),
             "-" if c.last_contact is None else str((args.today - c.last_contact).days)]
            for c in tracker.stale_contacts(contacts, args.today, args.stale_days)]
    print(table(["Name", "Employer", "Last contact", "Days"], rows))


def cmd_marks(args) -> None:
    courses = marks.load_courses(args.data_dir / "courses.csv")
    groups = marks.load_exemptions(args.data_dir / "exemptions.csv")
    print(f"Exemptions (target {args.target:g} average, at least {args.minimum:g} in each course):")
    rows = []
    for name, codes in groups.items():
        missing = [c for c in codes if c not in courses]
        if missing:
            sys.exit(f"exemptions.csv: {name} lists {', '.join(missing)}, which isn't in courses.csv")
        t = marks.exemption_target(name, [courses[c] for c in codes], args.target, args.minimum)
        if t.final_average is not None:
            detail = f"final average {t.final_average:.1f}"
        elif t.needed is not None:
            detail = f"need {t.needed:.1f} average on what's left"
        else:
            detail = f"a finished course is below {args.minimum:g}"
        rows.append([name, ", ".join(codes), t.status, detail])
    print(table(["Exemption", "Courses", "Status", "Detail"], rows))
    print("\nCourses:")
    rows = [[c.code, f"{c.done_weight:g}%", fmt_pct(c.average_so_far),
             fmt_need(c.needed_for(args.target)), fmt_need(c.needed_for(args.minimum))]
            for c in courses.values()]
    print(table(["Course", "Marked", "Average so far", f"Need for {args.target:g}",
                 f"Need for {args.minimum:g}"], rows))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="toolkit", description="Grad job-search toolkit.")
    parser.add_argument("--data-dir", type=Path, default=Path("data"),
                        help="folder holding your CSV files (default: data)")
    parser.add_argument("--today", type=date.fromisoformat, default=date.today(),
                        help="pretend today is this date, YYYY-MM-DD")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="create empty CSV files in the data folder").set_defaults(func=cmd_init)

    p = sub.add_parser("due", help="programs open now and opening soon")
    p.add_argument("--days", type=int, default=14, help="look-ahead window in days (default: 14)")
    p.set_defaults(func=cmd_due)

    p = sub.add_parser("merge", help="add programs from a scan file to applications.csv")
    p.add_argument("scan_file", type=Path, help="CSV with employer, role, route, open_date, close_date, notes")
    p.add_argument("--dry-run", action="store_true", help="show what would change without saving")
    p.set_defaults(func=cmd_merge)

    sub.add_parser("funnel", help="pass rate at each stage").set_defaults(func=cmd_funnel)

    p = sub.add_parser("followups", help="who to contact this week")
    p.add_argument("--stale-days", type=int, default=21, help="flag contacts after this many days (default: 21)")
    p.add_argument("--opened-within", type=int, default=7,
                   help="prompt a referral ask if their program opened this recently (default: 7)")
    p.set_defaults(func=cmd_followups)

    p = sub.add_parser("marks", help="marks needed for each exemption")
    p.add_argument("--target", type=float, default=65, help="average needed for the exemption (default: 65)")
    p.add_argument("--minimum", type=float, default=55, help="minimum in each course (default: 55)")
    p.set_defaults(func=cmd_marks)

    args = parser.parse_args(argv)
    try:
        args.func(args)
    except FileNotFoundError as e:
        sys.exit(f"{e.filename} not found. Run `toolkit init` first, or pass --data-dir sample_data.")
    except ValueError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
