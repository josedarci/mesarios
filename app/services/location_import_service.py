import hashlib
import logging
import unicodedata
from datetime import datetime
from typing import Any

from sqlalchemy import delete, or_, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import ImportRun, PollingLocation, PollingSection
from app.services.tse_client import TSEClient


logger = logging.getLogger(__name__)
IMPORT_BATCH_SIZE = 500


def _normalized_resource_name(value: Any) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value).strip().lower())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _value(row: dict[str, Any], name: str) -> str | None:
    value = row.get(name)
    if value is None:
        return None
    result = str(value).strip()
    return result or None


def _integer(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _coordinate(value: str | None, minimum: float, maximum: float) -> float | None:
    if value is None:
        return None
    try:
        coordinate = float(value.replace(",", "."))
    except ValueError:
        return None
    if not minimum <= coordinate <= maximum:
        return None
    return coordinate


def _normalized_location(
    row: dict[str, Any],
    election_year: int,
    import_id: int,
) -> tuple[dict, dict] | None:
    uf = _value(row, "SG_UF")
    municipality_code = _value(row, "CD_MUNICIPIO")
    municipality = _value(row, "NM_MUNICIPIO")
    zone = _integer(_value(row, "NR_ZONA"))
    place_number = _integer(_value(row, "NR_LOCAL_VOTACAO"))
    section_number = _value(row, "NR_SECAO")
    name = _value(row, "NM_LOCAL_VOTACAO")
    address = _value(row, "DS_ENDERECO")
    if not all((uf, municipality_code, zone, place_number, section_number)):
        return None
    if zone < 1 or place_number < 1:
        return None
    municipality = municipality or "Não informado"
    name = name or "Local de votação não informado"
    address = address or "Endereço não informado"

    identity = "|".join(
        (str(election_year), uf.upper(), municipality_code, str(zone), str(place_number))
    )
    location_key = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    section_identity = "|".join(
        (str(election_year), uf.upper(), municipality_code, str(zone), section_number)
    )
    section_key = hashlib.sha256(section_identity.encode("utf-8")).hexdigest()
    location = {
        "location_key": location_key,
        "import_id": import_id,
        "election_year": election_year,
        "uf": uf.upper(),
        "municipality_code": municipality_code,
        "municipality": municipality,
        "electoral_zone": zone,
        "polling_place_number": place_number,
        "name": name,
        "address": address,
        "neighborhood": _value(row, "NM_BAIRRO"),
        "postal_code": _value(row, "NR_CEP"),
        "latitude": _coordinate(_value(row, "NR_LATITUDE"), -35.0, 6.0),
        "longitude": _coordinate(_value(row, "NR_LONGITUDE"), -75.0, -30.0),
        "situation": _value(row, "DS_SITU_LOCAL_VOTACAO"),
    }
    section = {
        "section_key": section_key,
        "import_id": import_id,
        "location_key": location_key,
        "section_number": section_number,
        "election_year": election_year,
        "uf": uf.upper(),
        "municipality_code": municipality_code,
        "municipality": municipality,
        "electoral_zone": zone,
        "polling_place_number": place_number,
        "polling_place_name": name,
        "address": address,
        "neighborhood": _value(row, "NM_BAIRRO"),
        "postal_code": _value(row, "NR_CEP"),
        "latitude": location["latitude"],
        "longitude": location["longitude"],
        "situation": _value(row, "DS_SITU_LOCAL_VOTACAO"),
    }
    return location, section


def _upsert_locations(database: Session, records: list[dict]) -> None:
    if not records:
        return
    statement = _insert_statement(database, PollingLocation, records)
    update_columns = [
        "municipality",
        "name",
        "address",
        "neighborhood",
        "postal_code",
        "latitude",
        "longitude",
        "situation",
        "import_id",
    ]
    database.execute(_upsert(database, statement, update_columns))


def _upsert_sections(database: Session, records: list[dict]) -> None:
    if not records:
        return
    statement = _insert_statement(database, PollingSection, records)
    database.execute(
        _upsert(
            database,
            statement,
            [
                "location_key",
                "import_id",
                "section_number",
                "election_year",
                "uf",
                "municipality_code",
                "municipality",
                "electoral_zone",
                "polling_place_number",
                "polling_place_name",
                "address",
                "neighborhood",
                "postal_code",
                "latitude",
                "longitude",
                "situation",
            ],
        )
    )


def _insert_statement(
    database: Session,
    model: type[PollingLocation] | type[PollingSection],
    records: list[dict],
):
    dialect = database.get_bind().dialect.name
    if dialect == "mysql":
        return mysql_insert(model).values(records)
    if dialect == "sqlite":
        return sqlite_insert(model).values(records)
    raise RuntimeError(f"Banco de dados não suportado para importação do mapa: {dialect}.")


def _upsert(database: Session, statement, update_columns: list[str]):
    dialect = database.get_bind().dialect.name
    if dialect == "mysql":
        return statement.on_duplicate_key_update(
            **{name: getattr(statement.inserted, name) for name in update_columns}
        )
    if dialect == "sqlite":
        return statement.on_conflict_do_update(
            index_elements=list(statement.table.primary_key.columns),
            set_={name: getattr(statement.excluded, name) for name in update_columns},
        )
    raise RuntimeError(f"Banco de dados não suportado para importação do mapa: {dialect}.")


def _flush_batches(
    database: Session,
    location_batch: dict[str, dict],
    section_batch: dict[str, dict],
) -> None:
    _upsert_locations(database, list(location_batch.values()))
    _upsert_sections(database, list(section_batch.values()))
    database.commit()
    location_batch.clear()
    section_batch.clear()


def import_tse_polling_locations(
    run_id: int,
    ckan_url: str,
    dataset_id: str,
    election_year: int,
) -> None:
    database = SessionLocal()
    try:
        run = database.get(ImportRun, run_id)
        if run is None:
            raise RuntimeError(f"Execução de importação {run_id} não encontrada.")
        client = TSEClient(ckan_url)
        resources = client.get_resources(dataset_id)
        location_resource_found = False
        processed_rows = 0
        location_batch: dict[str, dict] = {}
        section_batch: dict[str, dict] = {}
        for resource in resources:
            resource_name = _normalized_resource_name(resource.get("name", ""))
            if "eleitorado por local de votacao" not in resource_name:
                continue
            url = resource.get("url")
            if not url:
                continue
            location_resource_found = True
            for row in client.iter_csv_records(url):
                normalized = _normalized_location(row, election_year, run_id)
                if normalized is None:
                    continue
                location, section = normalized
                location_batch[location["location_key"]] = location
                section_batch[section["section_key"]] = section
                run.records_processed += 1
                processed_rows += 1
                if len(section_batch) >= IMPORT_BATCH_SIZE:
                    _flush_batches(database, location_batch, section_batch)
            _flush_batches(database, location_batch, section_batch)
        if not location_resource_found:
            raise RuntimeError(
                f"O conjunto {dataset_id} não possui um recurso de eleitorado por local de votação."
            )
        if processed_rows == 0:
            raise RuntimeError(
                f"O recurso de locais do conjunto {dataset_id} não contém seções válidas."
            )
        database.execute(delete(PollingSection).where(PollingSection.import_id != run_id))
        has_current_sections = (
            select(PollingSection.section_key)
            .where(
                PollingSection.location_key == PollingLocation.location_key,
                PollingSection.import_id == run_id,
            )
            .exists()
        )
        database.execute(
            delete(PollingLocation).where(
                or_(
                    PollingLocation.import_id != run_id,
                    ~has_current_sections,
                )
            )
        )
        database.commit()
        run.status = "SUCCEEDED"
    except Exception as error:
        database.rollback()
        run = database.scalar(select(ImportRun).where(ImportRun.id == run_id))
        if run is not None:
            run.status = "FAILED"
            run.error_message = str(error)[:4000]
        logger.exception("Falha ao importar locais de votação do TSE.")
    finally:
        run = database.get(ImportRun, run_id)
        if run is not None:
            run.finished_at = datetime.utcnow()
            database.commit()
        database.close()
