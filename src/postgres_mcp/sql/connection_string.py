"""Connection string parsing and conversion utilities.

Supports auto-detection and conversion of .NET/ADO.NET connection strings
to PostgreSQL URI format.
"""

import logging
import re
from urllib.parse import quote_plus
from urllib.parse import urlencode

logger = logging.getLogger(__name__)


class ConnectionStringFormat:
    """Connection string format identifiers."""

    POSTGRESQL_URI = "postgresql_uri"
    DOTNET_ADO = "dotnet_ado"
    UNKNOWN = "unknown"


def detect_connection_string_format(connection_string: str) -> str:
    """
    Auto-detect the format of a connection string.

    Args:
        connection_string: The connection string to analyze

    Returns:
        ConnectionStringFormat constant indicating the detected format
    """
    if not connection_string or not connection_string.strip():
        return ConnectionStringFormat.UNKNOWN

    conn_str = connection_string.strip()

    # PostgreSQL URI detection: starts with postgres:// or postgresql://
    if re.match(r"^postgres(ql)?://", conn_str, re.IGNORECASE):
        return ConnectionStringFormat.POSTGRESQL_URI

    # .NET ADO.NET detection: contains key=value pairs with semicolons
    dotnet_indicators = [
        r"server\s*=",
        r"data\s+source\s*=",
        r"database\s*=",
        r"initial\s+catalog\s*=",
        r"user\s+id\s*=",
        r"uid\s*=",
    ]

    for pattern in dotnet_indicators:
        if re.search(pattern, conn_str, re.IGNORECASE):
            return ConnectionStringFormat.DOTNET_ADO

    # Fallback: check for semicolon-separated key=value pattern
    if re.match(r"^[^=]+=[^;]*;", conn_str):
        return ConnectionStringFormat.DOTNET_ADO

    return ConnectionStringFormat.UNKNOWN


def parse_dotnet_connection_string(connection_string: str) -> dict[str, str]:
    """
    Parse a .NET/ADO.NET style connection string into a dictionary.

    Args:
        connection_string: .NET format connection string

    Returns:
        Dictionary of key-value pairs (keys normalized to lowercase)

    Example:
        "Server=host;Database=db;User Id=user"
        -> {"server": "host", "database": "db", "user id": "user"}
    """
    result: dict[str, str] = {}

    # Handle quoted values: Key="value with ; semicolon"
    # Pattern: key=value or key="quoted value" or key='quoted value'
    pattern = r"""
        ([^=;]+)         # Key (anything before =)
        \s*=\s*          # Equals with optional whitespace
        (?:
            "([^"]*)"    # Double-quoted value
            |
            '([^']*)'    # Single-quoted value
            |
            ([^;]*)      # Unquoted value (until ; or end)
        )
    """

    for match in re.finditer(pattern, connection_string, re.VERBOSE):
        key = match.group(1).strip().lower()
        # Get the first non-None value from the groups
        value = match.group(2) or match.group(3) or match.group(4) or ""
        result[key] = value.strip()

    return result


# SSL mode mapping from .NET to PostgreSQL
_SSL_MODE_MAP = {
    "disable": "disable",
    "allow": "allow",
    "prefer": "prefer",
    "require": "require",
    "verify-ca": "verify-ca",
    "verifyca": "verify-ca",
    "verify-full": "verify-full",
    "verifyfull": "verify-full",
}

# .NET-specific parameters to ignore (with DEBUG log)
_IGNORED_PARAMS = {
    "minimum pool size",
    "min pool size",
    "maximum pool size",
    "max pool size",
    "connectionlifetime",
    "connection lifetime",
    "pooling",
    "enlist",
    "persist security info",
    "integrated security",
}


def convert_dotnet_to_postgresql_uri(connection_string: str) -> str:
    """
    Convert a .NET/ADO.NET connection string to PostgreSQL URI format.

    Args:
        connection_string: .NET format connection string

    Returns:
        PostgreSQL URI format string

    Raises:
        ValueError: If required fields (Server, Database) are missing
    """
    params = parse_dotnet_connection_string(connection_string)

    # Extract required fields (with aliases)
    host = params.get("server") or params.get("host") or params.get("data source")
    database = params.get("database") or params.get("initial catalog")

    if not host:
        raise ValueError("Missing required 'Server' or 'Host' in connection string")
    if not database:
        raise ValueError("Missing required 'Database' or 'Initial Catalog' in connection string")

    # Extract optional fields
    port = params.get("port", "5432")
    user = params.get("user id") or params.get("uid") or params.get("user")
    password = params.get("password") or params.get("pwd")

    # Build URI base
    if user and password:
        # URL-encode password for special characters
        encoded_password = quote_plus(password)
        uri = f"postgresql://{user}:{encoded_password}@{host}:{port}/{database}"
    elif user:
        uri = f"postgresql://{user}@{host}:{port}/{database}"
    else:
        uri = f"postgresql://{host}:{port}/{database}"

    # Build query parameters
    query_params: dict[str, str] = {}

    # SSL mode mapping
    ssl_mode = params.get("ssl mode") or params.get("sslmode")
    if ssl_mode:
        mapped_ssl = _SSL_MODE_MAP.get(ssl_mode.lower())
        if mapped_ssl:
            query_params["sslmode"] = mapped_ssl
        else:
            logger.warning("Unknown SSL mode '%s', ignoring", ssl_mode)

    # Application name
    app_name = params.get("application name")
    if app_name:
        query_params["application_name"] = app_name

    # Timeout mapping
    timeout = params.get("command timeout") or params.get("timeout") or params.get("connection timeout")
    if timeout:
        query_params["connect_timeout"] = timeout

    # Log warnings for ignored .NET-specific parameters
    for ignored in _IGNORED_PARAMS:
        if ignored in params:
            logger.debug("Ignoring .NET-specific parameter: %s=%s", ignored, params[ignored])

    # Append query string if any
    if query_params:
        uri += "?" + urlencode(query_params)

    return uri


def normalize_connection_string(connection_string: str | None) -> str | None:
    """
    Normalize any supported connection string format to PostgreSQL URI.

    This is the main entry point - it auto-detects the format and converts
    if necessary.

    Args:
        connection_string: Connection string in any supported format

    Returns:
        PostgreSQL URI format string, or None if input is None
    """
    if connection_string is None:
        return None

    if not connection_string.strip():
        return connection_string

    format_type = detect_connection_string_format(connection_string)

    if format_type == ConnectionStringFormat.POSTGRESQL_URI:
        logger.debug("Connection string detected as PostgreSQL URI, passing through")
        return connection_string

    if format_type == ConnectionStringFormat.DOTNET_ADO:
        logger.info("Converting .NET connection string to PostgreSQL URI format")
        return convert_dotnet_to_postgresql_uri(connection_string)

    # Unknown format - return as-is and let psycopg handle it
    logger.debug("Unknown connection string format, passing through as-is")
    return connection_string
