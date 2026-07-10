from collections.abc import Iterable

from app.ontology.models import EntityType, EntityTypeDefinition, PropertyDefinition


def _resolve_property_definitions(
    entity_type: EntityType,
    entity_types: Iterable[EntityTypeDefinition],
) -> tuple[PropertyDefinition, ...]:
    definitions_by_id = {item.id: item for item in entity_types}
    lineage: list[EntityTypeDefinition] = []
    current = definitions_by_id.get(entity_type)

    while current is not None:
        lineage.append(current)
        current = definitions_by_id.get(current.parent) if current.parent else None

    merged: dict[str, PropertyDefinition] = {}
    for definition in reversed(lineage):
        for property_definition in definition.property_definitions:
            merged[property_definition.id] = property_definition
    return tuple(merged.values())


def property_definitions_for(
    entity_type: EntityType,
) -> tuple[PropertyDefinition, ...]:
    from app.ontology.catalog import CATALOG

    definition = next(
        (item for item in CATALOG.entity_types if item.id == entity_type), None
    )
    return definition.effective_property_definitions if definition else ()


def property_definition_for(
    entity_type: EntityType, property_id: str
) -> PropertyDefinition | None:
    return next(
        (
            item
            for item in property_definitions_for(entity_type)
            if item.id == property_id
        ),
        None,
    )
