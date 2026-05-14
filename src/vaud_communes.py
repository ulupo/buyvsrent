"""
Official 2026 Vaud commune tax data used by the Streamlit selector.

Runtime intentionally loads a versioned CSV from the repository so the app does
not depend on the network when you open it.
"""
from __future__ import annotations

from dataclasses import dataclass
import csv
from functools import lru_cache
from pathlib import Path


VAUD_COMMUNE_SOURCE_TAX_YEAR = 2026
VAUD_COMMUNE_SOURCE_URL = (
    "https://www.vd.ch/fileadmin/user_upload/themes/territoire/communes/"
    "finances_communales/fichiers_xls/Arr%C3%AAt%C3%A9s_d_imposition_2026.xls"
)


@dataclass(frozen=True)
class VaudCommuneTaxRow:
    district: str
    commune_name: str
    source_tax_year: int
    adopted_year: int | None
    valid_until_year: int | None
    income_wealth_pct_base: float
    special_pct: float
    total_pct: float
    commune_multiplier: float
    property_tax_per_mille: float
    communal_property_tax_rate: float
    notes: str


def _data_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "vaud_communes_2026.csv"


def _parse_optional_int(value: str) -> int | None:
    text = value.strip()
    if not text:
        return None
    return int(text)


@lru_cache(maxsize=1)
def load_vaud_communes_2026() -> tuple[VaudCommuneTaxRow, ...]:
    path = _data_path()
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = []
        for raw in reader:
            rows.append(
                VaudCommuneTaxRow(
                    district=raw["district"],
                    commune_name=raw["commune_name"],
                    source_tax_year=int(raw["source_tax_year"]),
                    adopted_year=_parse_optional_int(raw["adopted_year"]),
                    valid_until_year=_parse_optional_int(raw["valid_until_year"]),
                    income_wealth_pct_base=float(raw["income_wealth_pct_base"]),
                    special_pct=float(raw["special_pct"]),
                    total_pct=float(raw["total_pct"]),
                    commune_multiplier=float(raw["commune_multiplier"]),
                    property_tax_per_mille=float(raw["property_tax_per_mille"]),
                    communal_property_tax_rate=float(raw["communal_property_tax_rate"]),
                    notes=raw["notes"],
                )
            )
    return tuple(rows)


@lru_cache(maxsize=1)
def vaud_communes_by_name() -> dict[str, VaudCommuneTaxRow]:
    return {row.commune_name: row for row in load_vaud_communes_2026()}


def get_vaud_commune(name: str) -> VaudCommuneTaxRow:
    return vaud_communes_by_name()[name]


def infer_vaud_commune_name(
    commune_multiplier: float,
    communal_property_tax_rate: float,
    tolerance: float = 1e-9,
    preferred_name: str | None = None,
) -> str | None:
    matches = [
        row.commune_name
        for row in load_vaud_communes_2026()
        if abs(row.commune_multiplier - commune_multiplier) <= tolerance
        and abs(row.communal_property_tax_rate - communal_property_tax_rate) <= tolerance
    ]
    if len(matches) == 1:
        return matches[0]
    if preferred_name is not None and preferred_name in matches:
        return preferred_name
    return None
