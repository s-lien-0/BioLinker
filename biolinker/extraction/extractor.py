"""
LLM-based biomarker extractor with support for multiple backends.
"""

import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Optional
from dataclasses import dataclass

import requests

from biolinker.extraction.models import (
    ExtractionResult,
    DiseaseInfo,
    MarkerInfo,
    AssociationInfo,
    StatisticalMetrics,
    MarkerType,
    AssociationType,
    EvidenceLevel,
    Directionality,
)
from biolinker.extraction.prompts import ExtractionPrompts
from biolinker.pubmed.parser import Article

logger = logging.getLogger(__name__)


@dataclass
class LLMConfig:
    """Configuration for LLM backend."""
    provider: str  # "ollama", "openai", "anthropic"
    model: str
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    temperature: float = 0.1
    max_tokens: int = 4096


class LLMBackend(ABC):
    """Abstract base class for LLM backends."""
    
    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Generate a response from the LLM."""
        pass


class OllamaBackend(LLMBackend):
    """Ollama local LLM backend."""
    
    def __init__(self, config: LLMConfig):
        self.config = config
        self.base_url = config.base_url or "http://localhost:11434"
    
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        url = f"{self.base_url}/api/generate"
        
        payload = {
            "model": self.config.model,
            "prompt": f"{system_prompt}\n\n{user_prompt}",
            "stream": False,
            "options": {
                "temperature": self.config.temperature,
                "num_predict": self.config.max_tokens,
            }
        }
        
        response = requests.post(url, json=payload, timeout=120)
        response.raise_for_status()
        
        return response.json().get("response", "")


class OpenAIBackend(LLMBackend):
    """OpenAI API backend."""
    
    def __init__(self, config: LLMConfig):
        self.config = config
        self.base_url = config.base_url or "https://api.openai.com/v1"
    
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        url = f"{self.base_url}/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }
        
        response = requests.post(url, headers=headers, json=payload, timeout=120)
        response.raise_for_status()
        
        return response.json()["choices"][0]["message"]["content"]


class AnthropicBackend(LLMBackend):
    """Anthropic Claude API backend."""
    
    def __init__(self, config: LLMConfig):
        self.config = config
        self.base_url = config.base_url or "https://api.anthropic.com/v1"
    
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        url = f"{self.base_url}/messages"
        
        headers = {
            "x-api-key": self.config.api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        
        payload = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": user_prompt},
            ],
        }
        
        response = requests.post(url, headers=headers, json=payload, timeout=120)
        response.raise_for_status()
        
        return response.json()["content"][0]["text"]


def create_backend(config: LLMConfig) -> LLMBackend:
    """Factory function to create LLM backend."""
    backends = {
        "ollama": OllamaBackend,
        "openai": OpenAIBackend,
        "anthropic": AnthropicBackend,
    }
    
    backend_class = backends.get(config.provider.lower())
    if not backend_class:
        raise ValueError(f"Unknown LLM provider: {config.provider}")
    
    return backend_class(config)


class BiomarkerExtractor:
    """
    Extract biomarker-disease associations from scientific articles.
    
    Supports multiple LLM backends (Ollama, OpenAI, Anthropic).
    """
    
    def __init__(self, config: Optional[LLMConfig] = None):
        """
        Initialize the extractor.
        
        Args:
            config: LLM configuration. Defaults to Ollama with ministral-3b.
        """
        if config is None:
            config = LLMConfig(provider="ollama", model="ministral-3:3b")
        
        self.config = config
        self.backend = create_backend(config)
        self.prompts = ExtractionPrompts()
    
    def extract(self, article: Article) -> ExtractionResult:
        """
        Extract biomarker information from an article.
        
        Args:
            article: Article to extract from
            
        Returns:
            ExtractionResult with diseases, markers, and associations
        """
        if not article.abstract:
            return ExtractionResult(
                pmid=article.pmid,
                extraction_successful=False,
                error_message="No abstract available"
            )
        
        try:
            # Generate extraction prompt
            system_prompt = self.prompts.get_system_prompt()
            user_prompt = self.prompts.get_extraction_prompt(
                title=article.title,
                abstract=article.abstract
            )
            
            # Get LLM response
            raw_response = self.backend.generate(system_prompt, user_prompt)
            
            # Parse response
            result = self._parse_response(article.pmid, raw_response)
            result.raw_response = raw_response
            
            return result
            
        except Exception as e:
            logger.error(f"Extraction failed for PMID {article.pmid}: {e}")
            return ExtractionResult(
                pmid=article.pmid,
                extraction_successful=False,
                error_message=str(e)
            )
    
    def extract_batch(self, articles: list[Article]) -> list[ExtractionResult]:
        """Extract from multiple articles."""
        return [self.extract(article) for article in articles]
    
    def _parse_response(self, pmid: str, response: str) -> ExtractionResult:
        """Parse the LLM response into structured data."""
        # Clean response - extract JSON from potential markdown
        json_str = self._extract_json(response)
        
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON for PMID {pmid}: {e}")
            return ExtractionResult(
                pmid=pmid,
                extraction_successful=False,
                error_message=f"JSON parse error: {e}"
            )
        
        # Parse diseases
        diseases = []
        for d in data.get("diseases", []):
            if d.get("name"):
                diseases.append(DiseaseInfo(
                    name=d["name"],
                    category=d.get("category"),
                ))
        
        # Parse markers
        markers = []
        marker_map = {}  # For linking associations
        for m in data.get("markers", []):
            if m.get("name"):
                marker = MarkerInfo(
                    name=m["name"],
                    symbol=m.get("symbol"),
                    marker_type=self._parse_marker_type(m.get("marker_type")),
                )
                markers.append(marker)
                marker_map[m["name"].lower()] = marker
        
        # Parse associations
        associations = []
        disease_map = {d.name.lower(): d for d in diseases}
        
        for a in data.get("associations", []):
            marker_name = a.get("marker_name", "").lower()
            disease_name = a.get("disease_name", "").lower()
            
            marker = marker_map.get(marker_name)
            disease = disease_map.get(disease_name)
            
            if marker and disease:
                # Parse statistics
                stats_data = a.get("statistics", {})
                statistics = StatisticalMetrics(
                    p_value=self._parse_float(stats_data.get("p_value")),
                    odds_ratio=self._parse_float(stats_data.get("odds_ratio")),
                    hazard_ratio=self._parse_float(stats_data.get("hazard_ratio")),
                    auc=self._parse_float(stats_data.get("auc")),
                    sensitivity=self._parse_float(stats_data.get("sensitivity")),
                    specificity=self._parse_float(stats_data.get("specificity")),
                    confidence_interval=stats_data.get("confidence_interval"),
                    sample_size=self._parse_int(stats_data.get("sample_size")),
                )
                
                association = AssociationInfo(
                    marker=marker,
                    disease=disease,
                    association_type=self._parse_association_type(a.get("association_type")),
                    evidence_level=self._parse_evidence_level(a.get("evidence_level")),
                    directionality=self._parse_directionality(a.get("directionality")),
                    strength=a.get("strength"),
                    functional_impact=a.get("functional_impact"),
                    statistics=statistics,
                )
                associations.append(association)
        
        return ExtractionResult(
            pmid=pmid,
            diseases=diseases,
            markers=markers,
            associations=associations,
        )
    
    def _extract_json(self, text: str) -> str:
        """Extract JSON from text, handling markdown code blocks."""
        # Remove markdown code blocks
        text = re.sub(r'```json\s*', '', text)
        text = re.sub(r'```\s*', '', text)
        
        # Try to find JSON object
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            return match.group()
        
        return text.strip()
    
    def _parse_marker_type(self, value: Optional[str]) -> MarkerType:
        """Parse marker type string to enum."""
        if not value:
            return MarkerType.OTHER
        
        mapping = {
            "gene": MarkerType.GENE,
            "protein": MarkerType.PROTEIN,
            "metabolite": MarkerType.METABOLITE,
            "mirna": MarkerType.MIRNA,
            "microrna": MarkerType.MIRNA,
            "lncrna": MarkerType.LNCRNA,
            "methylation": MarkerType.METHYLATION,
            "snp": MarkerType.SNP,
        }
        
        return mapping.get(value.lower(), MarkerType.OTHER)
    
    def _parse_association_type(self, value: Optional[str]) -> AssociationType:
        """Parse association type string to enum."""
        if not value:
            return AssociationType.OTHER
        
        mapping = {
            "diagnostic": AssociationType.DIAGNOSTIC,
            "prognostic": AssociationType.PROGNOSTIC,
            "predictive": AssociationType.PREDICTIVE,
            "therapeutic": AssociationType.THERAPEUTIC,
            "risk": AssociationType.RISK,
            "expression": AssociationType.EXPRESSION,
            "mutation": AssociationType.MUTATION,
        }
        
        return mapping.get(value.lower(), AssociationType.OTHER)
    
    def _parse_evidence_level(self, value: Optional[str]) -> EvidenceLevel:
        """Parse evidence level string to enum."""
        if not value:
            return EvidenceLevel.UNKNOWN
        
        mapping = {
            "clinical_trial": EvidenceLevel.CLINICAL_TRIAL,
            "cohort_study": EvidenceLevel.COHORT_STUDY,
            "case_control": EvidenceLevel.CASE_CONTROL,
            "case_series": EvidenceLevel.CASE_SERIES,
            "in_vivo": EvidenceLevel.IN_VIVO,
            "in_vitro": EvidenceLevel.IN_VITRO,
            "computational": EvidenceLevel.COMPUTATIONAL,
            "review": EvidenceLevel.REVIEW,
            "meta_analysis": EvidenceLevel.META_ANALYSIS,
        }
        
        return mapping.get(value.lower(), EvidenceLevel.UNKNOWN)
    
    def _parse_directionality(self, value: Optional[str]) -> Directionality:
        """Parse directionality string to enum."""
        if not value:
            return Directionality.UNKNOWN
        
        mapping = {
            "positive": Directionality.POSITIVE,
            "negative": Directionality.NEGATIVE,
            "bidirectional": Directionality.BIDIRECTIONAL,
        }
        
        return mapping.get(value.lower(), Directionality.UNKNOWN)
    
    def _parse_float(self, value) -> Optional[float]:
        """Safely parse a float value."""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    
    def _parse_int(self, value) -> Optional[int]:
        """Safely parse an integer value."""
        if value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

