"""Add geolocated TSE polling locations and sections."""

from alembic import op
import sqlalchemy as sa

revision = "0002_polling_locations"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "polling_locations",
        sa.Column("location_key", sa.String(length=64), primary_key=True),
        sa.Column("import_id", sa.Integer(), nullable=False),
        sa.Column("election_year", sa.Integer(), nullable=False),
        sa.Column("uf", sa.String(length=2), nullable=False),
        sa.Column("municipality_code", sa.String(length=12), nullable=False),
        sa.Column("municipality", sa.String(length=160), nullable=False),
        sa.Column("electoral_zone", sa.Integer(), nullable=False),
        sa.Column("polling_place_number", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("address", sa.String(length=500), nullable=False),
        sa.Column("neighborhood", sa.String(length=200), nullable=True),
        sa.Column("postal_code", sa.String(length=12), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("situation", sa.String(length=80), nullable=True),
        sa.ForeignKeyConstraint(["import_id"], ["import_runs.id"]),
    )
    op.create_index(
        "ix_polling_location_filters",
        "polling_locations",
        ["election_year", "uf", "municipality_code", "electoral_zone"],
    )
    op.create_index("ix_polling_location_import", "polling_locations", ["import_id"])
    op.create_table(
        "polling_sections",
        sa.Column("section_key", sa.String(length=64), nullable=False),
        sa.Column("import_id", sa.Integer(), nullable=False),
        sa.Column("location_key", sa.String(length=64), nullable=False),
        sa.Column("section_number", sa.String(length=12), nullable=False),
        sa.Column("election_year", sa.Integer(), nullable=False),
        sa.Column("uf", sa.String(length=2), nullable=False),
        sa.Column("municipality_code", sa.String(length=12), nullable=False),
        sa.Column("municipality", sa.String(length=160), nullable=False),
        sa.Column("electoral_zone", sa.Integer(), nullable=False),
        sa.Column("polling_place_number", sa.Integer(), nullable=False),
        sa.Column("polling_place_name", sa.String(length=500), nullable=False),
        sa.Column("address", sa.String(length=500), nullable=False),
        sa.Column("neighborhood", sa.String(length=200), nullable=True),
        sa.Column("postal_code", sa.String(length=12), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("situation", sa.String(length=80), nullable=True),
        sa.ForeignKeyConstraint(
            ["location_key"], ["polling_locations.location_key"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["import_id"], ["import_runs.id"]),
        sa.PrimaryKeyConstraint("section_key"),
    )
    op.create_index("ix_polling_section_location", "polling_sections", ["location_key"])
    op.create_index("ix_polling_section_import", "polling_sections", ["import_id"])


def downgrade() -> None:
    op.drop_index("ix_polling_section_import", table_name="polling_sections")
    op.drop_index("ix_polling_section_location", table_name="polling_sections")
    op.drop_table("polling_sections")
    op.drop_index("ix_polling_location_import", table_name="polling_locations")
    op.drop_index("ix_polling_location_filters", table_name="polling_locations")
    op.drop_table("polling_locations")
