"""
Database manager for BioLinker.

Supports SQLite (development) and PostgreSQL (production).
"""

import logging
import os
from datetime import datetime
from typing import Optional
from pathlib import Path

from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from biolinker.storage.models import (
    Base,
    ArticleModel,
    AuthorModel,
    KeywordModel,
    MeshTermModel,
    DiseaseModel,
    MarkerModel,
    AssociationModel,
    SearchQueryModel,
)
from biolinker.pubmed.parser import Article
from biolinker.extraction.models import ExtractionResult

logger = logging.getLogger(__name__)

# Singleton instance
_db_instance: Optional["DatabaseManager"] = None


def get_database_url() -> str:
    """Get database URL from environment or use default."""
    url = os.getenv("DATABASE_URL")
    if url:
        # Handle Heroku-style postgres:// URLs
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url
    
    # Default to SQLite
    db_path = Path.home() / ".biolinker" / "biolinker.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{db_path}"


class DatabaseManager:
    """
    Manager for BioLinker database operations.
    
    Handles storage and retrieval of articles, markers, diseases, and associations.
    Supports SQLite and PostgreSQL.
    """
    
    def __init__(self, database_url: Optional[str] = None):
        """
        Initialize the database manager.
        
        Args:
            database_url: SQLAlchemy database URL. Defaults to env var or SQLite.
        """
        global _db_instance
        
        if database_url is None:
            database_url = get_database_url()
        
        self.database_url = database_url
        self.is_sqlite = database_url.startswith("sqlite")
        
        # Configure engine based on database type
        if self.is_sqlite:
            # SQLite-specific settings
            self.engine = create_engine(
                database_url,
                echo=False,
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
        else:
            # PostgreSQL settings
            self.engine = create_engine(
                database_url,
                echo=False,
                pool_size=5,
                max_overflow=10,
                pool_pre_ping=True,
            )
        
        self.SessionLocal = sessionmaker(bind=self.engine)
        _db_instance = self
    
    def create_tables(self):
        """Create all database tables."""
        Base.metadata.create_all(self.engine)
        logger.info("Database tables created")
    
    def get_session(self) -> Session:
        """Get a new database session."""
        return self.SessionLocal()
    
    def store_article(self, article: Article, session: Optional[Session] = None) -> ArticleModel:
        """
        Store a PubMed article.
        
        Args:
            article: Article to store
            session: Database session (creates one if not provided)
            
        Returns:
            Stored ArticleModel
        """
        own_session = session is None
        if own_session:
            session = self.get_session()
        
        try:
            # Check if article already exists
            existing = session.query(ArticleModel).filter_by(pmid=article.pmid).first()
            if existing:
                return existing
            
            # Create article
            article_model = ArticleModel(
                pmid=article.pmid,
                title=article.title,
                abstract=article.abstract,
                journal=article.journal,
                publication_year=article.publication_year,
                publication_date=article.publication_date,
                doi=article.doi,
                pmc_id=article.pmc_id,
            )
            
            # Add authors
            for author in article.authors:
                author_model = self._get_or_create_author(session, author)
                article_model.authors.append(author_model)
            
            # Add keywords
            for keyword in article.keywords:
                keyword_model = self._get_or_create_keyword(session, keyword)
                article_model.keywords.append(keyword_model)
            
            # Add MeSH terms
            for term in article.mesh_terms:
                term_model = self._get_or_create_mesh_term(session, term)
                article_model.mesh_terms.append(term_model)
            
            session.add(article_model)
            
            if own_session:
                session.commit()
            
            return article_model
            
        except Exception as e:
            if own_session:
                session.rollback()
            raise e
        finally:
            if own_session:
                session.close()
    
    def store_extraction_result(
        self,
        result: ExtractionResult,
        session: Optional[Session] = None
    ) -> Optional[ArticleModel]:
        """
        Store extraction results for an article.
        
        Args:
            result: Extraction result to store
            session: Database session
            
        Returns:
            Updated ArticleModel
        """
        own_session = session is None
        if own_session:
            session = self.get_session()
        
        try:
            # Get article
            article = session.query(ArticleModel).filter_by(pmid=result.pmid).first()
            if not article:
                logger.warning(f"Article {result.pmid} not found in database")
                return None
            
            # Update processing status
            article.is_processed = True
            article.processed_at = datetime.utcnow()
            
            if not result.extraction_successful:
                article.extraction_error = result.error_message
                if own_session:
                    session.commit()
                return article
            
            # Store diseases and markers
            disease_models = {}
            marker_models = {}
            
            for disease in result.diseases:
                disease_model = self._get_or_create_disease(session, disease)
                disease_models[disease.name.lower()] = disease_model
            
            for marker in result.markers:
                marker_model = self._get_or_create_marker(session, marker)
                marker_models[marker.name.lower()] = marker_model
            
            # Store associations
            for assoc in result.associations:
                marker_model = marker_models.get(assoc.marker.name.lower())
                disease_model = disease_models.get(assoc.disease.name.lower())
                
                if marker_model and disease_model:
                    assoc_model = AssociationModel(
                        article_id=article.id,
                        marker_id=marker_model.id,
                        disease_id=disease_model.id,
                        association_type=assoc.association_type.value,
                        evidence_level=assoc.evidence_level.value,
                        directionality=assoc.directionality.value,
                        strength=assoc.strength,
                        functional_impact=assoc.functional_impact,
                        p_value=assoc.statistics.p_value,
                        odds_ratio=assoc.statistics.odds_ratio,
                        hazard_ratio=assoc.statistics.hazard_ratio,
                        confidence_interval=assoc.statistics.confidence_interval,
                        auc=assoc.statistics.auc,
                        sensitivity=assoc.statistics.sensitivity,
                        specificity=assoc.statistics.specificity,
                        sample_size=assoc.statistics.sample_size,
                        confidence_score=assoc.confidence_score,
                    )
                    session.add(assoc_model)
            
            if own_session:
                session.commit()
            
            return article
            
        except Exception as e:
            if own_session:
                session.rollback()
            raise e
        finally:
            if own_session:
                session.close()
    
    def _get_or_create_author(self, session: Session, author) -> AuthorModel:
        """Get or create an author."""
        full_name = author.full_name
        existing = session.query(AuthorModel).filter_by(full_name=full_name).first()
        if existing:
            return existing
        
        model = AuthorModel(
            first_name=author.first_name,
            last_name=author.last_name,
            full_name=full_name,
            orcid=author.orcid,
        )
        session.add(model)
        session.flush()
        return model
    
    def _get_or_create_keyword(self, session: Session, keyword: str) -> KeywordModel:
        """Get or create a keyword."""
        existing = session.query(KeywordModel).filter_by(keyword=keyword).first()
        if existing:
            return existing
        
        model = KeywordModel(keyword=keyword)
        session.add(model)
        session.flush()
        return model
    
    def _get_or_create_mesh_term(self, session: Session, term: str) -> MeshTermModel:
        """Get or create a MeSH term."""
        existing = session.query(MeshTermModel).filter_by(term=term).first()
        if existing:
            return existing
        
        model = MeshTermModel(term=term)
        session.add(model)
        session.flush()
        return model
    
    def _get_or_create_disease(self, session: Session, disease) -> DiseaseModel:
        """Get or create a disease."""
        normalized = disease.name.lower().strip()
        existing = session.query(DiseaseModel).filter_by(name_normalized=normalized).first()
        if existing:
            return existing
        
        model = DiseaseModel(
            name=disease.name,
            name_normalized=normalized,
            category=disease.category,
        )
        session.add(model)
        session.flush()
        return model
    
    def _get_or_create_marker(self, session: Session, marker) -> MarkerModel:
        """Get or create a marker."""
        # Try to find by symbol first, then name
        existing = None
        if marker.symbol:
            existing = session.query(MarkerModel).filter_by(symbol=marker.symbol).first()
        if not existing:
            existing = session.query(MarkerModel).filter_by(name=marker.name).first()
        
        if existing:
            return existing
        
        model = MarkerModel(
            name=marker.name,
            symbol=marker.symbol,
            marker_type=marker.marker_type.value,
            hgnc_id=marker.hgnc_id,
            uniprot_id=marker.uniprot_id,
            ensembl_id=marker.ensembl_id,
            chromosome=marker.chromosome,
        )
        session.add(model)
        session.flush()
        return model
    
    # Query methods
    
    def get_article(self, pmid: str) -> Optional[ArticleModel]:
        """Get an article by PMID."""
        with self.get_session() as session:
            return session.query(ArticleModel).filter_by(pmid=pmid).first()
    
    def get_marker(self, symbol: str) -> Optional[MarkerModel]:
        """Get a marker by symbol."""
        with self.get_session() as session:
            return session.query(MarkerModel).filter_by(symbol=symbol).first()
    
    def get_disease(self, name: str) -> Optional[DiseaseModel]:
        """Get a disease by name."""
        with self.get_session() as session:
            normalized = name.lower().strip()
            return session.query(DiseaseModel).filter_by(name_normalized=normalized).first()
    
    def get_associations_for_marker(self, symbol: str) -> list[dict]:
        """Get all associations for a marker."""
        with self.get_session() as session:
            marker = session.query(MarkerModel).filter_by(symbol=symbol).first()
            if not marker:
                return []
            
            results = []
            for assoc in marker.associations:
                results.append({
                    "disease": assoc.disease.name,
                    "association_type": assoc.association_type,
                    "evidence_level": assoc.evidence_level,
                    "article_pmid": assoc.article.pmid,
                    "article_title": assoc.article.title,
                    "p_value": assoc.p_value,
                    "auc": assoc.auc,
                })
            return results
    
    def get_associations_for_disease(self, disease_name: str) -> list[dict]:
        """Get all associations for a disease."""
        with self.get_session() as session:
            normalized = disease_name.lower().strip()
            disease = session.query(DiseaseModel).filter_by(name_normalized=normalized).first()
            if not disease:
                return []
            
            results = []
            for assoc in disease.associations:
                results.append({
                    "marker": assoc.marker.symbol or assoc.marker.name,
                    "marker_type": assoc.marker.marker_type,
                    "association_type": assoc.association_type,
                    "evidence_level": assoc.evidence_level,
                    "article_pmid": assoc.article.pmid,
                    "p_value": assoc.p_value,
                    "auc": assoc.auc,
                })
            return results
    
    def get_statistics(self) -> dict:
        """Get database statistics."""
        with self.get_session() as session:
            return {
                "articles": session.query(func.count(ArticleModel.id)).scalar(),
                "articles_processed": session.query(func.count(ArticleModel.id)).filter(
                    ArticleModel.is_processed == True
                ).scalar(),
                "markers": session.query(func.count(MarkerModel.id)).scalar(),
                "diseases": session.query(func.count(DiseaseModel.id)).scalar(),
                "associations": session.query(func.count(AssociationModel.id)).scalar(),
            }
    
    def search_markers(self, query: str, limit: int = 50) -> list[MarkerModel]:
        """Search markers by name or symbol."""
        with self.get_session() as session:
            return session.query(MarkerModel).filter(
                (MarkerModel.name.ilike(f"%{query}%")) |
                (MarkerModel.symbol.ilike(f"%{query}%"))
            ).limit(limit).all()
    
    def search_diseases(self, query: str, limit: int = 50) -> list[DiseaseModel]:
        """Search diseases by name."""
        with self.get_session() as session:
            return session.query(DiseaseModel).filter(
                DiseaseModel.name.ilike(f"%{query}%")
            ).limit(limit).all()

