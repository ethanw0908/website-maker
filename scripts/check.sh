#!/usr/bin/env sh
set -eu
python -m compileall app tests
pytest -q
