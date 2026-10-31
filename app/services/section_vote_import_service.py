import hashlib
import logging
import re
import unicodedata
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import delete, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import DataSource, Election, ImportRun, SectionVote
from app.services.tse_client import TSEClient


logger = logging.getLogger(__name__)
IMPORT_BATCH_SIZE = 100
BRAZILIAN_UFS = {
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO",
    "MA", "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR",
    "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO",
}


def _normalized_text(value: Any) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value).strip().lower())
    without_accents = "".join(
        char for char in decomposed if not unicodedata.combining(char)
    )
    return " ".join(without_accents.replace("_", " ").split())


def _field(row: dict[str, Any], *names: str) -> str | None:
    normalized_row = {
        _normalized_text(key): value for key, value in row.items() if key is not None
    }
    for name in names:
        value = normalized_row.get(_normalized_text(name))
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _integer(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _resource_id(resource: dict[str, Any]) -> str:
    resource_id = resource.get("id")
    if resource_id:
        return str(resource_id)[:255]
    return hashlib.sha256(str(resource.get("url", "")).encode("utf-8")).hexdigest()


def _section_vote_resources(
    resources: list[dict[str, Any]],
    uf: str | None = None,
) -> list[dict[str, Any]]:
    matching = []
    for resource in resources:
        name = _normalized_text(resource.get("name") or "")
        url = str(resource.get("url") or "")
        normalized_url = urlparse(url).path.lower()
        if "detalhe da apuracao" in name or "detalhe_votacao_secao" in normalized_url:
            continue
        if "votacao por secao eleitoral" in name or "votacao_secao_" in normalized_url:
            matching.append(resource)

    state_resources = []
    for resource in matching:
        filename = urlparse(str(resource.get("url") or "")).path.rsplit("/", 1)[-1]
        match = re.search(r"_([A-Z]{2})\.(?:zip|csv)$", filename, re.IGNORECASE)
        if match and match.group(1).upper() in BRAZILIAN_UFS:
            state_resources.append(resource)
    if uf:
        return [
            resource
            for resource in state_resources
            if re.search(
                rf"_{re.escape(uf.upper())}\.(?:zip|csv)$",
                urlparse(str(resource.get("url") or "")).path,
                re.IGNORECASE,
            )
        ]
    if state_resources:
        return state_resources
    return [
        resource
        for resource in matching
        if re.search(r"_BR\.(?:zip|csv)$", urlparse(str(resource.get("url") or "")).path, re.I)
    ] or matching


def _normalized_vote(
    row: dict[str, Any],
    election_year: int,
    import_id: int,
    source_id: int,
    election_id: int,
) -> dict[str, Any] | None:
    year = _integer(_field(row, "ANO_ELEICAO")) or election_year
    turn = _integer(_field(row, "NR_TURNO", "TURNO"))
    uf = _field(row, "SG_UF", "UF")
    municipality_code = _field(row, "CD_MUNICIPIO", "CD_MUN")
    zone = _integer(_field(row, "NR_ZONA", "ZONA"))
    section_number = _field(row, "NR_SECAO", "SECAO")
    office_code = _field(row, "CD_CARGO", "CODIGO CARGO")
    office_name = _field(row, "DS_CARGO", "NM_CARGO", "CARGO")
    vote_code = _field(row, "NR_VOTAVEL", "NR_CANDIDATO", "NR_PARTIDO")
    vote_name = _field(row, "NM_VOTAVEL", "NM_CANDIDATO", "NM_PARTIDO")
    votes = _integer(_field(row, "QT_VOTOS", "VOTOS"))
    if not all((uf, municipality_code, section_number, office_code, vote_code, vote_name)):
        return None
    if turn is None or turn < 1 or zone is None or zone < 1 or votes is None or votes < 0:
        return None

    normalized_name = _normalized_text(vote_name)
    if "branco" in normalized_name:
        vote_type = "BRANCO"
    elif "nulo" in normalized_name:
        vote_type = "NULO"
    elif "legenda" in normalized_name:
        vote_type = "LEGENDA"
    else:
        vote_type = "CANDIDATO"

    identity = "|".join(
        (
            str(year),
            _field(row, "CD_ELEICAO") or str(year),
            str(turn),
            uf.upper(),
            municipality_code,
            str(zone),
            section_number,
            office_code,
            vote_code,
            vote_type,
        )
    )
    return {
        "record_key": hashlib.sha256(identity.encode("utf-8")).hexdigest(),
        "election_id": election_id,
        "import_id": import_id,
        "source_id": source_id,
        "election_year": year,
        "turn": turn,
        "uf": uf.upper()[:2],
        "municipality_code": municipality_code,
        "municipality": _field(row, "NM_MUNICIPIO", "MUNICIPIO"),
        "electoral_zone": zone,
        "section_number": section_number,
        "polling_place_number": _field(row, "NR_LOCAL_VOTACAO", "CD_LOCAL_VOTACAO"),
        "office_code": office_code,
        "office_name": office_name or "Cargo não informado",
        "vote_code": vote_code,
        "vote_name": vote_name,
        "vote_type": vote_type,
        "candidate_registration_number": _field(row, "SQ_CANDIDATO"),
        "party_number": _field(row, "NR_PARTIDO"),
        "party_abbreviation": _field(row, "SG_PARTIDO"),
        "party_name": _field(row, "NM_PARTIDO"),
        "votes": votes,
    }


def _get_or_create_election(
    database: Session,
    row: dict[str, Any],
    election_year: int,
    elections: dict[str, int],
) -> int:
    election_code = _field(row, "CD_ELEICAO") or str(election_year)
    election_id = elections.get(election_code)
    if election_id is not None:
        return election_id

    election = database.scalar(
        select(Election).where(
            Election.election_year == election_year,
            Election.election_code == election_code,
        )
    )
    if election is None:
        election = Election(
            election_year=election_year,
            election_code=election_code,
            election_type=_field(row, "NM_TIPO_ELEICAO", "CD_TIPO_ELEICAO"),
            name=_field(row, "DS_ELEICAO", "NM_ELEICAO")
            or f"Eleições {election_year}",
            election_date=_field(row, "DT_ELEICAO"),
        )
        database.add(election)
        database.flush()
    elections[election_code] = election.id
    return election.id


def _upsert_vote_batch(database: Session, records: list[dict[str, Any]]) -> None:
    if not records:
        return
    dialect = database.get_bind().dialect.name
    if dialect == "mysql":
        statement = mysql_insert(SectionVote).values(records)
        database.execute(
            statement.on_duplicate_key_update(
                **{
                    name: getattr(statement.inserted, name)
                    for name in records[0]
                    if name not in {"id", "import_id", "record_key"}
                }
            )
        )
    elif dialect == "sqlite":
        statement = sqlite_insert(SectionVote).values(records)
        database.execute(
            statement.on_conflict_do_update(
                index_elements=[SectionVote.import_id, SectionVote.record_key],
                set_={
                    name: getattr(statement.excluded, name)
                    for name in records[0]
                    if name not in {"id", "import_id", "record_key"}
                },
            )
        )
    else:
        raise RuntimeError(f"Banco de dados não suportado para resultados: {dialect}.")


def _flush_vote_batch(
    database: Session,
    run: ImportRun,
    records: list[dict[str, Any]],
) -> None:
    if not records:
        return
    _upsert_vote_batch(database, records)
    run.records_processed += len(records)
    database.commit()
    records.clear()


def _import_resources(
    database: Session,
    run: ImportRun,
    client: TSEClient,
    dataset_id: str,
    election_year: int,
    uf: str | None = None,
) -> None:
    resources = _section_vote_resources(client.get_resources(dataset_id), uf)
    if not resources:
        raise RuntimeError(
            f"O conjunto {dataset_id} não possui recursos de votação por seção eleitoral."
        )

    elections: dict[str, int] = {}
    batch: list[dict[str, Any]] = []
    for resource in resources:
        url = resource.get("url")
        if not url:
            continue
        resource_id = _resource_id(resource)
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
                resource_name=str(resource.get("name") or resource_id)[:500],
                url=str(url)[:2048],
            )
            database.add(source)
            database.flush()
        else:
            source.dataset_id = dataset_id
            source.resource_name = str(resource.get("name") or resource_id)[:500]
            source.url = str(url)[:2048]

        for row in client.iter_csv_records(url):
            election_id = _get_or_create_election(database, row, election_year, elections)
            vote = _normalized_vote(row, election_year, run.id, source.id, election_id)
            if vote is None:
                continue
            batch.append(vote)
            if len(batch) >= IMPORT_BATCH_SIZE:
                _flush_vote_batch(database, run, batch)
    _flush_vote_batch(database, run, batch)

    if run.records_processed == 0:
        raise RuntimeError(
            f"Os recursos de votação por seção do conjunto {dataset_id} não contêm resultados válidos."
        )
    delete_filters = [
        SectionVote.election_year == election_year,
        SectionVote.import_id != run.id,
    ]
    if uf:
        delete_filters.append(SectionVote.uf == uf.upper())
    database.execute(delete(SectionVote).where(*delete_filters))


def import_tse_section_votes(
    run_id: int,
    ckan_url: str,
    dataset_id: str,
    election_year: int,
    uf: str | None = None,
) -> None:
    database = SessionLocal()
    try:
        run = database.get(ImportRun, run_id)
        if run is None:
            raise RuntimeError(f"Execução de importação {run_id} não encontrada.")
        _import_resources(
            database,
            run,
            TSEClient(ckan_url),
            dataset_id,
            election_year,
            uf,
        )
        run.status = "SUCCEEDED"
    except Exception as error:
        database.rollback()
        run = database.scalar(select(ImportRun).where(ImportRun.id == run_id))
        if run is not None:
            run.status = "FAILED"
            run.error_message = str(error)[:4000]
        logger.exception("Falha ao importar resultados eleitorais por seção do TSE.")
    finally:
        run = database.get(ImportRun, run_id)
        if run is not None:
            run.finished_at = datetime.utcnow()
            database.commit()
        database.close()
