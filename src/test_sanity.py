"""
test_sanity.py
Script-style verification checks for the simulator.

Run with:
    python src/test_sanity.py
"""
from __future__ import annotations

from pathlib import Path
import sys

import numpy as np

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import IGI_SCHEDULE, SwissConfig
from src.simulator import (
    _correlate_with_reference_shocks,
    _draw_stress_events_from_uniforms,
    _recover_stock_shocks_from_factors,
    _stress_transition_probabilities,
    run_simulation,
)
from src.tax_engine import (
    VaudTaxEngine,
    ifd_base,
    ifd_married,
    ifd_parental,
    vaud_icc_simple,
    vaud_igi_rate,
    vaud_wealth_simple,
)
from src.vaud_communes import get_vaud_commune, infer_vaud_commune_name, load_vaud_communes_2026


def _ok(msg: str) -> None:
    print(f"  OK   {msg}")


def _fail(msg: str) -> None:
    print(f"  FAIL {msg}")
    sys.exit(1)


def _check(cond: bool, msg: str, detail: str = "") -> None:
    if cond:
        _ok(msg)
    else:
        _fail(f"{msg}\n       {detail}")


def test_official_tax_points() -> None:
    print("[1] Official 2026 tax-table points")
    _check(abs(ifd_base(15_100.0) - 0.0) < 1e-9, "IFD single: CHF 15,100 => CHF 0")
    _check(abs(ifd_base(18_500.0) - 25.40) < 1e-9, "IFD single: CHF 18,500 => CHF 25.40")
    _check(abs(ifd_base(82_100.0) - 1_502.95) < 1e-9, "IFD single: CHF 82,100 => CHF 1,502.95")
    _check(abs(ifd_parental(82_100.0, 1) - (1_049.00 - 263.0)) < 1e-9, "IFD parental credit CHF 263 applied")
    _check(abs(vaud_icc_simple(15_100.0) - 603.0) < 1e-9, "Vaud income tax: CHF 15,100 => CHF 603.00")
    _check(abs(vaud_icc_simple(291_700.0) - 35_049.0) < 1e-9, "Vaud income tax: CHF 291,700 => CHF 35,049.00")
    _check(abs(vaud_wealth_simple(60_000.0) - 32.65) < 1e-9, "Vaud wealth tax: CHF 60,000 => CHF 32.65")
    _check(abs(vaud_wealth_simple(711_000.0) - 1_757.35) < 1e-9, "Vaud wealth tax: CHF 711,000 => CHF 1,757.35")


def test_owner_share_handling() -> None:
    print("[2] Owner-occupied VL and debt are split by ownership share")
    cfg = SwissConfig(n_children=0, salary_split=0.5)
    engine = VaudTaxEngine(cfg)
    market_rent = cfg.house_market_rent_monthly * 12.0
    res = engine.calculate_household_tax(
        year=cfg.start_year,
        salary_total=cfg.salary_total,
        portfolio=0.0,
        house_val=cfg.house_price,
        debt=cfg.house_price - cfg.downpayment,
        is_owner=True,
        pillar_3a_contribution_p1=0.0,
        pillar_3a_contribution_p2=0.0,
        market_rent_annual=market_rent,
    )
    p_salary = cfg.salary_total * cfg.salary_split
    p_sal_det = p_salary * (1.0 - cfg.social_security_rate)
    p_market_rent = market_rent * cfg.ownership_split
    vl_fed = p_market_rent * cfg.vl_factor_federal
    interest = (cfg.house_price - cfg.downpayment) * cfg.ownership_split * cfg.interest_rate
    maint = vl_fed * cfg.maintenance_deduction_rate_federal
    prof = max(cfg.fed_deduction_professional_flat * 0.5, min(p_sal_det * 0.03, cfg.fed_deduction_professional_flat))
    expected_taxable_fed = np.floor((p_sal_det + vl_fed - interest - maint - prof - cfg.fed_deduction_transport - cfg.fed_deduction_meals - cfg.fed_deduction_insurance_single) / 100.0) * 100.0
    _check(abs(res.p1.taxable_income_fed - expected_taxable_fed) < 1e-9, "P1 taxable federal income uses half the household VL/debt")
    _check(abs(res.p2.taxable_income_fed - expected_taxable_fed) < 1e-9, "P2 taxable federal income uses half the household VL/debt")


def test_cohabiting_child_split_defaults() -> None:
    print("[3] Cohabiting unmarried parents default to split Vaud child quotient")
    cfg = SwissConfig(
        salary_total=200_000.0,
        salary_split=0.5,
        n_children=1,
        child_claimed_by_p1=True,
        child_deduction_split_to_p1=0.5,
        vaud_single_parent_household=False,
        vaud_child_quotient_share_to_p1=0.5,
    )
    engine = VaudTaxEngine(cfg)
    res = engine.calculate_household_tax(
        year=cfg.start_year,
        salary_total=cfg.salary_total,
        portfolio=0.0,
        house_val=0.0,
        debt=0.0,
        is_owner=False,
        pillar_3a_contribution_p1=0.0,
        pillar_3a_contribution_p2=0.0,
        market_rent_annual=0.0,
    )
    _check(abs(res.p1.icc_income - res.p2.icc_income) < 1e-9, "With equal earnings and a 50/50 Vaud child split, both parents have the same Vaud income tax")
    _check(res.p1.ifd < res.p2.ifd, "Federal parental tariff only helps the claiming parent")


def test_cohabiting_unmarried_federal_child_defaults_follow_common_case() -> None:
    print("[3a] Cohabiting unmarried parents use the common federal child-sharing default")
    cfg = SwissConfig(
        household_status="unmarried",
        salary_total=100_000.0,
        salary_split=0.60,
        social_security_rate=0.0,
        n_children=1,
        child_claimed_by_p1=False,
        child_deduction_split_to_p1=1.0,
        childcare_spend_split_to_p1=1.0,
        vaud_single_parent_household=False,
        vaud_child_quotient_share_to_p1=0.5,
        annual_childcare_spend_household=10_000.0,
        childcare_deduction_years=1,
        fed_deduction_professional_flat=0.0,
        cant_deduction_professional_rate=0.0,
        cant_deduction_professional_min=0.0,
        cant_deduction_professional_max=0.0,
        fed_deduction_transport=0.0,
        cant_deduction_transport=0.0,
        fed_deduction_meals=0.0,
        cant_deduction_meals=0.0,
        fed_deduction_insurance_single=0.0,
        fed_deduction_insurance_single_without_pillars=0.0,
        cant_deduction_insurance_single=0.0,
        fed_deduction_insurance_child_supplement=0.0,
        cant_deduction_insurance_child_supplement=0.0,
        canton_multiplier=0.0,
        commune_multiplier=0.0,
        use_official_cantonal_income_tax_reduction_schedule=False,
        cantonal_income_tax_reduction_rate=0.0,
    )
    res = VaudTaxEngine(cfg).calculate_household_tax(
        year=cfg.start_year,
        salary_total=cfg.salary_total,
        portfolio=0.0,
        house_val=0.0,
        debt=0.0,
        is_owner=False,
        pillar_3a_contribution_p1=0.0,
        pillar_3a_contribution_p2=0.0,
        market_rent_annual=0.0,
    )
    _check(
        abs(res.p1.taxable_income_fed - 51_600.0) < 1e-9
        and abs(res.p2.taxable_income_fed - 31_600.0) < 1e-9,
        "Cohabiting unmarried parents split the federal child and childcare deductions 50/50 by default",
        detail=(
            f"expected p1/p2 taxable federal income 51600/31600, got "
            f"{res.p1.taxable_income_fed:.2f}/{res.p2.taxable_income_fed:.2f}"
        ),
    )
    _check(
        abs(res.p1.ifd - ifd_parental(51_600.0, 1)) < 1e-9
        and abs(res.p2.ifd - ifd_base(31_600.0)) < 1e-9,
        "The higher-income cohabiting parent gets the federal parental tariff by default",
        detail=f"p1/p2 ifd={res.p1.ifd:.2f}/{res.p2.ifd:.2f}",
    )


def test_federal_and_vaud_maintenance_rates_are_separate() -> None:
    print("[3b] Federal and Vaud flat maintenance deductions are modeled separately")
    cfg = SwissConfig(
        household_status="unmarried",
        salary_total=100_000.0,
        salary_split=1.0,
        ownership_split=1.0,
        social_security_rate=0.0,
        n_children=0,
        house_price=1_000_000.0,
        downpayment=500_000.0,
        interest_rate=0.0,
        dividend_yield=0.0,
        vl_factor_federal=1.0,
        vl_factor_cantonal=1.0,
        maintenance_deduction_rate_federal=0.10,
        maintenance_deduction_rate_cantonal=0.30,
        fed_deduction_professional_flat=0.0,
        cant_deduction_professional_rate=0.0,
        cant_deduction_professional_min=0.0,
        cant_deduction_professional_max=0.0,
        fed_deduction_transport=0.0,
        cant_deduction_transport=0.0,
        fed_deduction_meals=0.0,
        cant_deduction_meals=0.0,
        fed_deduction_insurance_single=0.0,
        fed_deduction_insurance_single_without_pillars=0.0,
        cant_deduction_insurance_single=0.0,
        canton_multiplier=1.0,
        commune_multiplier=0.0,
        communal_property_tax_rate=0.0,
    )
    market_rent = 20_000.0
    res = VaudTaxEngine(cfg).calculate_household_tax(
        year=cfg.start_year,
        salary_total=cfg.salary_total,
        portfolio=0.0,
        house_val=cfg.house_price,
        debt=cfg.house_price - cfg.downpayment,
        is_owner=True,
        pillar_3a_contribution_p1=0.0,
        pillar_3a_contribution_p2=0.0,
        market_rent_annual=market_rent,
    )
    _check(
        abs(res.p1.taxable_income_fed - 118_000.0) < 1e-9,
        "Federal taxable income uses the federal flat maintenance deduction bucket",
    )
    _check(
        abs(res.p1.taxable_income_cant - 114_000.0) < 1e-9,
        "Cantonal taxable income uses the separate Vaud flat maintenance deduction bucket",
    )


def test_married_joint_tax_without_children() -> None:
    print("[4] Married households use joint federal and Vaud taxation")
    cfg = SwissConfig(
        household_status="married",
        salary_total=180_000.0,
        salary_split=0.5,
        social_security_rate=0.0,
        n_children=0,
        canton_multiplier=1.0,
        commune_multiplier=0.0,
        use_official_cantonal_income_tax_reduction_schedule=False,
        cantonal_income_tax_reduction_rate=0.0,
        fed_deduction_professional_flat=0.0,
        cant_deduction_professional_rate=0.0,
        cant_deduction_professional_min=0.0,
        cant_deduction_professional_max=0.0,
        fed_deduction_transport=0.0,
        cant_deduction_transport=0.0,
        fed_deduction_meals=0.0,
        cant_deduction_meals=0.0,
        fed_deduction_insurance_married=0.0,
        cant_deduction_insurance_married=0.0,
        fed_deduction_married=0.0,
        fed_deduction_double_income_min=0.0,
        fed_deduction_double_income_max=0.0,
        cant_deduction_double_income_min=0.0,
        cant_deduction_double_income_max=0.0,
    )
    res = VaudTaxEngine(cfg).calculate_household_tax(
        year=cfg.start_year,
        salary_total=cfg.salary_total,
        portfolio=0.0,
        house_val=0.0,
        debt=0.0,
        is_owner=False,
        pillar_3a_contribution_p1=0.0,
        pillar_3a_contribution_p2=0.0,
        market_rent_annual=0.0,
    )
    _check(res.household is not None, "Married mode returns a household-level tax result")
    _check(res.p1 is None and res.p2 is None, "Married mode does not fabricate separate P1/P2 tax ledgers")
    _check(abs(res.household.taxable_income_fed - 180_000.0) < 1e-9, "Married taxable federal income is computed on the joint household base")
    _check(abs(res.household.ifd - ifd_married(180_000.0)) < 1e-9, "Married mode uses the federal married tariff")
    expected_icc_income = vaud_icc_simple(100_000.0) * 1.8
    _check(
        abs(res.household.icc_income - expected_icc_income) < 1e-9,
        "Married mode uses Vaud's 1.8 quotient for a childless couple",
        detail=f"expected={expected_icc_income:.2f}, got={res.household.icc_income:.2f}",
    )


def test_married_federal_double_income_uses_net_earned_income() -> None:
    print("[4b] Married federal double-income deduction uses net earned income")
    cfg = SwissConfig(
        household_status="married",
        salary_total=90_000.0,
        salary_split=2.0 / 3.0,
        social_security_rate=0.13,
        n_children=0,
        canton_multiplier=0.0,
        commune_multiplier=0.0,
        use_official_cantonal_income_tax_reduction_schedule=False,
        cantonal_income_tax_reduction_rate=0.0,
        fed_deduction_professional_flat=4_000.0,
        cant_deduction_professional_rate=0.0,
        cant_deduction_professional_min=0.0,
        cant_deduction_professional_max=0.0,
        fed_deduction_transport=3_300.0,
        cant_deduction_transport=0.0,
        fed_deduction_meals=1_600.0,
        cant_deduction_meals=0.0,
        fed_deduction_insurance_married=0.0,
        fed_deduction_insurance_married_without_pillars=0.0,
        cant_deduction_insurance_married=0.0,
        fed_deduction_married=0.0,
        fed_deduction_double_income_min=0.0,
        fed_deduction_double_income_max=14_100.0,
        cant_deduction_double_income_min=0.0,
        cant_deduction_double_income_max=0.0,
        p1_pillar2_affiliated=False,
        p2_pillar2_affiliated=False,
    )
    res = VaudTaxEngine(cfg).calculate_household_tax(
        year=cfg.start_year,
        salary_total=cfg.salary_total,
        portfolio=0.0,
        house_val=0.0,
        debt=0.0,
        is_owner=False,
        pillar_3a_contribution_p1=0.0,
        pillar_3a_contribution_p2=0.0,
        market_rent_annual=0.0,
    )
    _check(
        abs(res.household.taxable_income_fed - 54_900.0) < 1e-9,
        "Married federal taxable income uses the lower spouse's net earned income for the double-income deduction",
        detail=f"expected=54900.00, got={res.household.taxable_income_fed:.2f}",
    )
    _check(
        abs(res.household.ifd - ifd_married(54_900.0)) < 1e-9,
        "Married federal tax follows the corrected net-earned-income double-income deduction base",
    )


def test_married_vaud_child_cap_uses_official_table() -> None:
    print("[5] Married Vaud child quotient cap uses the official married-household table")
    cfg = SwissConfig(
        household_status="married",
        salary_total=300_000.0,
        salary_split=0.5,
        social_security_rate=0.0,
        n_children=4,
        canton_multiplier=1.0,
        commune_multiplier=0.0,
        use_official_cantonal_income_tax_reduction_schedule=False,
        cantonal_income_tax_reduction_rate=0.0,
        fed_deduction_professional_flat=0.0,
        cant_deduction_professional_rate=0.0,
        cant_deduction_professional_min=0.0,
        cant_deduction_professional_max=0.0,
        fed_deduction_transport=0.0,
        cant_deduction_transport=0.0,
        fed_deduction_meals=0.0,
        cant_deduction_meals=0.0,
        fed_deduction_insurance_married=0.0,
        cant_deduction_insurance_married=0.0,
        fed_deduction_insurance_child_supplement=0.0,
        cant_deduction_insurance_child_supplement=0.0,
        fed_deduction_childcare_per_child=0.0,
        cant_deduction_childcare_per_child=0.0,
        fed_deduction_per_child=0.0,
        cant_deduction_per_child=0.0,
        fed_deduction_married=0.0,
        fed_deduction_double_income_min=0.0,
        fed_deduction_double_income_max=0.0,
        cant_deduction_double_income_min=0.0,
        cant_deduction_double_income_max=0.0,
    )
    res = VaudTaxEngine(cfg).calculate_household_tax(
        year=cfg.start_year,
        salary_total=cfg.salary_total,
        portfolio=0.0,
        house_val=0.0,
        debt=0.0,
        is_owner=False,
        pillar_3a_contribution_p1=0.0,
        pillar_3a_contribution_p2=0.0,
        market_rent_annual=0.0,
    )
    expected_rate_income = np.floor(((300_000.0 / 1.8) - 82_953.0) / 100.0) * 100.0
    expected_icc_income = vaud_icc_simple(expected_rate_income) * (300_000.0 / expected_rate_income)
    _check(
        abs(res.household.taxable_income_cant - 300_000.0) < 1e-9,
        "Married taxable cantonal income is computed on the joint household base before the quotient",
    )
    _check(
        abs(res.household.icc_income - expected_icc_income) < 1e-9,
        "Married mode applies Vaud's official capped quotient logic for children",
        detail=f"expected={expected_icc_income:.2f}, got={res.household.icc_income:.2f}",
    )


