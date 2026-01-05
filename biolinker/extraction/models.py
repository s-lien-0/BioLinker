"""
Data models for biomarker extraction results.
"""

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class MarkerType(str, Enum):
    """Types of biomarkers."""
    GENE = "gene"
    PROTEIN = "protein"
    METABOLITE = "metabolite"
    MIRNA = "mirna"
    LNCRNA = "lncrna"
    METHYLATION = "methylation"
    SNP = "snp"
    OTHER = "other"


class AssociationType(str, Enum):
    """Types of marker-disease associations."""
    DIAGNOSTIC = "diagnostic"
    PROGNOSTIC = "prognostic"
    PREDICTIVE = "predictive"
    THERAPEUTIC = "therapeutic"
    RISK = "risk"
    EXPRESSION = "expression"
    MUTATION = "mutation"
    OTHER = "other"


class EvidenceLevel(str, Enum):
    """Evidence quality levels."""
    CLINICAL_TRIAL = "clinical_trial"
    COHORT_STUDY = "cohort_study"
    CASE_CONTROL = "case_control"
    CASE_SERIES = "case_series"
    IN_VIVO = "in_vivo"
    IN_VITRO = "in_vitro"
    COMPUTATIONAL = "computational"
    REVIEW = "review"
    META_ANALYSIS = "meta_analysis"
    UNKNOWN = "unknown"


class Directionality(str, Enum):
    """Direction of association."""
    POSITIVE = "positive"  # Upregulated, increased, etc.
    NEGATIVE = "negative"  # Downregulated, decreased, etc.
    BIDIRECTIONAL = "bidirectional"
    UNKNOWN = "unknown"


@dataclass
class DiseaseInfo:
    """Information about a disease mentioned in the study."""
    name: str
    category: Optional[str] = None
    icd_code: Optional[str] = None
    mesh_id: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "category": self.category,
            "icd_code": self.icd_code,
            "mesh_id": self.mesh_id,
        }


@dataclass
class MarkerInfo:
    """Information about a biomarker."""
    name: str
    marker_type: MarkerType = MarkerType.OTHER
    symbol: Optional[str] = None  # Official gene symbol
    hgnc_id: Optional[str] = None
    uniprot_id: Optional[str] = None
    ensembl_id: Optional[str] = None
    chromosome: Optional[str] = None
    description: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "marker_type": self.marker_type.value,
            "symbol": self.symbol,
            "hgnc_id": self.hgnc_id,
            "uniprot_id": self.uniprot_id,
            "ensembl_id": self.ensembl_id,
            "chromosome": self.chromosome,
            "description": self.description,
        }


@dataclass
class StatisticalMetrics:
    """Statistical metrics from the study."""
    p_value: Optional[float] = None
    odds_ratio: Optional[float] = None
    hazard_ratio: Optional[float] = None
    confidence_interval: Optional[str] = None
    auc: Optional[float] = None
    sensitivity: Optional[float] = None
    specificity: Optional[float] = None
    sample_size: Optional[int] = None
    
    def to_dict(self) -> dict:
        return {
            "p_value": self.p_value,
            "odds_ratio": self.odds_ratio,
            "hazard_ratio": self.hazard_ratio,
            "confidence_interval": self.confidence_interval,
            "auc": self.auc,
            "sensitivity": self.sensitivity,
            "specificity": self.specificity,
            "sample_size": self.sample_size,
        }


@dataclass
class AssociationInfo:
    """Information about a marker-disease association."""
    marker: MarkerInfo
    disease: DiseaseInfo
    association_type: AssociationType = AssociationType.OTHER
    evidence_level: EvidenceLevel = EvidenceLevel.UNKNOWN
    directionality: Directionality = Directionality.UNKNOWN
    strength: Optional[str] = None  # Qualitative description
    functional_impact: Optional[str] = None
    statistics: StatisticalMetrics = field(default_factory=StatisticalMetrics)
    confidence_score: float = 0.0  # LLM confidence in extraction
    
    def to_dict(self) -> dict:
        return {
            "marker": self.marker.to_dict(),
            "disease": self.disease.to_dict(),
            "association_type": self.association_type.value,
            "evidence_level": self.evidence_level.value,
            "directionality": self.directionality.value,
            "strength": self.strength,
            "functional_impact": self.functional_impact,
            "statistics": self.statistics.to_dict(),
            "confidence_score": self.confidence_score,
        }


@dataclass
class ExtractionResult:
    """Complete extraction result from an article."""
    pmid: str
    diseases: list[DiseaseInfo] = field(default_factory=list)
    markers: list[MarkerInfo] = field(default_factory=list)
    associations: list[AssociationInfo] = field(default_factory=list)
    raw_response: Optional[str] = None
    extraction_successful: bool = True
    error_message: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "pmid": self.pmid,
            "diseases": [d.to_dict() for d in self.diseases],
            "markers": [m.to_dict() for m in self.markers],
            "associations": [a.to_dict() for a in self.associations],
            "extraction_successful": self.extraction_successful,
            "error_message": self.error_message,
        }

