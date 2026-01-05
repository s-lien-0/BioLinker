"""
Background tasks for article processing.
"""

import logging
from typing import Optional

from biolinker.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def fetch_pubmed_articles_task(
    self,
    query: str,
    max_results: int = 100,
    user_id: Optional[int] = None,
):
    """
    Background task to fetch articles from PubMed.
    
    Args:
        query: PubMed search query
        max_results: Maximum articles to fetch
        user_id: Optional user ID for tracking
    """
    try:
        from biolinker.pubmed.client import PubMedClient
        from biolinker.storage.database import DatabaseManager
        
        logger.info(f"Starting PubMed fetch: {query[:50]}... (max {max_results})")
        
        client = PubMedClient()
        db = DatabaseManager()
        
        # Search
        search_result = client.search(query, max_results=max_results)
        logger.info(f"Found {search_result.count} articles")
        
        # Fetch and store
        session = db.get_session()
        count = 0
        
        try:
            for article in client.fetch_articles(search_result, max_articles=max_results):
                db.store_article(article, session)
                count += 1
                
                # Update progress every 10 articles
                if count % 10 == 0:
                    self.update_state(
                        state="PROGRESS",
                        meta={"current": count, "total": min(search_result.count, max_results)}
                    )
            
            session.commit()
            logger.info(f"Stored {count} articles")
            
            return {
                "status": "success",
                "articles_fetched": count,
                "total_found": search_result.count,
            }
            
        except Exception as e:
            session.rollback()
            raise
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"Fetch task failed: {e}")
        raise self.retry(exc=e)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=120)
def process_articles_task(
    self,
    article_ids: Optional[list[int]] = None,
    limit: int = 10,
    user_id: Optional[int] = None,
):
    """
    Background task to process articles with LLM extraction.
    
    Args:
        article_ids: Specific article IDs to process (or None for unprocessed)
        limit: Maximum articles to process
        user_id: Optional user ID for tracking
    """
    try:
        import os
        from biolinker.storage.database import DatabaseManager
        from biolinker.storage.models import ArticleModel
        from biolinker.extraction.extractor import BiomarkerExtractor, LLMConfig
        from biolinker.pubmed.parser import Article, Author
        
        logger.info(f"Starting article processing (limit: {limit})")
        
        db = DatabaseManager()
        
        # Initialize extractor
        extractor = BiomarkerExtractor(LLMConfig(
            provider=os.getenv("LLM_PROVIDER", "ollama"),
            model=os.getenv("LLM_MODEL", "ministral-3:3b"),
            base_url=os.getenv("LLM_BASE_URL", "http://localhost:11434"),
        ))
        
        processed = 0
        failed = 0
        
        with db.get_session() as session:
            # Get articles to process
            if article_ids:
                articles = session.query(ArticleModel).filter(
                    ArticleModel.id.in_(article_ids),
                    ArticleModel.is_processed == False
                ).all()
            else:
                articles = session.query(ArticleModel).filter(
                    ArticleModel.is_processed == False
                ).limit(limit).all()
            
            total = len(articles)
            logger.info(f"Processing {total} articles")
            
            for i, article_model in enumerate(articles):
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
                    processed += 1
                    
                    logger.info(f"Processed {article_model.pmid}: {len(result.markers)} markers, {len(result.associations)} associations")
                    
                    # Update progress
                    self.update_state(
                        state="PROGRESS",
                        meta={"current": i + 1, "total": total, "processed": processed}
                    )
                    
                except Exception as e:
                    logger.error(f"Failed to process {article_model.pmid}: {e}")
                    article_model.is_processed = True
                    article_model.extraction_error = str(e)
                    failed += 1
            
            session.commit()
        
        logger.info(f"Processing complete: {processed} succeeded, {failed} failed")
        
        return {
            "status": "success",
            "processed": processed,
            "failed": failed,
            "total": total,
        }
        
    except Exception as e:
        logger.error(f"Processing task failed: {e}")
        raise self.retry(exc=e)


@celery_app.task
def enrich_markers_task(marker_ids: Optional[list[int]] = None, limit: int = 50):
    """
    Background task to enrich markers with HGNC/UniProt data.
    """
    from biolinker.storage.database import DatabaseManager
    from biolinker.storage.models import MarkerModel
    from biolinker.enrichment.hgnc import HGNCClient
    from biolinker.enrichment.uniprot import UniProtClient
    from datetime import datetime
    import json
    
    logger.info("Starting marker enrichment")
    
    db = DatabaseManager()
    hgnc = HGNCClient()
    uniprot = UniProtClient()
    
    enriched = 0
    
    with db.get_session() as session:
        if marker_ids:
            markers = session.query(MarkerModel).filter(
                MarkerModel.id.in_(marker_ids)
            ).all()
        else:
            markers = session.query(MarkerModel).filter(
                MarkerModel.is_validated == False,
                MarkerModel.marker_type.in_(["gene", "protein"])
            ).limit(limit).all()
        
        for marker in markers:
            try:
                enrichment_data = {}
                
                # HGNC lookup
                gene_info = hgnc.fetch_by_symbol(marker.symbol or marker.name)
                if gene_info:
                    enrichment_data["hgnc"] = gene_info.to_dict()
                    marker.hgnc_id = gene_info.hgnc_id
                    marker.symbol = gene_info.symbol
                    marker.chromosome = gene_info.chromosome
                    
                    # UniProt lookup
                    if gene_info.uniprot_id:
                        protein_info = uniprot.fetch_by_id(gene_info.uniprot_id)
                        if protein_info:
                            enrichment_data["uniprot"] = protein_info.to_dict()
                            marker.uniprot_id = gene_info.uniprot_id
                
                marker.enrichment_data = enrichment_data
                marker.is_validated = True
                marker.validated_at = datetime.utcnow()
                enriched += 1
                
            except Exception as e:
                logger.warning(f"Failed to enrich {marker.name}: {e}")
        
        session.commit()
    
    logger.info(f"Enriched {enriched} markers")
    return {"enriched": enriched}

