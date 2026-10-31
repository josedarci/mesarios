import csv
import io
import os
import tempfile
import unicodedata
import zipfile
from collections.abc import Iterator
from typing import Any

import httpx


CSV_ENCODING = "latin-1"


class TSEClientError(RuntimeError):
    pass


def _normalized_key(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.strip().lower())
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(without_accents.replace("_", " ").split())


def _field(row: dict[str, Any], names: tuple[str, ...]) -> str | None:
    normalized = {_normalized_key(str(key)): value for key, value in row.items() if key is not None}
    for name in names:
        value = normalized.get(_normalized_key(name))
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


def normalize_record(row: dict[str, Any], election_year: int) -> dict[str, Any]:
    uf = _field(row, ("SG_UF", "UF"))
    return {
        "election_year": _integer(_field(row, ("ANO_ELEICAO",))) or election_year,
        "turn": _integer(_field(row, ("NR_TURNO",))),
        "uf": uf.upper()[:2] if uf else None,
        "municipality_code": _field(row, ("CD_MUNICIPIO", "CD_MUN", "CODIGO MUNICIPIO")),
        "municipality": _field(row, ("NM_MUNICIPIO", "MUNICIPIO", "NOME MUNICIPIO")),
        "electoral_zone": _integer(_field(row, ("NR_ZONA", "ZONA", "NR_ZONA_ELEITORAL"))),
        "mesario_type": _field(row, ("DS_TIPO_MESARIO",)),
        "electoral_activity": _field(row, ("DS_ATIVIDADE_ELEITORAL",)),
        "special_function": _field(row, ("DS_FUNCAO_ESPECIAL",)),
        "gender": _field(row, ("DS_GENERO",)),
        "marital_status": _field(row, ("DS_ESTADO_CIVIL",)),
        "age_range": _field(row, ("DS_FAIXA_ETARIA",)),
        "education_level": _field(row, ("DS_GRAU_INSTRUCAO",)),
        "race_color": _field(row, ("DS_COR_RACA",)),
        "quilombola_status": _field(row, ("DS_QUILOMBOLA",)),
        "libras_interpreter_status": _field(row, ("DS_INTERPRETE_LIBRAS",)),
        "gender_identity": _field(row, ("DS_IDENTIDADE_GENERO",)),
        "volunteer_status": _field(row, ("ST_VOLUNTARIO",)),
        "attendance_status": _field(row, ("ST_COMPARECIMENTO",)),
        "called_count": _integer(_field(row, ("QT_CONVOCADOS",))),
        "raw_data": {str(key): value for key, value in row.items() if key is not None},
    }


class TSEClient:
    def __init__(self, ckan_url: str, timeout_seconds: float = 120) -> None:
        self.ckan_url = ckan_url
        self.timeout_seconds = timeout_seconds

    def get_resources(self, dataset_id: str) -> list[dict[str, Any]]:
        response = httpx.get(
            self.ckan_url,
            params={"id": dataset_id},
            timeout=self.timeout_seconds,
            follow_redirects=True,
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("success"):
            raise TSEClientError(f"O catálogo CKAN não encontrou o conjunto {dataset_id}.")
        resources = payload.get("result", {}).get("resources", [])
        if not resources:
            raise TSEClientError(f"O conjunto {dataset_id} não possui recursos publicados.")
        return resources

    def iter_csv_records(self, url: str) -> Iterator[dict[str, Any]]:
        with tempfile.NamedTemporaryFile(delete=False) as download:
            temporary_path = download.name
        try:
            with httpx.stream(
                "GET", url, timeout=self.timeout_seconds, follow_redirects=True
            ) as response:
                response.raise_for_status()
                with open(temporary_path, "wb") as output:
                    for chunk in response.iter_bytes():
                        output.write(chunk)
            yield from _read_csv_file(temporary_path)
        finally:
            os.unlink(temporary_path)


def _read_csv_file(path: str) -> Iterator[dict[str, Any]]:
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
            if not csv_names:
                raise TSEClientError("O arquivo ZIP não contém CSV.")
            state_names = [name for name in csv_names if not name.lower().endswith("_brasil.csv")]
            for name in state_names or csv_names:
                with archive.open(name) as binary_file:
                    yield from _read_csv_stream(binary_file)
        return
    with open(path, "rb") as binary_file:
        yield from _read_csv_stream(binary_file)


def _read_csv_stream(binary_file: Any) -> Iterator[dict[str, Any]]:
    sample = binary_file.read(8192)
    binary_file.seek(0)
    text_sample = sample.decode(CSV_ENCODING)
    try:
        dialect = csv.Sniffer().sniff(text_sample, delimiters=";,\t,")
    except csv.Error:
        dialect = csv.excel
        dialect.delimiter = ";" if text_sample.count(";") > text_sample.count(",") else ","
    text_stream = io.TextIOWrapper(binary_file, encoding=CSV_ENCODING, newline="")
    yield from csv.DictReader(text_stream, dialect=dialect)