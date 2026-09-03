"""Allows `python -m his_emr_simulator` to work."""
import sys
from .runner import main

sys.exit(main())
