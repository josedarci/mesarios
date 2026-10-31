from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

from app.database import Base
from app.models import ImportRun, PollingLocation, PollingSection
from app.services.location_import_service import (
    _flush_batches,
    _normalized_location,
)


def test_normalized_location_preserves_section_address_and_parses_coordinates():
    location_and_section = _normalized_location(
        {
            "SG_UF": "sp",
            "CD_MUNICIPIO": "71072",
            "NM_MUNICIPIO": "São Paulo",
            "NR_ZONA": "12",
            "NR_LOCAL_VOTACAO": "1490",
            "NR_SECAO": "001",
            "NM_LOCAL_VOTACAO": "Colégio Central",
            "DS_ENDERECO": "Rua das Flores, 123",
            "NM_BAIRRO": "Centro",
            "NR_CEP": "01001000",
            "NR_LATITUDE": "-23,550000",
            "NR_LONGITUDE": "-46,630000",
            "DS_SITU_LOCAL_VOTACAO": "ATIVO",
        },
        election_year=2026,
        import_id=1,
    )

    assert location_and_section is not None
    location, section = location_and_section
    assert location["uf"] == "SP"
    assert location["latitude"] == -23.55
    assert location["longitude"] == -46.63
    assert section["section_number"] == "001"
    assert len(section["section_key"]) == 64
    assert section["address"] == "Rua das Flores, 123"
    assert section["neighborhood"] == "Centro"
    assert section["postal_code"] == "01001000"


def test_normalized_location_keeps_address_even_when_coordinates_are_missing():
    location_and_section = _normalized_location(
        {
            "SG_UF": "ZZ",
            "CD_MUNICIPIO": "99999",
            "NM_MUNICIPIO": "Exterior",
            "NR_ZONA": "1",
            "NR_LOCAL_VOTACAO": "7",
            "NR_SECAO": "001",
            "NM_LOCAL_VOTACAO": "Consulado",
            "DS_ENDERECO": "Avenida Central, 1",
        },
        election_year=2026,
        import_id=1,
    )

    assert location_and_section is not None
    location, section = location_and_section
    assert location["latitude"] is None
    assert section["address"] == "Avenida Central, 1"


def test_import_batches_persist_and_update_full_section_addresses():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as database:
        run = ImportRun(
            dataset_id="eleitorado-2026",
            status="RUNNING",
        )
        database.add(run)
        database.flush()
        normalized = _normalized_location(
            {
                "SG_UF": "SP",
                "CD_MUNICIPIO": "71072",
                "NM_MUNICIPIO": "São Paulo",
                "NR_ZONA": "12",
                "NR_LOCAL_VOTACAO": "1490",
                "NR_SECAO": "001",
                "NM_LOCAL_VOTACAO": "Colégio Central",
                "DS_ENDERECO": "Rua das Flores, 123",
                "NM_BAIRRO": "Centro",
                "NR_CEP": "01001000",
                "NR_LATITUDE": "-23,55",
                "NR_LONGITUDE": "-46,63",
            },
            election_year=2026,
            import_id=run.id,
        )
        assert normalized is not None
        location, section = normalized
        _flush_batches(database, {location["location_key"]: location}, {section["section_key"]: section})

        updated_location, updated_section = _normalized_location(
            {
                "SG_UF": "SP",
                "CD_MUNICIPIO": "71072",
                "NM_MUNICIPIO": "São Paulo",
                "NR_ZONA": "12",
                "NR_LOCAL_VOTACAO": "1490",
                "NR_SECAO": "001",
                "NM_LOCAL_VOTACAO": "Colégio Central",
                "DS_ENDERECO": "Rua das Flores, 125",
                "NM_BAIRRO": "Centro",
                "NR_CEP": "01001000",
            },
            election_year=2026,
            import_id=run.id,
        )
        assert updated_location is not None and updated_section is not None
        _flush_batches(
            database,
            {updated_location["location_key"]: updated_location},
            {updated_section["section_key"]: updated_section},
        )

        assert database.scalar(select(func.count()).select_from(PollingLocation)) == 1
        assert database.scalar(select(func.count()).select_from(PollingSection)) == 1
        assert database.scalar(select(PollingSection.address)) == "Rua das Flores, 125"
    engine.dispose()
