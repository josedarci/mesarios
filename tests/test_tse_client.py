import zipfile
from collections import Counter

from app.services.import_service import _record_hash
from app.services.tse_client import _read_csv_file, normalize_record


def _write_zip(path, files):
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)


def test_read_csv_file_decodes_latin1_and_skips_national_duplicate(tmp_path):
    path = tmp_path / "dados.zip"
    _write_zip(
        path,
        {
            "mesarios_SP.csv": '"SG_UF";"NM_MUNICIPIO"\n"SP";"SÃO PAULO"\n'.encode("latin-1"),
            "mesarios_BRASIL.csv": '"SG_UF";"NM_MUNICIPIO"\n"SP";"SÃO PAULO"\n'.encode("latin-1"),
            "leiame.pdf": b"%PDF",
        },
    )

    assert list(_read_csv_file(str(path))) == [{"SG_UF": "SP", "NM_MUNICIPIO": "SÃO PAULO"}]


def test_read_csv_file_uses_national_file_when_it_is_the_only_csv(tmp_path):
    path = tmp_path / "dados.zip"
    _write_zip(path, {"mesarios_BRASIL.csv": '"SG_UF"\n"SP"\n'.encode("latin-1")})

    assert list(_read_csv_file(str(path))) == [{"SG_UF": "SP"}]


def test_record_hash_keeps_identical_rows_as_distinct_records():
    row = {"SG_UF": "GO", "QT_CONVOCADOS": "1"}
    occurrences = Counter()

    assert _record_hash("recurso", row, occurrences) != _record_hash("recurso", row, occurrences)


def test_record_hash_is_stable_across_imports_and_generation_dates():
    first = {"DT_GERACAO": "30/10/2026", "HH_GERACAO": "06:52:30", "SG_UF": "GO"}
    second = {"DT_GERACAO": "31/10/2026", "HH_GERACAO": "07:10:00", "SG_UF": "GO"}

    assert _record_hash("recurso", first, Counter()) == _record_hash("recurso", second, Counter())


def test_normalize_record_reads_tse_aggregate_headers_without_inventing_person_data():
    record = normalize_record(
        {
            "ANO_ELEICAO": "2026",
            "NR_TURNO": "2",
            "SG_UF": "sp",
            "NM_MUNICIPIO": "São Paulo",
            "CD_MUNICIPIO": "71072",
            "NR_ZONA": "12",
            "DS_TIPO_MESARIO": "CONVOCADO",
            "DS_ATIVIDADE_ELEITORAL": "MESA RECEPTORA",
            "DS_GENERO": "FEMININO",
            "ST_VOLUNTARIO": "SIM",
            "ST_COMPARECIMENTO": "SIM",
            "QT_CONVOCADOS": "18",
        },
        election_year=2026,
    )

    assert record["election_year"] == 2026
    assert record["turn"] == 2
    assert record["uf"] == "SP"
    assert record["municipality"] == "São Paulo"
    assert record["municipality_code"] == "71072"
    assert record["electoral_zone"] == 12
    assert record["mesario_type"] == "CONVOCADO"
    assert record["electoral_activity"] == "MESA RECEPTORA"
    assert record["gender"] == "FEMININO"
    assert record["volunteer_status"] == "SIM"
    assert record["attendance_status"] == "SIM"
    assert record["called_count"] == 18
    assert "full_name" not in record
    assert "electoral_section" not in record


def test_normalize_record_leaves_unknown_columns_unmapped():
    record = normalize_record({"COLUNA_NOVA": "valor"}, election_year=2026)

    assert record["uf"] is None
    assert record["called_count"] is None
    assert record["raw_data"] == {"COLUNA_NOVA": "valor"}