def test_childcare_deduction_window() -> None:
    print("[6] Childcare deduction ends before the full child-dependency window")
    cfg = SwissConfig(
        salary_total=200_000.0,
        salary_split=1.0,
        social_security_rate=0.0,
        index_tax_parameters_with_inflation=False,
        n_children=1,
        child_claimed_by_p1=True,
        child_deduction_split_to_p1=1.0,
        vaud_child_quotient_share_to_p1=1.0,
        childcare_spend_split_to_p1=1.0,
        child_dependent_years=10,
        childcare_deduction_years=1,
        annual_childcare_spend_household=30_000.0,
        fed_deduction_transport=0.0,
        cant_deduction_transport=0.0,
        fed_deduction_meals=0.0,
        cant_deduction_meals=0.0,
        fed_deduction_insurance_single=0.0,
        cant_deduction_insurance_single=0.0,
        fed_deduction_insurance_child_supplement=0.0,
        cant_deduction_insurance_child_supplement=0.0,
    )
    engine = VaudTaxEngine(cfg)
    kwargs = dict(
        salary_total=cfg.salary_total,
        portfolio=0.0,
        house_val=0.0,
        debt=0.0,
        is_owner=False,
        pillar_3a_contribution_p1=0.0,
        pillar_3a_contribution_p2=0.0,
        market_rent_annual=0.0,
    )
    year0 = engine.calculate_household_tax(year=cfg.start_year, **kwargs)
    year1 = engine.calculate_household_tax(year=cfg.start_year + 1, **kwargs)
    _check(
        abs(
            (year1.p1.taxable_income_fed - year0.p1.taxable_income_fed)
            - (0.5 * cfg.fed_deduction_childcare_per_child)
        ) < 1e-9,
        "Federal childcare deduction stops once the childcare window ends",
    )
    _check(
        abs(
            (year1.p1.taxable_income_cant - year0.p1.taxable_income_cant)
            - (0.5 * cfg.cant_deduction_childcare_per_child)
        ) < 1e-9,
        "Vaud childcare deduction stops once the childcare window ends",
    )


def test_post_reform_owner_rules() -> None:
    print("[7] Post-2029 owner rules remove VL and ordinary maintenance deductions")
    cfg = SwissConfig(first_time_home_buyer_p1=False, first_time_home_buyer_p2=False)
    engine = VaudTaxEngine(cfg)
    market_rent = cfg.house_market_rent_monthly * 12.0
    pre = engine.calculate_household_tax(
        year=2028,
        salary_total=cfg.salary_total,
        portfolio=0.0,
        house_val=cfg.house_price,
        debt=cfg.house_price - cfg.downpayment,
        is_owner=True,
        pillar_3a_contribution_p1=cfg.pillar_3a_annual_per_person,
        pillar_3a_contribution_p2=cfg.pillar_3a_annual_per_person,
        market_rent_annual=market_rent,
    ).total
    post = engine.calculate_household_tax(
        year=2029,
        salary_total=cfg.salary_total,
        portfolio=0.0,
        house_val=cfg.house_price,
        debt=cfg.house_price - cfg.downpayment,
        is_owner=True,
        pillar_3a_contribution_p1=cfg.pillar_3a_annual_per_person,
        pillar_3a_contribution_p2=cfg.pillar_3a_annual_per_person,
        market_rent_annual=market_rent,
    ).total
    _check(post < pre, "Owner tax falls in the default scenario once VL disappears and no first-time-buyer deduction is claimed", detail=f"pre={pre:.2f}, post={post:.2f}")


def test_vd_cantonal_reduction_uses_official_schedule_by_default() -> None:
    print("[8] Vaud cantonal reduction follows the official adopted schedule by default")
    cfg = SwissConfig(
        salary_total=100_000.0,
        salary_split=1.0,
        social_security_rate=0.0,
        index_tax_parameters_with_inflation=False,
        n_children=0,
        canton_multiplier=1.0,
        commune_multiplier=0.0,
        fed_deduction_professional_flat=0.0,
        cant_deduction_professional_rate=0.0,
        cant_deduction_professional_min=0.0,
        cant_deduction_professional_max=0.0,
        fed_deduction_transport=0.0,
        cant_deduction_transport=0.0,
        fed_deduction_meals=0.0,
        cant_deduction_meals=0.0,
        fed_deduction_insurance_single=0.0,
        cant_deduction_insurance_single=0.0,
    )
    engine = VaudTaxEngine(cfg)
    kwargs = dict(
        salary_total=cfg.salary_total,
        portfolio=0.0,
        house_val=0.0,
        debt=0.0,
        is_owner=False,
        pillar_3a_contribution_p1=0.0,
        pillar_3a_contribution_p2=0.0,
        market_rent_annual=0.0,
    )
    tax_2026 = engine.calculate_household_tax(year=2026, **kwargs)
    tax_2027 = engine.calculate_household_tax(year=2027, **kwargs)
    expected_2026_icc = vaud_icc_simple(100_000.0) * 0.95
    expected_2027_icc = vaud_icc_simple(100_000.0) * 0.93
    _check(
        abs(tax_2026.p1.icc_income - expected_2026_icc) < 1e-9,
        "The official 5% Vaud cantonal reduction applies in 2026",
    )
    _check(
        abs(tax_2027.p1.icc_income - expected_2027_icc) < 1e-9,
        "The official 7% Vaud cantonal reduction applies from 2027 onward",
    )

    manual_cfg = SwissConfig(
        salary_total=100_000.0,
        salary_split=1.0,
        social_security_rate=0.0,
        index_tax_parameters_with_inflation=False,
        n_children=0,
        canton_multiplier=1.0,
        commune_multiplier=0.0,
        use_official_cantonal_income_tax_reduction_schedule=False,
        cantonal_income_tax_reduction_rate=0.05,
        cantonal_income_tax_reduction_start_year=2026,
        cantonal_income_tax_reduction_end_year=2026,
        fed_deduction_professional_flat=0.0,
        cant_deduction_professional_rate=0.0,
        cant_deduction_professional_min=0.0,
        cant_deduction_professional_max=0.0,
        fed_deduction_transport=0.0,
        cant_deduction_transport=0.0,
        fed_deduction_meals=0.0,
        cant_deduction_meals=0.0,
        fed_deduction_insurance_single=0.0,
        cant_deduction_insurance_single=0.0,
    )
    manual_engine = VaudTaxEngine(manual_cfg)
    manual_2027 = manual_engine.calculate_household_tax(year=2027, **kwargs)
    _check(
        abs(manual_2027.p1.icc_income - vaud_icc_simple(100_000.0)) < 1e-9,
        "The manual flat override still respects its configured end year",
    )


def test_first_time_buyer_phaseout_uses_configured_years() -> None:
    print("[9] First-time-buyer phase-out length uses config")
    cfg_short = SwissConfig(first_time_buyer_years=5, first_time_buyer_interest_deduction_single_max=5_000.0)
    cfg_long = SwissConfig(first_time_buyer_years=10, first_time_buyer_interest_deduction_single_max=5_000.0)
    short_engine = VaudTaxEngine(cfg_short)
    long_engine = VaudTaxEngine(cfg_long)
    short_deduction = short_engine._first_time_buyer_deduction(2031, 10_000.0, True)
    long_deduction = long_engine._first_time_buyer_deduction(2031, 10_000.0, True)
    _check(short_deduction == 0.0, "A 5-year first-time-buyer window is fully phased out by 2031")
    _check(abs(long_deduction - 2_500.0) < 1e-9, "A 10-year first-time-buyer window still leaves a 50% cap in 2031")


def test_married_first_time_buyer_uses_joint_cap() -> None:
    print("[10] Married first-time-buyer deduction uses the joint cap")
    cfg = SwissConfig(
        household_status="married",
        first_time_buyer_years=10,
        first_time_buyer_interest_deduction_single_max=5_000.0,
        first_time_buyer_interest_deduction_married_max=10_000.0,
    )
    engine = VaudTaxEngine(cfg)
    deduction = engine._first_time_buyer_deduction(2031, 20_000.0, True, married=True)
    _check(
        abs(deduction - 5_000.0) < 1e-9,
        "At the same phase-out point, married mode uses the CHF 10,000 starting cap",
    )


def test_cantonal_professional_deduction_uses_config() -> None:
    print("[11] Vaud professional deduction min/max/rate come from config")
    base_kwargs = dict(
        salary_total=100_000.0,
        salary_split=1.0,
        social_security_rate=0.0,
        n_children=0,
        cant_deduction_transport=0.0,
        cant_deduction_meals=0.0,
        cant_deduction_insurance_single=0.0,
        fed_deduction_transport=0.0,
        fed_deduction_meals=0.0,
        fed_deduction_insurance_single=0.0,
    )
    cfg_low = SwissConfig(
        cant_deduction_professional_rate=0.0,
        cant_deduction_professional_min=1_200.0,
        cant_deduction_professional_max=1_200.0,
        **base_kwargs,
    )
    cfg_high = SwissConfig(
        cant_deduction_professional_rate=0.0,
        cant_deduction_professional_min=3_400.0,
        cant_deduction_professional_max=3_400.0,
        **base_kwargs,
    )
    kwargs = dict(
        year=cfg_low.start_year,
        salary_total=cfg_low.salary_total,
        portfolio=0.0,
        house_val=0.0,
        debt=0.0,
        is_owner=False,
        pillar_3a_contribution_p1=0.0,
        pillar_3a_contribution_p2=0.0,
        market_rent_annual=0.0,
    )
    low = VaudTaxEngine(cfg_low).calculate_household_tax(**kwargs)
    high = VaudTaxEngine(cfg_high).calculate_household_tax(**kwargs)
    _check(
        abs((low.p1.taxable_income_cant - high.p1.taxable_income_cant) - 2_200.0) < 1e-9,
        "Changing the configured Vaud professional deduction changes taxable cantonal income",
    )


def test_work_deductions_require_salary() -> None:
    print("[12] Work travel and meal deductions require salary income")
    cfg = SwissConfig(
        salary_total=100_000.0,
        salary_split=1.0,
        portfolio_split=0.0,
        dividend_yield=0.015,
        fed_deduction_insurance_single=0.0,
        fed_deduction_insurance_single_without_pillars=0.0,
        cant_deduction_insurance_single=0.0,
        n_children=0,
    )
    res = VaudTaxEngine(cfg).calculate_household_tax(
        year=cfg.start_year,
        salary_total=cfg.salary_total,
        portfolio=200_000.0,
        house_val=0.0,
        debt=0.0,
        is_owner=False,
        pillar_3a_contribution_p1=0.0,
        pillar_3a_contribution_p2=0.0,
        market_rent_annual=0.0,
    )
    expected_dividend_income = 200_000.0 * cfg.dividend_yield
    _check(
        abs(res.p2.taxable_income_fed - expected_dividend_income) < 1e-9,
        "A partner with zero salary does not get federal work-travel or meal deductions",
    )
    _check(
        abs(res.p2.taxable_income_cant - expected_dividend_income) < 1e-9,
        "A partner with zero salary does not get cantonal work-travel or meal deductions",
    )


def test_positive_salary_without_pillar2_can_use_federal_no_pillars_cap() -> None:
    print("[12b] Positive salary without pillar contributions can use the higher federal insurance cap")
    cfg = SwissConfig(
        household_status="unmarried",
        salary_total=50_000.0,
        salary_split=1.0,
        social_security_rate=0.0,
        p1_pillar2_affiliated=False,
        p2_pillar2_affiliated=False,
        dividend_yield=0.0,
        fed_deduction_professional_flat=0.0,
        cant_deduction_professional_rate=0.0,
        cant_deduction_professional_min=0.0,
        cant_deduction_professional_max=0.0,
        fed_deduction_transport=0.0,
        cant_deduction_transport=0.0,
        fed_deduction_meals=0.0,
        cant_deduction_meals=0.0,
        fed_deduction_insurance_single=1_800.0,
        fed_deduction_insurance_single_without_pillars=2_700.0,
        cant_deduction_insurance_single=0.0,
        canton_multiplier=0.0,
        commune_multiplier=0.0,
        communal_property_tax_rate=0.0,
        n_children=0,
    )
    res = VaudTaxEngine(cfg).calculate_household_tax(
        year=cfg.start_year,
        salary_total=cfg.salary_total,
        portfolio=0.0,
        house_val=0.0,
        debt=0.0,
        is_owner=False,
        pillar_3a_contribution_p1=0.0,
        pillar_3a_contribution_p2=0.0,
        market_rent_annual=0.0,
    )
    _check(
        abs(res.p1.taxable_income_fed - 47_300.0) < 1e-9,
        "Without modeled pillar-2 or pillar-3a contributions, the higher federal no-pillars cap is used",
    )


def test_da1_credit_defaults_to_zero_without_explicit_eligible_share() -> None:
    print("[13] DA-1 defaults to zero unless an eligible dividend share is entered")
    cfg = SwissConfig(
        household_status="unmarried",
        salary_total=250_000.0,
        salary_split=0.0,
        portfolio_split=0.0,
        dividend_yield=0.10,
        social_security_rate=0.0,
        n_children=0,
        fed_deduction_professional_flat=0.0,
        cant_deduction_professional_rate=0.0,
        cant_deduction_professional_min=0.0,
        cant_deduction_professional_max=0.0,
        fed_deduction_transport=0.0,
        cant_deduction_transport=0.0,
        fed_deduction_meals=0.0,
        cant_deduction_meals=0.0,
        fed_deduction_insurance_single=0.0,
        cant_deduction_insurance_single=0.0,
        canton_multiplier=0.0,
        commune_multiplier=0.0,
        communal_property_tax_rate=0.0,
    )
    res = VaudTaxEngine(cfg).calculate_household_tax(
        year=cfg.start_year,
        salary_total=cfg.salary_total,
        portfolio=200_000.0,
        house_val=0.0,
        debt=0.0,
        is_owner=False,
        pillar_3a_contribution_p1=0.0,
        pillar_3a_contribution_p2=0.0,
        market_rent_annual=0.0,
    )
    _check(
        abs(res.foreign_dividend_wht_credit) < 1e-9,
        "Without an explicit eligible-dividend share, the simulator grants no DA-1 credit",
    )


