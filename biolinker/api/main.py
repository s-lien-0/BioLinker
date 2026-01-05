"""
FastAPI application for BioLinker.
"""

import logging
import os
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from pathlib import Path

from biolinker.pubmed.client import PubMedClient, create_biomarker_query
from biolinker.extraction.extractor import BiomarkerExtractor, LLMConfig
from biolinker.storage.database import DatabaseManager
from biolinker.enrichment.hgnc import HGNCClient
from biolinker.enrichment.uniprot import UniProtClient
from biolinker.auth.routes import router as auth_router
from biolinker.auth.models import UserModel, WaitlistModel
from biolinker.auth.utils import get_current_user

logger = logging.getLogger(__name__)

# Global instances
db: Optional[DatabaseManager] = None
pubmed_client: Optional[PubMedClient] = None
extractor: Optional[BiomarkerExtractor] = None
hgnc_client: Optional[HGNCClient] = None
uniprot_client: Optional[UniProtClient] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    global db, pubmed_client, extractor, hgnc_client, uniprot_client
    
    # Initialize services
    db = DatabaseManager()
    db.create_tables()
    
    # Also create auth tables
    from biolinker.auth.models import UserModel, WaitlistModel
    from biolinker.storage.models import Base
    Base.metadata.create_all(db.engine)
    
    pubmed_client = PubMedClient()
    
    # Get LLM config from environment
    llm_provider = os.getenv("LLM_PROVIDER", "ollama")
    llm_model = os.getenv("LLM_MODEL", "ministral-3:3b")
    llm_base_url = os.getenv("LLM_BASE_URL", "http://localhost:11434")
    
    extractor = BiomarkerExtractor(LLMConfig(
        provider=llm_provider,
        model=llm_model,
        base_url=llm_base_url,
    ))
    hgnc_client = HGNCClient()
    uniprot_client = UniProtClient()
    
    logger.info("BioLinker API initialized")
    yield
    
    # Cleanup
    logger.info("BioLinker API shutting down")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    application = FastAPI(
        title="BioLinker API",
        description="Biomarker discovery and knowledge graph platform",
        version="0.1.0",
        lifespan=lifespan,
    )
    
    # CORS middleware
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include auth routes
    application.include_router(auth_router)
    
    return application


app = create_app()


# ==================== Request/Response Models ====================

class SearchRequest(BaseModel):
    """Request model for PubMed search."""
    query: str = Field(..., description="PubMed search query")
    max_results: int = Field(100, ge=1, le=10000, description="Maximum results to fetch")
    diseases: Optional[list[str]] = Field(None, description="Filter by diseases")
    marker_types: Optional[list[str]] = Field(None, description="Filter by marker types")


class SearchResponse(BaseModel):
    """Response model for search results."""
    query: str
    total_count: int
    articles_fetched: int
    message: str


class ArticleResponse(BaseModel):
    """Response model for an article."""
    pmid: str
    title: str
    abstract: str
    authors: str
    journal: str
    publication_year: Optional[int]
    doi: Optional[str]
    is_processed: bool


class MarkerResponse(BaseModel):
    """Response model for a marker."""
    id: int
    name: str
    symbol: Optional[str]
    marker_type: str
    hgnc_id: Optional[str]
    uniprot_id: Optional[str]
    chromosome: Optional[str]
    association_count: int = 0


class DiseaseResponse(BaseModel):
    """Response model for a disease."""
    id: int
    name: str
    category: Optional[str]
    association_count: int = 0


class AssociationResponse(BaseModel):
    """Response model for an association."""
    marker_name: str
    marker_symbol: Optional[str]
    disease_name: str
    association_type: str
    evidence_level: str
    directionality: str
    p_value: Optional[float]
    auc: Optional[float]
    article_pmid: str
    article_title: str


class StatsResponse(BaseModel):
    """Response model for statistics."""
    articles: int
    articles_processed: int
    markers: int
    diseases: int
    associations: int


