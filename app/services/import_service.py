import hashlib
import json
from collections import Counter
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.orm import Session

from app.models import DataSource, ImportRun, MesarioAggregate
from app.services.tse_client import TSEClient, normalize_record


GENERATION_COLUMNS = {"DT_GERACAO", "HH_GERACAO"}


def import_tse_dataset(
    database: Session,
    client: TSEClient,
    dataset_id: str,
    election_year: int,
) -> ImportRun:
    run = ImportRun(dataset_id=dataset_id, status="RUNNING")
    database.add(run)
    database.commit()
    database.refresh(run)

    try:
        resources = client.get_resources(dataset_id)
        for resource in resources:
            url = resource.get("url")
            if not url:
                continue
            resource_id = str(resource.get("id") or url)
            source = database.scalar(
                select(DataSource).where(
                    DataSource.provider == "TSE",
                    DataSource.resource_id == resource_id,
                )
            )
            if source is None:
                source = DataSource(
                    dataset_id=dataset_id,
                    resource_id=resource_id,
                    resource_name=str(resource.get("name") or resource.get("description") or resource_id),
                    url=url,
                )
                database.add(source)
                database.flush()

            batch: list[dict[str, Any]] = []
            occurrences: Counter[bytes] = Counter()
            for row in client.iter_csv_records(url):
                normalized = normalize_record(row, election_year)
                record_hash = _record_hash(resource_id, row, occurrences)
                batch.append({"source_id": source.id, "record_hash": record_hash, **normalized})
                if len(batch) >= 100:
                    _upsert_batch(database, batch)
                    run.records_processed += len(batch)
                    database.commit()
                    batch.clear()
            if batch:
                _upsert_batch(database, batch)
                run.records_processed += len(batch)
                database.commit()

        run.status = "SUCCEEDED"
    except Exception as error:
        database.rollback()
        run.status = "FAILED"
        run.error_message = str(error)[:4000]
        raise
    finally:
        run.finished_at = datetime.utcnow()
        database.add(run)
        database.commit()
        database.refresh(run)
    return run


def _record_hash(resource_id: str, row: dict[str, Any], occurrences: Counter[bytes]) -> str:
    content = {key: value for key, value in row.items() if key not in GENERATION_COLUMNS}
    canonical = json.dumps(content, ensure_ascii=False, sort_keys=True, default=str)
    row_digest = hashlib.sha256(f"{resource_id}:{canonical}".encode("utf-8")).digest()
    occurrences[row_digest] += 1
    return hashlib.sha256(row_digest + str(occurrences[row_digest]).encode("ascii")).hexdigest()


def _upsert_batch(database: Session, batch: list[dict[str, Any]]) -> None:
    statement = mysql_insert(MesarioAggregate).values(batch)
    database.execute(statement.on_duplicate_key_update(record_hash=statement.inserted.record_hash))