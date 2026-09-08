"""Repair health schema drift after the api_dev migration squash.

Old databases still have pre-v2 health tables while django_migrations already
records health.0001_initial. Create HealthCase / HealthObservation if missing
and add TreatmentRecord.case_id (and related defensive columns).
"""

from django.db import migrations


SQL = [
    """
    CREATE TABLE IF NOT EXISTS health_healthcase (
        id bigserial NOT NULL PRIMARY KEY,
        title varchar(255) NOT NULL,
        notes text NOT NULL DEFAULT '',
        status varchar(16) NOT NULL DEFAULT 'open',
        opened_at timestamp with time zone NOT NULL DEFAULT NOW(),
        closed_at timestamp with time zone NULL,
        animal_id bigint NULL,
        closed_by_id uuid NULL,
        farm_id bigint NOT NULL,
        group_id bigint NULL,
        opened_by_id uuid NULL
    );
    """,
    "CREATE INDEX IF NOT EXISTS health_healthcase_animal_id_idx ON health_healthcase (animal_id);",
    "CREATE INDEX IF NOT EXISTS health_healthcase_closed_by_id_idx ON health_healthcase (closed_by_id);",
    "CREATE INDEX IF NOT EXISTS health_healthcase_farm_id_idx ON health_healthcase (farm_id);",
    "CREATE INDEX IF NOT EXISTS health_healthcase_group_id_idx ON health_healthcase (group_id);",
    "CREATE INDEX IF NOT EXISTS health_healthcase_opened_by_id_idx ON health_healthcase (opened_by_id);",
    """
    CREATE TABLE IF NOT EXISTS health_healthobservation (
        id bigserial NOT NULL PRIMARY KEY,
        observed_at timestamp with time zone NOT NULL,
        symptoms text NOT NULL,
        severity varchar(20) NOT NULL DEFAULT 'mild',
        created_at timestamp with time zone NOT NULL DEFAULT NOW(),
        animal_id bigint NULL,
        case_id bigint NULL,
        created_by_id uuid NULL,
        farm_id bigint NOT NULL,
        group_id bigint NULL
    );
    """,
    "CREATE INDEX IF NOT EXISTS health_healthobservation_animal_id_idx ON health_healthobservation (animal_id);",
    "CREATE INDEX IF NOT EXISTS health_healthobservation_case_id_idx ON health_healthobservation (case_id);",
    "CREATE INDEX IF NOT EXISTS health_healthobservation_created_by_id_idx ON health_healthobservation (created_by_id);",
    "CREATE INDEX IF NOT EXISTS health_healthobservation_farm_id_idx ON health_healthobservation (farm_id);",
    "CREATE INDEX IF NOT EXISTS health_healthobservation_group_id_idx ON health_healthobservation (group_id);",
    "ALTER TABLE health_treatmentrecord ADD COLUMN IF NOT EXISTS case_id bigint NULL;",
    "CREATE INDEX IF NOT EXISTS health_treatmentrecord_case_id_idx ON health_treatmentrecord (case_id);",
    "ALTER TABLE health_treatmentrecord ADD COLUMN IF NOT EXISTS drug_id bigint NULL;",
    "ALTER TABLE health_treatmentrecord ADD COLUMN IF NOT EXISTS drug_batch_id bigint NULL;",
    "ALTER TABLE health_treatmentrecord ADD COLUMN IF NOT EXISTS quantity_administered numeric(12,2) NULL;",
    "ALTER TABLE health_treatmentrecord ADD COLUMN IF NOT EXISTS dose varchar(100) NULL;",
    "ALTER TABLE health_treatmentrecord ADD COLUMN IF NOT EXISTS frequency varchar(100) NULL;",
    "ALTER TABLE health_treatmentrecord ADD COLUMN IF NOT EXISTS duration_days integer NULL;",
    "ALTER TABLE health_treatmentrecord ADD COLUMN IF NOT EXISTS administration_route varchar(20) NULL;",
    "ALTER TABLE health_treatmentrecord ADD COLUMN IF NOT EXISTS administered_by_id uuid NULL;",
    "ALTER TABLE health_treatmentrecord ADD COLUMN IF NOT EXISTS prescribed_by_id uuid NULL;",
    "ALTER TABLE health_treatmentrecord ADD COLUMN IF NOT EXISTS next_dose_date date NULL;",
    "ALTER TABLE health_treatmentrecord ADD COLUMN IF NOT EXISTS withdrawal_end_date date NULL;",
    "ALTER TABLE health_treatmentrecord ADD COLUMN IF NOT EXISTS treatment_cost numeric(14,2) NULL;",
    "ALTER TABLE health_treatmentrecord ADD COLUMN IF NOT EXISTS is_external_administration boolean NOT NULL DEFAULT false;",
    "ALTER TABLE health_treatmentrecord ADD COLUMN IF NOT EXISTS external_drug_name varchar(200) NULL;",
    "ALTER TABLE health_treatmentrecord ADD COLUMN IF NOT EXISTS external_unit varchar(50) NULL;",
    "ALTER TABLE health_treatmentrecord ADD COLUMN IF NOT EXISTS external_unit_cost numeric(14,2) NULL;",
    "ALTER TABLE health_treatmentrecord ADD COLUMN IF NOT EXISTS external_source varchar(200) NULL;",
    "ALTER TABLE health_treatmentrecord ADD COLUMN IF NOT EXISTS external_reason text NULL;",
    "ALTER TABLE health_treatmentrecord ADD COLUMN IF NOT EXISTS reconciled_to_batch_id bigint NULL;",
    "ALTER TABLE health_mortalityrecord ADD COLUMN IF NOT EXISTS status varchar(20) NOT NULL DEFAULT 'recorded';",
    "ALTER TABLE health_healthalert ADD COLUMN IF NOT EXISTS drug_batch_id bigint NULL;",
]


class Migration(migrations.Migration):

    dependencies = [
        ("health", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql=SQL,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
