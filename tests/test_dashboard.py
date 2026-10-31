import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import security
from app.core.config import Settings
from app.database import Base, get_db
from app.main import app as fastapi_app
from app.models import (
    DataSource,
    Election,
    ImportRun,
    MesarioAggregate,
    PollingLocation,
    PollingSection,
    SectionVote,
)
from app import routers


@pytest.fixture
def dashboard_client(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    database = Session(engine)
    source = DataSource(
        provider="TSE",
        dataset_id="dataset",
        resource_id="resource",
        resource_name="mesarios_SP.csv",
        url="https://example.test/mesarios.csv",
    )
    database.add(source)
    database.flush()
    map_import = ImportRun(
        dataset_id="eleitorado-2026",
        status="SUCCEEDED",
    )
    database.add(map_import)
    database.flush()
    database.add_all(
        [
            MesarioAggregate(
                source_id=source.id,
                record_hash="a" * 64,
                election_year=2026,
                turn=1,
                uf="SP",
                municipality_code="71072",
                municipality="São Paulo",
                electoral_zone=12,
                mesario_type="CONVOCADO",
                gender="FEMININO",
                marital_status="SOLTEIRO(A)",
                age_range="25 a 29 anos",
                education_level="ENSINO SUPERIOR COMPLETO",
                attendance_status="SIM",
                called_count=4,
                raw_data={"CAMPO_ORIGINAL": "campaign_alpha"},
            ),
            MesarioAggregate(
                source_id=source.id,
                record_hash="b" * 64,
                election_year=2026,
                turn=2,
                uf="RJ",
                municipality_code="60011",
                municipality="Rio de Janeiro",
                electoral_zone=3,
                mesario_type="VOLUNTARIO",
                gender="MASCULINO",
                marital_status="CASADO(A)",
                age_range="40 a 44 anos",
                education_level="ENSINO MÉDIO COMPLETO",
                attendance_status="NAO",
                called_count=7,
                raw_data={"CAMPO_ORIGINAL": "campaign_beta"},
            ),
        ]
    )
    location = PollingLocation(
        location_key="c" * 64,
        import_id=map_import.id,
        election_year=2026,
        uf="SP",
        municipality_code="71072",
        municipality="São Paulo",
        electoral_zone=12,
        polling_place_number=1490,
        name="Colégio Central",
        address="Rua das Flores, 123",
        neighborhood="Centro",
        postal_code="01001000",
        latitude=-23.55,
        longitude=-46.63,
        situation="ATIVO",
    )
    database.add(location)
    database.flush()
    database.add_all(
        [
            PollingSection(
                section_key="d" * 64,
                import_id=map_import.id,
                location_key=location.location_key,
                section_number="001",
                election_year=2026,
                uf="SP",
                municipality_code="71072",
                municipality="São Paulo",
                electoral_zone=12,
                polling_place_number=1490,
                polling_place_name="Colégio Central",
                address="Rua das Flores, 123",
                neighborhood="Centro",
                postal_code="01001000",
                latitude=-23.55,
                longitude=-46.63,
                situation="ATIVO",
            ),
            PollingSection(
                section_key="e" * 64,
                import_id=map_import.id,
                location_key=location.location_key,
                section_number="002",
                election_year=2026,
                uf="SP",
                municipality_code="71072",
                municipality="São Paulo",
                electoral_zone=12,
                polling_place_number=1490,
                polling_place_name="Colégio Central",
                address="Rua das Flores, 123",
                neighborhood="Centro",
                postal_code="01001000",
                latitude=-23.55,
                longitude=-46.63,
                situation="ATIVO",
            ),
        ]
    )
    database.commit()

    def override_get_db():
        yield database

    monkeypatch.setattr(security, "get_settings", lambda: Settings(api_key="test-key"))
    monkeypatch.setattr(
        routers,
        "get_settings",
        lambda: Settings(api_key="test-key", election_year=2026),
    )
    fastapi_app.dependency_overrides[get_db] = override_get_db
    with TestClient(fastapi_app) as client:
        client.database = database
        yield client
    fastapi_app.dependency_overrides.clear()
    database.close()
    engine.dispose()


def add_section_vote_fixtures(database):
    election = Election(
        election_year=2026,
        election_code="2026",
        election_type="ORDINARIA",
        name="Eleições 2026",
    )
    database.add(election)
    database.flush()
    source = database.query(DataSource).filter_by(dataset_id="dataset").one()
    import_run = database.query(ImportRun).filter_by(dataset_id="eleitorado-2026").one()
    vote_data = [
        ("001", "1", "Presidente", "10", "Candidato A", "CANDIDATO", 20, "ABC"),
        ("002", "1", "Presidente", "10", "Candidato A", "CANDIDATO", 30, "ABC"),
        ("001", "1", "Presidente", "11", "Candidato B", "CANDIDATO", 5, "XYZ"),
        ("002", "1", "Presidente", "11", "Candidato B", "CANDIDATO", 7, "XYZ"),
        ("001", "1", "Presidente", "95", "Votos em branco", "BRANCO", 1, None),
        ("002", "1", "Presidente", "95", "Votos em branco", "BRANCO", 2, None),
        ("001", "1", "Presidente", "96", "Votos nulos", "NULO", 2, None),
        ("002", "1", "Presidente", "96", "Votos nulos", "NULO", 3, None),
        ("001", "3", "Governador", "20", "Candidato C", "CANDIDATO", 8, "DEF"),
    ]
    database.add_all(
        SectionVote(
            record_key=f"{index:064x}",
            election_id=election.id,
            import_id=import_run.id,
            source_id=source.id,
            election_year=2026,
            turn=1,
            uf="SP",
            municipality_code="71072",
            municipality="São Paulo",
            electoral_zone=12,
            section_number=section_number,
            polling_place_number="1490",
            office_code=office_code,
            office_name=office_name,
            vote_code=vote_code,
            vote_name=vote_name,
            vote_type=vote_type,
            candidate_registration_number=vote_code if vote_type == "CANDIDATO" else None,
            party_number=None,
            party_abbreviation=party,
            party_name=None,
            votes=votes,
        )
        for index, (
            section_number,
            office_code,
            office_name,
            vote_code,
            vote_name,
            vote_type,
            votes,
            party,
        ) in enumerate(vote_data, start=1)
    )
    database.commit()


def test_dashboard_is_served_at_root(dashboard_client):
    response = dashboard_client.get("/")

    assert response.status_code == 200
    assert "Dados, com clareza." in response.text
    assert 'id="uf" name="uf"' in response.text
    assert 'id="municipality" name="municipality"' in response.text
    assert response.headers["cache-control"] == "no-store, no-cache, must-revalidate, max-age=0"


def test_visualizacao_returns_filtered_totals_and_full_record(dashboard_client):
    response = dashboard_client.get(
        "/api/v1/mesarios/visualizacao",
        params={"uf": "sp", "search": "campaign_alpha"},
        headers={"X-API-Key": "test-key"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["total_convocados"] == 4
    assert payload["por_comparecimento"] == [{"categoria": "SIM", "convocados": 4}]
    assert payload["items"][0]["raw_data"] == {"CAMPO_ORIGINAL": "campaign_alpha"}


def test_visualizacao_filters_by_gender_marital_status_age_and_education(dashboard_client):
    response = dashboard_client.get(
        "/api/v1/mesarios/visualizacao",
        params={
            "gender": "feminino",
            "marital_status": "solteiro",
            "age_range": "25 a 29",
            "education_level": "superior completo",
        },
        headers={"X-API-Key": "test-key"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["gender"] == "FEMININO"
    assert payload["items"][0]["marital_status"] == "SOLTEIRO(A)"
    assert payload["items"][0]["age_range"] == "25 a 29 anos"
    assert payload["items"][0]["education_level"] == "ENSINO SUPERIOR COMPLETO"


def test_mesario_filter_options_return_distinct_nonempty_values(dashboard_client):
    response = dashboard_client.get(
        "/api/v1/mesarios/opcoes",
        headers={"X-API-Key": "test-key"},
    )

    assert response.status_code == 200
    options = response.json()
    assert options == {
        "gender": ["FEMININO", "MASCULINO"],
        "marital_status": ["CASADO(A)", "SOLTEIRO(A)"],
        "age_range": ["25 a 29 anos", "40 a 44 anos"],
        "education_level": ["ENSINO MÉDIO COMPLETO", "ENSINO SUPERIOR COMPLETO"],
        "ufs": ["RJ", "SP"],
        "municipalities": ["Rio de Janeiro", "São Paulo"],
    }


def test_mesario_filter_options_limit_municipalities_to_selected_uf(dashboard_client):
    response = dashboard_client.get(
        "/api/v1/mesarios/opcoes",
        params={"uf": "sp"},
        headers={"X-API-Key": "test-key"},
    )

    assert response.status_code == 200
    options = response.json()
    assert options["ufs"] == ["RJ", "SP"]
    assert options["municipalities"] == ["São Paulo"]


def test_dashboard_grid_exposes_demographic_filters(dashboard_client):
    response = dashboard_client.get("/")

    assert response.status_code == 200
    assert '<select id="gender" name="gender"' in response.text
    assert '<select id="marital-status" name="marital_status"' in response.text
    assert '<select id="age-range" name="age_range"' in response.text
    assert '<select id="education-level" name="education_level"' in response.text
    assert '<select id="uf" name="uf"' in response.text
    assert '<select id="municipality" name="municipality"' in response.text
    assert "button-spinner" in response.text
    assert "is-loading::after" in response.text


def test_visualizacao_requires_api_key(dashboard_client):
    response = dashboard_client.get("/api/v1/mesarios/visualizacao")

    assert response.status_code == 401


def test_map_returns_filtered_locations_and_section_totals(dashboard_client):
    response = dashboard_client.get(
        "/api/v1/mapa/locais",
        params={
            "uf": "sp",
            "municipality": "São Paulo",
            "zoom": 12,
            "south": -24,
            "west": -47,
            "north": -22,
            "east": -45,
        },
        headers={"X-API-Key": "test-key"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_locations"] == 1
    assert payload["total_sections"] == 2
    assert payload["clustered"] is False
    assert payload["points"][0]["address"] == "Rua das Flores, 123"
    assert payload["points"][0]["section_count"] == 2


def test_map_location_details_return_full_address_for_each_section(dashboard_client):
    response = dashboard_client.get(
        f"/api/v1/mapa/locais/{'c' * 64}/secoes",
        headers={"X-API-Key": "test-key"},
    )

    assert response.status_code == 200
    assert [section["section_number"] for section in response.json()] == ["001", "002"]
    assert all(section["address"] == "Rua das Flores, 123" for section in response.json())
    assert all(section["postal_code"] == "01001000" for section in response.json())


def test_sections_grid_returns_section_addresses_and_supports_filters(dashboard_client):
    response = dashboard_client.get(
        "/api/v1/mapa/secoes",
        params={
            "uf": "sp",
            "municipality": "São Paulo",
            "zone": 12,
            "search": "Flores",
            "offset": 0,
            "limit": 1,
        },
        headers={"X-API-Key": "test-key"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert len(payload["items"]) == 1
    section = payload["items"][0]
    assert section["section_number"] == "001"
    assert section["polling_place_name"] == "Colégio Central"
    assert section["address"] == "Rua das Flores, 123"
    assert section["postal_code"] == "01001000"


def test_section_grid_filter_options_are_scoped_to_uf(dashboard_client):
    response = dashboard_client.get(
        "/api/v1/mapa/secoes/opcoes",
        params={"uf": "sp"},
        headers={"X-API-Key": "test-key"},
    )

    assert response.status_code == 200
    assert response.json() == {"ufs": ["SP"], "municipalities": ["São Paulo"]}


def test_section_grid_options_only_load_municipalities_after_uf_selection(dashboard_client):
    response = dashboard_client.get(
        "/api/v1/mapa/secoes/opcoes",
        headers={"X-API-Key": "test-key"},
    )

    assert response.status_code == 200
    assert response.json() == {"ufs": ["SP"], "municipalities": []}


def test_sections_grid_returns_empty_page_for_uf_without_imported_sections(dashboard_client):
    response = dashboard_client.get(
        "/api/v1/mapa/secoes",
        params={"uf": "AC"},
        headers={"X-API-Key": "test-key"},
    )

    assert response.status_code == 200
    assert response.json() == {"total": 0, "items": []}


def test_sections_grid_requires_api_key(dashboard_client):
    response = dashboard_client.get("/api/v1/mapa/secoes")

    assert response.status_code == 401


def test_start_results_import_uses_selected_year_dataset_and_exposes_status(
    dashboard_client, monkeypatch
):
    task_arguments = []

    def fake_import(*args):
        task_arguments.append(args)

    monkeypatch.setattr(routers, "import_tse_section_votes", fake_import)
    response = dashboard_client.post(
        "/api/v1/resultados/importacoes/tse",
        params={"election_year": 2024},
        headers={"X-API-Key": "test-key"},
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["dataset_id"] == "resultados-2024"
    assert payload["status"] == "RUNNING"
    assert task_arguments[0][2:] == ("resultados-2024", 2024, None)

    status = dashboard_client.get(
        f"/api/v1/resultados/importacoes/{payload['id']}",
        headers={"X-API-Key": "test-key"},
    )
    assert status.status_code == 200
    assert status.json()["dataset_id"] == "resultados-2024"


def test_start_results_import_can_be_limited_to_one_uf(dashboard_client, monkeypatch):
    task_arguments = []

    def fake_import(*args):
        task_arguments.append(args)

    monkeypatch.setattr(routers, "import_tse_section_votes", fake_import)

    response = dashboard_client.post(
        "/api/v1/resultados/importacoes/tse",
        params={"election_year": 2026, "uf": "sp"},
        headers={"X-API-Key": "test-key"},
    )

    assert response.status_code == 202
    assert response.json()["dataset_id"] == "resultados-2026-uf-SP"
    assert task_arguments[0][2:] == ("resultados-2026", 2026, "SP")


def test_results_import_rejects_overlapping_runs_for_the_same_year(
    dashboard_client, monkeypatch
):
    task_arguments = []

    def fake_import(*args):
        task_arguments.append(args)

    monkeypatch.setattr(routers, "import_tse_section_votes", fake_import)
    response = dashboard_client.post(
        "/api/v1/resultados/importacoes/tse",
        params={"election_year": 2026, "uf": "SP"},
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 202

    overlapping_response = dashboard_client.post(
        "/api/v1/resultados/importacoes/tse",
        params={"election_year": 2026},
        headers={"X-API-Key": "test-key"},
    )

    assert overlapping_response.status_code == 409
    assert "execução" in overlapping_response.json()["detail"]
    assert len(task_arguments) == 1


def test_results_import_is_blocked_after_successful_import_for_same_scope(dashboard_client):
    response = dashboard_client.post(
        "/api/v1/resultados/importacoes/tse",
        params={"election_year": 2026},
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 202
    run_id = response.json()["id"]

    run = dashboard_client.database.get(ImportRun, run_id)
    run.status = "SUCCEEDED"
    dashboard_client.database.commit()

    repeat_response = dashboard_client.post(
        "/api/v1/resultados/importacoes/tse",
        params={"election_year": 2026},
        headers={"X-API-Key": "test-key"},
    )

    assert repeat_response.status_code == 409
    assert "já foram importados com sucesso" in repeat_response.json()["detail"]


def test_successful_national_import_blocks_state_import_for_same_year(dashboard_client):
    response = dashboard_client.post(
        "/api/v1/resultados/importacoes/tse",
        params={"election_year": 2026},
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 202
    run_id = response.json()["id"]

    run = dashboard_client.database.get(ImportRun, run_id)
    run.status = "SUCCEEDED"
    dashboard_client.database.commit()

    state_response = dashboard_client.post(
        "/api/v1/resultados/importacoes/tse",
        params={"election_year": 2026, "uf": "SP"},
        headers={"X-API-Key": "test-key"},
    )

    assert state_response.status_code == 409
    assert "Brasil todo" in state_response.json()["detail"]


def test_dashboard_has_an_independent_sections_grid_tab(dashboard_client):
    response = dashboard_client.get("/")

    assert response.status_code == 200
    assert 'id="sections-tab"' in response.text
    assert 'id="sections-view"' in response.text
    assert 'id="sections-results"' in response.text
    assert 'id="results-import"' in response.text
    assert 'id="results-election-year"' in response.text
    assert 'id="results-uf"' in response.text
    assert "A importação dos votos não é automática" in response.text


def test_national_map_groups_markers_without_dropping_section_totals(dashboard_client):
    response = dashboard_client.get(
        "/api/v1/mapa/locais",
        params={
            "zoom": 4,
            "south": -35,
            "west": -75,
            "north": 6,
            "east": -30,
        },
        headers={"X-API-Key": "test-key"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["clustered"] is True
    assert sum(point["local_count"] for point in payload["points"]) == 1
    assert sum(point["section_count"] for point in payload["points"]) == 2


def test_map_accepts_longitudes_outside_world_bounds_from_wrapped_map(dashboard_client):
    response = dashboard_client.get(
        "/api/v1/mapa/locais",
        params={
            "zoom": 2,
            "south": -80.5,
            "west": -284.4,
            "north": 7,
            "east": 142.3,
        },
        headers={"X-API-Key": "test-key"},
    )

    assert response.status_code == 200
    assert response.json()["total_locations"] == 1
    assert response.json()["points"]


def test_map_viewport_crossing_dateline_normalizes_longitudes(dashboard_client):
    response = dashboard_client.get(
        "/api/v1/mapa/locais",
        params={
            "zoom": 12,
            "south": -30,
            "west": -200,
            "north": -20,
            "east": -30,
        },
        headers={"X-API-Key": "test-key"},
    )

    assert response.status_code == 200
    assert response.json()["total_locations"] == 1
    assert len(response.json()["points"]) == 1


def test_vote_map_tab_exposes_dependent_election_filters_and_map(dashboard_client):
    response = dashboard_client.get("/")

    assert response.status_code == 200
    assert 'id="vote-map-tab"' in response.text
    assert 'id="vote-map-view"' in response.text
    assert 'id="vote-map-office"' in response.text
    assert 'id="vote-map-candidate"' in response.text
    assert 'id="vote-map-candidate-preview"' in response.text
    assert 'id="vote-map-type"' in response.text
    assert 'id="vote-map-details-results"' in response.text


def test_vote_map_options_and_candidates_are_scoped_by_election_and_office(dashboard_client):
    add_section_vote_fixtures(dashboard_client.database)

    options = dashboard_client.get(
        "/api/v1/resultados/mapa/opcoes",
        params={"election_year": 2026, "turn": 1},
        headers={"X-API-Key": "test-key"},
    )
    assert options.status_code == 200
    assert options.json() == {
        "years": [2026],
        "turns": [1],
        "offices": [
            {"code": "3", "name": "Governador"},
            {"code": "1", "name": "Presidente"},
        ],
        "ufs": ["SP"],
        "municipalities": [],
    }

    candidates = dashboard_client.get(
        "/api/v1/resultados/mapa/candidatos",
        params={"election_year": 2026, "turn": 1, "office_code": "1"},
        headers={"X-API-Key": "test-key"},
    )
    assert candidates.status_code == 200
    assert [candidate["code"] for candidate in candidates.json()] == ["10", "11"]
    assert all(candidate["party"] for candidate in candidates.json())
    assert candidates.json()[0]["photo_url"] == (
        "https://josedarci.com/eleicoes2026/fotos-candidatos/BR/FBR10_div.jpg"
    )

    state_candidates = dashboard_client.get(
        "/api/v1/resultados/mapa/candidatos",
        params={"election_year": 2026, "turn": 1, "office_code": "3"},
        headers={"X-API-Key": "test-key"},
    )
    assert state_candidates.status_code == 200
    assert state_candidates.json()[0]["photo_url"] == (
        "https://josedarci.com/eleicoes2026/fotos-candidatos/SP/FSP20_div.jpg"
    )


def test_vote_map_returns_filtered_totals_and_details_by_section(dashboard_client):
    add_section_vote_fixtures(dashboard_client.database)

    response = dashboard_client.get(
        "/api/v1/resultados/mapa",
        params={
            "election_year": 2026,
            "turn": 1,
            "office_code": "1",
            "vote_type": "CANDIDATO",
            "vote_code": "10",
            "zoom": 12,
            "south": -24,
            "west": -47,
            "north": -22,
            "east": -45,
        },
        headers={"X-API-Key": "test-key"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_votes"] == 50
    assert payload["total_sections"] == 2
    assert payload["total_locations"] == 1
    assert payload["clustered"] is False
    assert len(payload["points"]) == 1
    assert payload["points"][0]["votes"] == 50

    details = dashboard_client.get(
        f"/api/v1/resultados/mapa/locais/{'c' * 64}/secoes",
        params={
            "election_year": 2026,
            "turn": 1,
            "office_code": "1",
            "vote_type": "CANDIDATO",
            "vote_code": "10",
        },
        headers={"X-API-Key": "test-key"},
    )
    assert details.status_code == 200
    assert [item["section_number"] for item in details.json()["items"]] == ["001", "002"]
    assert [item["votes"] for item in details.json()["items"]] == [20, 30]


def test_vote_map_can_filter_blank_and_null_votes_without_a_candidate(dashboard_client):
    add_section_vote_fixtures(dashboard_client.database)

    for vote_type, expected_total in (("BRANCO", 3), ("NULO", 5)):
        response = dashboard_client.get(
            "/api/v1/resultados/mapa",
            params={
                "election_year": 2026,
                "turn": 1,
                "office_code": "1",
                "vote_type": vote_type,
                "uf": "sp",
                "municipality": "São Paulo",
                "zone": 12,
                "zoom": 12,
            },
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 200
        assert response.json()["total_votes"] == expected_total
        assert response.json()["total_locations"] == 1


def test_vote_map_requires_api_key(dashboard_client):
    response = dashboard_client.get(
        "/api/v1/resultados/mapa/opcoes",
    )

    assert response.status_code == 401
