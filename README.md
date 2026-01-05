# 🧬 BioLinker

**A biomarker discovery and knowledge graph platform** that parses PubMed research articles, extracts biomarker-disease relationships using LLMs, and provides an interactive visualization interface.

![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-green.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)

## ✨ Features

- **🔍 PubMed Search** - Search millions of biomedical articles with advanced query building
- **🧠 LLM Extraction** - Extract biomarker-disease associations using local or cloud LLMs
- **🗄️ Knowledge Storage** - SQLite database for storing articles, markers, diseases, and associations
- **🔗 Data Enrichment** - Automatic enrichment via HGNC and UniProt APIs
- **📊 Network Visualization** - Interactive knowledge graph visualization
- **🌐 REST API** - Full-featured FastAPI backend with OpenAPI documentation
- **💻 Modern Dashboard** - Beautiful, responsive web interface

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- [Ollama](https://ollama.ai/) (for local LLM extraction) or OpenAI/Anthropic API key

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/biolinker.git
cd biolinker

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install BioLinker as a package
pip install -e .
```

### Start Ollama (for local LLM)

```bash
# Pull the ministral-3b model (or another model of your choice)
ollama pull ministral-3:3b
```

### Run the Application

```bash
# Start the API server
biolinker serve

# Or with auto-reload for development
biolinker serve --reload
```

Open your browser to:
- **Dashboard**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

## 📖 Usage

### Web Interface

1. **Search PubMed**: Enter biomarker-related search queries
2. **Process Articles**: Extract biomarker information using LLM
3. **Explore Data**: Browse markers, diseases, and their associations
4. **Visualize Networks**: View biomarker-disease relationship graphs
5. **Enrich Data**: Look up gene/protein details from HGNC & UniProt

### Command Line Interface

```bash
# Initialize the database
biolinker init

# Search PubMed and store articles
biolinker search "BRCA1 breast cancer biomarker" --max-results 50

# Look up gene information
biolinker enrich BRCA1

# Show database statistics
biolinker stats

# Start the server
biolinker serve --port 8000
```

### Python API

```python
from biolinker import PubMedClient, BiomarkerExtractor, DatabaseManager
from biolinker.extraction.extractor import LLMConfig

# Initialize
client = PubMedClient()
db = DatabaseManager()
db.create_tables()

# Search PubMed
result = client.search("biomarker cancer diagnosis", max_results=100)
print(f"Found {result.count} articles")

# Fetch and store articles
for article in client.fetch_articles(result, max_articles=50):
    db.store_article(article)
    print(f"Stored: {article.title[:60]}...")

# Extract biomarkers using LLM
config = LLMConfig(provider="ollama", model="ministral-3:3b")
extractor = BiomarkerExtractor(config)

# Process an article
article = client.fetch_single("12345678")  # PMID
extraction = extractor.extract(article)

print(f"Found {len(extraction.markers)} markers")
print(f"Found {len(extraction.diseases)} diseases")
print(f"Found {len(extraction.associations)} associations")
```

### Data Enrichment

```python
from biolinker.enrichment import HGNCClient, UniProtClient

# Gene lookup
hgnc = HGNCClient()
gene = hgnc.fetch_by_symbol("BRCA1")
print(f"HGNC ID: {gene.hgnc_id}")
print(f"Chromosome: {gene.chromosome}")

# Protein lookup
uniprot = UniProtClient()
protein = uniprot.fetch_by_id(gene.uniprot_id)
print(f"Function: {protein.function}")
```

## 🏗️ Project Structure

```
BioLinker/
├── biolinker/
│   ├── __init__.py
│   ├── cli.py                 # Command line interface
│   ├── pubmed/
│   │   ├── client.py          # PubMed API client
│   │   └── parser.py          # XML parsing utilities
│   ├── extraction/
│   │   ├── extractor.py       # LLM extraction engine
│   │   ├── models.py          # Data models
│   │   └── prompts.py         # Structured prompts
│   ├── enrichment/
│   │   ├── hgnc.py            # HGNC API client
│   │   └── uniprot.py         # UniProt API client
│   ├── storage/
│   │   ├── database.py        # Database manager
│   │   └── models.py          # SQLAlchemy models
│   └── api/
│       └── main.py            # FastAPI application
├── frontend/
│   ├── index.html             # Main dashboard
│   ├── styles.css             # Styles
│   └── app.js                 # Frontend logic
├── notebooks/
│   └── exploration.ipynb      # Jupyter notebooks
├── requirements.txt
├── setup.py
└── README.md
```

## 🔧 Configuration

### LLM Backends

BioLinker supports multiple LLM backends:

```python
from biolinker.extraction.extractor import LLMConfig

# Ollama (local)
config = LLMConfig(provider="ollama", model="ministral-3:3b")

# OpenAI
config = LLMConfig(
    provider="openai",
    model="gpt-4",
    api_key="your-api-key"
)

# Anthropic
config = LLMConfig(
    provider="anthropic",
    model="claude-3-sonnet-20240229",
    api_key="your-api-key"
)
```

### Database

By default, BioLinker uses SQLite stored at `~/.biolinker/biolinker.db`. You can customize this:

```python
from biolinker import DatabaseManager

# Custom SQLite path
db = DatabaseManager("sqlite:///path/to/your/database.db")

# PostgreSQL
db = DatabaseManager("postgresql://user:pass@localhost/biolinker")
```

## 📊 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/search` | POST | Search PubMed and store articles |
| `/articles` | GET | List stored articles |
| `/articles/{pmid}` | GET | Get article details |
| `/articles/process` | POST | Process articles with LLM |
| `/markers` | GET | List biomarkers |
| `/markers/{symbol}/associations` | GET | Get marker associations |
| `/diseases` | GET | List diseases |
| `/diseases/{name}/associations` | GET | Get disease associations |
| `/enrich/marker` | POST | Enrich marker with HGNC/UniProt |
| `/network/marker/{symbol}` | GET | Get marker network graph |
| `/network/disease/{name}` | GET | Get disease network graph |
| `/stats` | GET | Database statistics |

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [PubMed E-utilities](https://www.ncbi.nlm.nih.gov/books/NBK25501/) for biomedical literature access
- [HGNC](https://www.genenames.org/) for gene nomenclature
- [UniProt](https://www.uniprot.org/) for protein information
- [Ollama](https://ollama.ai/) for local LLM inference
