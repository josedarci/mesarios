"""Initial schema for aggregated TSE mesario data."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "data_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("dataset_id", sa.String(length=255), nullable=False),
        sa.Column("resource_id", sa.String(length=255), nullable=False),
        sa.Column("resource_name", sa.String(length=500), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("collected_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("provider", "resource_id", name="uq_source_resource"),
    )
    op.create_table(
        "import_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("dataset_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("records_processed", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "mesario_aggregates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("data_sources.id"), nullable=False),
        sa.Column("record_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("election_year", sa.Integer(), nullable=True),
        sa.Column("turn", sa.Integer(), nullable=True),
        sa.Column("uf", sa.String(length=2), nullable=True),
        sa.Column("municipality_code", sa.String(length=12), nullable=True),
        sa.Column("municipality", sa.String(length=160), nullable=True),
        sa.Column("electoral_zone", sa.Integer(), nullable=True),
        sa.Column("mesario_type", sa.String(length=255), nullable=True),
        sa.Column("electoral_activity", sa.String(length=255), nullable=True),
        sa.Column("special_function", sa.String(length=255), nullable=True),
        sa.Column("gender", sa.String(length=120), nullable=True),
        sa.Column("marital_status", sa.String(length=120), nullable=True),
        sa.Column("age_range", sa.String(length=120), nullable=True),
        sa.Column("education_level", sa.String(length=255), nullable=True),
        sa.Column("race_color", sa.String(length=120), nullable=True),
        sa.Column("quilombola_status", sa.String(length=120), nullable=True),
        sa.Column("libras_interpreter_status", sa.String(length=120), nullable=True),
        sa.Column("gender_identity", sa.String(length=120), nullable=True),
        sa.Column("volunteer_status", sa.String(length=120), nullable=True),
        sa.Column("attendance_status", sa.String(length=120), nullable=True),
        sa.Column("called_count", sa.Integer(), nullable=True),
        sa.Column("raw_data", mysql.JSON(), nullable=False),
        sa.Column("imported_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_aggregate_location",
        "mesario_aggregates",
        ["uf", "municipality_code", "electoral_zone", "election_year"],
    )
    op.create_index("ix_aggregate_type_status", "mesario_aggregates", ["mesario_type", "attendance_status"])


def downgrade() -> None:
    op.drop_index("ix_aggregate_type_status", table_name="mesario_aggregates")
    op.drop_index("ix_aggregate_location", table_name="mesario_aggregates")
    op.drop_table("mesario_aggregates")
    op.drop_table("import_runs")
    op.drop_table("data_sources")