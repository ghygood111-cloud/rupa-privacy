"""JSON/YAML configuration parsing for the core API."""

import json
from pathlib import Path

import yaml

from ..exceptions import ConfigurationError
from ..models import (
    AdjacencyConfig,
    DataSchema,
    PhysicalConstraint,
    PrivacyAccountingConfig,
    PrivacyConfig,
)


def load_config(path):
    """Load an untrusted JSON or YAML document with safe parsers."""
    source = Path(path)
    if not source.is_file():
        raise ConfigurationError("Configuration file does not exist: " + str(source))
    suffix = source.suffix.lower()
    try:
        with source.open("r", encoding="utf-8") as handle:
            if suffix == ".json":
                values = json.load(handle)
            elif suffix in {".yaml", ".yml"}:
                values = yaml.safe_load(handle)
            else:
                raise ConfigurationError("Configuration must use .json, .yaml, or .yml")
    except (OSError, json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ConfigurationError("Could not parse configuration: " + str(source)) from exc
    if not isinstance(values, dict):
        raise ConfigurationError("Configuration root must be a mapping")
    return values


def load_pipeline_config(path):
    """Return schema, privacy, constraints, prior, adjacency, and accounting."""
    values = load_config(path)
    required = {
        "schema",
        "privacy",
        "regulatory_prior",
        "adjacency",
        "privacy_accounting",
    }
    missing = required - set(values)
    if missing:
        raise ConfigurationError(
            "Configuration is missing sections: " + ", ".join(sorted(missing))
        )

    def require_mapping(section):
        section_values = values[section]
        if not isinstance(section_values, dict):
            raise ConfigurationError(section + " must be a mapping")
        return section_values

    def construct(section, constructor):
        try:
            return constructor.from_dict(require_mapping(section))
        except ConfigurationError:
            raise
        except (KeyError, IndexError, TypeError, ValueError, AttributeError) as exc:
            raise ConfigurationError(
                "Invalid {0} configuration: {1}".format(section, exc)
            ) from exc

    schema = construct("schema", DataSchema)
    privacy = construct("privacy", PrivacyConfig)
    adjacency = construct("adjacency", AdjacencyConfig)
    accounting = construct("privacy_accounting", PrivacyAccountingConfig)

    constraint_values = values.get("constraints", [])
    if not isinstance(constraint_values, list):
        raise ConfigurationError("constraints must be a list")
    constraints = []
    for index, item in enumerate(constraint_values):
        if not isinstance(item, dict):
            raise ConfigurationError(
                "constraints[{0}] must be a mapping".format(index)
            )
        try:
            constraints.append(PhysicalConstraint.from_dict(item))
        except ConfigurationError:
            raise
        except (KeyError, IndexError, TypeError, ValueError, AttributeError) as exc:
            raise ConfigurationError(
                "Invalid constraints[{0}] configuration: {1}".format(index, exc)
            ) from exc

    prior_values = require_mapping("regulatory_prior")
    prior = {str(name): weight for name, weight in prior_values.items()}
    return schema, privacy, constraints, prior, adjacency, accounting


def save_config(
    path,
    schema,
    privacy,
    constraints,
    regulatory_prior,
    adjacency,
    privacy_accounting,
):
    """Write a portable JSON or YAML pipeline configuration."""
    destination = Path(path)
    values = {
        "schema": schema.to_dict(),
        "privacy": privacy.to_dict(),
        "regulatory_prior": dict(regulatory_prior),
        "constraints": [constraint.to_dict() for constraint in constraints],
        "adjacency": adjacency.to_dict(),
        "privacy_accounting": privacy_accounting.to_dict(),
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as handle:
        if destination.suffix.lower() == ".json":
            json.dump(values, handle, indent=2, ensure_ascii=True)
        elif destination.suffix.lower() in {".yaml", ".yml"}:
            yaml.safe_dump(values, handle, sort_keys=False, allow_unicode=False)
        else:
            raise ConfigurationError("Configuration must use .json, .yaml, or .yml")