class EnrichmentRequest(BaseModel):
    """Request for marker enrichment."""
    marker_name: str
    marker_type: str = "gene"


class ProcessRequest(BaseModel):
    """Request to process articles."""
    pmids: Optional[list[str]] = None
    limit: int = Field(10, ge=1, le=100)


# ==================== API Endpoints ====================

@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "BioLinker API",
        "version": "0.1.0",
        "docs": "/docs",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/stats", response_model=StatsResponse)
async def get_statistics():
    """Get database statistics."""
    stats = db.get_statistics()
    return StatsResponse(**stats)


# ==================== Search Endpoints ====================

@app.post("/search", response_model=SearchResponse)
async def search_pubmed(request: SearchRequest, background_tasks: BackgroundTasks):
    """
    Search PubMed and store results.
    """
    try:
        # Build query
        if request.diseases or request.marker_types:
            query = create_biomarker_query(
                diseases=request.diseases,
                marker_types=request.marker_types,
                additional_terms=[request.query] if request.query else None
            )
        else:
            query = request.query
        
        # Execute search
        search_result = pubmed_client.search(query, max_results=request.max_results)
        
        # Fetch and store articles in background
        background_tasks.add_task(
            _fetch_and_store_articles,
            search_result,
            request.max_results
        )
        
        return SearchResponse(
            query=query,
            total_count=search_result.count,
            articles_fetched=min(search_result.count, request.max_results),
            message="Search initiated. Articles being fetched in background."
        )
        
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _fetch_and_store_articles(search_result, max_articles: int):
    """Background task to fetch and store articles."""
    session = db.get_session()
    try:
        for article in pubmed_client.fetch_articles(search_result, max_articles=max_articles):
            db.store_article(article, session)
        session.commit()
        logger.info(f"Stored articles from search")
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to store articles: {e}")
    finally:
        session.close()


# ==================== Article Endpoints ====================

@app.get("/articles", response_model=list[ArticleResponse])
async def list_articles(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    processed_only: bool = False,
):
    """List articles in the database."""
    with db.get_session() as session:
        from biolinker.storage.models import ArticleModel
        
        query = session.query(ArticleModel)
        if processed_only:
            query = query.filter(ArticleModel.is_processed == True)
        
        articles = query.offset(skip).limit(limit).all()
        
        return [
            ArticleResponse(
                pmid=a.pmid,
                title=a.title,
                abstract=a.abstract or "",
                authors=", ".join([auth.full_name for auth in a.authors]),
                journal=a.journal or "",
                publication_year=a.publication_year,
                doi=a.doi,
                is_processed=a.is_processed,
            )
            for a in articles
        ]


@app.get("/articles/{pmid}", response_model=ArticleResponse)
async def get_article(pmid: str):
    """Get a specific article by PMID."""
    with db.get_session() as session:
        from biolinker.storage.models import ArticleModel
        
        article = session.query(ArticleModel).filter_by(pmid=pmid).first()
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")
        
        return ArticleResponse(
            pmid=article.pmid,
            title=article.title,
            abstract=article.abstract or "",
            authors=", ".join([auth.full_name for auth in article.authors]),
            journal=article.journal or "",
            publication_year=article.publication_year,
            doi=article.doi,
            is_processed=article.is_processed,
        )


@app.post("/articles/process")
async def process_articles(request: ProcessRequest, background_tasks: BackgroundTasks):
    """Process articles to extract biomarker information."""
    background_tasks.add_task(_process_articles, request.pmids, request.limit)
    return {"message": "Processing started", "limit": request.limit}


