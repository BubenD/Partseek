# Partseek — part number search for PDF and CSV files.
# Copyright (C) 2026 ETS - Expand Technology Solutions.
# Licensed under the GNU AGPL-3.0-or-later. See the LICENSE file for details.

"""Entry point for running from source or bundling with PyInstaller."""
import sys

from partseek.app import main

if __name__ == "__main__":
    sys.exit(main())
