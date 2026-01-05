"""
BioLinker - A biomarker discovery and knowledge graph platform.

This package provides tools for:
- Searching and fetching PubMed articles
- Extracting biomarker-disease relationships using LLMs
- Enriching data with external databases (HGNC, UniProt)
- Storing and querying knowledge graphs
"""

__version__ = "0.1.0"
__author__ = "BioLinker Team"

from biolinker.pubmed.client import PubMedClient
from biolinker.extraction.extractor import BiomarkerExtractor
from biolinker.storage.database import DatabaseManager

__all__ = ["PubMedClient", "BiomarkerExtractor", "DatabaseManager"]