async def _process_articles(pmids: Optional[list[str]], limit: int):
    """Background task to process articles."""
    with db.get_session() as session:
        from biolinker.storage.models import ArticleModel
        from biolinker.pubmed.parser import Article, Author
        
        if pmids:
            articles = session.query(ArticleModel).filter(
                ArticleModel.pmid.in_(pmids),
                ArticleModel.is_processed == False
            ).all()
        else:
            articles = session.query(ArticleModel).filter(
                ArticleModel.is_processed == False
            ).limit(limit).all()
        
        for article_model in articles:
            try:
                # Convert to Article object
                article = Article(
                    pmid=article_model.pmid,
                    title=article_model.title,
                    abstract=article_model.abstract or "",
                    authors=[
                        Author(first_name=a.first_name, last_name=a.last_name)
                        for a in article_model.authors
                    ],
                    journal=article_model.journal or "",
                    publication_year=article_model.publication_year,
                )
                
                # Extract biomarkers
                result = extractor.extract(article)
                
                # Store results
                db.store_extraction_result(result, session)
                
                logger.info(f"Processed article {article_model.pmid}")
                
            except Exception as e:
                logger.error(f"Failed to process {article_model.pmid}: {e}")
                article_model.is_processed = True
                article_model.extraction_error = str(e)
        
        session.commit()


@app.post("/articles/reset")
async def reset_failed_articles():
    """Reset articles that failed processing so they can be re-processed."""
    with db.get_session() as session:
        from biolinker.storage.models import ArticleModel
        
        # Find articles that were processed but have errors (no associations extracted)
        failed_articles = session.query(ArticleModel).filter(
            ArticleModel.is_processed == True,
            ArticleModel.extraction_error != None
        ).all()
        
        count = len(failed_articles)
        for article in failed_articles:
            article.is_processed = False
            article.extraction_error = None
        
        session.commit()
        
        return {
            "message": f"Reset {count} failed articles for reprocessing",
            "reset_count": count
        }


@app.post("/articles/reset-all")
async def reset_all_articles():
    """Reset ALL articles for reprocessing (use with caution)."""
    with db.get_session() as session:
        from biolinker.storage.models import ArticleModel
        
        count = session.query(ArticleModel).update({
            ArticleModel.is_processed: False,
            ArticleModel.extraction_error: None
        })
        
        session.commit()
        
        return {
            "message": f"Reset {count} articles for reprocessing",
            "reset_count": count
        }


# ==================== Marker Endpoints ====================

@app.get("/markers", response_model=list[MarkerResponse])
async def list_markers(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    search: Optional[str] = None,
    marker_type: Optional[str] = None,
):
    """List markers in the database."""
    with db.get_session() as session:
        from biolinker.storage.models import MarkerModel
        from sqlalchemy import func
        
        query = session.query(MarkerModel)
        
        if search:
            query = query.filter(
                (MarkerModel.name.ilike(f"%{search}%")) |
                (MarkerModel.symbol.ilike(f"%{search}%"))
            )
        
        if marker_type:
            query = query.filter(MarkerModel.marker_type == marker_type)
        
        markers = query.offset(skip).limit(limit).all()
        
        return [
            MarkerResponse(
                id=m.id,
                name=m.name,
                symbol=m.symbol,
                marker_type=m.marker_type or "unknown",
                hgnc_id=m.hgnc_id,
                uniprot_id=m.uniprot_id,
                chromosome=m.chromosome,
                association_count=len(m.associations),
            )
            for m in markers
        ]


@app.get("/markers/{symbol}/associations", response_model=list[AssociationResponse])
async def get_marker_associations(symbol: str):
    """Get all associations for a marker."""
    associations = db.get_associations_for_marker(symbol)
    if not associations:
        raise HTTPException(status_code=404, detail="Marker not found or no associations")
    
    return [
        AssociationResponse(
            marker_name=symbol,
            marker_symbol=symbol,
            disease_name=a["disease"],
            association_type=a["association_type"] or "unknown",
            evidence_level=a["evidence_level"] or "unknown",
            directionality="unknown",
            p_value=a["p_value"],
            auc=a["auc"],
            article_pmid=a["article_pmid"],
            article_title=a["article_title"],
        )
        for a in associations
    ]


# ==================== Disease Endpoints ====================

