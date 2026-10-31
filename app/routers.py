from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import String, and_, cast, func, or_, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database import get_db
from app.models import (
    DataSource,
    ImportRun,
    MesarioAggregate,
    PollingLocation,
    PollingSection,
    SectionVote,
)
from app.schemas import AggregateOut, ImportOut
from app.security import require_api_key
from app.services.import_service import import_tse_dataset
from app.services.location_import_service import import_tse_polling_locations
from app.services.section_vote_import_service import import_tse_section_votes
from app.services.tse_client import TSEClient


router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_api_key)])


@router.post("/importacoes/tse", response_model=ImportOut, status_code=201)
def start_tse_import(database: Session = Depends(get_db)) -> ImportRun:
    settings = get_settings()
    client = TSEClient(settings.tse_ckan_url)
    return import_tse_dataset(database, client, settings.tse_dataset_id, settings.election_year)


@router.get("/mesarios", response_model=list[AggregateOut])
def search_mesarios(
    uf: str | None = Query(default=None, min_length=2, max_length=2),
    municipality_code: str | None = Query(default=None, max_length=12),
    zone: int | None = Query(default=None, ge=1),
    election_year: int | None = Query(default=None, ge=2000),
    turn: int | None = Query(default=None, ge=1, le=2),
    attendance_status: str | None = Query(default=None, max_length=120),
    mesario_type: str | None = Query(default=None, max_length=255),
    gender: str | None = Query(default=None, max_length=120),
    marital_status: str | None = Query(default=None, max_length=120),
    age_range: str | None = Query(default=None, max_length=120),
    education_level: str | None = Query(default=None, max_length=255),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    database: Session = Depends(get_db),
) -> list[MesarioAggregate]:
    filters = _mesario_filters(
        uf=uf,
        municipality_code=municipality_code,
        zone=zone,
        election_year=election_year,
        turn=turn,
        attendance_status=attendance_status,
        mesario_type=mesario_type,
        gender=gender,
        marital_status=marital_status,
        age_range=age_range,
        education_level=education_level,
    )
    statement = select(MesarioAggregate).where(*filters)
    return list(database.scalars(statement.order_by(MesarioAggregate.id).offset(offset).limit(limit)))


@router.get("/mesarios/opcoes")
def mesario_filter_options(
    uf: str | None = Query(default=None, min_length=2, max_length=2),
    database: Session = Depends(get_db),
) -> dict[str, list[str]]:
    columns = {
        "gender": MesarioAggregate.gender,
        "marital_status": MesarioAggregate.marital_status,
        "age_range": MesarioAggregate.age_range,
        "education_level": MesarioAggregate.education_level,
    }
    options = {
        name: [
            str(value)
            for value in database.scalars(
                select(column)
                .where(column.is_not(None), column != "")
                .distinct()
                .order_by(column)
            ).all()
        ]
        for name, column in columns.items()
    }
    options["ufs"] = [
        str(value)
        for value in database.scalars(
            select(MesarioAggregate.uf)
            .where(MesarioAggregate.uf.is_not(None), MesarioAggregate.uf != "")
            .distinct()
            .order_by(MesarioAggregate.uf)
        ).all()
    ]
    municipality_statement = (
        select(MesarioAggregate.municipality)
        .where(
            MesarioAggregate.municipality.is_not(None),
            MesarioAggregate.municipality != "",
        )
        .distinct()
        .order_by(MesarioAggregate.municipality)
    )
    if uf:
        municipality_statement = municipality_statement.where(
            MesarioAggregate.uf == uf.upper()
        )
    options["municipalities"] = [
        str(value) for value in database.scalars(municipality_statement).all()
    ]
    return options


@router.get("/mesarios/visualizacao")
def browse_mesarios(
    uf: str | None = Query(default=None, min_length=2, max_length=2),
    municipality_code: str | None = Query(default=None, max_length=12),
    municipality: str | None = Query(default=None, max_length=160),
    zone: int | None = Query(default=None, ge=1),
    election_year: int | None = Query(default=None, ge=2000),
    turn: int | None = Query(default=None, ge=1, le=2),
    attendance_status: str | None = Query(default=None, max_length=120),
    mesario_type: str | None = Query(default=None, max_length=255),
    gender: str | None = Query(default=None, max_length=120),
    marital_status: str | None = Query(default=None, max_length=120),
    age_range: str | None = Query(default=None, max_length=120),
    education_level: str | None = Query(default=None, max_length=255),
    search: str | None = Query(default=None, max_length=255),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    database: Session = Depends(get_db),
) -> dict:
    filters = _mesario_filters(
        uf=uf,
        municipality_code=municipality_code,
        municipality=municipality,
        zone=zone,
        election_year=election_year,
        turn=turn,
        attendance_status=attendance_status,
        mesario_type=mesario_type,
        gender=gender,
        marital_status=marital_status,
        age_range=age_range,
        education_level=education_level,
        search=search,
    )
    total = database.scalar(
        select(func.count()).select_from(MesarioAggregate).where(*filters)
    ) or 0
    total_called = database.scalar(
        select(func.coalesce(func.sum(MesarioAggregate.called_count), 0)).where(*filters)
    ) or 0
    by_attendance = database.execute(
        select(
            MesarioAggregate.attendance_status,
            func.coalesce(func.sum(MesarioAggregate.called_count), 0),
        )
        .where(*filters)
        .group_by(MesarioAggregate.attendance_status)
        .order_by(MesarioAggregate.attendance_status)
    ).all()
    items = database.scalars(
        select(MesarioAggregate)
        .where(*filters)
        .order_by(MesarioAggregate.id)
        .offset(offset)
        .limit(limit)
    ).all()
    return {
        "total": total,
        "total_convocados": int(total_called),
        "por_comparecimento": [
            {"categoria": status or "SEM_CATEGORIA", "convocados": int(called_count)}
            for status, called_count in by_attendance
        ],
        "items": [AggregateOut.model_validate(item).model_dump(mode="json") for item in items],
    }