def test_unmarried_da1_credit_is_opt_in_and_partner_specific() -> None:
    print("[14] Unmarried DA-1 uses only the explicit eligible share and stays partner-specific")
    cfg = SwissConfig(
        household_status="unmarried",
        salary_total=250_000.0,
        salary_split=0.0,
        portfolio_split=0.0,
        dividend_yield=0.10,
        da1_eligible_dividend_share=0.25,
        da1_non_refundable_withholding_rate=0.15,
        da1_minimum_non_refundable_tax=100.0,
        social_security_rate=0.0,
        n_children=0,
        fed_deduction_professional_flat=0.0,
        cant_deduction_professional_rate=0.0,
        cant_deduction_professional_min=0.0,
        cant_deduction_professional_max=0.0,
        fed_deduction_transport=0.0,
        cant_deduction_transport=0.0,
        fed_deduction_meals=0.0,
        cant_deduction_meals=0.0,
        fed_deduction_insurance_single=0.0,
        cant_deduction_insurance_single=0.0,
    )
    res = VaudTaxEngine(cfg).calculate_household_tax(
        year=cfg.start_year,
        salary_total=cfg.salary_total,
        portfolio=200_000.0,
        house_val=0.0,
        debt=0.0,
        is_owner=False,
        pillar_3a_contribution_p1=0.0,
        pillar_3a_contribution_p2=0.0,
        market_rent_annual=0.0,
    )
    expected_credit = 0.25 * 0.15 * (200_000.0 * cfg.dividend_yield)
    _check(
        abs(res.foreign_dividend_wht_credit - expected_credit) < 1e-9,
        "Only the explicit eligible dividend slice receives a DA-1 credit, and only for the taxed partner",
        detail=f"expected={expected_credit:.2f}, got={res.foreign_dividend_wht_credit:.2f}",
    )


def test_da1_minimum_threshold_is_respected() -> None:
    print("[15] DA-1 is zero below the minimum non-refundable foreign-tax threshold")
    cfg = SwissConfig(
        household_status="married",
        salary_total=250_000.0,
        dividend_yield=0.01,
        da1_eligible_dividend_share=1.0,
        da1_non_refundable_withholding_rate=0.15,
        da1_minimum_non_refundable_tax=100.0,
        social_security_rate=0.0,
        n_children=0,
        fed_deduction_professional_flat=0.0,
        cant_deduction_professional_rate=0.0,
        cant_deduction_professional_min=0.0,
        cant_deduction_professional_max=0.0,
        fed_deduction_transport=0.0,
        cant_deduction_transport=0.0,
        fed_deduction_meals=0.0,
        cant_deduction_meals=0.0,
        fed_deduction_insurance_married=0.0,
        cant_deduction_insurance_married=0.0,
        fed_deduction_married=0.0,
        fed_deduction_double_income_min=0.0,
        fed_deduction_double_income_max=0.0,
        cant_deduction_double_income_min=0.0,
        cant_deduction_double_income_max=0.0,
    )
    res = VaudTaxEngine(cfg).calculate_household_tax(
        year=cfg.start_year,
        salary_total=cfg.salary_total,
        portfolio=50_000.0,
        house_val=0.0,
        debt=0.0,
        is_owner=False,
        pillar_3a_contribution_p1=0.0,
        pillar_3a_contribution_p2=0.0,
        market_rent_annual=0.0,
    )
    _check(
        abs(res.foreign_dividend_wht_credit) < 1e-9,
        "Modeled DA-1 stays at zero when non-refundable foreign tax does not exceed the threshold",
    )


def test_validation_and_edge_cases() -> None:
    print("[16] Validation and numerical edge cases")
    defaults = SwissConfig()
    _check(
        abs(defaults.vl_factor_cantonal - 0.65) < 1e-12,
        "The shipped Vaud imputed-rent percentage stays at 65%",
    )
    _check(
        abs(defaults.vl_factor_federal - 0.90) < 1e-12,
        "The shipped federal imputed-rent percentage stays at 90%",
    )

    try:
        SwissConfig(house_price=500_000.0, downpayment=600_000.0).validate()
        _fail("Invalid config should have raised ValueError")
    except ValueError:
        _ok("Config rejects downpayment above purchase price")

    try:
        SwissConfig(
            cantonal_income_tax_reduction_start_year=2027,
            cantonal_income_tax_reduction_end_year=2026,
        ).validate()
        _fail("Invalid cantonal reduction year window should have raised ValueError")
    except ValueError:
        _ok("Config rejects a cantonal reduction window with start year after end year")

    try:
        SwissConfig(cantonal_income_tax_reduction_rate=2.0).validate()
        _fail("Invalid cantonal reduction rate should have raised ValueError")
    except ValueError:
        _ok("Config rejects a cantonal reduction rate above 100%")

    try:
        SwissConfig(
            official_cantonal_income_tax_reduction_schedule=((2027, 0.07), (2026, 0.05))
        ).validate()
        _fail("Unsorted official cantonal reduction schedule should have raised ValueError")
    except ValueError:
        _ok("Config rejects an unsorted official Vaud reduction schedule")

    try:
        SwissConfig(salary_total=float("nan")).validate()
        _fail("NaN salary_total should have raised ValueError")
    except ValueError:
        _ok("Config rejects non-finite numeric inputs")

    try:
        SwissConfig(annual_other_consumption=-1.0).validate()
        _fail("Negative annual_other_consumption should have raised ValueError")
    except ValueError:
        _ok("Config rejects negative annual household consumption")

    try:
        SwissConfig(salary_total=-1.0).validate()
        _fail("Negative salary_total should have raised ValueError")
    except ValueError:
        _ok("Config rejects negative household salary")

    try:
        SwissConfig(amortization_annual=-1.0).validate()
        _fail("Negative amortization_annual should have raised ValueError")
    except ValueError:
        _ok("Config rejects negative annual amortization")

    try:
        SwissConfig(pillar_3a_annual_per_person=-1.0).validate()
        _fail("Negative pillar_3a_annual_per_person should have raised ValueError")
    except ValueError:
        _ok("Config rejects negative pillar-3a contribution caps")

    try:
        SwissConfig(initial_pillar_3a_assets=-1.0).validate()
        _fail("Negative initial_pillar_3a_assets should have raised ValueError")
    except ValueError:
        _ok("Config rejects negative initial pillar-3a savings")

    try:
        SwissConfig(
            house_price=100.0,
            downpayment=100.0,
            buying_costs_pct=0.0,
            initial_liquid_assets=0.0,
            initial_pillar_3a_assets=100.0,
            pillar_3a_withdrawal_tax_rate=0.08,
        ).validate()
        _fail("Purchase without enough starting money should have raised ValueError")
    except ValueError:
        _ok("Config rejects purchases that cannot be paid from starting cash/investments and available 3a")

    try:
        SwissConfig(mortgage_rate_min=0.06, mortgage_rate_max=0.05).validate()
        _fail("Mortgage-rate floor above cap should have raised ValueError")
    except ValueError:
        _ok("Config rejects mortgage-rate floors above caps")

    try:
        SwissConfig(interest_rate=0.02, mortgage_rate_min=0.03).validate()
        _fail("Baseline mortgage rate outside floor/cap should have raised ValueError")
    except ValueError:
        _ok("Config rejects starting mortgage rates outside the configured floor/cap")

    try:
        SwissConfig(start_year=2025).validate()
        _fail("Pre-2026 start_year should have raised ValueError")
    except ValueError:
        _ok("Config rejects start years before the embedded official tax tables")

    try:
        SwissConfig(stress_persistence=1.5).validate()
        _fail("Invalid stress persistence should have raised ValueError")
    except ValueError:
        _ok("Config rejects stress persistence above 100%")

    try:
        SwissConfig(stock_volatility=500.0).validate()
        _fail("Extreme stock volatility should have raised ValueError")
    except ValueError:
        _ok("Config rejects extreme annual stock volatility")

    try:
        SwissConfig(pillar_3a_withdrawal_tax_rate=1.5).validate()
        _fail("Invalid pillar-3a withdrawal tax rate should have raised ValueError")
    except ValueError:
        _ok("Config rejects pillar-3a withdrawal tax rates above 100%")

    try:
        SwissConfig(canton_multiplier=-0.1).validate()
        _fail("Negative canton multiplier should have raised ValueError")
    except ValueError:
        _ok("Config rejects negative canton multipliers")

    try:
        SwissConfig(commune_multiplier=-0.1).validate()
        _fail("Negative commune multiplier should have raised ValueError")
    except ValueError:
        _ok("Config rejects negative commune multipliers")

    try:
        SwissConfig(first_time_buyer_interest_deduction_single_max=-1.0).validate()
        _fail("Negative single first-time-buyer cap should have raised ValueError")
    except ValueError:
        _ok("Config rejects negative single first-time-buyer interest-deduction caps")

    try:
        SwissConfig(first_time_buyer_interest_deduction_married_max=-1.0).validate()
        _fail("Negative married first-time-buyer cap should have raised ValueError")
    except ValueError:
        _ok("Config rejects negative married first-time-buyer interest-deduction caps")

    try:
        SwissConfig(first_time_buyer_years=10, first_time_buyer_years_used_before_start_p1=11).validate()
        _fail("Already-used first-time-buyer years above the full window should have raised ValueError")
    except ValueError:
        _ok("Config rejects already-used first-time-buyer years above the full deduction window")

    try:
        SwissConfig(forced_sale_rental_deposit_months=4.0).validate()
        _fail("Forced-sale rental deposit above 3 months should have raised ValueError")
    except ValueError:
        _ok("Config rejects forced-sale rental deposits above the Swiss 3-month cap")

    try:
        SwissConfig(
            household_status="unmarried",
            n_children=1,
            child_deduction_split_to_p1=0.3,
        ).validate()
        _fail("Invalid unmarried child split should have raised ValueError")
    except ValueError:
        _ok("Config rejects unmarried child splits outside whole-child / half-child steps")

    try:
        SwissConfig(household_status="married", n_children=6).validate()
        _fail("Unsupported married child count should have raised ValueError")
    except ValueError:
        _ok("Config rejects married child counts above the published table")

    try:
        SwissConfig(household_status="unmarried", n_children=4).validate()
        _fail("Unsupported unmarried child count should have raised ValueError")
    except ValueError:
        _ok("Config rejects unmarried child counts above the published Vaud table")

    try:
        SwissConfig(liquidity_shortfall_rate=-0.01).validate()
        _fail("Negative liquidity shortfall rate should have raised ValueError")
    except ValueError:
        _ok("Config rejects negative liquidity shortfall rates")

    try:
        SwissConfig(market_rent_real_growth=-1.0).validate()
        _fail("Invalid market-rent real growth should have raised ValueError")
    except ValueError:
        _ok("Config rejects market-rent real growth at or below -100%")

    _check(
        abs(SwissConfig().fed_deduction_transport - 3_300.0) < 1e-12,
        "The shipped federal transport deduction default matches the official 2026 CHF 3,300 ceiling",
    )

    cfg = SwissConfig(iterations=200, years=5, stock_volatility=0.0, house_volatility=0.0, asset_correlation=1.0)
    res = run_simulation(cfg)
    _check(np.all(np.isfinite(res.buy_terminal_liquid)), "Perfect correlation and zero volatility still produce finite outputs")
    _check(np.all(np.isfinite(res.rent_terminal_liquid)), "Perfect correlation and zero volatility still produce finite renter outputs")


def test_liquidity_shortfall_model() -> None:
    print("[17] Negative cash balances do not compound at stock returns")
    cfg = SwissConfig(
        years=2,
        iterations=1,
        rng_seed=1,
        annual_other_consumption=1_000_000.0,
        stock_growth_world_usd=0.08,
        chf_appreciation_vs_usd=0.0,
        stock_volatility=0.0,
        house_growth=0.0,
        house_volatility=0.0,
        inflation_volatility=0.0,
        portfolio_ter=0.0,
        pillar_3a_ter=0.0,
        liquidity_shortfall_rate=0.03,
        n_children=0,
        force_buy_sale_on_liquidity_crisis=False,
    )
    res = run_simulation(cfg)
    end_balance_year1 = float(res.buy_portfolio[0, 0])
    end_balance_year2 = float(res.buy_portfolio[0, 1])
    year2_surplus = float(res.buy_surplus[0, 1])
    expected = end_balance_year1 * (1.0 + cfg.liquidity_shortfall_rate) + year2_surplus
    _check(
        abs(end_balance_year2 - expected) < 1e-6,
        "Opening negative cash balance compounds at the shortfall rate, not at stock returns",
        detail=f"expected={expected:.2f}, got={end_balance_year2:.2f}",
    )


def test_stock_return_translation_uses_fx_formula() -> None:
    print("[18] USD stock return is translated into CHF with the compounding formula")
    cfg = SwissConfig(stock_growth_world_usd=0.06, chf_appreciation_vs_usd=0.015)
    expected = (1.0 + 0.06) / (1.0 + 0.015) - 1.0
    _check(
        abs(cfg.stock_growth_chf - expected) < 1e-12,
        "Effective CHF stock return matches the USD-to-CHF translation formula",
        detail=f"expected={expected:.12f}, got={cfg.stock_growth_chf:.12f}",
    )


def test_cashflow_uses_post_social_salary() -> None:
    print("[19] Cash flow uses salary after payroll deductions")
    cfg = SwissConfig(
        years=1,
        iterations=1,
        rng_seed=1,
        stock_growth_world_usd=0.0,
        chf_appreciation_vs_usd=0.0,
        stock_volatility=0.0,
        house_growth=0.0,
        house_volatility=0.0,
        inflation=0.0,
        salary_growth=0.0,
        base_rent_monthly=0.0,
        annual_other_consumption=0.0,
        pillar_3a_annual_per_person=0.0,
        social_security_rate=0.10,
        n_children=0,
    )
    res = run_simulation(cfg)
    expected_rent_surplus = cfg.salary_total * (1.0 - cfg.social_security_rate) - float(res.rent_tax[0, 0])
    _check(
        abs(float(res.rent_surplus[0, 0]) - expected_rent_surplus) < 1e-6,
        "Renter cash surplus starts from salary after payroll deductions",
        detail=f"expected={expected_rent_surplus:.2f}, got={float(res.rent_surplus[0, 0]):.2f}",
    )


def test_tax_indexation_preserves_real_tax_burden() -> None:
    print("[20] Indexed tax-law amounts keep the real tax burden stable when real income is flat")
    cfg = SwissConfig(
        household_status="married",
        salary_total=120_000.0,
        salary_split=0.5,
        social_security_rate=0.0,
        inflation=0.01,
        index_tax_parameters_with_inflation=True,
        n_children=0,
        canton_multiplier=1.0,
        commune_multiplier=0.0,
        use_official_cantonal_income_tax_reduction_schedule=False,
        cantonal_income_tax_reduction_rate=0.0,
        fed_deduction_professional_flat=0.0,
        cant_deduction_professional_rate=0.0,
        cant_deduction_professional_min=0.0,
        cant_deduction_professional_max=0.0,
        fed_deduction_transport=0.0,
        cant_deduction_transport=0.0,
        fed_deduction_meals=0.0,
        cant_deduction_meals=0.0,
        fed_deduction_insurance_married=0.0,
        cant_deduction_insurance_married=0.0,
        fed_deduction_married=0.0,
        fed_deduction_double_income_min=0.0,
        fed_deduction_double_income_max=0.0,
        cant_deduction_double_income_min=0.0,
        cant_deduction_double_income_max=0.0,
    )
    engine = VaudTaxEngine(cfg)
    base = engine.calculate_household_tax(
        year=2026,
        salary_total=120_000.0,
        portfolio=0.0,
        house_val=0.0,
        debt=0.0,
        is_owner=False,
        pillar_3a_contribution_p1=0.0,
        pillar_3a_contribution_p2=0.0,
        market_rent_annual=0.0,
    ).total
    year = 2036
    factor = (1.0 + cfg.inflation) ** (year - 2026)
    future = engine.calculate_household_tax(
        year=year,
        salary_total=120_000.0 * factor,
        portfolio=0.0,
        house_val=0.0,
        debt=0.0,
        is_owner=False,
        pillar_3a_contribution_p1=0.0,
        pillar_3a_contribution_p2=0.0,
        market_rent_annual=0.0,
    ).total
    _check(
        abs((future / factor) - base) < 5.0,
        "With indexed tax-law amounts, flat real income produces nearly flat real taxes",
        detail=f"base={base:.2f}, deflated_future={(future / factor):.2f}",
    )