@app.get("/diseases", response_model=list[DiseaseResponse])
async def list_diseases(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    search: Optional[str] = None,
):
    """List diseases in the database."""
    with db.get_session() as session:
        from biolinker.storage.models import DiseaseModel
        
        query = session.query(DiseaseModel)
        
        if search:
            query = query.filter(DiseaseModel.name.ilike(f"%{search}%"))
        
        diseases = query.offset(skip).limit(limit).all()
        
        return [
            DiseaseResponse(
                id=d.id,
                name=d.name,
                category=d.category,
                association_count=len(d.associations),
            )
            for d in diseases
        ]


@app.get("/diseases/{disease_name}/associations", response_model=list[AssociationResponse])
async def get_disease_associations(disease_name: str):
    """Get all associations for a disease."""
    associations = db.get_associations_for_disease(disease_name)
    if not associations:
        raise HTTPException(status_code=404, detail="Disease not found or no associations")
    
    return [
        AssociationResponse(
            marker_name=a["marker"],
            marker_symbol=a["marker"],
            disease_name=disease_name,
            association_type=a["association_type"] or "unknown",
            evidence_level=a["evidence_level"] or "unknown",
            directionality="unknown",
            p_value=a["p_value"],
            auc=a["auc"],
            article_pmid=a["article_pmid"],
            article_title="",
        )
        for a in associations
    ]


# ==================== Enrichment Endpoints ====================

@app.post("/enrich/marker")
async def enrich_marker(request: EnrichmentRequest):
    """Enrich a marker with external database information."""
    result = {"marker_name": request.marker_name, "marker_type": request.marker_type}
    
    if request.marker_type in ("gene", "protein"):
        # HGNC lookup
        gene_info = hgnc_client.fetch_by_symbol(request.marker_name)
        if gene_info:
            result["hgnc"] = gene_info.to_dict()
            
            # UniProt lookup
            if gene_info.uniprot_id:
                protein_info = uniprot_client.fetch_by_id(gene_info.uniprot_id)
                if protein_info:
                    result["uniprot"] = protein_info.to_dict()
        else:
            # Try search
            search_results = hgnc_client.search(request.marker_name)
            if search_results:
                result["hgnc_suggestions"] = [g.to_dict() for g in search_results[:5]]
    
    return result


@app.get("/enrich/gene/{symbol}")
async def enrich_gene(symbol: str):
    """Get HGNC information for a gene symbol."""
    gene_info = hgnc_client.fetch_by_symbol(symbol)
    if not gene_info:
        raise HTTPException(status_code=404, detail="Gene not found")
    return gene_info.to_dict()


@app.get("/enrich/protein/{uniprot_id}")
async def enrich_protein(uniprot_id: str):
    """Get UniProt information for a protein."""
    protein_info = uniprot_client.fetch_by_id(uniprot_id)
    if not protein_info:
        raise HTTPException(status_code=404, detail="Protein not found")
    return protein_info.to_dict()


# ==================== Network/Graph Endpoints ====================

@app.get("/network/marker/{symbol}")
async def get_marker_network(symbol: str, depth: int = Query(1, ge=1, le=3)):
    """
    Get network data for a marker.
    
    Returns nodes and edges for visualization.
    """
    with db.get_session() as session:
        from biolinker.storage.models import MarkerModel
        from sqlalchemy import or_, func
        
        # Search by symbol or name (case-insensitive)
        marker = session.query(MarkerModel).filter(
            or_(
                func.lower(MarkerModel.symbol) == symbol.lower(),
                func.lower(MarkerModel.name) == symbol.lower()
            )
        ).first()
        
        if not marker:
            # Try partial match
            marker = session.query(MarkerModel).filter(
                or_(
                    MarkerModel.symbol.ilike(f"%{symbol}%"),
                    MarkerModel.name.ilike(f"%{symbol}%")
                )
            ).first()
        
        if not marker:
            raise HTTPException(status_code=404, detail=f"Marker '{symbol}' not found")
        
        nodes = [{"id": f"marker_{marker.id}", "label": marker.symbol or marker.name, "type": "marker"}]
        edges = []
        seen_diseases = set()
        
        for assoc in marker.associations:
            disease_id = f"disease_{assoc.disease.id}"
            
            if disease_id not in seen_diseases:
                nodes.append({
                    "id": disease_id,
                    "label": assoc.disease.name,
                    "type": "disease"
                })
                seen_diseases.add(disease_id)
            
            edges.append({
                "source": f"marker_{marker.id}",
                "target": disease_id,
                "type": assoc.association_type,
                "weight": assoc.auc or 0.5,
            })
        
        return {"nodes": nodes, "edges": edges}


