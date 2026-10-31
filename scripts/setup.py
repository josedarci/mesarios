import getpass
import secrets
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
DEFAULT_PHOTOS_URL = "https://josedarci.com/eleicoes2026/fotos-candidatos"


def quote_env_value(value: str) -> str:
    if "\n" in value or "\r" in value:
        raise ValueError("Valores de configuração não podem conter quebras de linha.")
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("$", "$$")
    return f'"{escaped}"'


def build_env_contents(
    *,
    database_mode: str,
    mysql_host: str,
    mysql_port: str,
    mysql_database: str,
    mysql_user: str,
    mysql_password: str,
    api_key: str,
    mysql_root_password: str | None = None,
) -> str:
    if database_mode not in {"local", "remote"}:
        raise ValueError("O modo do banco deve ser 'local' ou 'remote'.")
    values = {
        "MYSQL_HOST": mysql_host,
        "MYSQL_PORT": mysql_port,
        "MYSQL_DATABASE": mysql_database,
        "MYSQL_USER": mysql_user,
        "MYSQL_PASSWORD": mysql_password,
        "API_KEY": api_key,
        "TSE_CKAN_URL": "https://dadosabertos.tse.jus.br/api/3/action/package_show",
        "TSE_DATASET_ID": "mesarias-mesarios-e-funcoes-especiais-2026",
        "TSE_LOCATIONS_DATASET_ID": "eleitorado-2026",
        "ELECTION_YEAR": "2026",
        "CANDIDATE_PHOTOS_BASE_URL": DEFAULT_PHOTOS_URL,
    }
    if database_mode == "local":
        if not mysql_root_password:
            raise ValueError("A senha de administrador é obrigatória para o MySQL local.")
        values["MYSQL_ROOT_PASSWORD"] = mysql_root_password
    return "".join(f"{key}={quote_env_value(value)}\n" for key, value in values.items())


def prompt_required(label: str) -> str:
    while True:
        value = input(f"{label}: ").strip()
        if value:
            return value
        print("Este campo é obrigatório.")


def compose_command(database_mode: str, *arguments: str) -> list[str]:
    command = ["docker", "compose"]
    if database_mode == "local":
        command.extend(["-f", "docker-compose.yml", "-f", "docker-compose.local.yml"])
    return [*command, *arguments]


def run_docker(database_mode: str, *arguments: str) -> None:
    subprocess.run(compose_command(database_mode, *arguments), cwd=ROOT, check=True)


def choose_database_mode() -> str:
    print("Como deseja configurar o MySQL?")
    print("1. Criar e usar um MySQL local em container Docker.")
    print("2. Usar um servidor MySQL remoto com credenciais existentes.")
    while True:
        choice = input("Escolha [1/2]: ").strip()
        if choice == "1":
            return "local"
        if choice == "2":
            return "remote"
        print("Escolha 1 para MySQL local ou 2 para MySQL remoto.")


def configure_env(database_mode: str) -> None:
    if ENV_PATH.exists():
        raise FileExistsError(
            f"{ENV_PATH} já existe. Para preservar suas credenciais, revise-o manualmente "
            "ou mova-o antes de executar este assistente."
        )

    root_password = None
    if database_mode == "local":
        host = "database"
        port = "3306"
        database = "mesarios"
        user = "mesarios_app"
        password = secrets.token_urlsafe(32)
        root_password = secrets.token_urlsafe(32)
    else:
        host = prompt_required("Endereço do servidor MySQL")
        port_text = input("Porta MySQL [3306]: ").strip() or "3306"
        try:
            port = str(int(port_text))
        except ValueError as error:
            raise ValueError("A porta MySQL deve ser um número entre 1 e 65535.") from error
        if not 1 <= int(port) <= 65535:
            raise ValueError("A porta MySQL deve ser um número entre 1 e 65535.")

        database = prompt_required("Nome do banco de dados")
        user = prompt_required("Usuário MySQL")
        password = getpass.getpass("Senha MySQL (não será exibida): ")
        if not password:
            raise ValueError("A senha MySQL é obrigatória.")

    contents = build_env_contents(
        database_mode=database_mode,
        mysql_host=host,
        mysql_port=port,
        mysql_database=database,
        mysql_user=user,
        mysql_password=password,
        api_key=secrets.token_urlsafe(32),
        mysql_root_password=root_password,
    )
    ENV_PATH.write_text(contents, encoding="utf-8")
    try:
        ENV_PATH.chmod(0o600)
    except OSError:
        pass
    print(f"Configuração salva em {ENV_PATH}.")


def main() -> int:
    if sys.version_info < (3, 10):
        print("Este assistente requer Python 3.10 ou superior.")
        return 1
    if shutil.which("docker") is None:
        print("Docker não foi encontrado. Instale e inicie o Docker Desktop ou Docker Engine.")
        return 1

    database_mode = ""
    try:
        database_mode = choose_database_mode()
        subprocess.run(["docker", "compose", "version"], cwd=ROOT, check=True)
        configure_env(database_mode)
        run_docker(database_mode, "config", "-q")
        run_docker(database_mode, "build", "api")
        if database_mode == "local":
            run_docker(
                database_mode,
                "up",
                "-d",
                "--wait",
                "--wait-timeout",
                "120",
                "database",
            )
        run_docker(
            database_mode,
            "run",
            "--rm",
            "--no-deps",
            "--entrypoint",
            "python",
            "api",
            "-c",
            (
                "from sqlalchemy import create_engine, text; "
                "from app.core.config import get_settings; "
                "engine = create_engine(get_settings().database_url); "
                "connection = engine.connect(); "
                "connection.execute(text('SELECT 1')); "
                "connection.close(); "
                "engine.dispose(); "
                "print('Conexão MySQL validada.')"
            ),
        )
        run_docker(
            database_mode,
            "run",
            "--rm",
            "--no-deps",
            "--entrypoint",
            "alembic",
            "api",
            "upgrade",
            "head",
        )
        run_docker(database_mode, "up", "-d", "api")
    except (FileExistsError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Configuração interrompida: {error}", file=sys.stderr)
        log_command = (
            "docker compose -f docker-compose.yml -f docker-compose.local.yml logs --tail=100 api"
            if database_mode == "local"
            else "docker compose logs --tail=100 api"
        )
        print(
            f"Consulte os logs com `{log_command}`. Corrija a configuração no arquivo .env "
            "antes de executar o Compose novamente.",
            file=sys.stderr,
        )
        return 1

    print("Instalação concluída. Acesse o painel em http://localhost:8000/")
    print("A chave de API gerada está no arquivo .env.")
    if database_mode == "local":
        compose_prefix = "docker compose -f docker-compose.yml -f docker-compose.local.yml"
    else:
        compose_prefix = "docker compose"
    print(f"Para conferir os logs: {compose_prefix} logs -f api")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