def _mesario_filters(
    *,
    uf: str | None = None,
    municipality_code: str | None = None,
    municipality: str | None = None,
    zone: int | None = None,
    election_year: int | None = None,
    turn: int | None = None,
    attendance_status: str | None = None,
    mesario_type: str | None = None,
    gender: str | None = None,
    marital_status: str | None = None,
    age_range: str | None = None,
    education_level: str | None = None,
    search: str | None = None,
) -> list:
    filters = []
    if uf:
        filters.append(MesarioAggregate.uf == uf.upper())
    if municipality_code:
        filters.append(MesarioAggregate.municipality_code == municipality_code)
    if municipality:
        filters.append(MesarioAggregate.municipality.ilike(f"%{municipality}%"))
    if zone is not None:
        filters.append(MesarioAggregate.electoral_zone == zone)
    if election_year is not None:
        filters.append(MesarioAggregate.election_year == election_year)
    if turn is not None:
        filters.append(MesarioAggregate.turn == turn)
    if attendance_status:
        filters.append(MesarioAggregate.attendance_status == attendance_status.upper())
    if mesario_type:
        filters.append(MesarioAggregate.mesario_type.ilike(f"%{mesario_type}%"))
    if gender:
        filters.append(MesarioAggregate.gender.ilike(f"%{gender}%"))
    if marital_status:
        filters.append(MesarioAggregate.marital_status.ilike(f"%{marital_status}%"))
    if age_range:
        filters.append(MesarioAggregate.age_range.ilike(f"%{age_range}%"))
    if education_level:
        filters.append(MesarioAggregate.education_level.ilike(f"%{education_level}%"))
    if search:
        term = f"%{search}%"
        filters.append(
            or_(
                MesarioAggregate.uf.ilike(term),
                MesarioAggregate.municipality_code.ilike(term),
                MesarioAggregate.municipality.ilike(term),
                MesarioAggregate.mesario_type.ilike(term),
                MesarioAggregate.electoral_activity.ilike(term),
                MesarioAggregate.special_function.ilike(term),
                MesarioAggregate.gender.ilike(term),
                MesarioAggregate.marital_status.ilike(term),
                MesarioAggregate.age_range.ilike(term),
                MesarioAggregate.education_level.ilike(term),
                MesarioAggregate.race_color.ilike(term),
                MesarioAggregate.quilombola_status.ilike(term),
                MesarioAggregate.libras_interpreter_status.ilike(term),
                MesarioAggregate.gender_identity.ilike(term),
                MesarioAggregate.volunteer_status.ilike(term),
                MesarioAggregate.attendance_status.ilike(term),
                cast(MesarioAggregate.raw_data, String).ilike(term),
            )
        )
    return filters


@router.post("/mapa/importacoes/tse", response_model=ImportOut, status_code=202)
def start_polling_location_import(
    background_tasks: BackgroundTasks,
    database: Session = Depends(get_db),
) -> ImportRun:
    settings = get_settings()
    existing_run = database.scalar(
        select(ImportRun)
        .where(
            ImportRun.dataset_id == settings.tse_locations_dataset_id,
            ImportRun.status == "RUNNING",
        )
        .order_by(ImportRun.started_at.desc())
    )
    if existing_run is not None:
        return existing_run

    run = ImportRun(
        dataset_id=settings.tse_locations_dataset_id,
        status="RUNNING",
    )
    database.add(run)
    database.commit()
    database.refresh(run)
    background_tasks.add_task(
        import_tse_polling_locations,
        run.id,
        settings.tse_ckan_url,
        settings.tse_locations_dataset_id,
        settings.election_year,
    )
    return run


