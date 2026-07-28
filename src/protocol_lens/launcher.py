"""Launch the local Streamlit application."""

from __future__ import annotations

import sys
from pathlib import Path

from streamlit.web import cli as streamlit_cli


def main() -> None:
    app = Path(__file__).with_name("app.py")
    sys.argv = ["streamlit", "run", str(app)]
    raise SystemExit(streamlit_cli.main())


if __name__ == "__main__":
    main()

