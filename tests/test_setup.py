import pytest

from scripts.setup import build_env_contents, quote_env_value


def test_quote_env_value_preserves_compose_and_dotenv_special_characters():
    assert quote_env_value("pass'word\\$value") == '"pass\'word\\\\$$value"'


def test_quote_env_value_rejects_line_breaks():
    with pytest.raises(ValueError, match="quebras de linha"):
        quote_env_value("password\nAPI_KEY=exposed")


def test_build_env_contents_quotes_credentials_and_generates_required_settings():
    contents = build_env_contents(
        database_mode="remote",
        mysql_host="db.example.test",
        mysql_port="3306",
        mysql_database="elections",
        mysql_user="dashboard",
        mysql_password="pa'ss\\word$1",
        api_key="generated-secret",
    )

    assert 'MYSQL_PASSWORD="pa\'ss\\\\word$$1"\n' in contents
    assert 'API_KEY="generated-secret"\n' in contents
    assert "CANDIDATE_PHOTOS_BASE_URL=" in contents


def test_build_env_contents_includes_local_database_root_password():
    contents = build_env_contents(
        database_mode="local",
        mysql_host="database",
        mysql_port="3306",
        mysql_database="mesarios",
        mysql_user="mesarios_app",
        mysql_password="app-secret",
        api_key="generated-secret",
        mysql_root_password="root-secret",
    )

    assert 'MYSQL_ROOT_PASSWORD="root-secret"\n' in contents


def test_build_env_contents_requires_root_password_for_local_database():
    with pytest.raises(ValueError, match="administrador"):
        build_env_contents(
            database_mode="local",
            mysql_host="database",
            mysql_port="3306",
            mysql_database="mesarios",
            mysql_user="mesarios_app",
            mysql_password="app-secret",
            api_key="generated-secret",
        )
