"""
HGNC (HUGO Gene Nomenclature Committee) API client for gene symbol validation.
"""

import logging
from typing import Optional
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)


@dataclass
class GeneInfo:
    """Information about a gene from HGNC."""
    hgnc_id: str
    symbol: str
    name: str
    locus_type: str
    chromosome: Optional[str] = None
    ensembl_id: Optional[str] = None
    uniprot_id: Optional[str] = None
    prev_symbols: list[str] = None
    alias_symbols: list[str] = None
    
    def __post_init__(self):
        if self.prev_symbols is None:
            self.prev_symbols = []
        if self.alias_symbols is None:
            self.alias_symbols = []
    
    def to_dict(self) -> dict:
        return {
            "hgnc_id": self.hgnc_id,
            "symbol": self.symbol,
            "name": self.name,
            "locus_type": self.locus_type,
            "chromosome": self.chromosome,
            "ensembl_id": self.ensembl_id,
            "uniprot_id": self.uniprot_id,
            "prev_symbols": self.prev_symbols,
            "alias_symbols": self.alias_symbols,
        }


class HGNCClient:
    """
    Client for the HGNC REST API.
    
    Provides gene symbol validation and normalization.
    https://www.genenames.org/help/rest/
    """
    
    BASE_URL = "https://rest.genenames.org"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
        })
        self._cache: dict[str, Optional[GeneInfo]] = {}
    
    def search(self, query: str) -> list[GeneInfo]:
        """
        Search HGNC for genes matching the query.
        
        Args:
            query: Gene symbol, name, or alias to search
            
        Returns:
            List of matching GeneInfo objects
        """
        try:
            response = self.session.get(
                f"{self.BASE_URL}/search/{query}",
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            results = []
            for doc in data.get("response", {}).get("docs", []):
                gene = self._parse_gene(doc)
                if gene:
                    results.append(gene)
            
            return results
            
        except Exception as e:
            logger.warning(f"HGNC search failed for '{query}': {e}")
            return []
    
    def fetch_by_symbol(self, symbol: str) -> Optional[GeneInfo]:
        """
        Fetch gene info by official symbol.
        
        Args:
            symbol: Official HGNC symbol (e.g., "BRCA1")
            
        Returns:
            GeneInfo if found, None otherwise
        """
        # Check cache first
        cache_key = f"symbol:{symbol.upper()}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        try:
            response = self.session.get(
                f"{self.BASE_URL}/fetch/symbol/{symbol}",
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            docs = data.get("response", {}).get("docs", [])
            if docs:
                gene = self._parse_gene(docs[0])
                self._cache[cache_key] = gene
                return gene
            
            self._cache[cache_key] = None
            return None
            
        except Exception as e:
            logger.warning(f"HGNC fetch failed for symbol '{symbol}': {e}")
            return None
    
    def fetch_by_hgnc_id(self, hgnc_id: str) -> Optional[GeneInfo]:
        """
        Fetch gene info by HGNC ID.
        
        Args:
            hgnc_id: HGNC ID (e.g., "HGNC:1100" or "1100")
            
        Returns:
            GeneInfo if found, None otherwise
        """
        # Normalize HGNC ID
        if not hgnc_id.startswith("HGNC:"):
            hgnc_id = f"HGNC:{hgnc_id}"
        
        cache_key = f"id:{hgnc_id}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        try:
            response = self.session.get(
                f"{self.BASE_URL}/fetch/hgnc_id/{hgnc_id}",
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            docs = data.get("response", {}).get("docs", [])
            if docs:
                gene = self._parse_gene(docs[0])
                self._cache[cache_key] = gene
                return gene
            
            self._cache[cache_key] = None
            return None
            
        except Exception as e:
            logger.warning(f"HGNC fetch failed for ID '{hgnc_id}': {e}")
            return None
    
    def validate_symbol(self, symbol: str) -> tuple[bool, Optional[str]]:
        """
        Validate a gene symbol and return the official symbol.
        
        Args:
            symbol: Gene symbol to validate
            
        Returns:
            Tuple of (is_valid, official_symbol)
        """
        # Try exact match first
        gene = self.fetch_by_symbol(symbol)
        if gene:
            return True, gene.symbol
        
        # Search for possible matches
        results = self.search(symbol)
        if results:
            # Check if it's an alias
            for gene in results:
                if symbol.upper() in [s.upper() for s in gene.alias_symbols]:
                    return True, gene.symbol
                if symbol.upper() in [s.upper() for s in gene.prev_symbols]:
                    return True, gene.symbol
            
            # Return first match as suggestion
            return False, results[0].symbol
        
        return False, None
    
    def normalize_symbols(self, symbols: list[str]) -> dict[str, Optional[str]]:
        """
        Normalize a list of gene symbols to official HGNC symbols.
        
        Args:
            symbols: List of symbols to normalize
            
        Returns:
            Dict mapping input symbols to official symbols (or None)
        """
        result = {}
        for symbol in symbols:
            _, official = self.validate_symbol(symbol)
            result[symbol] = official
        return result
    
    def _parse_gene(self, doc: dict) -> Optional[GeneInfo]:
        """Parse HGNC API response document to GeneInfo."""
        try:
            # Get UniProt ID (may be in different fields)
            uniprot_ids = doc.get("uniprot_ids", [])
            uniprot_id = uniprot_ids[0] if uniprot_ids else None
            
            # Get Ensembl ID
            ensembl_ids = doc.get("ensembl_gene_id")
            ensembl_id = ensembl_ids if isinstance(ensembl_ids, str) else None
            
            return GeneInfo(
                hgnc_id=doc.get("hgnc_id", ""),
                symbol=doc.get("symbol", ""),
                name=doc.get("name", ""),
                locus_type=doc.get("locus_type", ""),
                chromosome=doc.get("location"),
                ensembl_id=ensembl_id,
                uniprot_id=uniprot_id,
                prev_symbols=doc.get("prev_symbol", []),
                alias_symbols=doc.get("alias_symbol", []),
            )
        except Exception as e:
            logger.warning(f"Failed to parse HGNC document: {e}")
            return None

