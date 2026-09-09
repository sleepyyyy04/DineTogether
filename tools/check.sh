#!/usr/bin/env bash

set -e

echo "==> Running pytest"
python3 -m pytest -v

echo "==> Running Flake8"
flake8 .

echo "==> Running Bandit"
bandit -r . -x ./tests,./.venv,./venv

echo "==> Running Semgrep"
semgrep scan --config auto .

echo "==> All checks passed"
