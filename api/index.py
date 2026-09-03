import os
import sys

# Ensure root project directory is in python path
basedir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
if basedir not in sys.path:
    sys.path.insert(0, basedir)

from app import create_app

app = create_app("production")