def test_simulation_indexes_pillar_3a_cap_when_enabled() -> None:
    print("[21] Simulation indexes the annual pillar-3a cap when tax-law indexation is enabled")
    cfg = SwissConfig(
        years=2,
        iterations=1,
        rng_seed=1,
        stock_growth_world_usd=0.0,
        chf_appreciation_vs_usd=0.0,
        stock_volatility=0.0,
        house_growth=0.0,
        house_volatility=0.0,
        inflation=0.01,
        inflation_volatility=0.0,
        salary_growth=0.0,
        portfolio_ter=0.0,
        pillar_3a_ter=0.0,
        pillar_3a_annual_per_person=1_000.0,
        annual_other_consumption=0.0,
        n_children=0,
        index_tax_parameters_with_inflation=True,
    )
    res = run_simulation(cfg)
    first_year_total = 2.0 * 1_000.0
    second_year_increment = 2.0 * 1_010.0
    _check(
        abs(float(res.buy_pillar_3a[0, 0]) - first_year_total) < 1e-6,
        "Year-1 pillar-3a balance matches the indexed annual cap",
    )
    _check(
        abs(float(res.buy_pillar_3a[0, 1]) - (first_year_total + second_year_increment)) < 1e-6,
        "Year-2 pillar-3a balance uses the higher indexed cap",
    )


def test_voluntary_amortization_below_floor() -> None:
    print("[22] Voluntary amortization can reduce debt below the LTV floor")
    base_kwargs = dict(
        years=1,
        iterations=1,
        rng_seed=1,
        stock_growth_world_usd=0.0,
        chf_appreciation_vs_usd=0.0,
        stock_volatility=0.0,
        house_growth=0.0,
        house_volatility=0.0,
        inflation=0.0,
        salary_growth=0.0,
        portfolio_ter=0.0,
        pillar_3a_ter=0.0,
        n_children=0,
        annual_other_consumption=0.0,
    )
    cfg_off = SwissConfig(voluntary_amortization=False, **base_kwargs)
    cfg_on = SwissConfig(voluntary_amortization=True, **base_kwargs)
    res_off = run_simulation(cfg_off)
    res_on = run_simulation(cfg_on)

    start_debt = cfg_on.house_price - cfg_on.downpayment
    debt_off = float(res_off.debt[0, 0])
    debt_on = float(res_on.debt[0, 0])
    _check(abs(debt_off - start_debt) < 1e-6, "Without voluntary amortization, debt stays unchanged below the floor")
    _check(
        abs(debt_on - (start_debt - cfg_on.amortization_annual)) < 1e-6,
        "With voluntary amortization ON, debt falls by the configured annual amount below the floor",
    )
    _check(
        float(res_on.buy_surplus[0, 0]) < float(res_off.buy_surplus[0, 0]),
        "Voluntary amortization reduces the buyer's liquid surplus in that year",
    )


def test_indirect_amortization_via_3a() -> None:
    print("[23] Indirect amortization via pillar 3a keeps debt higher")
    base_kwargs = dict(
        years=1,
        iterations=1,
        rng_seed=1,
        stock_growth_world_usd=0.0,
        chf_appreciation_vs_usd=0.0,
        stock_volatility=0.0,
        house_growth=0.0,
        house_volatility=0.0,
        inflation=0.0,
        salary_growth=0.0,
        portfolio_ter=0.0,
        pillar_3a_ter=0.0,
        n_children=0,
        downpayment=400_000.0,
        annual_other_consumption=0.0,
    )
    cfg_direct = SwissConfig(amortization_strategy="direct", **base_kwargs)
    cfg_indirect = SwissConfig(amortization_strategy="indirect_3a", **base_kwargs)
    res_direct = run_simulation(cfg_direct)
    res_indirect = run_simulation(cfg_indirect)

    household_3a = 2.0 * cfg_direct.pillar_3a_annual_per_person
    required_amortization = min(
        cfg_direct.amortization_annual,
        (cfg_direct.house_price - cfg_direct.downpayment) - cfg_direct.house_price * cfg_direct.ltv_floor,
    )
    expected_direct_amortization = required_amortization - min(required_amortization, household_3a)

    direct_debt_end = float(res_direct.debt[0, 0])
    indirect_debt_end = float(res_indirect.debt[0, 0])
    _check(abs(direct_debt_end - ((cfg_direct.house_price - cfg_direct.downpayment) - required_amortization)) < 1e-6, "Direct amortization reduces debt by the full required amount")
    _check(abs(indirect_debt_end - ((cfg_indirect.house_price - cfg_indirect.downpayment) - expected_direct_amortization)) < 1e-6, "Indirect amortization only reduces debt by the direct-paydown remainder")
    _check(indirect_debt_end > direct_debt_end, "Indirect amortization keeps debt higher than direct amortization")
    _check(float(res_indirect.buy_surplus[0, 0]) > float(res_direct.buy_surplus[0, 0]), "Indirect amortization leaves more liquid surplus in year 1 than direct amortization")


def test_reproducibility() -> None:
    print("[24] Reproducibility with fixed seed")
    cfg_a = SwissConfig(iterations=200, years=10, rng_seed=42)
    cfg_b = SwissConfig(iterations=200, years=10, rng_seed=42)
    cfg_c = SwissConfig(iterations=200, years=10, rng_seed=43)
    res_a = run_simulation(cfg_a)
    res_b = run_simulation(cfg_b)
    res_c = run_simulation(cfg_c)
    _check(np.allclose(res_a.buy_terminal_liquid, res_b.buy_terminal_liquid), "Same seed => same buyer terminal wealth")
    _check(np.allclose(res_a.rent_terminal_liquid, res_b.rent_terminal_liquid), "Same seed => same renter terminal wealth")
    _check(not np.allclose(res_a.buy_terminal_liquid, res_c.buy_terminal_liquid), "Different seed => different paths")


def test_renter_path_is_independent_of_buyer_downpayment() -> None:
    print("[24a] Renter path is independent of buyer downpayment when initial wealth is fixed")
    common = dict(
        iterations=50,
        years=5,
        rng_seed=42,
        parallel_workers=1,
        initial_liquid_assets=700_000.0,
        house_price=1_000_000.0,
        buying_costs_pct=0.05,
    )
    low_downpayment = run_simulation(SwissConfig(**common, downpayment=200_000.0))
    high_downpayment = run_simulation(SwissConfig(**common, downpayment=400_000.0))
    _check(
        np.allclose(low_downpayment.rent_terminal_liquid, high_downpayment.rent_terminal_liquid)
        and np.allclose(low_downpayment.rent_portfolio, high_downpayment.rent_portfolio)
        and np.allclose(low_downpayment.rent_tax, high_downpayment.rent_tax),
        "Changing only the buyer downpayment leaves the renter path unchanged",
    )
    _check(
        not np.allclose(low_downpayment.debt, high_downpayment.debt),
        "Changing buyer downpayment still changes the buyer mortgage path",
    )


def test_mortgage_rate_floor_and_cap_do_not_affect_zero_volatility_rate_inside_range() -> None:
    print("[24aa] Mortgage-rate floor/cap do not affect a zero-volatility rate inside the range")
    common = dict(
        iterations=20,
        years=5,
        rng_seed=42,
        parallel_workers=1,
        interest_rate=0.02,
        mortgage_rate_volatility=0.0,
        stress_event_probability=0.0,
    )
    wide_bounds = run_simulation(
        SwissConfig(**common, mortgage_rate_min=0.0, mortgage_rate_max=0.10)
    )
    tight_bounds = run_simulation(
        SwissConfig(**common, mortgage_rate_min=0.01, mortgage_rate_max=0.03)
    )
    _check(
        np.allclose(wide_bounds.buy_terminal_liquid, tight_bounds.buy_terminal_liquid)
        and np.allclose(wide_bounds.rent_terminal_liquid, tight_bounds.rent_terminal_liquid)
        and np.allclose(wide_bounds.buy_tax, tight_bounds.buy_tax),
        "Changing mortgage-rate floor/cap leaves zero-volatility, no-stress paths unchanged when the rate is inside both ranges",
    )


def test_parallel_reproducibility_matches_serial() -> None:
    print("[24b] Parallel chunks preserve the serial fixed-seed result")
    base_kwargs = dict(iterations=203, years=10, rng_seed=42)
    res_serial = run_simulation(SwissConfig(parallel_workers=1, **base_kwargs))
    res_parallel = run_simulation(SwissConfig(parallel_workers=2, **base_kwargs))
    array_fields = (
        "buy_net_worth",
        "rent_net_worth",
        "buy_terminal_liquid",
        "rent_terminal_liquid",
        "buy_portfolio",
        "rent_portfolio",
        "buy_pillar_3a",
        "rent_pillar_3a",
        "house_val",
        "debt",
        "buy_tax",
        "rent_tax",
        "buy_surplus",
        "rent_surplus",
        "buy_rental_deposit",
        "buy_ruin_any",
        "rent_ruin_any",
        "buy_forced_sale_any",
        "inflation_rate",
        "inflation_index",
        "tax_index_factor",
    )
    for field in array_fields:
        serial_value = getattr(res_serial, field)
        parallel_value = getattr(res_parallel, field)
        if serial_value.dtype == bool:
            matches = np.array_equal(serial_value, parallel_value)
        else:
            matches = np.allclose(serial_value, parallel_value)
        _check(matches, f"Parallel {field} matches serial output")


def test_official_igi_schedule() -> None:
    print("[25] Official Vaud IGI schedule matches the published holding-period bands")
    official_points = {
        0: 0.30,
        1: 0.27,
        2: 0.24,
        5: 0.18,
        7: 0.16,
        9: 0.15,
        10: 0.14,
        12: 0.13,
        15: 0.12,
        18: 0.10,
        20: 0.09,
        24: 0.07,
    }
    for holding_years, expected_rate in official_points.items():
        actual_rate = vaud_igi_rate(holding_years, IGI_SCHEDULE)
        _check(
            abs(actual_rate - expected_rate) < 1e-12,
            f"IGI rate at {holding_years} completed years is {expected_rate:.0%}",
            detail=f"expected={expected_rate:.4f}, got={actual_rate:.4f}",
        )


def test_married_ifd_child_credit_is_applied() -> None:
    print("[26] Married federal tax uses the CHF 263 per-child reduction")
    cfg = SwissConfig(
        household_status="married",
        salary_total=100_000.0,
        salary_split=1.0,
        social_security_rate=0.0,
        n_children=1,
        fed_deduction_professional_flat=0.0,
        fed_deduction_transport=0.0,
        fed_deduction_meals=0.0,
        fed_deduction_insurance_married=0.0,
        fed_deduction_insurance_child_supplement=0.0,
        fed_deduction_childcare_per_child=0.0,
        fed_deduction_per_child=0.0,
        fed_deduction_married=0.0,
        fed_deduction_double_income_min=0.0,
        fed_deduction_double_income_max=0.0,
        cant_deduction_professional_rate=0.0,
        cant_deduction_professional_min=0.0,
        cant_deduction_professional_max=0.0,
        cant_deduction_transport=0.0,
        cant_deduction_meals=0.0,
        cant_deduction_insurance_married=0.0,
        cant_deduction_insurance_child_supplement=0.0,
        cant_deduction_childcare_per_child=0.0,
        cant_deduction_per_child=0.0,
        cant_deduction_double_income_min=0.0,
        cant_deduction_double_income_max=0.0,
    )
    res = VaudTaxEngine(cfg).calculate_household_tax(
        year=cfg.start_year,
        salary_total=cfg.salary_total,
        portfolio=0.0,
        house_val=0.0,
        debt=0.0,
        is_owner=False,
        pillar_3a_contribution_p1=0.0,
        pillar_3a_contribution_p2=0.0,
        market_rent_annual=0.0,
    )
    _check(
        abs(res.household.ifd - ifd_parental(100_000.0, 1)) < 1e-9,
        "Married households with a dependent child receive the CHF 263 federal tax reduction",
    )


def test_vaud_married_double_income_uses_2026_cap() -> None:
    print("[27] Married Vaud double-income deduction uses the CHF 1,700 2026 cap")
    cfg = SwissConfig(household_status="married")
    engine = VaudTaxEngine(cfg)
    deduction = engine._cantonal_double_income_deduction(cfg.start_year, 50_000.0, 60_000.0)
    _check(
        abs(deduction - 1_700.0) < 1e-9,
        "Vaud married double-income deduction is capped at CHF 1,700",
        detail=f"expected=1700.00, got={deduction:.2f}",
    )


def test_vaud_family_deduction_applies_in_married_mode() -> None:
    print("[28] Vaud family deduction reduces married taxable income")
    cfg = SwissConfig(
        household_status="married",
        salary_total=100_000.0,
        salary_split=1.0,
        social_security_rate=0.0,
        n_children=1,
        canton_multiplier=1.0,
        commune_multiplier=0.0,
        use_official_cantonal_income_tax_reduction_schedule=False,
        cantonal_income_tax_reduction_rate=0.0,
        fed_deduction_professional_flat=0.0,
        cant_deduction_professional_rate=0.0,
        cant_deduction_professional_min=0.0,
        cant_deduction_professional_max=0.0,
        fed_deduction_transport=0.0,
        cant_deduction_transport=0.0,
        fed_deduction_meals=0.0,
        cant_deduction_meals=0.0,
        fed_deduction_insurance_married=0.0,
        cant_deduction_insurance_married=0.0,
        fed_deduction_insurance_child_supplement=0.0,
        cant_deduction_insurance_child_supplement=0.0,
        fed_deduction_childcare_per_child=0.0,
        cant_deduction_childcare_per_child=0.0,
        fed_deduction_per_child=0.0,
        cant_deduction_per_child=0.0,
        fed_deduction_married=0.0,
        fed_deduction_double_income_min=0.0,
        fed_deduction_double_income_max=0.0,
        cant_deduction_double_income_min=0.0,
        cant_deduction_double_income_max=0.0,
    )
    res = VaudTaxEngine(cfg).calculate_household_tax(
        year=cfg.start_year,
        salary_total=cfg.salary_total,
        portfolio=0.0,
        house_val=0.0,
        debt=0.0,
        is_owner=False,
        pillar_3a_contribution_p1=0.0,
        pillar_3a_contribution_p2=0.0,
        market_rent_annual=0.0,
    )
    _check(
        abs(res.household.taxable_income_cant - 97_700.0) < 1e-9,
        "Married Vaud taxable income includes the code-725 family deduction",
        detail=f"expected=97700.00, got={res.household.taxable_income_cant:.2f}",
    )


def test_unmarried_vaud_child_cap_applies() -> None:
    print("[29] Separately taxed Vaud child quotient uses the official cap")
    cfg = SwissConfig(
        household_status="unmarried",
        salary_total=240_000.0,
        salary_split=1.0,
        social_security_rate=0.0,
        n_children=1,
        child_claimed_by_p1=True,
        child_deduction_split_to_p1=1.0,
        vaud_single_parent_household=False,
        vaud_child_quotient_share_to_p1=1.0,
        canton_multiplier=1.0,
        commune_multiplier=0.0,
        use_official_cantonal_income_tax_reduction_schedule=False,
        cantonal_income_tax_reduction_rate=0.0,
        fed_deduction_professional_flat=0.0,
        cant_deduction_professional_rate=0.0,
        cant_deduction_professional_min=0.0,
        cant_deduction_professional_max=0.0,
        fed_deduction_transport=0.0,
        cant_deduction_transport=0.0,
        fed_deduction_meals=0.0,
        cant_deduction_meals=0.0,
        fed_deduction_insurance_single=0.0,
        cant_deduction_insurance_single=0.0,
        fed_deduction_insurance_child_supplement=0.0,
        cant_deduction_insurance_child_supplement=0.0,
        fed_deduction_childcare_per_child=0.0,
        cant_deduction_childcare_per_child=0.0,
        fed_deduction_per_child=0.0,
        cant_deduction_per_child=0.0,
    )
    res = VaudTaxEngine(cfg).calculate_household_tax(
        year=cfg.start_year,
        salary_total=cfg.salary_total,
        portfolio=0.0,
        house_val=0.0,
        debt=0.0,
        is_owner=False,
        pillar_3a_contribution_p1=0.0,
        pillar_3a_contribution_p2=0.0,
        market_rent_annual=0.0,
    )
    expected_rate_income = np.floor((240_000.0 - 70_967.0) / 100.0) * 100.0
    expected_icc_income = vaud_icc_simple(expected_rate_income) * (240_000.0 / expected_rate_income)
    _check(
        abs(res.p1.icc_income - expected_icc_income) < 1e-9,
        "Separately taxed full-child-share cases use Vaud's capped quotient logic",
        detail=f"expected={expected_icc_income:.2f}, got={res.p1.icc_income:.2f}",
    )