@router.get("/mapa/importacoes/{import_id}", response_model=ImportOut)
def polling_location_import_status(
    import_id: int,
    database: Session = Depends(get_db),
) -> ImportRun:
    settings = get_settings()
    run = database.get(ImportRun, import_id)
    if run is None or run.dataset_id != settings.tse_locations_dataset_id:
        raise HTTPException(status_code=404, detail="Importação do mapa não encontrada.")
    return run


@router.post("/resultados/importacoes/tse", response_model=ImportOut, status_code=202)
def start_tse_section_vote_import(
    background_tasks: BackgroundTasks,
    election_year: int | None = Query(default=None, ge=1994, le=2100),
    uf: str | None = Query(default=None, min_length=2, max_length=2, pattern="^[A-Za-z]{2}$"),
    database: Session = Depends(get_db),
) -> ImportRun:
    settings = get_settings()
    year = election_year or settings.election_year
    dataset_id = f"resultados-{year}"
    run_dataset_id = f"{dataset_id}-uf-{uf.upper()}" if uf else dataset_id
    existing_run = database.scalar(
        select(ImportRun)
        .where(
            ImportRun.dataset_id == run_dataset_id,
            ImportRun.status == "RUNNING",
        )
        .order_by(ImportRun.started_at.desc())
    )
    if existing_run is not None:
        return existing_run

    completed_scope_filters = [ImportRun.dataset_id == run_dataset_id]
    if uf:
        completed_scope_filters.append(ImportRun.dataset_id == dataset_id)
    completed_run = database.scalar(
        select(ImportRun)
        .where(
            ImportRun.status == "SUCCEEDED",
            or_(*completed_scope_filters),
        )
        .order_by(ImportRun.finished_at.desc())
    )
    if completed_run is not None:
        completed_scope = "Brasil todo" if not uf or completed_run.dataset_id == dataset_id else uf.upper()
        raise HTTPException(
            status_code=409,
            detail=(
                f"Os resultados de {year} para {completed_scope} já foram importados "
                f"com sucesso (execução {completed_run.id}). Uma nova importação foi bloqueada."
            ),
        )

    conflicting_run = database.scalar(
        select(ImportRun)
        .where(
            ImportRun.status == "RUNNING",
            or_(
                ImportRun.dataset_id == dataset_id,
                ImportRun.dataset_id.like(f"{dataset_id}-uf-%"),
            ),
        )
        .order_by(ImportRun.started_at.desc())
    )
    if conflicting_run is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Já existe uma importação de resultados de {year} em andamento "
                f"(execução {conflicting_run.id}: {conflicting_run.dataset_id}). "
                "Aguarde a conclusão antes de iniciar outra."
            ),
        )

    run = ImportRun(dataset_id=run_dataset_id, status="RUNNING")
    database.add(run)
    database.commit()
    database.refresh(run)
    background_tasks.add_task(
        import_tse_section_votes,
        run.id,
        settings.tse_ckan_url,
        dataset_id,
        year,
        uf.upper() if uf else None,
    )
    return run


@router.get("/resultados/importacoes/{import_id}", response_model=ImportOut)
def section_vote_import_status(
    import_id: int,
    database: Session = Depends(get_db),
) -> ImportRun:
    run = database.get(ImportRun, import_id)
    if run is None or not run.dataset_id.startswith("resultados-"):
        raise HTTPException(status_code=404, detail="Importação de resultados não encontrada.")
    return run


@router.get("/mapa/secoes/opcoes")
def polling_section_filter_options(
    uf: str | None = Query(default=None, min_length=2, max_length=2),
    database: Session = Depends(get_db),
) -> dict[str, list[str]]:
    filters = _polling_section_filters(uf=uf)
    ufs = database.scalars(
        select(PollingSection.uf)
        .where(PollingSection.election_year == get_settings().election_year)
        .distinct()
        .order_by(PollingSection.uf)
    ).all()
    municipalities = (
        database.scalars(
            select(PollingSection.municipality)
            .where(*filters)
            .distinct()
            .order_by(PollingSection.municipality)
        ).all()
        if uf
        else []
    )
    return {
        "ufs": [str(value) for value in ufs if value],
        "municipalities": [str(value) for value in municipalities if value],
    }


@router.get("/mapa/secoes")
def browse_polling_sections(
    uf: str | None = Query(default=None, min_length=2, max_length=2),
    municipality: str | None = Query(default=None, max_length=160),
    zone: int | None = Query(default=None, ge=1),
    search: str | None = Query(default=None, max_length=255),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    database: Session = Depends(get_db),
) -> dict:
    filters = _polling_section_filters(
        uf=uf,
        municipality=municipality,
        zone=zone,
        search=search,
    )
    total = database.scalar(
        select(func.count()).select_from(PollingSection).where(*filters)
    ) or 0
    sections = database.execute(
        select(
            PollingSection.section_number,
            PollingSection.election_year,
            PollingSection.uf,
            PollingSection.municipality_code,
            PollingSection.municipality,
            PollingSection.electoral_zone,
            PollingSection.polling_place_number,
            PollingSection.polling_place_name,
            PollingSection.address,
            PollingSection.neighborhood,
            PollingSection.postal_code,
            PollingSection.latitude,
            PollingSection.longitude,
            PollingSection.situation,
        )
        .where(*filters)
        .order_by(
            PollingSection.uf,
            PollingSection.municipality,
            PollingSection.electoral_zone,
            PollingSection.section_number,
        )
        .offset(offset)
        .limit(limit)
    ).mappings().all()
    return {
        "total": int(total),
        "items": [
            {
                **dict(section),
                "latitude": (
                    float(section["latitude"]) if section["latitude"] is not None else None
                ),
                "longitude": (
                    float(section["longitude"]) if section["longitude"] is not None else None
                ),
            }
            for section in sections
        ],
    }


