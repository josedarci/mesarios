"""Store TSE election results by electoral section."""

from alembic import op
import sqlalchemy as sa


revision = "0003_section_votes"
down_revision = "0002_polling_locations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "elections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("election_year", sa.Integer(), nullable=False),
        sa.Column("election_code", sa.String(length=32), nullable=False),
        sa.Column("election_type", sa.String(length=80), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("election_date", sa.String(length=20), nullable=True),
        sa.UniqueConstraint("election_year", "election_code", name="uq_election_year_code"),
    )
    op.create_table(
        "section_votes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("record_key", sa.String(length=64), nullable=False),
        sa.Column("election_id", sa.Integer(), nullable=False),
        sa.Column("import_id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("election_year", sa.Integer(), nullable=False),
        sa.Column("turn", sa.Integer(), nullable=False),
        sa.Column("uf", sa.String(length=2), nullable=False),
        sa.Column("municipality_code", sa.String(length=12), nullable=False),
        sa.Column("municipality", sa.String(length=160), nullable=True),
        sa.Column("electoral_zone", sa.Integer(), nullable=False),
        sa.Column("section_number", sa.String(length=12), nullable=False),
        sa.Column("polling_place_number", sa.String(length=12), nullable=True),
        sa.Column("office_code", sa.String(length=12), nullable=False),
        sa.Column("office_name", sa.String(length=120), nullable=False),
        sa.Column("vote_code", sa.String(length=32), nullable=False),
        sa.Column("vote_name", sa.String(length=255), nullable=False),
        sa.Column("vote_type", sa.String(length=32), nullable=False),
        sa.Column("candidate_registration_number", sa.String(length=32), nullable=True),
        sa.Column("party_number", sa.String(length=12), nullable=True),
        sa.Column("party_abbreviation", sa.String(length=20), nullable=True),
        sa.Column("party_name", sa.String(length=160), nullable=True),
        sa.Column("votes", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["election_id"], ["elections.id"]),
        sa.ForeignKeyConstraint(["import_id"], ["import_runs.id"]),
        sa.ForeignKeyConstraint(["source_id"], ["data_sources.id"]),
        sa.UniqueConstraint("import_id", "record_key", name="uq_section_vote_import_record"),
    )
    op.create_index(
        "ix_section_vote_section",
        "section_votes",
        [
            "election_year",
            "turn",
            "uf",
            "municipality_code",
            "electoral_zone",
            "section_number",
            "office_code",
        ],
    )
    op.create_index(
        "ix_section_vote_candidate",
        "section_votes",
        ["election_year", "office_code", "vote_code"],
    )
    op.create_index("ix_section_vote_import", "section_votes", ["import_id"])


def downgrade() -> None:
    op.drop_index("ix_section_vote_import", table_name="section_votes")
    op.drop_index("ix_section_vote_candidate", table_name="section_votes")
    op.drop_index("ix_section_vote_section", table_name="section_votes")
    op.drop_table("section_votes")
    op.drop_table("elections")