def test_vaud_single_parent_uplift_is_not_double_counted() -> None:
    print("[30] Vaud single-parent uplift applies to only one separately taxed adult")
    cfg = SwissConfig(
        household_status="unmarried",
        salary_total=120_000.0,
        salary_split=0.5,
        social_security_rate=0.0,
        n_children=1,
        child_claimed_by_p1=True,
        child_deduction_split_to_p1=0.5,
        vaud_single_parent_household=True,
        vaud_child_quotient_share_to_p1=0.5,
        canton_multiplier=1.0,
        commune_multiplier=0.0,
        use_official_cantonal_income_tax_reduction_schedule=False,
        cantonal_income_tax_reduction_rate=0.0,
        fed_deduction_professional_flat=0.0,
        cant_deduction_professional_rate=0.0,
        cant_deduction_professional_min=0.0,
        cant_deduction_professional_max=0.0,
        fed_deduction_transport=0.0,
        cant_deduction_transport=0.0,
        fed_deduction_meals=0.0,
        cant_deduction_meals=0.0,
        fed_deduction_insurance_single=0.0,
        cant_deduction_insurance_single=0.0,
        fed_deduction_insurance_child_supplement=0.0,
        cant_deduction_insurance_child_supplement=0.0,
        fed_deduction_childcare_per_child=0.0,
        cant_deduction_childcare_per_child=0.0,
        fed_deduction_per_child=0.0,
        cant_deduction_per_child=0.0,
    )
    res = VaudTaxEngine(cfg).calculate_household_tax(
        year=cfg.start_year,
        salary_total=cfg.salary_total,
        portfolio=0.0,
        house_val=0.0,
        debt=0.0,
        is_owner=False,
        pillar_3a_contribution_p1=0.0,
        pillar_3a_contribution_p2=0.0,
        market_rent_annual=0.0,
    )
    _check(
        res.p1.icc_income < res.p2.icc_income,
        "Only the designated single-parent side gets Vaud's extra 0.3 part",
        detail=f"p1={res.p1.icc_income:.2f}, p2={res.p2.icc_income:.2f}",
    )


def test_indirect_amortization_credit_counts_toward_floor() -> None:
    print("[31] Indirect amortization credit eventually stops required direct paydown")
    cfg = SwissConfig(
        years=6,
        iterations=1,
        rng_seed=1,
        amortization_strategy="indirect_3a",
        stock_growth_world_usd=0.0,
        chf_appreciation_vs_usd=0.0,
        stock_volatility=0.0,
        house_growth=0.0,
        house_volatility=0.0,
        inflation=0.0,
        inflation_volatility=0.0,
        salary_growth=0.0,
        portfolio_ter=0.0,
        pillar_3a_ter=0.0,
        n_children=0,
        downpayment=400_000.0,
        annual_other_consumption=0.0,
    )
    res = run_simulation(cfg)
    debt_path = res.debt[0]
    _check(
        abs(float(debt_path[-1]) - float(debt_path[-2])) < 1e-6,
        "Once pledged 3a has satisfied the bank-required reduction, debt stops falling further",
        detail=f"last_two={float(debt_path[-2]):.2f}, {float(debt_path[-1]):.2f}",
    )
    _check(
        float(debt_path[-1]) > cfg.house_price * cfg.ltv_floor,
        "Indirect amortization can still leave the actual mortgage above the contractual floor",
    )


def test_voluntary_amortization_continues_after_crossing_floor() -> None:
    print("[32] Voluntary amortization continues below the floor after required paydown ends")
    cfg = SwissConfig(
        years=11,
        iterations=1,
        rng_seed=1,
        stock_growth_world_usd=0.0,
        chf_appreciation_vs_usd=0.0,
        stock_volatility=0.0,
        house_growth=0.0,
        house_volatility=0.0,
        inflation=0.0,
        inflation_volatility=0.0,
        salary_growth=0.0,
        portfolio_ter=0.0,
        pillar_3a_ter=0.0,
        n_children=0,
        downpayment=300_000.0,
        annual_other_consumption=0.0,
        voluntary_amortization=True,
        amortization_strategy="direct",
    )
    res = run_simulation(cfg)
    debt_path = res.debt[0]
    floor = cfg.house_price * cfg.ltv_floor
    _check(
        abs(float(debt_path[8]) - 970_000.0) < 1e-6,
        "Debt is still above the floor one year before the crossing year",
        detail=f"year9={float(debt_path[8]):.2f}, floor={floor:.2f}",
    )
    _check(
        abs(float(debt_path[9]) - floor) < 1e-6,
        "Required amortization trims debt exactly to the floor in the crossing year",
        detail=f"year10={float(debt_path[9]):.2f}, floor={floor:.2f}",
    )
    _check(
        abs(float(debt_path[10]) - (floor - cfg.amortization_annual)) < 1e-6,
        "With voluntary amortization ON, the next year continues below the floor by the configured annual amount",
        detail=f"year11={float(debt_path[10]):.2f}, floor_minus_amort={floor - cfg.amortization_annual:.2f}",
    )


def test_married_wealth_threshold_uses_the_2026_no_tax_floor() -> None:
    print("[33] Married wealth tax uses the CHF 120,000 no-tax threshold")
    cfg = SwissConfig(
        household_status="married",
        salary_total=0.0,
        social_security_rate=0.0,
        n_children=0,
        canton_multiplier=1.0,
        commune_multiplier=0.0,
        use_official_cantonal_income_tax_reduction_schedule=False,
        cantonal_income_tax_reduction_rate=0.0,
        index_tax_parameters_with_inflation=False,
        fed_deduction_professional_flat=0.0,
        cant_deduction_professional_rate=0.0,
        cant_deduction_professional_min=0.0,
        cant_deduction_professional_max=0.0,
        fed_deduction_transport=0.0,
        cant_deduction_transport=0.0,
        fed_deduction_meals=0.0,
        cant_deduction_meals=0.0,
        fed_deduction_insurance_married=0.0,
        cant_deduction_insurance_married=0.0,
        fed_deduction_married=0.0,
        fed_deduction_double_income_min=0.0,
        fed_deduction_double_income_max=0.0,
        cant_deduction_double_income_min=0.0,
        cant_deduction_double_income_max=0.0,
    )
    engine = VaudTaxEngine(cfg)
    below = engine.calculate_household_tax(
        year=cfg.start_year,
        salary_total=0.0,
        portfolio=100_000.0,
        house_val=0.0,
        debt=0.0,
        is_owner=False,
        pillar_3a_contribution_p1=0.0,
        pillar_3a_contribution_p2=0.0,
        market_rent_annual=0.0,
    )
    at_threshold = engine.calculate_household_tax(
        year=cfg.start_year,
        salary_total=0.0,
        portfolio=120_000.0,
        house_val=0.0,
        debt=0.0,
        is_owner=False,
        pillar_3a_contribution_p1=0.0,
        pillar_3a_contribution_p2=0.0,
        market_rent_annual=0.0,
    )
    _check(abs(below.household.icc_wealth) < 1e-9, "Married households below CHF 120,000 taxable wealth pay no Vaud wealth tax")
    _check(abs(at_threshold.household.icc_wealth - 108.85) < 1e-9, "The published Vaud wealth table starts applying at CHF 120,000 for married households")


def test_same_year_contributions_are_added_after_growth() -> None:
    print("[34] Same-year savings and 3a contributions are added after growth")
    common = dict(
        years=1,
        iterations=1,
        rng_seed=1,
        stock_growth_world_usd=0.10,
        chf_appreciation_vs_usd=0.0,
        stock_volatility=0.0,
        house_growth=0.0,
        house_volatility=0.0,
        inflation=0.0,
        salary_growth=0.0,
        portfolio_ter=0.0,
        pillar_3a_ter=0.0,
        n_children=0,
        house_price=1.0,
        initial_liquid_assets=1.0,
        downpayment=1.0,
        buying_costs_pct=0.0,
        sale_cost_pct=0.0,
        base_rent_monthly=0.0,
        house_market_rent_monthly=0.0,
        interest_rate=0.0,
        amortization_annual=0.0,
        maintenance_rate=0.0,
        dividend_yield=0.0,
        social_security_rate=0.0,
        fed_deduction_professional_flat=0.0,
        cant_deduction_professional_rate=0.0,
        cant_deduction_professional_min=0.0,
        cant_deduction_professional_max=0.0,
        fed_deduction_transport=0.0,
        cant_deduction_transport=0.0,
        fed_deduction_meals=0.0,
        cant_deduction_meals=0.0,
        fed_deduction_insurance_single=0.0,
        cant_deduction_insurance_single=0.0,
        canton_multiplier=0.0,
        commune_multiplier=0.0,
        communal_property_tax_rate=0.0,
    )
    cfg_cash = SwissConfig(
        **common,
        salary_total=100.0,
        salary_split=1.0,
        annual_other_consumption=0.0,
        pillar_3a_annual_per_person=0.0,
    )
    cash_res = run_simulation(cfg_cash)
    _check(
        abs(float(cash_res.buy_portfolio[0, 0]) - 100.0) < 1e-6,
        "Same-year liquid savings are added after growth instead of receiving a full year's return",
    )

    cfg_3a = SwissConfig(
        **common,
        salary_total=100.0,
        salary_split=1.0,
        annual_other_consumption=0.0,
        pillar_3a_annual_per_person=100.0,
        pillar_3a_withdrawal_tax_rate=0.0,
    )
    res_3a = run_simulation(cfg_3a)
    _check(
        abs(float(res_3a.buy_pillar_3a[0, 0]) - 100.0) < 1e-6,
        "Same-year pillar-3a contributions are added after growth instead of receiving a full year's return",
    )


def test_initial_pillar_3a_assets_are_separate_from_liquid_assets() -> None:
    print("[34a] Initial pillar 3a savings are modeled separately from liquid assets")
    cfg = SwissConfig(
        years=1,
        iterations=1,
        rng_seed=1,
        initial_liquid_assets=0.0,
        initial_pillar_3a_assets=100.0,
        salary_total=0.0,
        stock_growth_world_usd=0.10,
        chf_appreciation_vs_usd=0.0,
        stock_volatility=0.0,
        house_growth=0.0,
        house_volatility=0.0,
        inflation=0.0,
        inflation_volatility=0.0,
        salary_growth=0.0,
        salary_growth_volatility=0.0,
        rent_growth_volatility=0.0,
        mortgage_rate_volatility=0.0,
        stress_event_probability=0.0,
        portfolio_ter=0.0,
        pillar_3a_ter=0.0,
        pillar_3a_annual_per_person=0.0,
        pillar_3a_withdrawal_tax_rate=0.0,
        house_price=1.0,
        downpayment=0.0,
        buying_costs_pct=0.0,
        sale_cost_pct=0.0,
        base_rent_monthly=0.0,
        house_market_rent_monthly=0.0,
        annual_other_consumption=0.0,
        interest_rate=0.0,
        amortization_annual=0.0,
        maintenance_rate=0.0,
        dividend_yield=0.0,
        canton_multiplier=0.0,
        commune_multiplier=0.0,
        communal_property_tax_rate=0.0,
        use_official_cantonal_income_tax_reduction_schedule=False,
        cantonal_income_tax_reduction_rate=0.0,
        n_children=0,
        force_buy_sale_on_liquidity_crisis=False,
    )
    res = run_simulation(cfg)
    _check(
        abs(float(res.buy_pillar_3a[0, 0]) - 110.0) < 1e-6
        and abs(float(res.rent_pillar_3a[0, 0]) - 110.0) < 1e-6,
        "Opening pillar 3a grows as 3a wealth in both paths",
        detail=f"buy/rent 3a={res.buy_pillar_3a[0, 0]:.2f}/{res.rent_pillar_3a[0, 0]:.2f}",
    )
    _check(
        abs(float(res.rent_portfolio[0, 0])) < 1e-6,
        "Opening pillar 3a is not treated as the renter's taxable liquid portfolio",
        detail=f"rent liquid={res.rent_portfolio[0, 0]:.2f}",
    )


def test_initial_pillar_3a_can_help_pay_for_purchase() -> None:
    print("[34aa] Initial pillar 3a can help pay for the buyer purchase")
    cfg = SwissConfig(
        years=1,
        iterations=1,
        rng_seed=1,
        initial_liquid_assets=40.0,
        initial_pillar_3a_assets=100.0,
        pillar_3a_withdrawal_tax_rate=0.08,
        salary_total=0.0,
        stock_growth_world_usd=0.0,
        chf_appreciation_vs_usd=0.0,
        stock_volatility=0.0,
        house_growth=0.0,
        house_volatility=0.0,
        inflation=0.0,
        inflation_volatility=0.0,
        salary_growth=0.0,
        salary_growth_volatility=0.0,
        rent_growth_volatility=0.0,
        mortgage_rate_volatility=0.0,
        stress_event_probability=0.0,
        portfolio_ter=0.0,
        pillar_3a_ter=0.0,
        pillar_3a_annual_per_person=0.0,
        house_price=100.0,
        downpayment=86.0,
        buying_costs_pct=0.0,
        sale_cost_pct=0.0,
        base_rent_monthly=0.0,
        house_market_rent_monthly=0.0,
        annual_other_consumption=0.0,
        interest_rate=0.0,
        amortization_annual=0.0,
        maintenance_rate=0.0,
        dividend_yield=0.0,
        canton_multiplier=0.0,
        commune_multiplier=0.0,
        communal_property_tax_rate=0.0,
        use_official_cantonal_income_tax_reduction_schedule=False,
        cantonal_income_tax_reduction_rate=0.0,
        n_children=0,
        force_buy_sale_on_liquidity_crisis=False,
    )
    res = run_simulation(cfg)
    _check(
        abs(float(res.buy_portfolio[0, 0])) < 1e-6
        and abs(float(res.buy_pillar_3a[0, 0]) - 50.0) < 1e-6,
        "Buyer uses enough starting 3a to pay for the purchase after estimated withdrawal tax",
        detail=(
            f"buy liquid/3a={float(res.buy_portfolio[0, 0]):.2f}/"
            f"{float(res.buy_pillar_3a[0, 0]):.2f}"
        ),
    )
    _check(
        abs(float(res.rent_portfolio[0, 0]) - 40.0) < 1e-6
        and abs(float(res.rent_pillar_3a[0, 0]) - 100.0) < 1e-6,
        "Renter keeps both the cash/taxable investments and starting 3a savings",
        detail=(
            f"rent liquid/3a={float(res.rent_portfolio[0, 0]):.2f}/"
            f"{float(res.rent_pillar_3a[0, 0]):.2f}"
        ),
    )