@router.get("/mapa/locais")
def polling_location_map(
    uf: str | None = Query(default=None, min_length=2, max_length=2),
    municipality: str | None = Query(default=None, max_length=160),
    zone: int | None = Query(default=None, ge=1),
    search: str | None = Query(default=None, max_length=255),
    south: float | None = Query(default=None, ge=-90, le=90),
    west: float | None = Query(default=None, ge=-540, le=540),
    north: float | None = Query(default=None, ge=-90, le=90),
    east: float | None = Query(default=None, ge=-540, le=540),
    zoom: int = Query(default=4, ge=2, le=20),
    database: Session = Depends(get_db),
) -> dict:
    bounds = (south, west, north, east)
    if any(value is not None for value in bounds) and not all(value is not None for value in bounds):
        raise HTTPException(status_code=422, detail="Informe os quatro limites do mapa.")
    if south is not None and north is not None and south >= north:
        raise HTTPException(status_code=422, detail="O limite sul deve ser menor que o limite norte.")
    filters = _polling_location_filters(uf, municipality, zone, search)
    section_counts = (
        select(
            PollingSection.location_key,
            func.count(PollingSection.section_number).label("section_count"),
        )
        .group_by(PollingSection.location_key)
        .subquery()
    )
    summarized = (
        select(
            PollingLocation.location_key,
            PollingLocation.latitude,
            PollingLocation.longitude,
            PollingLocation.uf,
            PollingLocation.municipality,
            PollingLocation.electoral_zone,
            PollingLocation.polling_place_number,
            PollingLocation.name,
            PollingLocation.address,
            PollingLocation.neighborhood,
            PollingLocation.postal_code,
            PollingLocation.situation,
            func.coalesce(section_counts.c.section_count, 0).label("section_count"),
        )
        .outerjoin(section_counts, section_counts.c.location_key == PollingLocation.location_key)
        .where(*filters)
        .subquery()
    )
    total_locations = database.scalar(select(func.count()).select_from(summarized)) or 0
    total_sections = database.scalar(
        select(func.coalesce(func.sum(summarized.c.section_count), 0))
    ) or 0

    viewport = []
    if south is not None and west is not None and north is not None and east is not None:
        viewport.append(summarized.c.latitude.between(south, north))
        if east - west < 360:
            normalized_west = (west + 180) % 360 - 180
            normalized_east = (east + 180) % 360 - 180
            if normalized_west <= normalized_east:
                viewport.append(
                    summarized.c.longitude.between(normalized_west, normalized_east)
                )
            else:
                viewport.append(
                    or_(
                        summarized.c.longitude >= normalized_west,
                        summarized.c.longitude <= normalized_east,
                    )
                )
    visible_query = select(summarized).where(
        summarized.c.latitude.is_not(None),
        summarized.c.longitude.is_not(None),
        *viewport,
    )

    clustered = zoom < 11
    if clustered:
        latitude_span = north - south if south is not None and north is not None else 40.0
        longitude_span = (
            min(east - west, 360)
            if east is not None and west is not None
            else 40.0
        )
        latitude_step = max(latitude_span / 70, 0.01)
        longitude_step = max(longitude_span / 100, 0.01)
        points = database.execute(
            select(
                func.avg(summarized.c.latitude).label("latitude"),
                func.avg(summarized.c.longitude).label("longitude"),
                func.count().label("local_count"),
                func.sum(summarized.c.section_count).label("section_count"),
            )
            .select_from(summarized)
            .where(
                summarized.c.latitude.is_not(None),
                summarized.c.longitude.is_not(None),
                *viewport,
            )
            .group_by(
                func.floor(summarized.c.latitude / latitude_step),
                func.floor(summarized.c.longitude / longitude_step),
            )
        ).mappings().all()
        map_points = [
            {
                "latitude": float(point["latitude"]),
                "longitude": float(point["longitude"]),
                "local_count": int(point["local_count"]),
                "section_count": int(point["section_count"] or 0),
            }
            for point in points
        ]
        truncated = False
    else:
        point_rows = database.execute(
            visible_query.order_by(
                summarized.c.uf,
                summarized.c.municipality,
                summarized.c.electoral_zone,
                summarized.c.polling_place_number,
            ).limit(20000)
        ).mappings().all()
        map_points = [
            {
                "location_key": row["location_key"],
                "latitude": float(row["latitude"]),
                "longitude": float(row["longitude"]),
                "local_count": 1,
                "section_count": int(row["section_count"]),
                "uf": row["uf"],
                "municipality": row["municipality"],
                "electoral_zone": row["electoral_zone"],
                "polling_place_number": row["polling_place_number"],
                "name": row["name"],
                "address": row["address"],
                "neighborhood": row["neighborhood"],
                "postal_code": row["postal_code"],
                "situation": row["situation"],
            }
            for row in point_rows
        ]
        truncated = len(point_rows) == 20000

    return {
        "total_locations": int(total_locations),
        "total_sections": int(total_sections),
        "clustered": clustered,
        "truncated": truncated,
        "points": map_points,
    }


