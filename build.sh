#!/usr/bin/env bash
set -o errexit

npm install
python manage.py collectstatic --no-input
python manage.py migrate