def test_pillar_3a_contributions_are_capped_by_available_cash() -> None:
    print("[34b] Pillar 3a contributions stop at what the path can actually afford")
    cfg = SwissConfig(
        years=1,
        iterations=1,
        rng_seed=1,
        salary_total=1.0,
        salary_split=1.0,
        social_security_rate=0.0,
        stock_growth_world_usd=0.0,
        chf_appreciation_vs_usd=0.0,
        stock_volatility=0.0,
        house_growth=0.0,
        house_volatility=0.0,
        inflation=0.0,
        inflation_volatility=0.0,
        salary_growth=0.0,
        salary_growth_volatility=0.0,
        rent_growth_volatility=0.0,
        mortgage_rate_volatility=0.0,
        stress_event_probability=0.0,
        portfolio_ter=0.0,
        pillar_3a_ter=0.0,
        pillar_3a_annual_per_person=100.0,
        pillar_3a_withdrawal_tax_rate=0.0,
        house_price=1.0,
        initial_liquid_assets=0.0,
        downpayment=0.0,
        buying_costs_pct=0.0,
        sale_cost_pct=0.0,
        base_rent_monthly=0.0,
        house_market_rent_monthly=0.0,
        annual_other_consumption=0.0,
        interest_rate=0.0,
        amortization_annual=0.0,
        maintenance_rate=0.0,
        dividend_yield=0.0,
        canton_multiplier=0.0,
        commune_multiplier=0.0,
        communal_property_tax_rate=0.0,
        use_official_cantonal_income_tax_reduction_schedule=False,
        cantonal_income_tax_reduction_rate=0.0,
        n_children=0,
        force_buy_sale_on_liquidity_crisis=False,
    )
    res = run_simulation(cfg)
    _check(
        abs(float(res.buy_pillar_3a[0, 0]) - 1.0) < 1e-6
        and abs(float(res.rent_pillar_3a[0, 0]) - 1.0) < 1e-6,
        "The simulator scales 3a contributions down to the cash the path can really fund",
        detail=f"buy/rent 3a={res.buy_pillar_3a[0, 0]:.2f}/{res.rent_pillar_3a[0, 0]:.2f}",
    )
    _check(
        abs(float(res.buy_portfolio[0, 0])) < 1e-6
        and abs(float(res.rent_portfolio[0, 0])) < 1e-6,
        "Affordability-capped 3a contributions no longer create a fake negative cash balance",
        detail=f"buy/rent liquid={res.buy_portfolio[0, 0]:.2f}/{res.rent_portfolio[0, 0]:.2f}",
    )


def test_negative_liquidity_reduces_taxable_wealth() -> None:
    print("[35] Negative liquid balances reduce taxable wealth in later tax years")
    cfg = SwissConfig(
        years=2,
        iterations=1,
        rng_seed=1,
        salary_total=0.0,
        stock_growth_world_usd=0.0,
        chf_appreciation_vs_usd=0.0,
        stock_volatility=0.0,
        house_growth=0.0,
        house_volatility=0.0,
        salary_growth_volatility=0.0,
        rent_growth_volatility=0.0,
        mortgage_rate_volatility=0.0,
        stress_event_probability=0.0,
        inflation=0.0,
        inflation_volatility=0.0,
        salary_growth=0.0,
        portfolio_ter=0.0,
        pillar_3a_ter=0.0,
        annual_other_consumption=1_000_000.0,
        interest_rate=0.0,
        amortization_annual=0.0,
        n_children=0,
        communal_property_tax_rate=0.0,
        force_buy_sale_on_liquidity_crisis=False,
    )
    res = run_simulation(cfg)
    expected = VaudTaxEngine(cfg).calculate_household_tax(
        year=cfg.start_year + 1,
        salary_total=0.0,
        portfolio=float(res.buy_portfolio[0, 0]),
        house_val=float(res.house_val[0, 0]),
        debt=float(res.debt[0, 0]),
        is_owner=True,
        pillar_3a_contribution_p1=0.0,
        pillar_3a_contribution_p2=0.0,
        market_rent_annual=cfg.house_market_rent_monthly * 12.0,
    ).total
    _check(
        abs(float(res.buy_tax[0, 1]) - expected) < 1e-6,
        "Later-year taxes use the negative liquid balance as a wealth offset instead of clipping it away",
    )


def test_buyer_forced_sale_after_liquidity_crisis() -> None:
    print("[36] Buyer path can force a home sale after a severe liquidity crisis")
    cfg = SwissConfig(
        years=2,
        iterations=1,
        rng_seed=1,
        salary_total=0.0,
        stock_growth_world_usd=0.0,
        chf_appreciation_vs_usd=0.0,
        stock_volatility=0.0,
        house_growth=0.0,
        house_volatility=0.0,
        salary_growth_volatility=0.0,
        rent_growth_volatility=0.0,
        mortgage_rate_volatility=0.0,
        stress_event_probability=0.0,
        inflation=0.0,
        inflation_volatility=0.0,
        salary_growth=0.0,
        portfolio_ter=0.0,
        pillar_3a_ter=0.0,
        annual_other_consumption=1_000_000.0,
        interest_rate=0.0,
        amortization_annual=0.0,
        sale_cost_pct=0.0,
        buying_costs_pct=0.0,
        n_children=0,
        liquidity_crisis_buffer_months=0.0,
        force_buy_sale_on_liquidity_crisis=True,
    )
    res = run_simulation(cfg)
    _check(bool(res.buy_forced_sale_any[0]), "A severe buyer liquidity crisis triggers a forced sale when that safeguard is enabled")
    _check(abs(float(res.house_val[0, 0])) < 1e-9 and abs(float(res.debt[0, 0])) < 1e-9, "The house and mortgage disappear from the buyer path after the forced sale")
    _check(abs(float(res.house_val[0, 1])) < 1e-9 and abs(float(res.debt[0, 1])) < 1e-9, "Once sold, the buyer path stays out of owner-occupied housing")


def test_buyer_rent_switches_to_market_rent_after_forced_sale() -> None:
    print("[37] After a forced sale, the buyer path re-rents from the market-rent baseline")
    cfg = SwissConfig(
        years=2,
        iterations=1,
        rng_seed=1,
        salary_total=0.0,
        social_security_rate=0.0,
        stock_growth_world_usd=0.0,
        chf_appreciation_vs_usd=0.0,
        stock_volatility=0.0,
        house_growth=0.0,
        house_volatility=0.0,
        inflation=0.0,
        inflation_volatility=0.0,
        salary_growth=0.0,
        salary_growth_volatility=0.0,
        rent_growth_volatility=0.0,
        mortgage_rate_volatility=0.0,
        stress_event_probability=0.0,
        portfolio_ter=0.0,
        pillar_3a_ter=0.0,
        base_rent_monthly=1_000.0,
        house_market_rent_monthly=2_000.0,
        annual_other_consumption=0.0,
        interest_rate=0.05,
        amortization_annual=0.0,
        maintenance_rate=0.0,
        sale_cost_pct=0.0,
        buying_costs_pct=0.0,
        initial_liquid_assets=600_000.0,
        dividend_yield=0.0,
        pillar_3a_annual_per_person=0.0,
        n_children=0,
        liquidity_crisis_buffer_months=0.0,
        force_buy_sale_on_liquidity_crisis=True,
        canton_multiplier=0.0,
        commune_multiplier=0.0,
        use_official_cantonal_income_tax_reduction_schedule=False,
        cantonal_income_tax_reduction_rate=0.0,
    )
    res = run_simulation(cfg)
    _check(bool(res.buy_forced_sale_any[0]), "This scenario triggers a forced sale in year 1")
    _check(
        abs(float(res.buy_surplus[0, 1]) + 24_000.0) < 1e-6,
        "After a forced sale, the buyer path uses the modeled market rent rather than the renter path's old lease rent",
    )


def test_market_rent_can_grow_above_inflation() -> None:
    print("[37a] Market rent can grow above inflation independently of current contract rent")
    cfg = SwissConfig(
        years=2,
        iterations=1,
        rng_seed=1,
        salary_total=0.0,
        social_security_rate=0.0,
        stock_growth_world_usd=0.0,
        chf_appreciation_vs_usd=0.0,
        stock_volatility=0.0,
        house_growth=0.0,
        house_volatility=0.0,
        inflation=0.0,
        inflation_volatility=0.0,
        salary_growth=0.0,
        salary_growth_volatility=0.0,
        market_rent_real_growth=0.10,
        rent_growth_volatility=0.0,
        mortgage_rate_volatility=0.0,
        stress_event_probability=0.0,
        portfolio_ter=0.0,
        pillar_3a_ter=0.0,
        base_rent_monthly=1_000.0,
        house_market_rent_monthly=2_000.0,
        annual_other_consumption=0.0,
        interest_rate=0.05,
        amortization_annual=0.0,
        maintenance_rate=0.0,
        sale_cost_pct=0.0,
        buying_costs_pct=0.0,
        initial_liquid_assets=600_000.0,
        dividend_yield=0.0,
        pillar_3a_annual_per_person=0.0,
        n_children=0,
        liquidity_crisis_buffer_months=0.0,
        force_buy_sale_on_liquidity_crisis=True,
        canton_multiplier=0.0,
        commune_multiplier=0.0,
        use_official_cantonal_income_tax_reduction_schedule=False,
        cantonal_income_tax_reduction_rate=0.0,
    )
    res = run_simulation(cfg)
    _check(bool(res.buy_forced_sale_any[0]), "This scenario triggers a forced sale in year 1")
    _check(
        abs(float(res.buy_surplus[0, 1]) + 26_400.0) < 1e-6,
        "After a forced sale, the buyer's new market rent can grow above inflation",
    )


def test_stress_salary_hit_stays_one_year_wide() -> None:
    print("[38] Repeated stress years cut salary each year without shrinking the future salary base")
    cfg = SwissConfig(
        years=2,
        iterations=1,
        rng_seed=1,
        salary_total=100.0,
        social_security_rate=0.0,
        stock_growth_world_usd=0.0,
        chf_appreciation_vs_usd=0.0,
        stock_volatility=0.0,
        house_growth=0.0,
        house_volatility=0.0,
        inflation=0.0,
        inflation_volatility=0.0,
        salary_growth=0.0,
        salary_growth_volatility=0.0,
        rent_growth_volatility=0.0,
        mortgage_rate_volatility=0.0,
        stress_event_probability=1.0,
        stress_salary_hit=0.50,
        annual_other_consumption=0.0,
        base_rent_monthly=0.0,
        house_market_rent_monthly=0.0,
        house_price=1.0,
        downpayment=1.0,
        buying_costs_pct=0.0,
        sale_cost_pct=0.0,
        interest_rate=0.0,
        amortization_annual=0.0,
        maintenance_rate=0.0,
        dividend_yield=0.0,
        pillar_3a_annual_per_person=0.0,
        portfolio_ter=0.0,
        pillar_3a_ter=0.0,
        canton_multiplier=0.0,
        commune_multiplier=0.0,
        use_official_cantonal_income_tax_reduction_schedule=False,
        cantonal_income_tax_reduction_rate=0.0,
        n_children=0,
    )
    res = run_simulation(cfg)
    _check(
        abs(float(res.rent_surplus[0, 1]) - 50.0) < 1e-6,
        "A 50% stress salary hit applies to each stress year itself without permanently shrinking later salary levels",
    )


def test_stress_rent_jump_stays_one_year_wide() -> None:
    print("[39] Repeated stress years raise rent each year without compounding the lease base")
    cfg = SwissConfig(
        years=2,
        iterations=1,
        rng_seed=1,
        salary_total=0.0,
        social_security_rate=0.0,
        stock_growth_world_usd=0.0,
        chf_appreciation_vs_usd=0.0,
        stock_volatility=0.0,
        house_growth=0.0,
        house_volatility=0.0,
        inflation=0.0,
        inflation_volatility=0.0,
        salary_growth=0.0,
        salary_growth_volatility=0.0,
        rent_growth_volatility=0.0,
        mortgage_rate_volatility=0.0,
        stress_event_probability=1.0,
        stress_rent_jump=0.10,
        interest_rate=0.0125,
        mortgage_rate_min=0.0125,
        mortgage_rate_max=0.0125,
        rent_reference_rate_current=0.0125,
        rent_reference_rate_smoothing=1.0,
        rent_cpi_passthrough=0.0,
        annual_other_consumption=0.0,
        base_rent_monthly=1_000.0,
        house_market_rent_monthly=1_000.0,
        house_price=1.0,
        downpayment=0.0,
        buying_costs_pct=0.0,
        sale_cost_pct=0.0,
        maintenance_rate=0.0,
        amortization_annual=0.0,
        dividend_yield=0.0,
        pillar_3a_annual_per_person=0.0,
        portfolio_ter=0.0,
        pillar_3a_ter=0.0,
        canton_multiplier=0.0,
        commune_multiplier=0.0,
        use_official_cantonal_income_tax_reduction_schedule=False,
        cantonal_income_tax_reduction_rate=0.0,
        n_children=0,
    )
    res = run_simulation(cfg)
    _check(
        abs(float(res.rent_surplus[0, 1]) + 13_200.0) < 1e-6,
        "A 10% stress rent jump affects each stress year itself without ratcheting up the next year's base lease rent",
    )


def test_separate_pillar_3a_process_can_diverge_from_taxable_portfolio() -> None:
    print("[40] Pillar 3a can use a separate return process")
    cfg = SwissConfig(
        years=2,
        iterations=1,
        rng_seed=1,
        stock_growth_world_usd=0.0,
        chf_appreciation_vs_usd=0.0,
        stock_volatility=0.0,
        house_growth=0.0,
        house_volatility=0.0,
        inflation_volatility=0.0,
        salary_growth_volatility=0.0,
        rent_growth_volatility=0.0,
        mortgage_rate_volatility=0.0,
        stress_event_probability=0.0,
        inflation=0.0,
        salary_growth=0.0,
        portfolio_ter=0.0,
        pillar_3a_ter=0.0,
        pillar_3a_growth_chf=0.10,
        pillar_3a_volatility=0.0,
        pillar_3a_correlation_to_portfolio=0.0,
        pillar_3a_annual_per_person=100.0,
        salary_total=100_000.0,
        salary_split=1.0,
        annual_other_consumption=0.0,
        house_price=1.0,
        downpayment=1.0,
        buying_costs_pct=0.0,
        sale_cost_pct=0.0,
        base_rent_monthly=0.0,
        house_market_rent_monthly=0.0,
        interest_rate=0.0,
        amortization_annual=0.0,
        maintenance_rate=0.0,
        dividend_yield=0.0,
        social_security_rate=0.0,
        n_children=0,
        pillar_3a_withdrawal_tax_rate=0.0,
    )
    res = run_simulation(cfg)
    _check(
        abs(float(res.buy_pillar_3a[0, 1]) - 210.0) < 1e-6,
        "A custom pillar-3a process can grow differently from the taxable portfolio path",
    )


def test_non_affiliated_worker_uses_20pct_3a_rule() -> None:
    print("[40b] A non-affiliated worker uses the 20%-of-earned-income 3a rule")
    cfg = SwissConfig(
        years=1,
        iterations=1,
        rng_seed=1,
        stock_growth_world_usd=0.0,
        chf_appreciation_vs_usd=0.0,
        stock_volatility=0.0,
        house_growth=0.0,
        house_volatility=0.0,
        inflation_volatility=0.0,
        salary_growth_volatility=0.0,
        rent_growth_volatility=0.0,
        mortgage_rate_volatility=0.0,
        stress_event_probability=0.0,
        inflation=0.0,
        salary_growth=0.0,
        portfolio_ter=0.0,
        pillar_3a_ter=0.0,
        pillar_3a_annual_per_person=7_258.0,
        pillar_3a_unaffiliated_rate=0.20,
        pillar_3a_unaffiliated_max=36_288.0,
        salary_total=1_000.0,
        salary_split=1.0,
        p1_pillar2_affiliated=False,
        p2_pillar2_affiliated=False,
        annual_other_consumption=0.0,
        house_price=1.0,
        downpayment=1.0,
        buying_costs_pct=0.0,
        sale_cost_pct=0.0,
        base_rent_monthly=0.0,
        house_market_rent_monthly=0.0,
        interest_rate=0.0,
        amortization_annual=0.0,
        maintenance_rate=0.0,
        dividend_yield=0.0,
        social_security_rate=0.0,
        n_children=0,
        pillar_3a_withdrawal_tax_rate=0.0,
    )
    res = run_simulation(cfg)
    _check(
        abs(float(res.buy_pillar_3a[0, 0]) - 200.0) < 1e-6,
        "A non-affiliated worker uses the Swiss 20%-of-earned-income rule instead of the full employee cap",
    )


