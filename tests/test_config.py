from __future__ import annotations

from routeros_lsp.config import DEFAULT_CONTEXT_VARIABLES, DEFAULT_SETTINGS, Settings, parse_settings


def parse(raw: object) -> tuple[Settings, list[str]]:
    warnings: list[str] = []
    return parse_settings(raw, warnings.append), warnings


def test_anything_that_is_not_an_object_means_the_defaults() -> None:
    for raw in (None, 3, "x", [], True):
        settings, warnings = parse(raw)
        assert settings == DEFAULT_SETTINGS
        assert warnings == []


def test_accepts_the_bare_object_and_one_nested_under_routeros() -> None:
    bare, _ = parse({"scope": "script"})
    nested, _ = parse({"routeros": {"scope": "script"}})
    assert bare == nested
    assert bare.scope == "script"


def test_reads_severities_and_reports_the_ones_it_cannot_use() -> None:
    settings, warnings = parse(
        {
            "severities": {
                "vars/undeclared-read": "error",
                "no/such-rule": "off",
                "syntax/bom": "loud",
                "schema/unknown-command": 3,
            }
        }
    )
    assert settings.severities == {"vars/undeclared-read": "error"}
    assert len(warnings) == 3
    assert any("no/such-rule" in w for w in warnings)


def test_a_severities_value_that_is_not_an_object_is_ignored_with_a_warning() -> None:
    settings, warnings = parse({"severities": ["error"]})
    assert settings.severities == {}
    assert len(warnings) == 1


def test_scope_must_be_import_or_script() -> None:
    assert parse({"scope": "import"})[0].scope == "import"
    settings, warnings = parse({"scope": "file"})
    assert settings.scope == "import"
    assert len(warnings) == 1


def test_extra_context_variables_are_added_to_the_defaults() -> None:
    settings, _ = parse({"contextVariables": ["custom"]})
    assert settings.context_variables == (*DEFAULT_CONTEXT_VARIABLES, "custom")
    settings, warnings = parse({"contextVariables": "custom"})
    assert settings.context_variables == DEFAULT_CONTEXT_VARIABLES
    assert len(warnings) == 1


def test_schema_is_bundled_off_or_a_path() -> None:
    assert parse({})[0].schema == "bundled"
    assert parse({"schema": "off"})[0].schema == "off"
    assert parse({"schema": "db.json"})[0].schema == "db.json"
    settings, warnings = parse({"schema": ""})
    assert settings.schema == "bundled"
    assert len(warnings) == 1
