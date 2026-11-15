"""Entry point for PyInstaller and for running from source: python run_wav2c64.py"""
import sys

from wav2c64.app import main

if __name__ == "__main__":
    sys.exit(main())