def test_swiss_contract_rent_stays_flat_when_reference_rate_is_unchanged() -> None:
    print("[41] Swiss contract rent can stay flat even when general inflation is positive")
    cfg = SwissConfig(
        years=2,
        iterations=1,
        rng_seed=1,
        salary_total=0.0,
        social_security_rate=0.0,
        stock_growth_world_usd=0.0,
        chf_appreciation_vs_usd=0.0,
        stock_volatility=0.0,
        house_growth=0.0,
        house_volatility=0.0,
        inflation=0.03,
        inflation_volatility=0.0,
        salary_growth=0.0,
        salary_growth_volatility=0.0,
        rent_growth_volatility=0.0,
        mortgage_rate_volatility=0.0,
        interest_rate=0.0125,
        mortgage_rate_min=0.0125,
        mortgage_rate_max=0.0125,
        rent_reference_rate_current=0.0125,
        rent_reference_rate_smoothing=1.0,
        rent_cpi_passthrough=0.0,
        annual_other_consumption=0.0,
        base_rent_monthly=1_000.0,
        house_market_rent_monthly=1_000.0,
        house_price=1.0,
        downpayment=0.0,
        buying_costs_pct=0.0,
        sale_cost_pct=0.0,
        maintenance_rate=0.0,
        amortization_annual=0.0,
        dividend_yield=0.0,
        pillar_3a_annual_per_person=0.0,
        portfolio_ter=0.0,
        pillar_3a_ter=0.0,
        canton_multiplier=0.0,
        commune_multiplier=0.0,
        use_official_cantonal_income_tax_reduction_schedule=False,
        cantonal_income_tax_reduction_rate=0.0,
        n_children=0,
    )
    res = run_simulation(cfg)
    _check(
        abs(float(res.rent_surplus[0, 1]) + 12_000.0) < 1e-6,
        "With no reference-rate step and no inflation pass-through, contract rent stays flat despite positive inflation",
    )


def test_swiss_contract_rent_can_step_up_with_reference_rate() -> None:
    print("[42] Swiss contract rent can rise when the reference rate steps up")
    cfg = SwissConfig(
        years=2,
        iterations=1,
        rng_seed=1,
        salary_total=0.0,
        social_security_rate=0.0,
        stock_growth_world_usd=0.0,
        chf_appreciation_vs_usd=0.0,
        stock_volatility=0.0,
        house_growth=0.0,
        house_volatility=0.0,
        inflation=0.03,
        inflation_volatility=0.0,
        salary_growth=0.0,
        salary_growth_volatility=0.0,
        rent_growth_volatility=0.0,
        mortgage_rate_volatility=0.0,
        interest_rate=0.015,
        mortgage_rate_min=0.015,
        mortgage_rate_max=0.015,
        rent_reference_rate_current=0.0125,
        rent_reference_rate_smoothing=1.0,
        rent_cpi_passthrough=0.0,
        annual_other_consumption=0.0,
        base_rent_monthly=1_000.0,
        house_market_rent_monthly=1_000.0,
        house_price=1.0,
        downpayment=0.0,
        buying_costs_pct=0.0,
        sale_cost_pct=0.0,
        maintenance_rate=0.0,
        amortization_annual=0.0,
        dividend_yield=0.0,
        pillar_3a_annual_per_person=0.0,
        portfolio_ter=0.0,
        pillar_3a_ter=0.0,
        canton_multiplier=0.0,
        commune_multiplier=0.0,
        use_official_cantonal_income_tax_reduction_schedule=False,
        cantonal_income_tax_reduction_rate=0.0,
        n_children=0,
    )
    res = run_simulation(cfg)
    _check(
        abs(float(res.rent_surplus[0, 1]) + 12_360.0) < 1e-6,
        "A 0.25-point reference-rate step can raise the next year's contract rent by 3%",
    )


def test_stochastic_inflation_indexes_tax_caps_from_the_realized_path() -> None:
    print("[43] Stochastic inflation can move tax-law CHF caps using the realized inflation path")
    cfg = SwissConfig(
        years=2,
        iterations=1,
        rng_seed=7,
        stock_growth_world_usd=0.0,
        chf_appreciation_vs_usd=0.0,
        stock_volatility=0.0,
        house_growth=0.0,
        house_volatility=0.0,
        inflation=0.01,
        inflation_volatility=0.03,
        inflation_min=-0.02,
        inflation_max=0.08,
        salary_growth=0.0,
        salary_growth_volatility=0.0,
        rent_growth_volatility=0.0,
        mortgage_rate_volatility=0.0,
        stress_event_probability=0.0,
        portfolio_ter=0.0,
        pillar_3a_ter=0.0,
        pillar_3a_annual_per_person=1_000.0,
        annual_other_consumption=0.0,
        n_children=0,
        index_tax_parameters_with_inflation=True,
    )
    res = run_simulation(cfg)
    realized_inflation_year1 = float(res.inflation_rate[0, 0])
    expected_year2_factor = 1.0 + max(0.0, realized_inflation_year1)
    expected_year2_total = 2.0 * cfg.pillar_3a_annual_per_person * (1.0 + expected_year2_factor)
    _check(
        abs(float(res.tax_index_factor[0, 1]) - expected_year2_factor) < 1e-9,
        "Year-2 tax indexing uses the realized year-1 inflation path rather than the baseline inflation input",
    )
    _check(
        abs(float(res.buy_pillar_3a[0, 1]) - expected_year2_total) < 1e-6,
        "The indexed pillar-3a cap follows the realized inflation path in later years",
    )


def test_owner_tax_uses_the_simulated_mortgage_rate() -> None:
    print("[44] Owner tax deductions use the simulated mortgage rate")
    cfg = SwissConfig(
        years=1,
        iterations=1,
        rng_seed=1,
        household_status="married",
        salary_total=200_000.0,
        salary_split=0.5,
        stock_growth_world_usd=0.0,
        chf_appreciation_vs_usd=0.0,
        stock_volatility=0.0,
        house_growth=0.0,
        house_volatility=0.0,
        inflation=0.0,
        inflation_volatility=0.0,
        salary_growth=0.0,
        salary_growth_volatility=0.0,
        rent_growth_volatility=0.0,
        mortgage_rate_volatility=0.0,
        mortgage_rate_min=0.05,
        mortgage_rate_max=0.05,
        interest_rate=0.05,
        stress_event_probability=0.0,
        portfolio_ter=0.0,
        pillar_3a_ter=0.0,
        dividend_yield=0.0,
        annual_other_consumption=0.0,
        maintenance_rate=0.0,
        n_children=0,
        communal_property_tax_rate=0.0,
    )
    res = run_simulation(cfg)
    expected_pre_tax_portfolio = (
        cfg.salary_total * (1.0 - cfg.social_security_rate)
        - 2.0 * cfg.pillar_3a_annual_per_person
        - (cfg.house_price - cfg.downpayment) * 0.05
    )
    expected = VaudTaxEngine(cfg).calculate_household_tax(
        year=cfg.start_year,
        salary_total=cfg.salary_total,
        portfolio=0.0,
        house_val=cfg.house_price,
        debt=cfg.house_price - cfg.downpayment,
        is_owner=True,
        pillar_3a_contribution_p1=cfg.pillar_3a_annual_per_person,
        pillar_3a_contribution_p2=cfg.pillar_3a_annual_per_person,
        market_rent_annual=cfg.house_market_rent_monthly * 12.0,
        interest_rate_override=0.05,
        wealth_portfolio=expected_pre_tax_portfolio,
        wealth_house_val=cfg.house_price,
        wealth_debt=cfg.house_price - cfg.downpayment,
    ).total
    _check(
        abs(float(res.buy_tax[0, 0]) - expected) < 1e-6,
        "Owner tax calculations follow the actual simulated mortgage rate instead of the fixed config baseline",
    )


def test_private_interest_deduction_is_capped_before_2029() -> None:
    print("[45] Pre-2029 private debt interest is capped before deduction")
    cfg = SwissConfig(
        household_status="unmarried",
        salary_total=200_000.0,
        salary_split=1.0,
        ownership_split=1.0,
        social_security_rate=0.0,
        n_children=0,
        house_price=1_000_000.0,
        downpayment=100_000.0,
        interest_rate=0.10,
        maintenance_deduction_rate_federal=0.0,
        maintenance_deduction_rate_cantonal=0.0,
        vl_factor_federal=0.60,
        vl_factor_cantonal=0.65,
        fed_deduction_professional_flat=0.0,
        cant_deduction_professional_rate=0.0,
        cant_deduction_professional_min=0.0,
        cant_deduction_professional_max=0.0,
        fed_deduction_transport=0.0,
        cant_deduction_transport=0.0,
        fed_deduction_meals=0.0,
        cant_deduction_meals=0.0,
        fed_deduction_insurance_single=0.0,
        fed_deduction_insurance_single_without_pillars=0.0,
        cant_deduction_insurance_single=0.0,
    )
    market_rent = 20_000.0
    res = VaudTaxEngine(cfg).calculate_household_tax(
        year=cfg.start_year,
        salary_total=cfg.salary_total,
        portfolio=0.0,
        house_val=cfg.house_price,
        debt=cfg.house_price - cfg.downpayment,
        is_owner=True,
        pillar_3a_contribution_p1=0.0,
        pillar_3a_contribution_p2=0.0,
        market_rent_annual=market_rent,
    )
    expected_fed_interest_deduction = 50_000.0 + market_rent * cfg.vl_factor_federal
    expected_cant_interest_deduction = 50_000.0 + market_rent * cfg.vl_factor_cantonal
    expected_taxable_fed = np.floor(
        (cfg.salary_total + market_rent * cfg.vl_factor_federal - expected_fed_interest_deduction)
        / 100.0
    ) * 100.0
    expected_taxable_cant = np.floor(
        (cfg.salary_total + market_rent * cfg.vl_factor_cantonal - expected_cant_interest_deduction)
        / 100.0
    ) * 100.0
    _check(
        abs(res.p1.taxable_income_fed - expected_taxable_fed) < 1e-9,
        "Federal taxable income uses the capped private-interest deduction before 2029",
    )
    _check(
        abs(res.p1.taxable_income_cant - expected_taxable_cant) < 1e-9,
        "Cantonal taxable income also uses the capped private-interest deduction before 2029",
    )


def test_communal_property_tax_is_modeled_separately() -> None:
    print("[46] Commune property tax is added separately to buyer taxes")
    cfg = SwissConfig(
        years=1,
        iterations=1,
        rng_seed=1,
        salary_total=0.0,
        stock_growth_world_usd=0.0,
        chf_appreciation_vs_usd=0.0,
        stock_volatility=0.0,
        house_growth=0.0,
        house_volatility=0.0,
        inflation=0.0,
        inflation_volatility=0.0,
        salary_growth=0.0,
        salary_growth_volatility=0.0,
        rent_growth_volatility=0.0,
        mortgage_rate_volatility=0.0,
        stress_event_probability=0.0,
        portfolio_ter=0.0,
        pillar_3a_ter=0.0,
        annual_other_consumption=0.0,
        base_rent_monthly=0.0,
        house_market_rent_monthly=0.0,
        interest_rate=0.0,
        amortization_annual=0.0,
        maintenance_rate=0.0,
        dividend_yield=0.0,
        n_children=0,
        canton_multiplier=0.0,
        commune_multiplier=0.0,
        communal_property_tax_rate=0.0010,
        wealth_tax_value_ratio=0.50,
        property_tax_value_ratio=0.75,
        force_buy_sale_on_liquidity_crisis=False,
        fed_deduction_insurance_single_without_pillars=0.0,
    )
    res = run_simulation(cfg)
    expected = cfg.house_price * cfg.property_tax_value_ratio * cfg.communal_property_tax_rate
    _check(
        abs(float(res.buy_tax[0, 0]) - expected) < 1e-6,
        "Buyer taxes include the separate commune-level impôt foncier",
        detail=f"expected={expected:.2f}, got={float(res.buy_tax[0, 0]):.2f}",
    )


def test_negative_inflation_does_not_reduce_tax_indexing() -> None:
    print("[47] Negative inflation does not push tax-law CHF amounts downward")
    cfg = SwissConfig(
        years=2,
        iterations=1,
        rng_seed=1,
        stock_growth_world_usd=0.0,
        chf_appreciation_vs_usd=0.0,
        stock_volatility=0.0,
        house_growth=0.0,
        house_volatility=0.0,
        inflation=-0.01,
        inflation_volatility=0.0,
        salary_growth=0.0,
        salary_growth_volatility=0.0,
        rent_growth_volatility=0.0,
        mortgage_rate_volatility=0.0,
        stress_event_probability=0.0,
        portfolio_ter=0.0,
        pillar_3a_ter=0.0,
        n_children=0,
        index_tax_parameters_with_inflation=True,
    )
    res = run_simulation(cfg)
    _check(
        abs(cfg.tax_parameter_index_factor(cfg.start_year + 1) - 1.0) < 1e-12,
        "The config layer does not lower indexed tax-law amounts under negative inflation",
    )
    _check(
        abs(float(res.tax_index_factor[0, 1]) - 1.0) < 1e-12,
        "The simulator also keeps the indexed tax-law factor flat when inflation is negative",
    )


def test_official_vd_commune_table_contains_lausanne_defaults() -> None:
    print("[48] Official 2026 Vaud commune table includes Lausanne with the shipped defaults")
    rows = load_vaud_communes_2026()
    lausanne = get_vaud_commune("Lausanne")
    _check(len(rows) == 300, "The bundled 2026 Vaud commune table has 300 communes")
    _check(
        abs(lausanne.commune_multiplier - 0.785) < 1e-12,
        "Lausanne uses the official 78.5% total commune coefficient",
    )
    _check(
        abs(lausanne.communal_property_tax_rate - 0.0015) < 1e-12,
        "Lausanne uses the official 1.5‰ commune property-tax rate",
    )


def test_vd_commune_table_uses_total_pct_when_special_tax_exists() -> None:
    print("[49] Commune selector data uses the published total percentage when there is a special add-on")
    ormont_dessous = get_vaud_commune("Ormont-Dessous")
    _check(
        abs(ormont_dessous.income_wealth_pct_base - 74.9) < 1e-12,
        "The table keeps the ordinary base percentage for reference",
    )
    _check(
        abs(ormont_dessous.special_pct - 2.1) < 1e-12,
        "The table also keeps the special add-on percentage for reference",
    )
    _check(
        abs(ormont_dessous.commune_multiplier - 0.77) < 1e-12,
        "The selector uses the official 77.0% total commune percentage in the model input",
    )


def test_vd_commune_defaults_infer_lausanne() -> None:
    print("[50] Current shipped commune defaults map back to Lausanne")
    cfg = SwissConfig()
    _check(
        infer_vaud_commune_name(
            cfg.commune_multiplier,
            cfg.communal_property_tax_rate,
            preferred_name="Lausanne",
        )
        == "Lausanne",
        "The selector can infer Lausanne from the current shipped default tax inputs",
    )


