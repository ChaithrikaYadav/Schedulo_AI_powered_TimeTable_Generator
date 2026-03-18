"""
chronoai/data_ingestion/__init__.py
CSV-to-database ingestion pipeline for ChronoAI.
"""

from chronoai.data_ingestion.csv_loader import CSVIngestionPipeline

__all__ = ["CSVIngestionPipeline"]
