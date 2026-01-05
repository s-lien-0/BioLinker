"""
UniProt API client for protein information enrichment.
"""

import logging
from typing import Optional
from dataclasses import dataclass, field

import requests

logger = logging.getLogger(__name__)


@dataclass
class ProteinInfo:
    """Information about a protein from UniProt."""
    uniprot_id: str
    entry_name: str
    protein_name: str
    gene_names: list[str] = field(default_factory=list)
    organism: str = ""
    function: str = ""
    subcellular_location: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    diseases: list[str] = field(default_factory=list)
    sequence_length: Optional[int] = None
    mass: Optional[int] = None
    
    def to_dict(self) -> dict:
        return {
            "uniprot_id": self.uniprot_id,
            "entry_name": self.entry_name,
            "protein_name": self.protein_name,
            "gene_names": self.gene_names,
            "organism": self.organism,
            "function": self.function,
            "subcellular_location": self.subcellular_location,
            "keywords": self.keywords,
            "diseases": self.diseases,
            "sequence_length": self.sequence_length,
            "mass": self.mass,
        }


class UniProtClient:
    """
    Client for the UniProt REST API.
    
    Provides protein information and gene-protein mappings.
    https://www.uniprot.org/help/api
    """
    
    BASE_URL = "https://rest.uniprot.org"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
        })
        self._cache: dict[str, Optional[ProteinInfo]] = {}
    
    def fetch_by_id(self, uniprot_id: str) -> Optional[ProteinInfo]:
        """
        Fetch protein info by UniProt accession ID.
        
        Args:
            uniprot_id: UniProt accession (e.g., "P04637")
            
        Returns:
            ProteinInfo if found, None otherwise
        """
        cache_key = f"id:{uniprot_id}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        try:
            response = self.session.get(
                f"{self.BASE_URL}/uniprotkb/{uniprot_id}.json",
                timeout=30
            )
            
            if response.status_code == 404:
                self._cache[cache_key] = None
                return None
            
            response.raise_for_status()
            data = response.json()
            
            protein = self._parse_protein(data)
            self._cache[cache_key] = protein
            return protein
            
        except Exception as e:
            logger.warning(f"UniProt fetch failed for '{uniprot_id}': {e}")
            return None
    
    def search_by_gene(
        self,
        gene_symbol: str,
        organism: str = "human",
        reviewed: bool = True
    ) -> list[ProteinInfo]:
        """
        Search for proteins by gene symbol.
        
        Args:
            gene_symbol: Gene symbol to search
            organism: Organism name (default: human)
            reviewed: Only return Swiss-Prot (reviewed) entries
            
        Returns:
            List of matching ProteinInfo objects
        """
        query_parts = [f"gene:{gene_symbol}"]
        
        if organism:
            query_parts.append(f"organism_name:{organism}")
        
        if reviewed:
            query_parts.append("reviewed:true")
        
        query = " AND ".join(query_parts)
        
        return self.search(query)
    
    def search(self, query: str, limit: int = 10) -> list[ProteinInfo]:
        """
        Search UniProt with a query string.
        
        Args:
            query: UniProt query string
            limit: Maximum results to return
            
        Returns:
            List of ProteinInfo objects
        """
        try:
            params = {
                "query": query,
                "format": "json",
                "size": limit,
            }
            
            response = self.session.get(
                f"{self.BASE_URL}/uniprotkb/search",
                params=params,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            results = []
            for entry in data.get("results", []):
                protein = self._parse_protein(entry)
                if protein:
                    results.append(protein)
            
            return results
            
        except Exception as e:
            logger.warning(f"UniProt search failed for '{query}': {e}")
            return []
    
    def get_protein_for_gene(
        self,
        gene_symbol: str,
        organism: str = "human"
    ) -> Optional[ProteinInfo]:
        """
        Get the primary protein for a gene symbol.
        
        Args:
            gene_symbol: Gene symbol
            organism: Organism name
            
        Returns:
            ProteinInfo for the primary protein, or None
        """
        results = self.search_by_gene(gene_symbol, organism, reviewed=True)
        if results:
            return results[0]
        
        # Fall back to unreviewed
        results = self.search_by_gene(gene_symbol, organism, reviewed=False)
        return results[0] if results else None
    
    def _parse_protein(self, data: dict) -> Optional[ProteinInfo]:
        """Parse UniProt API response to ProteinInfo."""
        try:
            # Get primary accession
            uniprot_id = data.get("primaryAccession", "")
            if not uniprot_id:
                return None
            
            # Get entry name
            entry_name = data.get("uniProtkbId", "")
            
            # Get protein name
            protein_desc = data.get("proteinDescription", {})
            rec_name = protein_desc.get("recommendedName", {})
            full_name = rec_name.get("fullName", {})
            protein_name = full_name.get("value", "Unknown")
            
            # Get gene names
            gene_names = []
            for gene in data.get("genes", []):
                if gene.get("geneName", {}).get("value"):
                    gene_names.append(gene["geneName"]["value"])
                for syn in gene.get("synonyms", []):
                    if syn.get("value"):
                        gene_names.append(syn["value"])
            
            # Get organism
            organism_data = data.get("organism", {})
            organism = organism_data.get("scientificName", "")
            
            # Get function from comments
            function = ""
            subcellular = []
            diseases = []
            
            for comment in data.get("comments", []):
                comment_type = comment.get("commentType", "")
                
                if comment_type == "FUNCTION":
                    texts = comment.get("texts", [])
                    if texts:
                        function = texts[0].get("value", "")
                
                elif comment_type == "SUBCELLULAR LOCATION":
                    for loc in comment.get("subcellularLocations", []):
                        location = loc.get("location", {})
                        if location.get("value"):
                            subcellular.append(location["value"])
                
                elif comment_type == "DISEASE":
                    disease = comment.get("disease", {})
                    if disease.get("diseaseId"):
                        diseases.append(disease["diseaseId"])
            
            # Get keywords
            keywords = [kw.get("name", "") for kw in data.get("keywords", [])]
            keywords = [k for k in keywords if k]
            
            # Get sequence info
            sequence = data.get("sequence", {})
            
            return ProteinInfo(
                uniprot_id=uniprot_id,
                entry_name=entry_name,
                protein_name=protein_name,
                gene_names=gene_names,
                organism=organism,
                function=function,
                subcellular_location=subcellular,
                keywords=keywords,
                diseases=diseases,
                sequence_length=sequence.get("length"),
                mass=sequence.get("molWeight"),
            )
            
        except Exception as e:
            logger.warning(f"Failed to parse UniProt entry: {e}")
            return None


class EnrichmentService:
    """
    Service for enriching biomarker data with external database information.
    """
    
    def __init__(self):
        self.hgnc = None
        self.uniprot = UniProtClient()
        self._hgnc_loaded = False
    
    def _ensure_hgnc(self):
        """Lazy-load HGNC client."""
        if not self._hgnc_loaded:
            from biolinker.enrichment.hgnc import HGNCClient
            self.hgnc = HGNCClient()
            self._hgnc_loaded = True
    
    def enrich_marker(self, marker_name: str, marker_type: str) -> dict:
        """
        Enrich a marker with external database information.
        
        Args:
            marker_name: Name or symbol of the marker
            marker_type: Type of marker (gene, protein, etc.)
            
        Returns:
            Dict with enrichment data
        """
        result = {
            "original_name": marker_name,
            "marker_type": marker_type,
            "hgnc": None,
            "uniprot": None,
        }
        
        if marker_type in ("gene", "protein"):
            # Try HGNC lookup
            self._ensure_hgnc()
            gene_info = self.hgnc.fetch_by_symbol(marker_name)
            if gene_info:
                result["hgnc"] = gene_info.to_dict()
                
                # Try UniProt if we have the ID
                if gene_info.uniprot_id:
                    protein_info = self.uniprot.fetch_by_id(gene_info.uniprot_id)
                    if protein_info:
                        result["uniprot"] = protein_info.to_dict()
            else:
                # Try searching
                results = self.hgnc.search(marker_name)
                if results:
                    result["hgnc"] = results[0].to_dict()
                    result["hgnc"]["is_exact_match"] = False
        
        return result

