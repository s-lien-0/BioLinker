"""
PubMed XML response parser.
"""

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional, Generator
from datetime import date
import logging

logger = logging.getLogger(__name__)


@dataclass
class Author:
    """Represents an article author."""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    affiliation: Optional[str] = None
    orcid: Optional[str] = None
    
    @property
    def full_name(self) -> str:
        """Get the author's full name."""
        parts = [p for p in [self.first_name, self.last_name] if p]
        return " ".join(parts) if parts else "Unknown"


@dataclass
class Article:
    """Represents a PubMed article with full metadata."""
    pmid: str
    title: str
    abstract: str = ""
    authors: list[Author] = field(default_factory=list)
    journal: str = ""
    publication_date: Optional[date] = None
    publication_year: Optional[int] = None
    doi: Optional[str] = None
    pmc_id: Optional[str] = None
    keywords: list[str] = field(default_factory=list)
    mesh_terms: list[str] = field(default_factory=list)
    publication_types: list[str] = field(default_factory=list)
    
    @property
    def author_names(self) -> list[str]:
        """Get list of author full names."""
        return [a.full_name for a in self.authors]
    
    @property
    def authors_string(self) -> str:
        """Get comma-separated author names."""
        return ", ".join(self.author_names)
    
    def to_dict(self) -> dict:
        """Convert article to dictionary."""
        return {
            "pmid": self.pmid,
            "title": self.title,
            "abstract": self.abstract,
            "authors": self.authors_string,
            "journal": self.journal,
            "publication_year": self.publication_year,
            "doi": self.doi,
            "pmc_id": self.pmc_id,
            "keywords": self.keywords,
            "mesh_terms": self.mesh_terms,
        }


class PubMedParser:
    """Parser for PubMed XML responses."""
    
    def parse_xml(self, xml_content: str) -> Generator[Article, None, None]:
        """
        Parse PubMed XML response and yield Article objects.
        
        Args:
            xml_content: Raw XML string from efetch
            
        Yields:
            Article objects
        """
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            logger.error(f"Failed to parse XML: {e}")
            return
        
        for article_elem in root.findall(".//PubmedArticle"):
            try:
                article = self._parse_article(article_elem)
                if article:
                    yield article
            except Exception as e:
                logger.warning(f"Failed to parse article: {e}")
                continue
    
    def _parse_article(self, elem: ET.Element) -> Optional[Article]:
        """Parse a single PubmedArticle element."""
        # Get PMID
        pmid_elem = elem.find(".//PMID")
        if pmid_elem is None or not pmid_elem.text:
            return None
        pmid = pmid_elem.text
        
        # Get title
        title_elem = elem.find(".//ArticleTitle")
        title = self._get_text_content(title_elem) if title_elem is not None else "No Title"
        
        # Get abstract (handle structured abstracts)
        abstract = self._parse_abstract(elem)
        
        # Get authors
        authors = self._parse_authors(elem)
        
        # Get journal
        journal_elem = elem.find(".//Journal/Title")
        journal = journal_elem.text if journal_elem is not None else ""
        
        # Get publication date
        pub_date, pub_year = self._parse_date(elem)
        
        # Get DOI
        doi = None
        for id_elem in elem.findall(".//ArticleIdList/ArticleId"):
            if id_elem.get("IdType") == "doi":
                doi = id_elem.text
                break
        
        # Get PMC ID
        pmc_id = None
        for id_elem in elem.findall(".//ArticleIdList/ArticleId"):
            if id_elem.get("IdType") == "pmc":
                pmc_id = id_elem.text
                break
        
        # Get keywords
        keywords = []
        for kw_elem in elem.findall(".//KeywordList/Keyword"):
            if kw_elem.text:
                keywords.append(kw_elem.text)
        
        # Get MeSH terms
        mesh_terms = []
        for mesh_elem in elem.findall(".//MeshHeadingList/MeshHeading/DescriptorName"):
            if mesh_elem.text:
                mesh_terms.append(mesh_elem.text)
        
        # Get publication types
        pub_types = []
        for pt_elem in elem.findall(".//PublicationTypeList/PublicationType"):
            if pt_elem.text:
                pub_types.append(pt_elem.text)
        
        return Article(
            pmid=pmid,
            title=title,
            abstract=abstract,
            authors=authors,
            journal=journal,
            publication_date=pub_date,
            publication_year=pub_year,
            doi=doi,
            pmc_id=pmc_id,
            keywords=keywords,
            mesh_terms=mesh_terms,
            publication_types=pub_types,
        )
    
    def _get_text_content(self, elem: ET.Element) -> str:
        """Get all text content from an element, including nested tags."""
        return "".join(elem.itertext())
    
    def _parse_abstract(self, elem: ET.Element) -> str:
        """Parse abstract, handling structured abstracts."""
        abstract_parts = []
        
        # Try structured abstract first
        for abstract_text in elem.findall(".//Abstract/AbstractText"):
            label = abstract_text.get("Label", "")
            text = self._get_text_content(abstract_text) if abstract_text is not None else ""
            
            if label and text:
                abstract_parts.append(f"{label}: {text}")
            elif text:
                abstract_parts.append(text)
        
        if abstract_parts:
            return "\n\n".join(abstract_parts)
        
        # Fall back to simple abstract
        simple_abstract = elem.find(".//AbstractText")
        if simple_abstract is not None:
            return self._get_text_content(simple_abstract)
        
        return ""
    
    def _parse_authors(self, elem: ET.Element) -> list[Author]:
        """Parse author list."""
        authors = []
        
        for author_elem in elem.findall(".//AuthorList/Author"):
            last_name = author_elem.find("LastName")
            first_name = author_elem.find("ForeName")
            affiliation = author_elem.find("AffiliationInfo/Affiliation")
            
            # Get ORCID if available
            orcid = None
            for identifier in author_elem.findall("Identifier"):
                if identifier.get("Source") == "ORCID":
                    orcid = identifier.text
            
            author = Author(
                first_name=first_name.text if first_name is not None else None,
                last_name=last_name.text if last_name is not None else None,
                affiliation=affiliation.text if affiliation is not None else None,
                orcid=orcid,
            )
            authors.append(author)
        
        return authors
    
    def _parse_date(self, elem: ET.Element) -> tuple[Optional[date], Optional[int]]:
        """Parse publication date."""
        # Try PubDate first
        pub_date_elem = elem.find(".//PubDate")
        if pub_date_elem is not None:
            year = pub_date_elem.find("Year")
            month = pub_date_elem.find("Month")
            day = pub_date_elem.find("Day")
            
            if year is not None and year.text:
                year_int = int(year.text)
                
                # Try to build full date
                try:
                    month_int = self._parse_month(month.text) if month is not None and month.text else 1
                    day_int = int(day.text) if day is not None and day.text else 1
                    return date(year_int, month_int, day_int), year_int
                except (ValueError, TypeError):
                    return None, year_int
        
        # Fall back to ArticleDate
        article_date = elem.find(".//ArticleDate")
        if article_date is not None:
            year = article_date.find("Year")
            if year is not None and year.text:
                return None, int(year.text)
        
        return None, None
    
    def _parse_month(self, month_str: str) -> int:
        """Convert month string to integer."""
        month_map = {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4,
            "may": 5, "jun": 6, "jul": 7, "aug": 8,
            "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        }
        
        # Try numeric first
        try:
            return int(month_str)
        except ValueError:
            pass
        
        # Try month name
        return month_map.get(month_str.lower()[:3], 1)