@app.get("/network/disease/{disease_name}")
async def get_disease_network(disease_name: str, depth: int = Query(1, ge=1, le=3)):
    """
    Get network data for a disease.
    
    Returns nodes and edges for visualization.
    """
    with db.get_session() as session:
        from biolinker.storage.models import DiseaseModel
        
        # Try exact match first
        normalized = disease_name.lower().strip()
        disease = session.query(DiseaseModel).filter_by(name_normalized=normalized).first()
        
        if not disease:
            # Try partial match
            disease = session.query(DiseaseModel).filter(
                DiseaseModel.name.ilike(f"%{disease_name}%")
            ).first()
        
        if not disease:
            raise HTTPException(status_code=404, detail=f"Disease '{disease_name}' not found")
        
        nodes = [{"id": f"disease_{disease.id}", "label": disease.name, "type": "disease"}]
        edges = []
        seen_markers = set()
        
        for assoc in disease.associations:
            marker_id = f"marker_{assoc.marker.id}"
            
            if marker_id not in seen_markers:
                nodes.append({
                    "id": marker_id,
                    "label": assoc.marker.symbol or assoc.marker.name,
                    "type": "marker",
                    "marker_type": assoc.marker.marker_type,
                })
                seen_markers.add(marker_id)
            
            edges.append({
                "source": marker_id,
                "target": f"disease_{disease.id}",
                "type": assoc.association_type,
                "weight": assoc.auc or 0.5,
            })
        
        return {"nodes": nodes, "edges": edges}


# Serve frontend static files
def get_frontend_path() -> Optional[Path]:
    """Find the frontend directory, checking multiple possible locations."""
    possible_paths = [
        # Relative to this file (works for editable installs)
        Path(__file__).resolve().parent.parent.parent / "frontend",
        # Current working directory
        Path.cwd() / "frontend",
        # Environment variable override
        Path(os.getenv("BIOLINKER_FRONTEND_PATH", "")) if os.getenv("BIOLINKER_FRONTEND_PATH") else None,
    ]
    
    for path in possible_paths:
        if path and path.exists() and (path / "landing.html").exists():
            return path
    
    return None

frontend_path = get_frontend_path()
logger.info(f"Frontend path: {frontend_path}")

# Mount frontend as static files
if frontend_path and frontend_path.exists():
    app.mount("/frontend", StaticFiles(directory=frontend_path, html=True), name="frontend")


@app.get("/", include_in_schema=False)
async def serve_landing():
    """Serve the landing page at root."""
    fe_path = get_frontend_path()
    
    if fe_path:
        landing = fe_path / "landing.html"
        if landing.exists():
            return FileResponse(landing)
    
    return {"name": "BioLinker API", "version": "0.1.0", "docs": "/docs"}


@app.get("/app")
async def serve_app():
    """Redirect to the frontend app."""
    if frontend_path.exists():
        return FileResponse(frontend_path / "index.html")
    return {"error": "Frontend not found"}


@app.get("/app/{full_path:path}")
async def serve_app_routes(full_path: str):
    """Serve frontend for SPA routes."""
    if frontend_path.exists():
        file_path = frontend_path / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(frontend_path / "index.html")
    return {"error": "Frontend not found"}

