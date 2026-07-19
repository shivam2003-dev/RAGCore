import pytest

from core.exceptions import ValidationError
from repositories.code_search import validate_exact_code_query
from services.github_index import (
    owners_for_path,
    parse_codeowners,
    path_policy,
    validate_path_patterns,
)


def test_path_allow_deny_secret_binary_and_size_policy():
    kwargs = {
        "allowlist": ["src/**", "CODEOWNERS"],
        "denylist": ["**/*secret*", "vendor/**"],
        "max_bytes": 1000,
    }
    assert path_policy("src/app.py", size=100, **kwargs) == "allowed"
    assert path_policy("CODEOWNERS", size=100, **kwargs) == "allowed"
    assert path_policy("src/secret_key.py", size=100, **kwargs) == "denied"
    assert path_policy("vendor/app.py", size=100, **kwargs) == "denied"
    assert path_policy("src/logo.png", size=100, **kwargs) == "denied"
    assert path_policy("src/large.py", size=1001, **kwargs) == "oversized"
    with pytest.raises(ValidationError):
        validate_path_patterns(["../private/**"])


def test_codeowners_parser_uses_last_matching_rule():
    rules = parse_codeowners(
        """
# Default owners
* @platform
src/** @backend @sre
src/security/** @security
"""
    )
    assert owners_for_path("README.md", rules) == ["@platform"]
    assert owners_for_path("src/api/main.py", rules) == ["@backend", "@sre"]
    assert owners_for_path("src/security/auth.py", rules) == ["@security"]


def test_exact_code_query_is_literal_and_rejects_control_characters():
    assert validate_exact_code_query("target_symbol; rm -rf /") == "target_symbol; rm -rf /"
    with pytest.raises(ValidationError):
        validate_exact_code_query("target\nsecond command")
    with pytest.raises(ValidationError):
        validate_exact_code_query("x")
