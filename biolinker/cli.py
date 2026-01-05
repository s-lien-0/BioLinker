"""
BioLinker Command Line Interface
"""

import click
import logging
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


@click.group()
@click.version_option(version='0.1.0')
def cli():
    """BioLinker - Biomarker Discovery Platform"""
    pass


@cli.command()
@click.option('--host', default='0.0.0.0', help='Host to bind to')
@click.option('--port', default=8000, help='Port to bind to')
@click.option('--reload', is_flag=True, help='Enable auto-reload')
def serve(host, port, reload):
    """Start the BioLinker API server."""
    import uvicorn
    
    console.print(f"[bold cyan]🧬 Starting BioLinker API Server[/bold cyan]")
    console.print(f"   Host: {host}")
    console.print(f"   Port: {port}")
    console.print(f"   Docs: http://{host if host != '0.0.0.0' else 'localhost'}:{port}/docs")
    console.print()
    
    uvicorn.run(
        "biolinker.api.main:app",
        host=host,
        port=port,
        reload=reload,
    )


@cli.command()
@click.argument('query')
@click.option('--max-results', '-n', default=100, help='Maximum results to fetch')
@click.option('--process', is_flag=True, help='Process articles after fetching')
def search(query, max_results, process):
    """Search PubMed and store articles."""
    from biolinker.pubmed.client import PubMedClient
    from biolinker.storage.database import DatabaseManager
    from biolinker.extraction.extractor import BiomarkerExtractor, LLMConfig
    
    console.print(f"[bold]🔍 Searching PubMed:[/bold] {query}")
    
    client = PubMedClient()
    db = DatabaseManager()
    db.create_tables()
    
    # Search
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Searching...", total=None)
        result = client.search(query, max_results=max_results)
        progress.update(task, description=f"Found {result.count:,} results")
    
    console.print(f"[green]✓[/green] Found {result.count:,} articles")
    
    # Fetch
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Fetching articles...", total=min(result.count, max_results))
        
        session = db.get_session()
        count = 0
        for article in client.fetch_articles(result, max_articles=max_results):
            db.store_article(article, session)
            count += 1
            progress.update(task, advance=1, description=f"Fetched {count} articles")
        
        session.commit()
        session.close()
    
    console.print(f"[green]✓[/green] Stored {count} articles")
    
    # Process if requested
    if process:
        console.print("[bold]🧠 Processing articles with LLM...[/bold]")
        extractor = BiomarkerExtractor(LLMConfig(provider="ollama", model="ministral-3:3b"))
        
        # This would process articles - simplified for CLI
        console.print("[yellow]Note: Use the web interface for full processing[/yellow]")


@cli.command()
@click.argument('symbol')
def enrich(symbol):
    """Look up gene/protein information."""
    from biolinker.enrichment.hgnc import HGNCClient
    from biolinker.enrichment.uniprot import UniProtClient
    
    console.print(f"[bold]🔬 Looking up:[/bold] {symbol}")
    
    hgnc = HGNCClient()
    uniprot = UniProtClient()
    
    # HGNC lookup
    gene_info = hgnc.fetch_by_symbol(symbol)
    
    if gene_info:
        table = Table(title="HGNC Gene Information")
        table.add_column("Field", style="cyan")
        table.add_column("Value")
        
        table.add_row("Symbol", gene_info.symbol)
        table.add_row("Name", gene_info.name)
        table.add_row("HGNC ID", gene_info.hgnc_id)
        table.add_row("Locus Type", gene_info.locus_type)
        table.add_row("Chromosome", gene_info.chromosome or "N/A")
        table.add_row("Ensembl ID", gene_info.ensembl_id or "N/A")
        table.add_row("UniProt ID", gene_info.uniprot_id or "N/A")
        
        console.print(table)
        
        # UniProt lookup
        if gene_info.uniprot_id:
            protein_info = uniprot.fetch_by_id(gene_info.uniprot_id)
            
            if protein_info:
                table2 = Table(title="UniProt Protein Information")
                table2.add_column("Field", style="green")
                table2.add_column("Value")
                
                table2.add_row("Accession", protein_info.uniprot_id)
                table2.add_row("Protein Name", protein_info.protein_name)
                table2.add_row("Organism", protein_info.organism)
                table2.add_row("Length", f"{protein_info.sequence_length} aa" if protein_info.sequence_length else "N/A")
                
                console.print(table2)
    else:
        console.print(f"[red]Gene not found:[/red] {symbol}")
        
        # Try search
        results = hgnc.search(symbol)
        if results:
            console.print("\n[yellow]Did you mean?[/yellow]")
            for r in results[:5]:
                console.print(f"  • {r.symbol} - {r.name}")


@cli.command()
def stats():
    """Show database statistics."""
    from biolinker.storage.database import DatabaseManager
    
    db = DatabaseManager()
    
    try:
        statistics = db.get_statistics()
        
        table = Table(title="BioLinker Database Statistics")
        table.add_column("Metric", style="cyan")
        table.add_column("Count", justify="right")
        
        table.add_row("Articles", f"{statistics['articles']:,}")
        table.add_row("Processed", f"{statistics['articles_processed']:,}")
        table.add_row("Biomarkers", f"{statistics['markers']:,}")
        table.add_row("Diseases", f"{statistics['diseases']:,}")
        table.add_row("Associations", f"{statistics['associations']:,}")
        
        console.print(table)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        console.print("Run the server first to initialize the database.")


@cli.command()
def init():
    """Initialize the database."""
    from biolinker.storage.database import DatabaseManager
    
    console.print("[bold]🗄️ Initializing database...[/bold]")
    
    db = DatabaseManager()
    db.create_tables()
    
    console.print("[green]✓[/green] Database initialized successfully")
    console.print(f"   Location: ~/.biolinker/biolinker.db")


if __name__ == '__main__':
    cli()

