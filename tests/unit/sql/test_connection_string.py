"""Unit tests for connection string parsing and conversion."""

import pytest

from postgres_mcp.sql.connection_string import ConnectionStringFormat
from postgres_mcp.sql.connection_string import convert_dotnet_to_postgresql_uri
from postgres_mcp.sql.connection_string import detect_connection_string_format
from postgres_mcp.sql.connection_string import normalize_connection_string
from postgres_mcp.sql.connection_string import parse_dotnet_connection_string


class TestDetectConnectionStringFormat:
    """Tests for format detection."""

    def test_detect_postgresql_uri(self):
        """postgresql:// URLs are detected correctly."""
        assert detect_connection_string_format("postgresql://user:pass@host:5432/db") == ConnectionStringFormat.POSTGRESQL_URI

    def test_detect_postgres_uri(self):
        """postgres:// URLs are detected correctly."""
        assert detect_connection_string_format("postgres://user:pass@host/db") == ConnectionStringFormat.POSTGRESQL_URI

    def test_detect_postgresql_uri_case_insensitive(self):
        """PostgreSQL URI detection is case-insensitive."""
        assert detect_connection_string_format("POSTGRESQL://user@host/db") == ConnectionStringFormat.POSTGRESQL_URI

    def test_detect_dotnet_server(self):
        """.NET connection strings with Server= are detected."""
        assert detect_connection_string_format("Server=host;Database=db;") == ConnectionStringFormat.DOTNET_ADO

    def test_detect_dotnet_data_source(self):
        """.NET connection strings with Data Source= are detected."""
        assert detect_connection_string_format("Data Source=host;Initial Catalog=db;") == ConnectionStringFormat.DOTNET_ADO

    def test_detect_dotnet_user_id(self):
        """.NET connection strings with User Id= are detected."""
        assert detect_connection_string_format("Server=host;User Id=admin;") == ConnectionStringFormat.DOTNET_ADO

    def test_detect_unknown_empty(self):
        """Empty string returns UNKNOWN."""
        assert detect_connection_string_format("") == ConnectionStringFormat.UNKNOWN

    def test_detect_unknown_none(self):
        """None returns UNKNOWN."""
        assert detect_connection_string_format(None) == ConnectionStringFormat.UNKNOWN

    def test_detect_unknown_whitespace(self):
        """Whitespace-only string returns UNKNOWN."""
        assert detect_connection_string_format("   ") == ConnectionStringFormat.UNKNOWN


class TestParseDotnetConnectionString:
    """Tests for .NET connection string parsing."""

    def test_parse_basic(self):
        """Basic key=value;key=value parsing."""
        result = parse_dotnet_connection_string("Server=host;Database=db;")
        assert result["server"] == "host"
        assert result["database"] == "db"

    def test_parse_case_insensitive_keys(self):
        """Keys are normalized to lowercase."""
        result = parse_dotnet_connection_string("SERVER=host;DATABASE=db;")
        assert "server" in result
        assert "database" in result

    def test_parse_with_spaces_in_keys(self):
        """Keys with spaces are preserved (lowercase)."""
        result = parse_dotnet_connection_string("User Id=admin;Ssl Mode=Prefer;")
        assert result["user id"] == "admin"
        assert result["ssl mode"] == "Prefer"

    def test_parse_double_quoted_values(self):
        """Double-quoted values are handled."""
        result = parse_dotnet_connection_string('Password="pass;word";Server=host;')
        assert result["password"] == "pass;word"
        assert result["server"] == "host"

    def test_parse_single_quoted_values(self):
        """Single-quoted values are handled."""
        result = parse_dotnet_connection_string("Password='pass;word';Server=host;")
        assert result["password"] == "pass;word"

    def test_parse_empty_value(self):
        """Empty values are handled."""
        result = parse_dotnet_connection_string("Server=host;Password=;Database=db;")
        assert result["password"] == ""

    def test_parse_value_with_equals(self):
        """Values containing = are handled."""
        result = parse_dotnet_connection_string('Password="pass=word";Server=host;')
        assert result["password"] == "pass=word"