@router.get("/mapa/locais/{location_key}/secoes")
def polling_location_sections(
    location_key: str,
    database: Session = Depends(get_db),
) -> list[dict]:
    location = database.get(PollingLocation, location_key)
    if location is None:
        raise HTTPException(status_code=404, detail="Local de votação não encontrado.")
    sections = database.scalars(
        select(PollingSection)
        .where(PollingSection.location_key == location_key)
        .order_by(PollingSection.section_number)
    ).all()
    return [
        {
            "section_number": section.section_number,
            "election_year": section.election_year,
            "uf": section.uf,
            "municipality_code": section.municipality_code,
            "municipality": section.municipality,
            "electoral_zone": section.electoral_zone,
            "polling_place_number": section.polling_place_number,
            "polling_place_name": section.polling_place_name,
            "address": section.address,
            "neighborhood": section.neighborhood,
            "postal_code": section.postal_code,
            "latitude": section.latitude,
            "longitude": section.longitude,
            "situation": section.situation,
        }
        for section in sections
    ]


def _polling_location_filters(
    uf: str | None,
    municipality: str | None,
    zone: int | None,
    search: str | None,
) -> list:
    filters = [PollingLocation.election_year == get_settings().election_year]
    if uf:
        filters.append(PollingLocation.uf == uf.upper())
    if municipality:
        filters.append(PollingLocation.municipality.ilike(f"%{municipality}%"))
    if zone is not None:
        filters.append(PollingLocation.electoral_zone == zone)
    if search:
        term = f"%{search}%"
        filters.append(
            or_(
                PollingLocation.municipality.ilike(term),
                PollingLocation.name.ilike(term),
                PollingLocation.address.ilike(term),
                PollingLocation.neighborhood.ilike(term),
                PollingLocation.municipality_code.ilike(term),
            )
        )
    return filters


def _polling_section_filters(
    *,
    uf: str | None = None,
    municipality: str | None = None,
    zone: int | None = None,
    search: str | None = None,
) -> list:
    filters = [PollingSection.election_year == get_settings().election_year]
    if uf:
        filters.append(PollingSection.uf == uf.upper())
    if municipality:
        filters.append(PollingSection.municipality == municipality)
    if zone is not None:
        filters.append(PollingSection.electoral_zone == zone)
    if search:
        term = f"%{search}%"
        filters.append(
            or_(
                PollingSection.section_number.ilike(term),
                PollingSection.municipality_code.ilike(term),
                PollingSection.municipality.ilike(term),
                PollingSection.polling_place_name.ilike(term),
                PollingSection.address.ilike(term),
                PollingSection.neighborhood.ilike(term),
                PollingSection.postal_code.ilike(term),
            )
        )
    return filters


@router.get("/mesarios/agregados/{aggregate_id}", response_model=AggregateOut)
def get_mesario_aggregate(
    aggregate_id: int, database: Session = Depends(get_db)
) -> MesarioAggregate:
    aggregate = database.get(MesarioAggregate, aggregate_id)
    if aggregate is None:
        raise HTTPException(status_code=404, detail="Registro não encontrado.")
    return aggregate


