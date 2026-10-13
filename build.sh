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
