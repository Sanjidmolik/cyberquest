#!/usr/bin/env bash
# Render build command. Runs on every deploy.
set -o errexit
set -o pipefail

pip install -r requirements.txt
npm install
python manage.py collectstatic --no-input
# Fails the build on configuration errors; warnings are printed for review.
python manage.py check --deploy
python manage.py migrate --no-input
# Idempotent: keeps the eight defence courses and the Coming Soon shelf in sync.
python manage.py sync_curriculum
# Idempotent: loads the interactive practice scenarios (needs the courses above).
python manage.py load_scenarios
# Idempotent: converts every original practice scenario to the interactive engine.
python manage.py convert_scenarios
