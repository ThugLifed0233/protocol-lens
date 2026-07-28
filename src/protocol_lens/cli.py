"""Command-line entry point for Protocol Lens."""

from __future__ import annotations

import argparse
from pathlib import Path

from . import __version__
from .apple_health import iter_export
from .database import connect, ingest_records
from .report import generate_report
from .sample import build_sample_database

DEFAULT_DB = Path("data/processed/protocol-lens.duckdb")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="protocol-lens",
        description="Personal Apple Health trends, workouts, and correlations.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)

    importer = commands.add_parser("import", help="Import an Apple Health ZIP or export.xml")
    importer.add_argument("source", type=Path)
    importer.add_argument("--db", type=Path, default=DEFAULT_DB)

    report = commands.add_parser("report", help="Generate a local interactive HTML report")
    report.add_argument("--db", type=Path, default=DEFAULT_DB)
    report.add_argument("--out", type=Path, default=Path("reports/apple-health.html"))

    sample = commands.add_parser("sample", help="Generate and report on synthetic demo data")
    sample.add_argument("--db", type=Path, default=Path("data/processed/sample.duckdb"))
    sample.add_argument("--out", type=Path, default=Path("reports/sample.html"))
    commands.add_parser("app", help="Open the local Protocol Lens web app")
    snapshot = commands.add_parser(
        "snapshot",
        help="Write a reviewed summary snapshot",
    )
    snapshot.add_argument("--db", type=Path, default=DEFAULT_DB)
    snapshot.add_argument(
        "--out",
        type=Path,
        default=Path("public-results/results.json"),
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "import":
        if not args.source.exists():
            raise SystemExit(f"Source not found: {args.source}")
        connection = connect(args.db)
        try:
            seen, inserted = ingest_records(
                connection,
                iter_export(args.source),
                args.source,
                __version__,
            )
        finally:
            connection.close()
        if inserted == 0:
            print(f"Already imported: {seen:,} supported records")
        else:
            print(f"Imported {inserted:,} supported records into {args.db}")
    elif args.command == "report":
        connection = connect(args.db)
        try:
            generate_report(connection, args.out)
        finally:
            connection.close()
        print(f"Report ready: {args.out}")
    elif args.command == "sample":
        build_sample_database(args.db)
        connection = connect(args.db)
        try:
            generate_report(connection, args.out)
        finally:
            connection.close()
        print(f"Synthetic sample ready: {args.out}")
    elif args.command == "app":
        from .launcher import main as launch_app

        launch_app()
    else:
        from .experiments import public_snapshot_json

        connection = connect(args.db)
        try:
            content = public_snapshot_json(connection)
        finally:
            connection.close()
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(content)
        print(f"Summary snapshot ready for review: {args.out}")


if __name__ == "__main__":
    main()