@router.get("/resultados/mapa/opcoes")
def section_vote_map_options(
    election_year: int | None = Query(default=None, ge=1994, le=2100),
    turn: int | None = Query(default=None, ge=1, le=2),
    uf: str | None = Query(default=None, min_length=2, max_length=2),
    municipality: str | None = Query(default=None, max_length=160),
    database: Session = Depends(get_db),
) -> dict:
    year_filters = []
    if election_year is not None:
        year_filters.append(SectionVote.election_year == election_year)

    years = database.scalars(
        select(SectionVote.election_year).distinct().order_by(SectionVote.election_year.desc())
    ).all()
    turns = database.scalars(
        select(SectionVote.turn)
        .where(*year_filters)
        .distinct()
        .order_by(SectionVote.turn)
    ).all()
    scoped_filters = list(year_filters)
    if turn is not None:
        scoped_filters.append(SectionVote.turn == turn)
    office_filters = list(scoped_filters)
    if uf:
        office_filters.append(SectionVote.uf == uf.upper())
    if municipality:
        office_filters.append(SectionVote.municipality == municipality)
    offices = database.execute(
        select(SectionVote.office_code, SectionVote.office_name)
        .where(*office_filters)
        .distinct()
        .order_by(SectionVote.office_name)
    ).all()
    ufs = database.scalars(
        select(SectionVote.uf)
        .where(*scoped_filters)
        .distinct()
        .order_by(SectionVote.uf)
    ).all()
    municipality_filters = list(scoped_filters)
    if uf:
        municipality_filters.append(SectionVote.uf == uf.upper())
    municipalities = (
        database.scalars(
            select(SectionVote.municipality)
            .where(*municipality_filters, SectionVote.municipality.is_not(None))
            .distinct()
            .order_by(SectionVote.municipality)
        ).all()
        if uf
        else []
    )
    return {
        "years": [int(value) for value in years],
        "turns": [int(value) for value in turns],
        "offices": [{"code": str(code), "name": str(name)} for code, name in offices],
        "ufs": [str(value) for value in ufs],
        "municipalities": [str(value) for value in municipalities if value],
    }


@router.get("/resultados/mapa/candidatos")
def section_vote_candidate_options(
    election_year: int = Query(ge=1994, le=2100),
    turn: int = Query(ge=1, le=2),
    office_code: str = Query(min_length=1, max_length=12),
    uf: str | None = Query(default=None, min_length=2, max_length=2),
    municipality: str | None = Query(default=None, max_length=160),
    database: Session = Depends(get_db),
) -> list[dict[str, str | None]]:
    filters = [
        SectionVote.election_year == election_year,
        SectionVote.turn == turn,
        SectionVote.office_code == office_code,
        SectionVote.vote_type == "CANDIDATO",
    ]
    if uf:
        filters.append(SectionVote.uf == uf.upper())
    if municipality:
        filters.append(SectionVote.municipality == municipality)
    candidates = database.execute(
        select(
            SectionVote.vote_code,
            SectionVote.vote_name,
            SectionVote.candidate_registration_number,
            SectionVote.party_abbreviation,
            func.min(SectionVote.uf),
        )
        .where(*filters)
        .group_by(
            SectionVote.vote_code,
            SectionVote.vote_name,
            SectionVote.candidate_registration_number,
            SectionVote.party_abbreviation,
        )
        .order_by(SectionVote.vote_name, SectionVote.vote_code)
    ).all()
    return [
        {
            "code": str(vote_code),
            "name": str(vote_name),
            "registration_number": registration_number,
            "party": party,
            "photo_url": _candidate_photo_url(
                election_year=election_year,
                office_code=office_code,
                uf=str(candidate_uf),
                registration_number=registration_number,
            ),
        }
        for vote_code, vote_name, registration_number, party, candidate_uf in candidates
    ]


def _candidate_photo_url(
    *,
    election_year: int,
    office_code: str,
    uf: str,
    registration_number: str | None,
) -> str | None:
    if election_year != 2026 or not registration_number or not registration_number.isdigit():
        return None
    photo_uf = "BR" if office_code == "1" else uf.upper()
    base_url = get_settings().candidate_photos_base_url.rstrip("/")
    filename = quote(f"F{photo_uf}{registration_number}_div.jpg", safe="")
    return f"{base_url}/{photo_uf}/{filename}"


