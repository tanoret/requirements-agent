from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class ComponentConfig:
    """
    Registry entry for a component type supported by the CLI/agent.

    template_default/schema_default are *repo-root-relative* default paths.
    profile_key is the key name used inside the generated requirements instance JSON
    (must match the corresponding *_requirements_instance.schema.json).
    """
    name: str
    template_default: str
    schema_default: str
    instance_schema_default: str
    profile_key: str
    tag_field: str
    profile_title: str


COMPONENTS: Dict[str, ComponentConfig] = {
    "valve": ComponentConfig(
        name="valve",
        template_default="data/valve_baseline.json",
        schema_default="schemas/valve_profile.schema.json",
        instance_schema_default="schemas/valve_requirements_instance.schema.json",
        profile_key="valve_profile",
        tag_field="valve_tag",
        profile_title="ValveProfile",
    ),
    "pump": ComponentConfig(
        name="pump",
        template_default="data/pump_baseline.json",
        schema_default="schemas/pump_profile.schema.json",
        instance_schema_default="schemas/pump_requirements_instance.schema.json",
        profile_key="pump_profile",
        tag_field="pump_tag",
        profile_title="PumpProfile",
    ),
    "steam_generator": ComponentConfig(
        name="steam_generator",
        template_default="data/steam_generator_baseline.json",
        schema_default="schemas/steam_generator_profile.schema.json",
        instance_schema_default="schemas/steam_generator_requirements_instance.schema.json",
        profile_key="steam_generator_profile",
        tag_field="sg_tag",
        profile_title="SteamGeneratorProfile",
    ),
    "turbine": ComponentConfig(
        name="turbine",
        template_default="data/turbine_baseline.json",
        schema_default="schemas/turbine_profile.schema.json",
        instance_schema_default="schemas/turbine_requirements_instance.schema.json",
        profile_key="turbine_profile",
        tag_field="turbine_tag",
        profile_title="TurbineProfile",
    ),
    "condenser": ComponentConfig(
        name="condenser",
        template_default="data/condenser_baseline.json",
        schema_default="schemas/condenser_profile.schema.json",
        instance_schema_default="schemas/condenser_requirements_instance.schema.json",
        profile_key="condenser_profile",
        tag_field="condenser_tag",
        profile_title="CondenserProfile",
    ),
    "pressurizer": ComponentConfig(
        name="pressurizer",
        template_default="data/pressurizer_baseline.json",
        schema_default="schemas/pressurizer_profile.schema.json",
        instance_schema_default="schemas/pressurizer_requirements_instance.schema.json",
        profile_key="pressurizer_profile",
        tag_field="pressurizer_tag",
        profile_title="PressurizerProfile",
    ),
}


def get_component(name: str) -> ComponentConfig:
    key = (name or "").strip().lower()
    if key not in COMPONENTS:
        raise ValueError(f"Unknown component '{name}'. Supported: {sorted(COMPONENTS.keys())}")
    return COMPONENTS[key]
