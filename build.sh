#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt
npm install
python manage.py collectstatic --no-input
python manage.py migrate
