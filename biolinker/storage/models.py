"""
SQLAlchemy database models for BioLinker.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column, Integer, String, Text, Float, DateTime, Boolean,
    ForeignKey, Table, Enum as SQLEnum, JSON
)
from sqlalchemy.orm import relationship, DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


# Association tables for many-to-many relationships
article_authors = Table(
    'article_authors',
    Base.metadata,
    Column('article_id', Integer, ForeignKey('articles.id'), primary_key=True),
    Column('author_id', Integer, ForeignKey('authors.id'), primary_key=True)
)

article_keywords = Table(
    'article_keywords',
    Base.metadata,
    Column('article_id', Integer, ForeignKey('articles.id'), primary_key=True),
    Column('keyword_id', Integer, ForeignKey('keywords.id'), primary_key=True)
)

article_mesh_terms = Table(
    'article_mesh_terms',
    Base.metadata,
    Column('article_id', Integer, ForeignKey('articles.id'), primary_key=True),
    Column('mesh_term_id', Integer, ForeignKey('mesh_terms.id'), primary_key=True)
)


class AuthorModel(Base):
    """Author entity."""
    __tablename__ = 'authors'
    
    id = Column(Integer, primary_key=True)
    first_name = Column(String(100))
    last_name = Column(String(100))
    full_name = Column(String(200), index=True)
    orcid = Column(String(50), unique=True, nullable=True)
    
    articles = relationship('ArticleModel', secondary=article_authors, back_populates='authors')


class KeywordModel(Base):
    """Keyword entity."""
    __tablename__ = 'keywords'
    
    id = Column(Integer, primary_key=True)
    keyword = Column(String(200), unique=True, index=True)
    
    articles = relationship('ArticleModel', secondary=article_keywords, back_populates='keywords')


class MeshTermModel(Base):
    """MeSH term entity."""
    __tablename__ = 'mesh_terms'
    
    id = Column(Integer, primary_key=True)
    term = Column(String(200), unique=True, index=True)
    mesh_id = Column(String(50), nullable=True)
    
    articles = relationship('ArticleModel', secondary=article_mesh_terms, back_populates='mesh_terms')


class ArticleModel(Base):
    """PubMed article entity."""
    __tablename__ = 'articles'
    
    id = Column(Integer, primary_key=True)
    pmid = Column(String(20), unique=True, index=True, nullable=False)
    title = Column(Text, nullable=False)
    abstract = Column(Text)
    journal = Column(String(500))
    publication_year = Column(Integer, index=True)
    publication_date = Column(DateTime)
    doi = Column(String(100), nullable=True)
    pmc_id = Column(String(20), nullable=True)
    
    # Processing status
    is_processed = Column(Boolean, default=False)
    processed_at = Column(DateTime, nullable=True)
    extraction_error = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    authors = relationship('AuthorModel', secondary=article_authors, back_populates='articles')
    keywords = relationship('KeywordModel', secondary=article_keywords, back_populates='articles')
    mesh_terms = relationship('MeshTermModel', secondary=article_mesh_terms, back_populates='articles')
    associations = relationship('AssociationModel', back_populates='article')


class DiseaseModel(Base):
    """Disease entity."""
    __tablename__ = 'diseases'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(500), nullable=False, index=True)
    name_normalized = Column(String(500), index=True)  # Lowercase, standardized
    category = Column(String(200))
    icd_code = Column(String(20))
    mesh_id = Column(String(50))
    doid = Column(String(50))  # Disease Ontology ID
    description = Column(Text)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    associations = relationship('AssociationModel', back_populates='disease')
    
    # Unique constraint on normalized name
    __table_args__ = (
        # Index('ix_diseases_name_normalized', 'name_normalized'),
    )


class MarkerModel(Base):
    """Biomarker entity."""
    __tablename__ = 'markers'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False, index=True)
    symbol = Column(String(50), index=True)  # Official gene/protein symbol
    marker_type = Column(String(50), index=True)  # gene, protein, metabolite, etc.
    
    # External IDs
    hgnc_id = Column(String(20))
    uniprot_id = Column(String(20))
    ensembl_id = Column(String(30))
    entrez_id = Column(String(20))
    
    # Additional info
    chromosome = Column(String(10))
    description = Column(Text)
    aliases = Column(JSON)  # List of alternative names
    
    # Enrichment data
    enrichment_data = Column(JSON)  # Full enrichment response
    is_validated = Column(Boolean, default=False)
    validated_at = Column(DateTime)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    associations = relationship('AssociationModel', back_populates='marker')


class AssociationModel(Base):
    """Marker-disease association entity."""
    __tablename__ = 'associations'
    
    id = Column(Integer, primary_key=True)
    
    # Foreign keys
    article_id = Column(Integer, ForeignKey('articles.id'), nullable=False)
    marker_id = Column(Integer, ForeignKey('markers.id'), nullable=False)
    disease_id = Column(Integer, ForeignKey('diseases.id'), nullable=False)
    
    # Association details
    association_type = Column(String(50))  # diagnostic, prognostic, etc.
    evidence_level = Column(String(50))
    directionality = Column(String(20))  # positive, negative, etc.
    strength = Column(String(200))  # Qualitative description
    functional_impact = Column(Text)
    
    # Statistical metrics
    p_value = Column(Float)
    odds_ratio = Column(Float)
    hazard_ratio = Column(Float)
    confidence_interval = Column(String(50))
    auc = Column(Float)
    sensitivity = Column(Float)
    specificity = Column(Float)
    sample_size = Column(Integer)
    
    # Extraction metadata
    confidence_score = Column(Float)  # LLM confidence
    raw_extraction = Column(JSON)  # Raw LLM output
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    article = relationship('ArticleModel', back_populates='associations')
    marker = relationship('MarkerModel', back_populates='associations')
    disease = relationship('DiseaseModel', back_populates='associations')


class SearchQueryModel(Base):
    """Track search queries for reproducibility."""
    __tablename__ = 'search_queries'
    
    id = Column(Integer, primary_key=True)
    query = Column(Text, nullable=False)
    result_count = Column(Integer)
    articles_fetched = Column(Integer)
    articles_processed = Column(Integer)
    
    # Timestamps
    executed_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)

