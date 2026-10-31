from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DataSource(Base):
    __tablename__ = "data_sources"
    __table_args__ = (UniqueConstraint("provider", "resource_id", name="uq_source_resource"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(40), default="TSE", nullable=False)
    dataset_id: Mapped[str] = mapped_column(String(255), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(255), nullable=False)
    resource_name: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    aggregates: Mapped[list["MesarioAggregate"]] = relationship(back_populates="source")


class ImportRun(Base):
    __tablename__ = "import_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(40), default="TSE", nullable=False)
    dataset_id: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="RUNNING", nullable=False)
    records_processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


class MesarioAggregate(Base):
    __tablename__ = "mesario_aggregates"
    __table_args__ = (
        Index("ix_aggregate_location", "uf", "municipality_code", "electoral_zone", "election_year"),
        Index("ix_aggregate_type_status", "mesario_type", "attendance_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"), nullable=False)
    record_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    election_year: Mapped[int | None] = mapped_column(Integer)
    turn: Mapped[int | None] = mapped_column(Integer)
    uf: Mapped[str | None] = mapped_column(String(2))
    municipality_code: Mapped[str | None] = mapped_column(String(12))
    municipality: Mapped[str | None] = mapped_column(String(160))
    electoral_zone: Mapped[int | None] = mapped_column(Integer)
    mesario_type: Mapped[str | None] = mapped_column(String(255))
    electoral_activity: Mapped[str | None] = mapped_column(String(255))
    special_function: Mapped[str | None] = mapped_column(String(255))
    gender: Mapped[str | None] = mapped_column(String(120))
    marital_status: Mapped[str | None] = mapped_column(String(120))
    age_range: Mapped[str | None] = mapped_column(String(120))
    education_level: Mapped[str | None] = mapped_column(String(255))
    race_color: Mapped[str | None] = mapped_column(String(120))
    quilombola_status: Mapped[str | None] = mapped_column(String(120))
    libras_interpreter_status: Mapped[str | None] = mapped_column(String(120))
    gender_identity: Mapped[str | None] = mapped_column(String(120))
    volunteer_status: Mapped[str | None] = mapped_column(String(120))
    attendance_status: Mapped[str | None] = mapped_column(String(120))
    called_count: Mapped[int | None] = mapped_column(Integer)
    raw_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    source: Mapped[DataSource] = relationship(back_populates="aggregates")


class PollingLocation(Base):
    __tablename__ = "polling_locations"
    __table_args__ = (
        Index(
            "ix_polling_location_filters",
            "election_year",
            "uf",
            "municipality_code",
            "electoral_zone",
        ),
        Index("ix_polling_location_import", "import_id"),
    )

    location_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("import_runs.id"), nullable=False)
    election_year: Mapped[int] = mapped_column(Integer, nullable=False)
    uf: Mapped[str] = mapped_column(String(2), nullable=False)
    municipality_code: Mapped[str] = mapped_column(String(12), nullable=False)
    municipality: Mapped[str] = mapped_column(String(160), nullable=False)
    electoral_zone: Mapped[int] = mapped_column(Integer, nullable=False)
    polling_place_number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    address: Mapped[str] = mapped_column(String(500), nullable=False)
    neighborhood: Mapped[str | None] = mapped_column(String(200))
    postal_code: Mapped[str | None] = mapped_column(String(12))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    situation: Mapped[str | None] = mapped_column(String(80))


class PollingSection(Base):
    __tablename__ = "polling_sections"
    __table_args__ = (
        Index("ix_polling_section_location", "location_key"),
        Index("ix_polling_section_import", "import_id"),
    )

    section_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("import_runs.id"), nullable=False)
    location_key: Mapped[str] = mapped_column(
        ForeignKey("polling_locations.location_key", ondelete="CASCADE"),
        nullable=False,
    )
    section_number: Mapped[str] = mapped_column(String(12), nullable=False)
    election_year: Mapped[int] = mapped_column(Integer, nullable=False)
    uf: Mapped[str] = mapped_column(String(2), nullable=False)
    municipality_code: Mapped[str] = mapped_column(String(12), nullable=False)
    municipality: Mapped[str] = mapped_column(String(160), nullable=False)
    electoral_zone: Mapped[int] = mapped_column(Integer, nullable=False)
    polling_place_number: Mapped[int] = mapped_column(Integer, nullable=False)
    polling_place_name: Mapped[str] = mapped_column(String(500), nullable=False)
    address: Mapped[str] = mapped_column(String(500), nullable=False)
    neighborhood: Mapped[str | None] = mapped_column(String(200))
    postal_code: Mapped[str | None] = mapped_column(String(12))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    situation: Mapped[str | None] = mapped_column(String(80))


class Election(Base):
    __tablename__ = "elections"
    __table_args__ = (
        UniqueConstraint("election_year", "election_code", name="uq_election_year_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    election_year: Mapped[int] = mapped_column(Integer, nullable=False)
    election_code: Mapped[str] = mapped_column(String(32), nullable=False)
    election_type: Mapped[str | None] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    election_date: Mapped[str | None] = mapped_column(String(20))


class SectionVote(Base):
    __tablename__ = "section_votes"
    __table_args__ = (
        UniqueConstraint("import_id", "record_key", name="uq_section_vote_import_record"),
        Index(
            "ix_section_vote_section",
            "election_year",
            "turn",
            "uf",
            "municipality_code",
            "electoral_zone",
            "section_number",
            "office_code",
        ),
        Index(
            "ix_section_vote_candidate",
            "election_year",
            "office_code",
            "vote_code",
        ),
        Index("ix_section_vote_import", "import_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    record_key: Mapped[str] = mapped_column(String(64), nullable=False)
    election_id: Mapped[int] = mapped_column(ForeignKey("elections.id"), nullable=False)
    import_id: Mapped[int] = mapped_column(ForeignKey("import_runs.id"), nullable=False)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"), nullable=False)
    election_year: Mapped[int] = mapped_column(Integer, nullable=False)
    turn: Mapped[int] = mapped_column(Integer, nullable=False)
    uf: Mapped[str] = mapped_column(String(2), nullable=False)
    municipality_code: Mapped[str] = mapped_column(String(12), nullable=False)
    municipality: Mapped[str | None] = mapped_column(String(160))
    electoral_zone: Mapped[int] = mapped_column(Integer, nullable=False)
    section_number: Mapped[str] = mapped_column(String(12), nullable=False)
    polling_place_number: Mapped[str | None] = mapped_column(String(12))
    office_code: Mapped[str] = mapped_column(String(12), nullable=False)
    office_name: Mapped[str] = mapped_column(String(120), nullable=False)
    vote_code: Mapped[str] = mapped_column(String(32), nullable=False)
    vote_name: Mapped[str] = mapped_column(String(255), nullable=False)
    vote_type: Mapped[str] = mapped_column(String(32), nullable=False)
    candidate_registration_number: Mapped[str | None] = mapped_column(String(32))
    party_number: Mapped[str | None] = mapped_column(String(12))
    party_abbreviation: Mapped[str | None] = mapped_column(String(20))
    party_name: Mapped[str | None] = mapped_column(String(160))
    votes: Mapped[int] = mapped_column(BigInteger, nullable=False)