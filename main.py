"""Walled DLP - entry point.

Run:  python main.py
"""

import logging
import sys


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    # Imported late so a missing dependency gives a clear message.
    try:
        from app.desktop import run
    except ImportError as exc:
        print(f"Missing dependency: {exc}\nInstall with: pip install -r requirements.txt")
        return 1
    return run()


if __name__ == "__main__":
    sys.exit(main())