@router.get("/resultados/mapa")
def section_vote_map(
    election_year: int = Query(ge=1994, le=2100),
    turn: int = Query(ge=1, le=2),
    office_code: str = Query(min_length=1, max_length=12),
    vote_type: str = Query(default="CANDIDATO", pattern="^(CANDIDATO|BRANCO|NULO|LEGENDA)$"),
    vote_code: str | None = Query(default=None, max_length=32),
    uf: str | None = Query(default=None, min_length=2, max_length=2),
    municipality: str | None = Query(default=None, max_length=160),
    zone: int | None = Query(default=None, ge=1),
    south: float | None = Query(default=None, ge=-90, le=90),
    west: float | None = Query(default=None, ge=-540, le=540),
    north: float | None = Query(default=None, ge=-90, le=90),
    east: float | None = Query(default=None, ge=-540, le=540),
    zoom: int = Query(default=4, ge=2, le=20),
    database: Session = Depends(get_db),
) -> dict:
    vote_filters = [
        SectionVote.election_year == election_year,
        SectionVote.turn == turn,
        SectionVote.office_code == office_code,
        SectionVote.vote_type == vote_type,
    ]
    if vote_code:
        vote_filters.append(SectionVote.vote_code == vote_code)
    if uf:
        vote_filters.append(SectionVote.uf == uf.upper())
    if municipality:
        vote_filters.append(SectionVote.municipality == municipality)
    if zone is not None:
        vote_filters.append(SectionVote.electoral_zone == zone)

    geometry_year = get_settings().election_year
    section_match = and_(
        PollingSection.election_year == geometry_year,
        PollingSection.uf == SectionVote.uf,
        PollingSection.municipality_code == SectionVote.municipality_code,
        PollingSection.electoral_zone == SectionVote.electoral_zone,
        PollingSection.section_number == SectionVote.section_number,
    )
    map_filters = []
    if south is not None and west is not None and north is not None and east is not None:
        map_filters.append(PollingLocation.latitude.between(south, north))
        if east - west < 360:
            normalized_west = (west + 180) % 360 - 180
            normalized_east = (east + 180) % 360 - 180
            if normalized_west <= normalized_east:
                map_filters.append(
                    PollingLocation.longitude.between(normalized_west, normalized_east)
                )
            else:
                map_filters.append(
                    or_(
                        PollingLocation.longitude >= normalized_west,
                        PollingLocation.longitude <= normalized_east,
                    )
                )
    summarized = (
        select(
            PollingLocation.location_key.label("location_key"),
            PollingLocation.latitude.label("latitude"),
            PollingLocation.longitude.label("longitude"),
            PollingLocation.uf.label("uf"),
            PollingLocation.municipality.label("municipality"),
            PollingLocation.electoral_zone.label("electoral_zone"),
            PollingLocation.name.label("name"),
            PollingLocation.address.label("address"),
            func.count(func.distinct(PollingSection.section_key)).label("section_count"),
            func.sum(SectionVote.votes).label("votes"),
        )
        .select_from(SectionVote)
        .join(PollingSection, section_match)
        .join(PollingLocation, PollingLocation.location_key == PollingSection.location_key)
        .where(
            *vote_filters,
            *map_filters,
            PollingLocation.latitude.is_not(None),
            PollingLocation.longitude.is_not(None),
        )
        .group_by(
            PollingLocation.location_key,
            PollingLocation.latitude,
            PollingLocation.longitude,
            PollingLocation.uf,
            PollingLocation.municipality,
            PollingLocation.electoral_zone,
            PollingLocation.name,
            PollingLocation.address,
        )
        .subquery()
    )

    totals = database.execute(
        select(
            func.count().label("location_count"),
            func.coalesce(func.sum(summarized.c.section_count), 0).label("section_count"),
            func.coalesce(func.sum(summarized.c.votes), 0).label("votes"),
        ).select_from(summarized)
    ).mappings().one()
    visible_query = select(summarized)
    clustered = zoom < 9
    if clustered:
        latitude_span = north - south if south is not None and north is not None else 40.0
        longitude_span = min(east - west, 360) if east is not None and west is not None else 40.0
        latitude_step = max(latitude_span / 70, 0.01)
        longitude_step = max(longitude_span / 100, 0.01)
        rows = database.execute(
            select(
                func.avg(summarized.c.latitude).label("latitude"),
                func.avg(summarized.c.longitude).label("longitude"),
                func.count().label("location_count"),
                func.sum(summarized.c.section_count).label("section_count"),
                func.sum(summarized.c.votes).label("votes"),
            )
            .select_from(summarized)
            .group_by(
                func.floor(summarized.c.latitude / latitude_step),
                func.floor(summarized.c.longitude / longitude_step),
            )
        ).mappings().all()
        points = [
            {
                "latitude": float(row["latitude"]),
                "longitude": float(row["longitude"]),
                "location_count": int(row["location_count"]),
                "section_count": int(row["section_count"] or 0),
                "votes": int(row["votes"] or 0),
            }
            for row in rows
        ]
        truncated = False
    else:
        rows = database.execute(
            visible_query.order_by(
                summarized.c.uf,
                summarized.c.municipality,
                summarized.c.electoral_zone,
                summarized.c.name,
            ).limit(20000)
        ).mappings().all()
        points = [
            {
                "location_key": row["location_key"],
                "latitude": float(row["latitude"]),
                "longitude": float(row["longitude"]),
                "location_count": 1,
                "section_count": int(row["section_count"] or 0),
                "votes": int(row["votes"] or 0),
                "uf": row["uf"],
                "municipality": row["municipality"],
                "electoral_zone": row["electoral_zone"],
                "name": row["name"],
                "address": row["address"],
            }
            for row in rows
        ]
        truncated = len(rows) == 20000

    return {
        "total_locations": int(totals["location_count"] or 0),
        "total_sections": int(totals["section_count"] or 0),
        "total_votes": int(totals["votes"] or 0),
        "clustered": clustered,
        "truncated": truncated,
        "points": points,
    }


