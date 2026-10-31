from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AggregateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    election_year: int | None
    turn: int | None
    uf: str | None
    municipality_code: str | None
    municipality: str | None
    electoral_zone: int | None
    mesario_type: str | None
    electoral_activity: str | None
    special_function: str | None
    gender: str | None
    marital_status: str | None
    age_range: str | None
    education_level: str | None
    race_color: str | None
    quilombola_status: str | None
    libras_interpreter_status: str | None
    gender_identity: str | None
    volunteer_status: str | None
    attendance_status: str | None
    called_count: int | None
    raw_data: dict[str, Any]
    source_id: int
    imported_at: datetime


class ImportOut(BaseModel):
    id: int
    dataset_id: str
    status: str
    records_processed: int
    error_message: str | None
    started_at: datetime
    finished_at: datetime | None