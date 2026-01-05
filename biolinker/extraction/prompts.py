"""
Structured prompts for biomarker extraction.
"""

EXTRACTION_SYSTEM_PROMPT = """You are a biomedical information extraction expert. Your task is to extract structured information about biomarkers and their disease associations from scientific abstracts.

You must respond ONLY with valid JSON. Do not include any explanatory text before or after the JSON.

Focus on extracting:
1. Diseases mentioned in the study
2. Biomarkers (genes, proteins, metabolites, miRNAs, etc.)
3. Associations between markers and diseases
4. Statistical evidence (p-values, AUC, odds ratios, etc.)

Be precise and only extract information explicitly stated in the text. If information is not available, use null."""


EXTRACTION_USER_PROMPT = """Extract biomarker-disease associations from this abstract:

Title: {title}

Abstract: {abstract}

Respond with JSON in this exact format:
{{
  "diseases": [
    {{
      "name": "disease name",
      "category": "disease category (e.g., cancer, cardiovascular, autoimmune)"
    }}
  ],
  "markers": [
    {{
      "name": "marker name",
      "symbol": "official symbol if gene/protein",
      "marker_type": "gene|protein|metabolite|mirna|lncrna|methylation|snp|other"
    }}
  ],
  "associations": [
    {{
      "marker_name": "name of marker",
      "disease_name": "name of disease",
      "association_type": "diagnostic|prognostic|predictive|therapeutic|risk|expression|mutation|other",
      "evidence_level": "clinical_trial|cohort_study|case_control|case_series|in_vivo|in_vitro|computational|review|meta_analysis|unknown",
      "directionality": "positive|negative|bidirectional|unknown",
      "strength": "qualitative description of association strength",
      "functional_impact": "how the marker affects the disease",
      "statistics": {{
        "p_value": null,
        "odds_ratio": null,
        "hazard_ratio": null,
        "auc": null,
        "sensitivity": null,
        "specificity": null,
        "confidence_interval": null,
        "sample_size": null
      }}
    }}
  ]
}}

Important:
- Extract ALL biomarkers mentioned (genes, proteins, miRNAs, metabolites)
- Include statistical values when mentioned (convert percentages to decimals for AUC/sensitivity/specificity)
- Be specific about association types
- Only include information explicitly stated in the abstract"""


class ExtractionPrompts:
    """Manager for extraction prompts."""
    
    @staticmethod
    def get_system_prompt() -> str:
        return EXTRACTION_SYSTEM_PROMPT
    
    @staticmethod
    def get_extraction_prompt(title: str, abstract: str) -> str:
        return EXTRACTION_USER_PROMPT.format(title=title, abstract=abstract)
    
    @staticmethod
    def get_validation_prompt(marker_name: str) -> str:
        """Prompt for validating/normalizing marker names."""
        return f"""Given the biomarker name "{marker_name}", provide:
1. The official HGNC gene symbol (if it's a gene)
2. The marker type (gene, protein, metabolite, mirna, etc.)
3. Any alternative names

Respond with JSON:
{{
  "official_symbol": "symbol or null",
  "marker_type": "type",
  "aliases": ["list", "of", "aliases"]
}}"""