@router.get("/resultados/mapa/locais/{location_key}/secoes")
def section_vote_location_details(
    location_key: str,
    election_year: int = Query(ge=1994, le=2100),
    turn: int = Query(ge=1, le=2),
    office_code: str = Query(min_length=1, max_length=12),
    vote_type: str = Query(default="CANDIDATO", pattern="^(CANDIDATO|BRANCO|NULO|LEGENDA)$"),
    vote_code: str | None = Query(default=None, max_length=32),
    database: Session = Depends(get_db),
) -> dict:
    location = database.get(PollingLocation, location_key)
    if location is None:
        raise HTTPException(status_code=404, detail="Local de votação não encontrado.")
    filters = [
        SectionVote.election_year == election_year,
        SectionVote.turn == turn,
        SectionVote.office_code == office_code,
        SectionVote.vote_type == vote_type,
        SectionVote.uf == location.uf,
        SectionVote.municipality_code == location.municipality_code,
        SectionVote.electoral_zone == location.electoral_zone,
    ]
    if vote_code:
        filters.append(SectionVote.vote_code == vote_code)
    detail_rows = database.execute(
        select(
            SectionVote.section_number,
            SectionVote.municipality,
            SectionVote.uf,
            SectionVote.electoral_zone,
            SectionVote.vote_code,
            SectionVote.vote_name,
            SectionVote.party_abbreviation,
            func.sum(SectionVote.votes).label("votes"),
        )
        .join(
            PollingSection,
            and_(
                PollingSection.location_key == location_key,
                PollingSection.election_year == get_settings().election_year,
                PollingSection.uf == SectionVote.uf,
                PollingSection.municipality_code == SectionVote.municipality_code,
                PollingSection.electoral_zone == SectionVote.electoral_zone,
                PollingSection.section_number == SectionVote.section_number,
            ),
        )
        .where(*filters)
        .group_by(
            SectionVote.section_number,
            SectionVote.municipality,
            SectionVote.uf,
            SectionVote.electoral_zone,
            SectionVote.vote_code,
            SectionVote.vote_name,
            SectionVote.party_abbreviation,
        )
        .order_by(SectionVote.section_number, SectionVote.vote_name)
        .limit(2000)
    ).mappings().all()
    return {
        "location": location.name,
        "address": location.address,
        "municipality": location.municipality,
        "uf": location.uf,
        "zone": location.electoral_zone,
        "truncated": len(detail_rows) == 2000,
        "items": [dict(row) for row in detail_rows],
    }


@router.get("/indicadores/nacional")
def national_indicators(database: Session = Depends(get_db)) -> dict:
    return _aggregate_indicators(database)


@router.get("/indicadores/uf/{uf}")
def state_indicators(uf: str, database: Session = Depends(get_db)) -> dict:
    state = uf.upper()
    return _aggregate_indicators(database, state)


def _aggregate_indicators(database: Session, uf: str | None = None) -> dict:
    filters = [MesarioAggregate.uf == uf] if uf else []
    aggregate_rows = database.scalar(
        select(func.count()).select_from(MesarioAggregate).where(*filters)
    ) or 0
    grouped = database.execute(
        select(
            DataSource.resource_name,
            MesarioAggregate.attendance_status,
            func.count(MesarioAggregate.id),
            func.coalesce(func.sum(MesarioAggregate.called_count), 0),
        )
        .join(DataSource, DataSource.id == MesarioAggregate.source_id)
        .where(*filters)
        .group_by(DataSource.resource_name, MesarioAggregate.attendance_status)
        .order_by(DataSource.resource_name, MesarioAggregate.attendance_status)
    ).all()

    by_resource: dict[str, dict] = {}
    for resource_name, attendance_status, row_count, called_count in grouped:
        summary = by_resource.setdefault(
            resource_name,
            {"linhas_agregadas": 0, "convocados_por_categoria_comparecimento": {}},
        )
        summary["linhas_agregadas"] += row_count
        status = attendance_status or "SEM_CATEGORIA"
        summary["convocados_por_categoria_comparecimento"][status] = int(called_count)

    result = {"linhas_agregadas": aggregate_rows, "por_recurso": by_resource}
    if uf:
        result["uf"] = uf
    return result


@router.get("/importacoes", response_model=list[ImportOut])
def list_imports(
    limit: int = Query(default=50, ge=1, le=200), database: Session = Depends(get_db)
) -> list[ImportRun]:
    return list(database.scalars(select(ImportRun).order_by(ImportRun.started_at.desc()).limit(limit)))


@router.get("/fontes")
def list_sources(database: Session = Depends(get_db)) -> list[dict]:
    sources = database.scalars(select(DataSource).order_by(DataSource.collected_at.desc())).all()
    return [
        {
            "id": source.id,
            "provider": source.provider,
            "dataset_id": source.dataset_id,
            "resource_id": source.resource_id,
            "resource_name": source.resource_name,
            "url": source.url,
            "collected_at": source.collected_at,
        }
        for source in sources
    ]


def check_database(database: Session = Depends(get_db)) -> dict:
    try:
        database.execute(text("SELECT 1"))
    except Exception as error:
        raise HTTPException(status_code=503, detail="Banco de dados indisponível.") from error
    return {"status": "ok", "checked_at": datetime.utcnow()}