class TestConvertDotnetToPostgresqlUri:
    """Tests for .NET to PostgreSQL URI conversion."""

    def test_convert_basic(self):
        """Basic Server/Database/User/Password conversion."""
        dotnet = "Server=host;Database=db;User Id=user;Password=pass;"
        result = convert_dotnet_to_postgresql_uri(dotnet)
        assert result == "postgresql://user:pass@host:5432/db"

    def test_convert_with_port(self):
        """Custom port is included in URI."""
        dotnet = "Server=host;Database=db;Port=5433;User Id=user;Password=pass;"
        result = convert_dotnet_to_postgresql_uri(dotnet)
        assert result == "postgresql://user:pass@host:5433/db"

    def test_convert_default_port(self):
        """Missing port defaults to 5432."""
        dotnet = "Server=host;Database=db;User Id=user;Password=pass;"
        result = convert_dotnet_to_postgresql_uri(dotnet)
        assert ":5432/" in result

    def test_convert_ssl_mode_prefer(self):
        """Ssl Mode=Prefer maps to sslmode=prefer."""
        dotnet = "Server=host;Database=db;User Id=user;Password=pass;Ssl Mode=Prefer;"
        result = convert_dotnet_to_postgresql_uri(dotnet)
        assert "sslmode=prefer" in result

    def test_convert_ssl_mode_require(self):
        """Ssl Mode=Require maps to sslmode=require."""
        dotnet = "Server=host;Database=db;User Id=user;Password=pass;Ssl Mode=Require;"
        result = convert_dotnet_to_postgresql_uri(dotnet)
        assert "sslmode=require" in result

    def test_convert_ssl_mode_disable(self):
        """Ssl Mode=Disable maps to sslmode=disable."""
        dotnet = "Server=host;Database=db;User Id=user;Password=pass;Ssl Mode=Disable;"
        result = convert_dotnet_to_postgresql_uri(dotnet)
        assert "sslmode=disable" in result

    def test_convert_ssl_mode_verify_full(self):
        """Ssl Mode=VerifyFull maps to sslmode=verify-full."""
        dotnet = "Server=host;Database=db;User Id=user;Password=pass;Ssl Mode=VerifyFull;"
        result = convert_dotnet_to_postgresql_uri(dotnet)
        assert "sslmode=verify-full" in result

    def test_convert_with_special_password_chars(self):
        """Passwords with special chars are URL-encoded."""
        dotnet = 'Server=host;Database=db;User Id=user;Password="p@ss:w/rd?";'
        result = convert_dotnet_to_postgresql_uri(dotnet)
        # @ : / ? should be encoded
        assert "p%40ss%3Aw%2Frd%3F" in result

    def test_convert_missing_server_raises(self):
        """Missing Server raises ValueError."""
        with pytest.raises(ValueError, match="Server"):
            convert_dotnet_to_postgresql_uri("Database=db;User Id=user;")

    def test_convert_missing_database_raises(self):
        """Missing Database raises ValueError."""
        with pytest.raises(ValueError, match="Database"):
            convert_dotnet_to_postgresql_uri("Server=host;User Id=user;")

    def test_convert_with_application_name(self):
        """Application Name is passed through."""
        dotnet = "Server=host;Database=db;User Id=user;Password=pass;Application Name=myapp;"
        result = convert_dotnet_to_postgresql_uri(dotnet)
        assert "application_name=myapp" in result

    def test_convert_with_timeout(self):
        """Command Timeout maps to connect_timeout."""
        dotnet = "Server=host;Database=db;User Id=user;Password=pass;Command Timeout=30;"
        result = convert_dotnet_to_postgresql_uri(dotnet)
        assert "connect_timeout=30" in result

    def test_convert_without_user(self):
        """Connection without user credentials."""
        dotnet = "Server=host;Database=db;"
        result = convert_dotnet_to_postgresql_uri(dotnet)
        assert result == "postgresql://host:5432/db"

    def test_convert_user_without_password(self):
        """Connection with user but no password."""
        dotnet = "Server=host;Database=db;User Id=user;"
        result = convert_dotnet_to_postgresql_uri(dotnet)
        assert result == "postgresql://user@host:5432/db"

    def test_convert_initial_catalog_alias(self):
        """Initial Catalog is recognized as database."""
        dotnet = "Server=host;Initial Catalog=mydb;User Id=user;Password=pass;"
        result = convert_dotnet_to_postgresql_uri(dotnet)
        assert "/mydb" in result

    def test_convert_data_source_alias(self):
        """Data Source is recognized as server."""
        dotnet = "Data Source=host;Database=db;User Id=user;Password=pass;"
        result = convert_dotnet_to_postgresql_uri(dotnet)
        assert "@host:" in result

    def test_convert_uid_alias(self):
        """UID is recognized as user."""
        dotnet = "Server=host;Database=db;UID=admin;Password=pass;"
        result = convert_dotnet_to_postgresql_uri(dotnet)
        assert "admin:" in result

    def test_convert_pwd_alias(self):
        """PWD is recognized as password."""
        dotnet = "Server=host;Database=db;User Id=user;PWD=secret;"
        result = convert_dotnet_to_postgresql_uri(dotnet)
        assert ":secret@" in result


