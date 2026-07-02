#!/usr/bin/env python3
"""
Package entrypoint.

Run from the `basic-xapp` directory with:

    python3 -m gui_client_student

Module execution concept:

    Python looks for `gui_client_student/__main__.py` when the package is run
    with `-m`.
"""

from .client import main


if __name__ == "__main__":
    main()
