"""
Shared cache table for rate limits and verification-code attempt counters.

Django's database cache is not a model, so createcachetable is the schema.
This migration runs that same creation during migrate, including on the test
database. LocMemCache cannot be shared by Gunicorn workers.
"""

from django.db import migrations


def create_shared_cache(apps, schema_editor):
    from django.core.management.commands.createcachetable import Command

    connection = schema_editor.connection
    command = Command()
    command.verbosity = 0
    command.create_table(connection.alias, "cyberquest_cache", dry_run=False)


def drop_shared_cache(apps, schema_editor):
    schema_editor.execute("DROP TABLE IF EXISTS cyberquest_cache")


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0010_email_verified_and_course_thumbnail"),
    ]

    operations = [
        migrations.RunPython(create_shared_cache, drop_shared_cache),
    ]
