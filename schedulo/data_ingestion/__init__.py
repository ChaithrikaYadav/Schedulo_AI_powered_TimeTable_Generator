"""
schedulo/data_ingestion/__init__.py
CSV-to-database ingestion pipeline for Schedulo.
"""

from schedulo.data_ingestion.csv_loader import CSVIngestionPipeline

__all__ = ["CSVIngestionPipeline"]
