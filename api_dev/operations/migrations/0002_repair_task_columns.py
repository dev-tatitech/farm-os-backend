"""Repair Task columns when a pre-squash schema is still in the database.

After the api_dev migration squash, some environments keep the old
operations_task table while django_migrations already records 0001_initial.
This migration adds any missing v2.1/v2.2 columns without failing if they
already exist.
"""

from django.db import migrations


ALTER_STATEMENTS = [
    "ALTER TABLE operations_task ADD COLUMN IF NOT EXISTS unable_to_complete_at timestamp with time zone NULL;",
    "ALTER TABLE operations_task ADD COLUMN IF NOT EXISTS unable_reason_code varchar(64) NOT NULL DEFAULT '';",
    "ALTER TABLE operations_task ADD COLUMN IF NOT EXISTS unable_notes text NOT NULL DEFAULT '';",
    "ALTER TABLE operations_task ADD COLUMN IF NOT EXISTS completion_payload jsonb NULL;",
    "ALTER TABLE operations_task ADD COLUMN IF NOT EXISTS source_type varchar(32) NOT NULL DEFAULT 'manual';",
    "ALTER TABLE operations_task ADD COLUMN IF NOT EXISTS source_id integer NULL;",
    "ALTER TABLE operations_task ADD COLUMN IF NOT EXISTS occurrence_key varchar(120) NOT NULL DEFAULT '';",
    "ALTER TABLE operations_task ADD COLUMN IF NOT EXISTS result_reference_table varchar(100) NOT NULL DEFAULT '';",
    "ALTER TABLE operations_task ADD COLUMN IF NOT EXISTS result_reference_id integer NULL;",
    "ALTER TABLE operations_task ADD COLUMN IF NOT EXISTS cancel_reason text NOT NULL DEFAULT '';",
    "ALTER TABLE operations_task ADD COLUMN IF NOT EXISTS accepted_at timestamp with time zone NULL;",
    "ALTER TABLE operations_task ADD COLUMN IF NOT EXISTS started_at timestamp with time zone NULL;",
    "ALTER TABLE operations_task ADD COLUMN IF NOT EXISTS completed_at timestamp with time zone NULL;",
    "ALTER TABLE operations_task ADD COLUMN IF NOT EXISTS cancelled_at timestamp with time zone NULL;",
    "CREATE INDEX IF NOT EXISTS operations_task_occurrence_key_idx ON operations_task (occurrence_key);",
]


class Migration(migrations.Migration):

    dependencies = [
        ("operations", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql=ALTER_STATEMENTS,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
