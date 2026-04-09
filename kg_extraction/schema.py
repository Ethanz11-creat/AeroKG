from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum


class NodeType(Enum):
    DOCUMENT = "Document"
    STRUCTURAL_UNIT = "StructuralUnit"
    TERM = "Term"
    DEFINITION = "Definition"
    RULE = "Rule"
    CONDITION = "Condition"
    CONSTRAINT = "Constraint"
    REFERENCE = "Reference"


class EdgeType(Enum):
    CONTAINS = "CONTAINS"
    DEFINES = "DEFINES"
    HAS_RULE = "HAS_RULE"
    APPLIES_TO = "APPLIES_TO"
    HAS_CONDITION = "HAS_CONDITION"
    HAS_CONSTRAINT = "HAS_CONSTRAINT"
    REFERENCES = "REFERENCES"
    SAME_AS = "SAME_AS"


class RuleType(Enum):
    OBLIGATION = "obligation"
    PROHIBITION = "prohibition"
    PERMISSION = "permission"
    RESPONSIBILITY = "responsibility"
    DEFINITION_REF = "definition_ref"
    REQUIREMENT = "requirement"


class ConditionType(Enum):
    SCOPE = "scope"
    PREREQUISITE = "prerequisite"
    TRIGGER = "trigger"
    EXCEPTION = "exception"
    TEMPORAL = "temporal"
    SPATIAL = "spatial"
    OPERATIONAL = "operational"


class TermCategory(Enum):
    AIRSPACE = "airspace"
    FLIGHT_RULE = "flight_rule"
    ATC_SERVICE = "atc_service"
    ORGANIZATION = "organization"
    FACILITY = "facility"
    AIRCRAFT = "aircraft"
    UAV = "uav"
    PROCEDURE = "procedure"
    LICENSE = "license"
    GENERIC = "generic"


class UnitType(Enum):
    CHAPTER = "chapter"
    SECTION = "section"
    ARTICLE = "article"


class Comparator(Enum):
    GT = ">"
    GTE = ">="
    LT = "<"
    LTE = "<="
    EQ = "="
    RANGE = "range"
    NONE = "none"


class RefType(Enum):
    LAW = "law"
    REGULATION = "regulation"
    ANNEX = "annex"
    ARTICLE = "article"


@dataclass
class DocumentNode:
    id: str
    doc_title: str
    source_file: str
    source_type: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "doc_title": self.doc_title,
            "source_file": self.source_file,
            "source_type": self.source_type,
            "type": NodeType.DOCUMENT.value,
        }


@dataclass
class StructuralUnitNode:
    id: str
    unit_type: str
    title: str
    chapter: str
    section: str
    article_no: str
    article_num: str
    doc_title: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "unit_type": self.unit_type,
            "title": self.title,
            "chapter": self.chapter,
            "section": self.section,
            "article_no": self.article_no,
            "article_num": self.article_num,
            "doc_title": self.doc_title,
            "type": NodeType.STRUCTURAL_UNIT.value,
        }


@dataclass
class TermNode:
    id: str
    name: str
    normalized_name: str
    category: str
    chunk_id: str
    evidence_text: str
    aliases: List[str] = field(default_factory=list)
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "normalized_name": self.normalized_name,
            "category": self.category,
            "aliases": self.aliases,
            "confidence": self.confidence,
            "chunk_id": self.chunk_id,
            "evidence_text": self.evidence_text,
            "type": NodeType.TERM.value,
        }


@dataclass
class DefinitionNode:
    id: str
    term_name: str
    definition_text: str
    chunk_id: str
    evidence_text: str
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "term_name": self.term_name,
            "definition_text": self.definition_text,
            "confidence": self.confidence,
            "chunk_id": self.chunk_id,
            "evidence_text": self.evidence_text,
            "type": NodeType.DEFINITION.value,
        }


@dataclass
class RuleNode:
    id: str
    rule_type: str
    modality: str
    subject: str
    action: str
    object: str
    chunk_id: str
    evidence_text: str
    normalized_subject: str = ""
    normalized_action: str = ""
    normalized_object: str = ""
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "rule_type": self.rule_type,
            "modality": self.modality,
            "subject": self.subject,
            "action": self.action,
            "object": self.object,
            "normalized_subject": self.normalized_subject,
            "normalized_action": self.normalized_action,
            "normalized_object": self.normalized_object,
            "confidence": self.confidence,
            "chunk_id": self.chunk_id,
            "evidence_text": self.evidence_text,
            "type": NodeType.RULE.value,
        }


@dataclass
class ConditionNode:
    id: str
    text: str
    condition_type: str
    chunk_id: str
    evidence_text: str
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "condition_type": self.condition_type,
            "confidence": self.confidence,
            "chunk_id": self.chunk_id,
            "evidence_text": self.evidence_text,
            "type": NodeType.CONDITION.value,
        }


@dataclass
class ConstraintNode:
    id: str
    text: str
    comparator: str
    value: str
    unit: str
    chunk_id: str
    evidence_text: str
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "comparator": self.comparator,
            "value": self.value,
            "unit": self.unit,
            "confidence": self.confidence,
            "chunk_id": self.chunk_id,
            "evidence_text": self.evidence_text,
            "type": NodeType.CONSTRAINT.value,
        }


@dataclass
class ReferenceNode:
    id: str
    ref_type: str
    ref_text: str
    chunk_id: str
    evidence_text: str
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "ref_type": self.ref_type,
            "ref_text": self.ref_text,
            "confidence": self.confidence,
            "chunk_id": self.chunk_id,
            "evidence_text": self.evidence_text,
            "type": NodeType.REFERENCE.value,
        }


@dataclass
class Edge:
    source_id: str
    target_id: str
    relation_type: str
    chunk_id: str
    article_no: str
    doc_title: str
    evidence_text: str
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation_type": self.relation_type,
            "chunk_id": self.chunk_id,
            "article_no": self.article_no,
            "doc_title": self.doc_title,
            "evidence_text": self.evidence_text,
            "confidence": self.confidence,
        }
