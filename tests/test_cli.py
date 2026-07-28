from pathlib import Path

from protocol_lens.cli import build_parser


def test_catalog_command_has_public_results_default() -> None:
    args = build_parser().parse_args(["catalog"])

    assert args.command == "catalog"
    assert args.out == Path("public-results/supplements.json")
