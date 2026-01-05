"""Data enrichment module for external database lookups."""

from biolinker.enrichment.hgnc import HGNCClient
from biolinker.enrichment.uniprot import UniProtClient

__all__ = ["HGNCClient", "UniProtClient"]