class TestNormalizeConnectionString:
    """Tests for the main normalize_connection_string function."""

    def test_normalize_postgresql_uri_passthrough(self):
        """PostgreSQL URIs pass through unchanged."""
        uri = "postgresql://user:pass@host:5432/db?sslmode=require"
        assert normalize_connection_string(uri) == uri

    def test_normalize_postgres_uri_passthrough(self):
        """postgres:// URIs pass through unchanged."""
        uri = "postgres://user:pass@host/db"
        assert normalize_connection_string(uri) == uri

    def test_normalize_dotnet_converts(self):
        """.NET strings are converted."""
        dotnet = "Server=host;Database=db;User Id=user;Password=pass;"
        result = normalize_connection_string(dotnet)
        assert result.startswith("postgresql://")
        assert "user:pass@host" in result

    def test_normalize_none_returns_none(self):
        """None input returns None."""
        assert normalize_connection_string(None) is None

    def test_normalize_empty_returns_empty(self):
        """Empty string passes through."""
        assert normalize_connection_string("") == ""

    def test_normalize_whitespace_passthrough(self):
        """Whitespace-only string passes through."""
        assert normalize_connection_string("   ") == "   "

    def test_normalize_real_azure_string(self):
        """Convert real Azure .NET connection string."""
        dotnet = (
            "Server=simple-db-uat.postgres.database.azure.com;"
            "Database=uat;Port=5432;User Id=jetwallet;"
            "Password=x0KNq5g_O6LS;Ssl Mode=Prefer;"
            "Minimum Pool Size=1;Maximum Pool Size=1;ConnectionLifetime=10800;"
        )

        result = normalize_connection_string(dotnet)

        expected = "postgresql://jetwallet:x0KNq5g_O6LS@simple-db-uat.postgres.database.azure.com:5432/uat?sslmode=prefer"
        assert result == expected


class TestPoolSettingsIgnored:
    """Tests that .NET pool settings are properly ignored."""

    def test_pool_settings_not_in_uri(self):
        """Pool settings don't appear in output URI."""
        dotnet = "Server=host;Database=db;User Id=user;Password=pass;Minimum Pool Size=5;Maximum Pool Size=100;ConnectionLifetime=3600;"
        result = convert_dotnet_to_postgresql_uri(dotnet)

        assert "pool" not in result.lower()
        assert "lifetime" not in result.lower()
        assert "5" not in result or "5432" in result  # Only port should have 5
        assert "100" not in result
        assert "3600" not in result
