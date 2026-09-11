#!/usr/bin/env python
import os
import sys
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
from django.core.management import execute_from_command_line

if len(sys.argv) == 2 and sys.argv[1] == "test":
    test_root = Path(__file__).resolve().parents[1] / "tests"
    sys.argv.extend((str(test_root / "contracts"), str(test_root / "scenarios")))
execute_from_command_line(sys.argv)
