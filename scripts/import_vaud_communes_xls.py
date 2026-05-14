"""
Import the official Vaud 2026 commune tax XLS file into a versioned CSV.

Usage:
    python scripts/import_vaud_communes_xls.py \
        /path/to/Arrêtes_d_imposition_2026.xls
"""
from __future__ import annotations

import csv
from pathlib import Path
import re
import sys

import xlrd


SOURCE_TAX_YEAR = 2026
SOURCE_URL = (
    "https://www.vd.ch/fileadmin/user_upload/themes/territoire/communes/"
    "finances_communales/fichiers_xls/Arr%C3%AAt%C3%A9s_d_imposition_2026.xls"
)
SHEET_NAME = "arreteImposition"


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _default_output_path() -> Path:
    return _repo_root() / "data" / "vaud_communes_2026.csv"


def _clean_year(value: object) -> str:
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:.0f}"
    text = str(value).strip()
    return text


def _clean_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text or text == "-":
        return None
    return float(text.replace(",", "."))


def _clean_district(raw_name: str) -> str:
    core = raw_name.replace("DISTRICT ", "").strip().lower()
    if core.startswith("d'"):
        return "District d'" + core[2:].title()
    if core.startswith("de "):
        return "District de " + core[3:].title()
    return "District " + core.title()


def _split_footnote_marker(name: str) -> tuple[str, str]:
    match = re.match(r"^(.*?)(\*+)?$", name.strip())
    if not match:
        return name.strip(), ""
    return match.group(1).strip(), match.group(2) or ""


def _collect_footnotes(sheet: xlrd.sheet.Sheet) -> dict[str, str]:
    footnotes: dict[str, str] = {}
    for row_idx in range(sheet.nrows):
        label = str(sheet.cell_value(row_idx, 0)).strip()
        if not label.startswith("*"):
            continue
        marker = label.split(" ", 1)[0]
        footnotes[marker] = label[len(marker) :].strip()
    return footnotes


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python scripts/import_vaud_communes_xls.py /path/to/file.xls")

    input_path = Path(sys.argv[1]).expanduser().resolve()
    output_path = (
        Path(sys.argv[2]).expanduser().resolve()
        if len(sys.argv) >= 3
        else _default_output_path().resolve()
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    book = xlrd.open_workbook(input_path.as_posix())
    sheet = book.sheet_by_name(SHEET_NAME)

    year_cell = sheet.cell_value(0, 0)
    if not isinstance(year_cell, (int, float)) or int(year_cell) != SOURCE_TAX_YEAR:
        raise ValueError(f"Unexpected tax-year cell in {input_path}")
    if "Impôt foncier" not in str(sheet.cell_value(0, 6)):
        raise ValueError(f"Unexpected header layout in {input_path}")

    footnotes = _collect_footnotes(sheet)
    rows: list[dict[str, str | float]] = []
    current_district = ""

    for row_idx in range(5, sheet.nrows):
        row = sheet.row_values(row_idx)
        label = str(row[0]).strip()
        if not label:
            continue
        if label.startswith("DISTRICT "):
            current_district = _clean_district(label)
            continue
        if "(fraction)" in label.lower():
            continue
        total_pct = _clean_float(row[5])
        if total_pct is None:
            continue

        commune_name, footnote_marker = _split_footnote_marker(label)
        property_tax_per_mille = _clean_float(row[6])
        if property_tax_per_mille is None:
            raise ValueError(f"Missing impôt foncier rate for {commune_name}")

        income_wealth_pct_base = _clean_float(row[3])
        if income_wealth_pct_base is None:
            raise ValueError(f"Missing commune coefficient for {commune_name}")

        special_pct = _clean_float(row[4]) or 0.0
        rows.append(
            {
                "district": current_district,
                "commune_name": commune_name,
                "source_tax_year": SOURCE_TAX_YEAR,
                "adopted_year": _clean_year(row[1]),
                "valid_until_year": _clean_year(row[2]),
                "income_wealth_pct_base": f"{income_wealth_pct_base:.1f}",
                "special_pct": f"{special_pct:.1f}",
                "total_pct": f"{total_pct:.1f}",
                "commune_multiplier": f"{total_pct / 100.0:.3f}",
                "property_tax_per_mille": f"{property_tax_per_mille:.2f}",
                "communal_property_tax_rate": f"{property_tax_per_mille / 1_000.0:.5f}",
                "notes": footnotes.get(footnote_marker, ""),
            }
        )

    with output_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "district",
                "commune_name",
                "source_tax_year",
                "adopted_year",
                "valid_until_year",
                "income_wealth_pct_base",
                "special_pct",
                "total_pct",
                "commune_multiplier",
                "property_tax_per_mille",
                "communal_property_tax_rate",
                "notes",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} communes to {output_path}")
    print(f"Source: {SOURCE_URL}")


if __name__ == "__main__":
    main()