def test_first_time_buyer_years_used_before_start_reduce_remaining_cap() -> None:
    print("[51] Already-used years can shrink the remaining first-time-buyer deduction window")
    cfg = SwissConfig(
        household_status="unmarried",
        salary_total=120_000.0,
        salary_split=1.0,
        ownership_split=1.0,
        portfolio_split=1.0,
        social_security_rate=0.0,
        n_children=0,
        house_price=500_000.0,
        downpayment=400_000.0,
        interest_rate=0.10,
        reform_year=2029,
        first_time_buyer_years=10,
        first_time_home_buyer_p1=True,
        first_time_home_buyer_p2=False,
        first_time_buyer_years_used_before_start_p1=4,
        first_time_buyer_interest_deduction_single_max=5_000.0,
        fed_deduction_professional_flat=0.0,
        cant_deduction_professional_rate=0.0,
        cant_deduction_professional_min=0.0,
        cant_deduction_professional_max=0.0,
        fed_deduction_transport=0.0,
        cant_deduction_transport=0.0,
        fed_deduction_meals=0.0,
        cant_deduction_meals=0.0,
        fed_deduction_insurance_single=0.0,
        fed_deduction_insurance_single_without_pillars=0.0,
        cant_deduction_insurance_single=0.0,
        canton_multiplier=0.0,
        commune_multiplier=0.0,
        use_official_cantonal_income_tax_reduction_schedule=False,
        cantonal_income_tax_reduction_rate=0.0,
    )
    res = VaudTaxEngine(cfg).calculate_household_tax(
        year=2029,
        salary_total=cfg.salary_total,
        portfolio=0.0,
        house_val=cfg.house_price,
        debt=cfg.house_price - cfg.downpayment,
        is_owner=True,
        pillar_3a_contribution_p1=0.0,
        pillar_3a_contribution_p2=0.0,
        market_rent_annual=0.0,
    )
    _check(
        abs(res.p1.taxable_income_fed - 118_500.0) < 1e-9,
        "The first-time-buyer deduction can start partly used before the simulation start year",
    )


def test_stress_clustering_uses_state_dependent_transitions() -> None:
    print("[52] Stress clustering can turn isolated stress draws into multi-year runs")
    enter_prob, stay_prob = _stress_transition_probabilities(0.20, 0.50)
    _check(
        abs(enter_prob - 0.10) < 1e-12 and abs(stay_prob - 0.60) < 1e-12,
        "Stress clustering preserves the 20% long-run share while changing the transition probabilities",
    )
    uniforms = np.array([[0.10, 0.25, 0.30, 0.70, 0.20]])
    events = _draw_stress_events_from_uniforms(uniforms, 0.20, 0.50)
    expected = np.array([[True, True, True, False, False]])
    _check(
        np.array_equal(events, expected),
        "A persistent stress regime can keep consecutive bad years together",
        detail=f"expected={expected.tolist()}, got={events.tolist()}",
    )


def test_forced_sale_friction_keeps_deposit_as_wealth_but_not_liquidity() -> None:
    print("[53] Forced-sale friction can lock cash as a rental deposit without destroying that wealth")
    cfg = SwissConfig(
        years=1,
        iterations=1,
        rng_seed=1,
        salary_total=0.0,
        social_security_rate=0.0,
        stock_growth_world_usd=0.0,
        chf_appreciation_vs_usd=0.0,
        stock_volatility=0.0,
        house_growth=0.0,
        house_volatility=0.0,
        inflation=0.0,
        inflation_volatility=0.0,
        salary_growth=0.0,
        salary_growth_volatility=0.0,
        rent_growth_volatility=0.0,
        mortgage_rate_volatility=0.0,
        stress_event_probability=0.0,
        portfolio_ter=0.0,
        pillar_3a_ter=0.0,
        house_price=120_000.0,
        initial_liquid_assets=120_000.0,
        downpayment=120_000.0,
        buying_costs_pct=0.0,
        sale_cost_pct=0.0,
        base_rent_monthly=1_000.0,
        house_market_rent_monthly=2_000.0,
        annual_other_consumption=10_000.0,
        interest_rate=0.0,
        amortization_annual=0.0,
        maintenance_rate=0.0,
        dividend_yield=0.0,
        pillar_3a_annual_per_person=0.0,
        n_children=0,
        force_buy_sale_on_liquidity_crisis=True,
        liquidity_crisis_buffer_months=0.0,
        forced_sale_extra_cost_chf=12_000.0,
        forced_sale_transition_months=1.5,
        forced_sale_rental_deposit_months=3.0,
        communal_property_tax_rate=0.0,
        canton_multiplier=0.0,
        commune_multiplier=0.0,
        use_official_cantonal_income_tax_reduction_schedule=False,
        cantonal_income_tax_reduction_rate=0.0,
    )
    res = run_simulation(cfg)
    _check(bool(res.buy_forced_sale_any[0]), "This one-year setup forces a sale")
    _check(
        bool(res.buy_cash_crisis_any[0]),
        "A forced sale counts as a buyer cash crisis even if sale proceeds restore liquidity",
    )
    _check(
        abs(float(res.buy_portfolio[0, 0]) - 89_000.0) < 1e-6,
        "Forced-sale frictions reduce liquid cash by the true costs plus the locked deposit",
    )
    _check(
        abs(float(res.buy_surplus[0, 0]) - 89_000.0) < 1e-6,
        "Forced-sale years record the true net cash added to liquid balances after sale proceeds and frictions",
    )
    _check(
        abs(float(res.buy_rental_deposit[0, 0]) - 6_000.0) < 1e-6,
        "The forced-sale rental deposit is tracked as a separate locked asset",
    )
    _check(
        abs(float(res.buy_net_worth[0, 0]) - 95_000.0) < 1e-6,
        "The forced-sale rental deposit still counts toward total wealth",
    )


def test_forced_sale_year_wealth_tax_uses_post_sale_assets() -> None:
    print("[53a] Forced-sale year wealth tax uses the post-sale year-end balance")
    cfg = SwissConfig(
        years=1,
        iterations=1,
        rng_seed=1,
        salary_total=0.0,
        social_security_rate=0.0,
        stock_growth_world_usd=0.0,
        chf_appreciation_vs_usd=0.0,
        stock_volatility=0.0,
        house_growth=0.0,
        house_volatility=0.0,
        inflation=0.0,
        inflation_volatility=0.0,
        salary_growth=0.0,
        salary_growth_volatility=0.0,
        rent_growth_volatility=0.0,
        mortgage_rate_volatility=0.0,
        stress_event_probability=0.0,
        portfolio_ter=0.0,
        pillar_3a_ter=0.0,
        house_price=1_000_000.0,
        initial_liquid_assets=1_000_000.0,
        downpayment=1_000_000.0,
        buying_costs_pct=0.0,
        sale_cost_pct=0.0,
        base_rent_monthly=0.0,
        house_market_rent_monthly=0.0,
        annual_other_consumption=600_000.0,
        interest_rate=0.0,
        amortization_annual=0.0,
        maintenance_rate=0.0,
        dividend_yield=0.0,
        pillar_3a_annual_per_person=0.0,
        n_children=0,
        force_buy_sale_on_liquidity_crisis=True,
        liquidity_crisis_buffer_months=0.0,
        forced_sale_extra_cost_chf=0.0,
        forced_sale_transition_months=0.0,
        forced_sale_rental_deposit_months=0.0,
        communal_property_tax_rate=0.0,
        use_official_cantonal_income_tax_reduction_schedule=False,
        cantonal_income_tax_reduction_rate=0.0,
    )
    res = run_simulation(cfg)
    expected_post_sale_wealth = 400_000.0
    expected_tax = VaudTaxEngine(cfg).calculate_household_tax(
        year=cfg.start_year,
        salary_total=0.0,
        portfolio=0.0,
        house_val=cfg.house_price,
        debt=0.0,
        is_owner=True,
        pillar_3a_contribution_p1=0.0,
        pillar_3a_contribution_p2=0.0,
        market_rent_annual=0.0,
        interest_rate_override=0.0,
        wealth_portfolio=expected_post_sale_wealth,
        wealth_house_val=0.0,
        wealth_debt=0.0,
        annual_childcare_spend_household_override=0.0,
    ).total
    _check(bool(res.buy_forced_sale_any[0]), "This setup forces a year-end sale")
    _check(
        abs(float(res.buy_tax[0, 0]) - expected_tax) < 1e-6,
        "Forced-sale tax uses the liquid post-sale 31 December wealth state, not the pre-sale house/debt state",
        detail=f"expected={expected_tax:.2f}, got={float(res.buy_tax[0, 0]):.2f}",
    )


def test_tax_parameter_index_factor_matches_manual_compounding() -> None:
    print("[54] Tax-law CHF amounts follow simple positive inflation compounding")
    cfg = SwissConfig(inflation=0.02, index_tax_parameters_with_inflation=True)
    _check(
        abs(cfg.tax_parameter_index_factor(2026) - 1.0) < 1e-12,
        "The 2026 tax parameter factor stays at 1.0 in the reference year",
    )
    _check(
        abs(cfg.tax_parameter_index_factor(2031) - (1.02 ** 5)) < 1e-12,
        "Later tax parameter factors match manual positive inflation compounding",
    )
    _check(
        abs(cfg.indexed_tax_amount(4_000.0, 2031) - (4_000.0 * (1.02 ** 5))) < 1e-9,
        "Indexed tax amounts follow the same manual compounding rule",
    )


def test_tax_engine_validates_config_on_direct_use() -> None:
    print("[55] Direct tax-engine use validates config before calculation")
    try:
        VaudTaxEngine(SwissConfig(household_status="married", n_children=6))
        _fail("Invalid married child count should have raised ValueError in the tax engine")
    except ValueError:
        _ok("Tax engine rejects configs that would otherwise fail later with a KeyError")


def test_zero_stock_volatility_keeps_3a_shocks_standard_normal() -> None:
    print("[56] Separate 3a shocks keep their variance when stock volatility is zero")
    rng = np.random.default_rng(123)
    recovered = _recover_stock_shocks_from_factors(
        np.ones((20_000, 1)),
        mu=0.04,
        sigma=0.0,
        ter=0.0,
    )
    shocks = _correlate_with_reference_shocks(rng, recovered, 0.5)
    std = float(np.std(shocks))
    _check(
        0.98 <= std <= 1.02,
        "A partial 3a correlation with a deterministic stock path still gives standard-normal 3a shocks",
        detail=f"std={std:.4f}",
    )


def test_pillar_3a_stress_drawdown_matches_taxable_portfolio() -> None:
    print("[57] Mirrored pillar 3a uses the same stress drawdown as taxable stocks")
    cfg = SwissConfig(
        years=2,
        iterations=1,
        rng_seed=1,
        salary_total=1_000.0,
        salary_split=1.0,
        social_security_rate=0.0,
        stock_growth_world_usd=0.0,
        chf_appreciation_vs_usd=0.0,
        stock_volatility=0.0,
        house_growth=0.0,
        house_volatility=0.0,
        inflation=0.0,
        inflation_volatility=0.0,
        salary_growth=0.0,
        salary_growth_volatility=0.0,
        rent_growth_volatility=0.0,
        mortgage_rate_volatility=0.0,
        stress_event_probability=1.0,
        stress_stock_drawdown=1.0,
        portfolio_ter=0.0,
        pillar_3a_ter=0.0,
        pillar_3a_annual_per_person=100.0,
        pillar_3a_withdrawal_tax_rate=0.0,
        house_price=1.0,
        downpayment=1.0,
        buying_costs_pct=0.0,
        sale_cost_pct=0.0,
        base_rent_monthly=0.0,
        house_market_rent_monthly=0.0,
        annual_other_consumption=0.0,
        interest_rate=0.0,
        amortization_annual=0.0,
        maintenance_rate=0.0,
        dividend_yield=0.0,
        canton_multiplier=0.0,
        commune_multiplier=0.0,
        communal_property_tax_rate=0.0,
        use_official_cantonal_income_tax_reduction_schedule=False,
        cantonal_income_tax_reduction_rate=0.0,
        n_children=0,
    )
    res = run_simulation(cfg)
    _check(
        abs(float(res.buy_pillar_3a[0, 1]) - cfg.pillar_3a_annual_per_person) < 1e-6,
        "A 100% stress drawdown wipes the opening 3a balance before the same-year contribution is added",
        detail=f"year2_3a={float(res.buy_pillar_3a[0, 1]):.2f}",
    )


def main() -> None:
    print("Running simulator sanity tests\n")
    test_official_tax_points()
    test_owner_share_handling()
    test_cohabiting_child_split_defaults()
    test_cohabiting_unmarried_federal_child_defaults_follow_common_case()
    test_federal_and_vaud_maintenance_rates_are_separate()
    test_married_joint_tax_without_children()
    test_married_federal_double_income_uses_net_earned_income()
    test_married_vaud_child_cap_uses_official_table()
    test_childcare_deduction_window()
    test_post_reform_owner_rules()
    test_vd_cantonal_reduction_uses_official_schedule_by_default()
    test_first_time_buyer_phaseout_uses_configured_years()
    test_married_first_time_buyer_uses_joint_cap()
    test_cantonal_professional_deduction_uses_config()
    test_work_deductions_require_salary()
    test_positive_salary_without_pillar2_can_use_federal_no_pillars_cap()
    test_da1_credit_defaults_to_zero_without_explicit_eligible_share()
    test_unmarried_da1_credit_is_opt_in_and_partner_specific()
    test_da1_minimum_threshold_is_respected()
    test_validation_and_edge_cases()
    test_liquidity_shortfall_model()
    test_stock_return_translation_uses_fx_formula()
    test_cashflow_uses_post_social_salary()
    test_tax_indexation_preserves_real_tax_burden()
    test_simulation_indexes_pillar_3a_cap_when_enabled()
    test_voluntary_amortization_below_floor()
    test_indirect_amortization_via_3a()
    test_reproducibility()
    test_renter_path_is_independent_of_buyer_downpayment()
    test_mortgage_rate_floor_and_cap_do_not_affect_zero_volatility_rate_inside_range()
    test_parallel_reproducibility_matches_serial()
    test_official_igi_schedule()
    test_married_ifd_child_credit_is_applied()
    test_vaud_married_double_income_uses_2026_cap()
    test_vaud_family_deduction_applies_in_married_mode()
    test_unmarried_vaud_child_cap_applies()
    test_vaud_single_parent_uplift_is_not_double_counted()
    test_indirect_amortization_credit_counts_toward_floor()
    test_voluntary_amortization_continues_after_crossing_floor()
    test_married_wealth_threshold_uses_the_2026_no_tax_floor()
    test_same_year_contributions_are_added_after_growth()
    test_initial_pillar_3a_assets_are_separate_from_liquid_assets()
    test_initial_pillar_3a_can_help_pay_for_purchase()
    test_pillar_3a_contributions_are_capped_by_available_cash()
    test_negative_liquidity_reduces_taxable_wealth()
    test_buyer_forced_sale_after_liquidity_crisis()
    test_buyer_rent_switches_to_market_rent_after_forced_sale()
    test_market_rent_can_grow_above_inflation()
    test_stress_salary_hit_stays_one_year_wide()
    test_stress_rent_jump_stays_one_year_wide()
    test_separate_pillar_3a_process_can_diverge_from_taxable_portfolio()
    test_non_affiliated_worker_uses_20pct_3a_rule()
    test_swiss_contract_rent_stays_flat_when_reference_rate_is_unchanged()
    test_swiss_contract_rent_can_step_up_with_reference_rate()
    test_stochastic_inflation_indexes_tax_caps_from_the_realized_path()
    test_owner_tax_uses_the_simulated_mortgage_rate()
    test_private_interest_deduction_is_capped_before_2029()
    test_communal_property_tax_is_modeled_separately()
    test_negative_inflation_does_not_reduce_tax_indexing()
    test_official_vd_commune_table_contains_lausanne_defaults()
    test_vd_commune_table_uses_total_pct_when_special_tax_exists()
    test_vd_commune_defaults_infer_lausanne()
    test_first_time_buyer_years_used_before_start_reduce_remaining_cap()
    test_stress_clustering_uses_state_dependent_transitions()
    test_forced_sale_friction_keeps_deposit_as_wealth_but_not_liquidity()
    test_forced_sale_year_wealth_tax_uses_post_sale_assets()
    test_tax_parameter_index_factor_matches_manual_compounding()
    test_tax_engine_validates_config_on_direct_use()
    test_zero_stock_volatility_keeps_3a_shocks_standard_normal()
    test_pillar_3a_stress_drawdown_matches_taxable_portfolio()
    print("\nAll checks passed.")


if __name__ == "__main__":
    main()
