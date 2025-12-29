#!/usr/bin/env python3
"""Simple launcher for pm_live.py - Live terminal interface"""
import sys
import subprocess

if __name__ == "__main__":
    # Launch the live terminal interface by default
    subprocess.run([sys.executable, "pm_live.py"] + sys.argv[1:])
