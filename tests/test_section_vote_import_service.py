from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

from app.database import Base
from app.models import DataSource, Election, ImportRun, SectionVote
from app.services.section_vote_import_service import (
    _import_resources,
    _normalized_vote,
    _section_vote_resources,
)


def test_section_vote_resources_prefer_state_files_and_exclude_detail_and_brazil_file():
    resources = [
        {
            "name": "Presidente - Votação por seção eleitoral - 2026",
            "url": "https://cdn.tse.jus.br/votacao_secao_2026_BR.zip",
        },
        {
            "name": "SP - Votação por seção eleitoral - 2026",
            "url": "https://cdn.tse.jus.br/votacao_secao_2026_SP.zip",
        },
        {
            "name": "Detalhe da apuração por seção eleitoral",
            "url": "https://cdn.tse.jus.br/detalhe_votacao_secao_2026.zip",
        },
    ]

    assert _section_vote_resources(resources) == [resources[1]]
    assert _section_vote_resources(resources, "sp") == [resources[1]]
    assert _section_vote_resources(resources, "RJ") == []


def test_normalized_section_vote_preserves_candidate_and_section_identity():
    vote = _normalized_vote(
        {
            "ANO_ELEICAO": "2026",
            "CD_ELEICAO": "999",
            "NR_TURNO": "1",
            "SG_UF": "sp",
            "CD_MUNICIPIO": "71072",
            "NM_MUNICIPIO": "São Paulo",
            "NR_ZONA": "12",
            "NR_SECAO": "0012",
            "NR_LOCAL_VOTACAO": "01490",
            "CD_CARGO": "3",
            "DS_CARGO": "Governador",
            "NR_VOTAVEL": "12345",
            "NM_VOTAVEL": "CANDIDATO EXEMPLO",
            "SQ_CANDIDATO": "123456789012",
            "NR_PARTIDO": "10",
            "SG_PARTIDO": "ABC",
            "NM_PARTIDO": "Partido Exemplo",
            "QT_VOTOS": "27",
        },
        election_year=2026,
        import_id=7,
        source_id=8,
        election_id=9,
    )

    assert vote is not None
    assert vote["uf"] == "SP"
    assert vote["municipality_code"] == "71072"
    assert vote["section_number"] == "0012"
    assert vote["polling_place_number"] == "01490"
    assert vote["office_name"] == "Governador"
    assert vote["vote_code"] == "12345"
    assert vote["vote_name"] == "CANDIDATO EXEMPLO"
    assert vote["vote_type"] == "CANDIDATO"
    assert vote["party_abbreviation"] == "ABC"
    assert vote["votes"] == 27


def test_import_resources_persists_votes_with_source_and_election():
    class FakeTSEClient:
        def get_resources(self, dataset_id):
            assert dataset_id == "resultados-2026"
            return [
                {
                    "id": "resource-sp",
                    "name": "SP - Votação por seção eleitoral - 2026",
                    "url": "https://example.test/votacao_secao_2026_SP.zip",
                },
                {
                    "id": "resource-br",
                    "name": "Presidente - Votação por seção eleitoral - 2026",
                    "url": "https://example.test/votacao_secao_2026_BR.zip",
                },
            ]

        def iter_csv_records(self, url):
            assert url.endswith("_SP.zip")
            yield {
                "ANO_ELEICAO": "2026",
                "CD_ELEICAO": "999",
                "DS_ELEICAO": "Eleições Gerais 2026",
                "NR_TURNO": "1",
                "SG_UF": "SP",
                "CD_MUNICIPIO": "71072",
                "NM_MUNICIPIO": "São Paulo",
                "NR_ZONA": "12",
                "NR_SECAO": "001",
                "CD_CARGO": "3",
                "DS_CARGO": "Governador",
                "NR_VOTAVEL": "12345",
                "NM_VOTAVEL": "CANDIDATO EXEMPLO",
                "QT_VOTOS": "27",
            }

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as database:
        run = ImportRun(dataset_id="resultados-2026", status="RUNNING")
        database.add(run)
        database.commit()

        _import_resources(
            database,
            run,
            FakeTSEClient(),
            "resultados-2026",
            2026,
        )

        vote = database.scalar(select(SectionVote))
        assert vote is not None
        assert vote.votes == 27
        assert vote.vote_name == "CANDIDATO EXEMPLO"
        assert vote.import_id == run.id
        assert database.scalar(select(func.count()).select_from(Election)) == 1
        assert database.scalar(select(func.count()).select_from(DataSource)) == 1
        assert run.records_processed == 1
    engine.dispose()


def test_empty_reimport_keeps_the_last_saved_results():
    class FakeTSEClient:
        def get_resources(self, dataset_id):
            return [
                {
                    "id": "resource-sp",
                    "name": "SP - Votação por seção eleitoral - 2026",
                    "url": "https://example.test/votacao_secao_2026_SP.zip",
                }
            ]

        def iter_csv_records(self, url):
            return iter(())

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as database:
        previous_run = ImportRun(dataset_id="resultados-2026", status="RUNNING")
        database.add(previous_run)
        database.commit()
        source = DataSource(
            dataset_id="resultados-2026",
            resource_id="resource-sp",
            resource_name="SP - Votação por seção eleitoral - 2026",
            url="https://example.test/votacao_secao_2026_SP.zip",
        )
        election = Election(
            election_year=2026,
            election_code="999",
            name="Eleições Gerais 2026",
        )
        database.add_all([source, election])
        database.flush()
        database.add(
            SectionVote(
                record_key="a" * 64,
                election_id=election.id,
                import_id=previous_run.id,
                source_id=source.id,
                election_year=2026,
                turn=1,
                uf="SP",
                municipality_code="71072",
                municipality="São Paulo",
                electoral_zone=12,
                section_number="001",
                office_code="3",
                office_name="Governador",
                vote_code="12345",
                vote_name="CANDIDATO EXEMPLO",
                vote_type="CANDIDATO",
                votes=27,
            )
        )
        database.commit()

        new_run = ImportRun(dataset_id="resultados-2026", status="RUNNING")
        database.add(new_run)
        database.commit()
        try:
            _import_resources(database, new_run, FakeTSEClient(), "resultados-2026", 2026)
        except RuntimeError as error:
            assert "não contêm resultados válidos" in str(error)
        else:
            raise AssertionError("A importação vazia deveria falhar.")

        saved = database.scalar(select(SectionVote))
        assert saved is not None
        assert saved.import_id == previous_run.id
        assert saved.votes == 27
    engine.dispose()
