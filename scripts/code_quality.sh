#!/usr/bin/env bash
set -e

echo "Running Ruff (lint + fix)..."
ruff check --fix syndesi

echo "Running isort..."
isort syndesi

echo "Running Black..."
black syndesi

echo "Running mypy..."
mypy syndesi

echo "Running Bandit..."
bandit -r syndesi