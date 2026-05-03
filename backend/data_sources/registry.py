"""
Loads dataset metadata from `data_sources/metadata/*.yaml`.

Each YAML declares a dataset's id, columns, and inline rows. The CSV /
DB query nodes consume from here. New mock datasets = new YAML, no code.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)
METADATA_DIR = Path(__file__).parent / "metadata"


@lru_cache(maxsize=1)
def _load_all() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for p in sorted(METADATA_DIR.glob("*.yaml")):
        try:
            data = yaml.safe_load(p.read_text())
            if not data or "id" not in data:
                continue
            out[data["id"]] = data
        except Exception as exc:
            logger.warning("Failed to load dataset metadata %s: %s", p, exc)
    logger.info("Loaded %d datasets from %s", len(out), METADATA_DIR)
    return out


def dataset_names() -> list[str]:
    return sorted(_load_all().keys())


def get_dataset(name: str) -> dict[str, Any] | None:
    return _load_all().get(name)


def get_rows(name: str) -> list[dict[str, Any]]:
    ds = get_dataset(name)
    return list(ds.get("rows", [])) if ds else []


# ---- PDF mock content -------------------------------------------------------
PDF_MOCK = {
    "default": {
        "pages": 4,
        "text": (
            "Executive Summary\n\nThis document outlines the Q1 2026 performance metrics. "
            "Total revenue reached $2.4M, up 34% YoY. Customer acquisition cost dropped to "
            "$380, while LTV increased to $4,200. Net Revenue Retention stands at 118%."
        ),
    },
    "contract.pdf": {
        "pages": 8,
        "text": (
            "SERVICE AGREEMENT\n\nThis Service Agreement is entered into as of March 1, 2026. "
            "Provider agrees to deliver AI workflow automation services. Customer agrees to pay "
            "$4,800/month."
        ),
    },
    "report.pdf": {
        "pages": 12,
        "text": (
            "MARKET RESEARCH REPORT 2026\n\nThe AI workflow automation market is projected to "
            "reach $18.6B by 2028, growing at 31% CAGR."
        ),
    },
}
  