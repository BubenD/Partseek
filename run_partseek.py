"""Entry point for running from source or bundling with PyInstaller."""
import sys

from partseek.app import main

if __name__ == "__main__":
    sys.exit(main())
