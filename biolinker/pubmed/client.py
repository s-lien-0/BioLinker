"""
PubMed E-utilities API Client with rate limiting and retry logic.
"""

import time
import logging
from typing import Optional, Generator
from dataclasses import dataclass
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from biolinker.pubmed.parser import PubMedParser, Article

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Container for PubMed search results."""
    count: int
    webenv: str
    query_key: str
    ids: list[str]


class PubMedClient:
    """
    Client for interacting with PubMed's E-utilities API.
    
    Features:
    - Automatic rate limiting (3 requests/second without API key, 10 with)
    - Retry logic with exponential backoff
    - Batch fetching with progress tracking
    - History server support for large result sets
    """
    
    BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        email: Optional[str] = None,
        tool_name: str = "BioLinker",
        requests_per_second: float = 3.0
    ):
        """
        Initialize the PubMed client.
        
        Args:
            api_key: NCBI API key (optional, increases rate limit to 10/sec)
            email: Contact email (recommended by NCBI)
            tool_name: Name of the tool making requests
            requests_per_second: Rate limit (default 3, max 10 with API key)
        """
        self.api_key = api_key
        self.email = email
        self.tool_name = tool_name
        self.requests_per_second = min(requests_per_second, 10.0 if api_key else 3.0)
        self._last_request_time = 0.0
        
        # Set up session with retry logic
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        
        self.parser = PubMedParser()
    
    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        min_interval = 1.0 / self.requests_per_second
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_request_time = time.time()
    
    def _get_base_params(self) -> dict:
        """Get base parameters for all requests."""
        params = {"tool": self.tool_name}
        if self.api_key:
            params["api_key"] = self.api_key
        if self.email:
            params["email"] = self.email
        return params
    
    def search(
        self,
        query: str,
        max_results: Optional[int] = None,
        use_history: bool = True,
        sort: str = "relevance",
        min_date: Optional[str] = None,
        max_date: Optional[str] = None,
    ) -> SearchResult:
        """
        Search PubMed for articles matching the query.
        
        Args:
            query: Search query (supports PubMed syntax)
            max_results: Maximum number of results (None for all)
            use_history: Use history server for large result sets
            sort: Sort order ('relevance' or 'date')
            min_date: Minimum publication date (YYYY/MM/DD)
            max_date: Maximum publication date (YYYY/MM/DD)
            
        Returns:
            SearchResult with count, webenv, query_key, and IDs
        """
        self._rate_limit()
        
        params = {
            **self._get_base_params(),
            "db": "pubmed",
            "term": query,
            "retmode": "json",
            "usehistory": "y" if use_history else "n",
            "sort": sort,
        }
        
        if max_results:
            params["retmax"] = min(max_results, 10000)  # NCBI limit
        
        if min_date:
            params["mindate"] = min_date
            params["datetype"] = "pdat"
        if max_date:
            params["maxdate"] = max_date
            params["datetype"] = "pdat"
        
        logger.info(f"Searching PubMed: {query}")
        response = self.session.get(f"{self.BASE_URL}/esearch.fcgi", params=params)
        response.raise_for_status()
        
        data = response.json()["esearchresult"]
        
        result = SearchResult(
            count=int(data.get("count", 0)),
            webenv=data.get("webenv", ""),
            query_key=data.get("querykey", ""),
            ids=data.get("idlist", [])
        )
        
        logger.info(f"Found {result.count} results")
        return result
    
    def fetch_articles(
        self,
        search_result: Optional[SearchResult] = None,
        pmids: Optional[list[str]] = None,
        batch_size: int = 100,
        max_articles: Optional[int] = None,
    ) -> Generator[Article, None, None]:
        """
        Fetch full article details from PubMed.
        
        Args:
            search_result: Result from search() to fetch from history
            pmids: List of PMIDs to fetch directly
            batch_size: Number of articles per request (max 500)
            max_articles: Maximum total articles to fetch
            
        Yields:
            Article objects with full metadata
        """
        batch_size = min(batch_size, 500)  # NCBI limit
        
        if pmids:
            # Direct fetch by PMIDs
            total = len(pmids) if not max_articles else min(len(pmids), max_articles)
            for i in range(0, total, batch_size):
                batch_pmids = pmids[i:i + batch_size]
                yield from self._fetch_batch(pmids=batch_pmids)
                
        elif search_result:
            # Fetch from history server
            total = search_result.count
            if max_articles:
                total = min(total, max_articles)
            
            for retstart in range(0, total, batch_size):
                actual_batch = min(batch_size, total - retstart)
                logger.info(f"Fetching articles {retstart + 1}-{retstart + actual_batch} of {total}")
                yield from self._fetch_batch(
                    webenv=search_result.webenv,
                    query_key=search_result.query_key,
                    retstart=retstart,
                    retmax=actual_batch
                )
    
    def _fetch_batch(
        self,
        pmids: Optional[list[str]] = None,
        webenv: Optional[str] = None,
        query_key: Optional[str] = None,
        retstart: int = 0,
        retmax: int = 100,
    ) -> Generator[Article, None, None]:
        """Fetch a batch of articles."""
        self._rate_limit()
        
        params = {
            **self._get_base_params(),
            "db": "pubmed",
            "retmode": "xml",
            "rettype": "abstract",
        }
        
        if pmids:
            params["id"] = ",".join(pmids)
        else:
            params["WebEnv"] = webenv
            params["query_key"] = query_key
            params["retstart"] = retstart
            params["retmax"] = retmax
        
        response = self.session.get(f"{self.BASE_URL}/efetch.fcgi", params=params)
        response.raise_for_status()
        
        yield from self.parser.parse_xml(response.text)
    
    def fetch_single(self, pmid: str) -> Optional[Article]:
        """Fetch a single article by PMID."""
        articles = list(self._fetch_batch(pmids=[pmid]))
        return articles[0] if articles else None


def create_biomarker_query(
    diseases: Optional[list[str]] = None,
    marker_types: Optional[list[str]] = None,
    additional_terms: Optional[list[str]] = None,
) -> str:
    """
    Build a PubMed query for biomarker research.
    
    Args:
        diseases: List of diseases to search for
        marker_types: Types of markers (gene, protein, metabolite)
        additional_terms: Additional search terms
        
    Returns:
        Formatted PubMed query string
    """
    base_terms = [
        "biomarker[tiab]",
        "marker[tiab]",
        "gene expression[tiab]",
        "diagnostic marker[tiab]",
        "prognostic marker[tiab]",
    ]
    
    query_parts = [f"({' OR '.join(base_terms)})"]
    
    if diseases:
        disease_terms = [f'"{d}"[tiab]' for d in diseases]
        query_parts.append(f"({' OR '.join(disease_terms)})")
    
    if marker_types:
        type_map = {
            "gene": "gene[tiab] OR genetic[tiab]",
            "protein": "protein[tiab] OR proteome[tiab]",
            "metabolite": "metabolite[tiab] OR metabolome[tiab]",
            "mirna": "miRNA[tiab] OR microRNA[tiab]",
        }
        type_terms = [type_map.get(t, f"{t}[tiab]") for t in marker_types]
        query_parts.append(f"({' OR '.join(type_terms)})")
    
    if additional_terms:
        query_parts.extend(additional_terms)
    
    return " AND ".join(query_parts)

