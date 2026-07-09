from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class EntityType(StrEnum):
    PERSON = "Person"
    ORGANIZATION = "Organization"
    SECT = "Sect"
    CLAN = "Clan"
    ESCORT_AGENCY = "EscortAgency"
    POLITICAL_FORCE = "PoliticalForce"
    MARTIAL_ART = "MartialArt"
    SWORDPLAY = "Swordplay"
    INTERNAL_SKILL = "InternalSkill"
    PALM_TECHNIQUE = "PalmTechnique"
    QINGGONG = "Qinggong"
    MUSIC_SCORE = "MusicScore"
    EVENT = "Event"
    TEACHING_EVENT = "TeachingEvent"
    PLACE = "Place"
    ARTIFACT = "Artifact"


class RelationType(StrEnum):
    MEMBER_OF = "MEMBER_OF"
    MASTER_OF = "MASTER_OF"
    SPOUSE_OF = "SPOUSE_OF"
    KIN_OF = "KIN_OF"
    ALLY_OF = "ALLY_OF"
    ENEMY_OF = "ENEMY_OF"
    KNOWS = "KNOWS"
    TEACHER = "TEACHER"
    STUDENT = "STUDENT"
    SUBJECT = "SUBJECT"
    HOLDS = "HOLDS"
    PARTICIPATES_IN = "PARTICIPATES_IN"
    OCCURS_AT = "OCCURS_AT"


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class EntityTypeDefinition(FrozenModel):
    id: EntityType
    label: str
    description: str
    color: str
    parent: EntityType | None = None


class RelationTypeDefinition(FrozenModel):
    id: RelationType
    label: str
    description: str
    source_types: tuple[EntityType, ...]
    target_types: tuple[EntityType, ...]
    symmetric: bool = False
    temporal: bool = False


class TripleExample(FrozenModel):
    subject: str
    predicate: RelationType
    object: str


class OntologyCatalog(FrozenModel):
    entity_types: tuple[EntityTypeDefinition, ...]
    relation_types: tuple[RelationTypeDefinition, ...]
    example: TripleExample
