from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_database: str = "mesarios"
    mysql_user: str = "mesarios"
    mysql_password: str = ""
    api_key: str = ""
    tse_ckan_url: str = "https://dadosabertos.tse.jus.br/api/3/action/package_show"
    tse_dataset_id: str = "mesarias-mesarios-e-funcoes-especiais-2026"
    tse_locations_dataset_id: str = "eleitorado-2026"
    election_year: int = 2026
    candidate_photos_base_url: str = "https://josedarci.com/eleicoes2026/fotos-candidatos"

    @property
    def database_url(self) -> URL:
        return URL.create(
            "mysql+pymysql",
            username=self.mysql_user,
            password=self.mysql_password,
            host=self.mysql_host,
            port=self.mysql_port,
            database=self.mysql_database,
            query={"charset": "utf8mb4"},
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()