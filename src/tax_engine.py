"""
tax_engine.py
Swiss federal + Vaud cantonal + commune-adjusted tax engine for two-adult
households in Vaud, with separate handling for unmarried and married filing.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from src.config import (
    SwissConfig,
    IFD_BAREME_BASE,
    IFD_BAREME_MARRIED,
    IFD_CONST_CAP_THRESHOLD,
    IFD_CONST_CAP_RATE,
    IFD_MARRIED_CAP_THRESHOLD,
    IFD_PARENTAL_PER_CHILD_CREDIT,
    PRIVATE_DEBT_INTEREST_ADDITIONAL_ALLOWANCE,
    VAUD_ICC_SIMPLE_BRACKETS,
    VAUD_QUOTIENT_LIMITS_WITH_CHILDREN,
    VAUD_QUOTIENT_MARRIED_MAX_DEDUCTION,
    VAUD_QUOTIENT_SINGLE_PARENT_MAX_DEDUCTION,
    VAUD_QUOTIENT_SINGLE_MAX_DEDUCTION,
    VAUD_FAMILY_DEDUCTION_BASE_MARRIED,
    VAUD_FAMILY_DEDUCTION_BASE_SINGLE_PARENT,
    VAUD_FAMILY_DEDUCTION_PER_CHILD,
    VAUD_FAMILY_DEDUCTION_PHASEOUT_START,
    VAUD_FAMILY_DEDUCTION_PHASEOUT_MID,
    VAUD_FAMILY_DEDUCTION_PHASEOUT_STEP_BELOW_MID,
    VAUD_FAMILY_DEDUCTION_PHASEOUT_STEP_ABOVE_MID,
    VAUD_WEALTH_SIMPLE_BRACKETS,
    VAUD_WEALTH_MARRIED_NO_TAX_THRESHOLD,
)


def _apply_bracket_table(brackets, base: float) -> float:
    """Piecewise-linear tax from a (lower, base_tax, marginal) bracket list."""
    if base <= 0.0:
        return 0.0
    lower, base_tax, marginal = brackets[0]
    for b_lower, b_base, b_marginal in brackets:
        if b_lower <= base:
            lower, base_tax, marginal = b_lower, b_base, b_marginal
        else:
            break
    return base_tax + (base - lower) * marginal


def _floor_to_step(value: float, step: float) -> float:
    if value <= 0.0:
        return 0.0
    return math.floor(value / step) * step


def _round_down_to_0_05(value: float) -> float:
    return math.floor(value * 20.0) / 20.0


def _apply_ifd_minimum_tax(tax_amount: float) -> float:
    """Federal tax amounts below CHF 25 are not levied."""
    return 0.0 if tax_amount < 25.0 else tax_amount


def _scale_brackets(brackets, factor: float):
    return [(lower * factor, base_tax * factor, marginal) for lower, base_tax, marginal in brackets]


def ifd_base(income: float) -> float:
    """Federal single-person tariff on taxable income floored to CHF 100."""
    income = _floor_to_step(income, 100.0)
    if income <= 0.0:
        return 0.0
    if income >= IFD_CONST_CAP_THRESHOLD:
        return _apply_ifd_minimum_tax(_round_down_to_0_05(IFD_CONST_CAP_RATE * income))
    return _apply_ifd_minimum_tax(_round_down_to_0_05(_apply_bracket_table(IFD_BAREME_BASE, income)))


def ifd_married(income: float) -> float:
    """Federal married / parental tariff base on taxable income floored to CHF 100."""
    income = _floor_to_step(income, 100.0)
    if income <= 0.0:
        return 0.0
    if income >= IFD_MARRIED_CAP_THRESHOLD:
        return _apply_ifd_minimum_tax(_round_down_to_0_05(IFD_CONST_CAP_RATE * income))
    return _apply_ifd_minimum_tax(
        _round_down_to_0_05(_apply_bracket_table(IFD_BAREME_MARRIED, income))
    )


def ifd_parental(income: float, n_children: int) -> float:
    """Federal parental tariff = married tariff minus the per-child credit."""
    return _apply_ifd_minimum_tax(
        max(0.0, ifd_married(income) - IFD_PARENTAL_PER_CHILD_CREDIT * n_children)
    )


def vaud_icc_simple(income: float) -> float:
    """Vaud income tax at coefficient 100 %, with taxable income floored to CHF 100."""
    return _apply_bracket_table(VAUD_ICC_SIMPLE_BRACKETS, _floor_to_step(income, 100.0))


def vaud_wealth_simple(net_taxable_wealth: float) -> float:
    """Vaud wealth tax at coefficient 100 %, with wealth floored to CHF 1 000."""
    return _apply_bracket_table(
        VAUD_WEALTH_SIMPLE_BRACKETS,
        _floor_to_step(net_taxable_wealth, 1_000.0),
    )


@dataclass
class PartnerTax:
    ifd: float
    icc_income: float
    icc_wealth: float
    taxable_income_fed: float
    taxable_income_cant: float
    taxable_wealth: float

    @property
    def total(self) -> float:
        return self.ifd + self.icc_income + self.icc_wealth

    @property
    def income_tax_total(self) -> float:
        return self.ifd + self.icc_income


@dataclass
class TaxResult:
    p1: PartnerTax | None = None
    p2: PartnerTax | None = None
    household: PartnerTax | None = None
    foreign_dividend_wht_credit: float = 0.0

    @property
    def total(self) -> float:
        if self.household is not None:
            return self.household.total - self.foreign_dividend_wht_credit
        return (
            (0.0 if self.p1 is None else self.p1.total)
            + (0.0 if self.p2 is None else self.p2.total)
            - self.foreign_dividend_wht_credit
        )


class VaudTaxEngine:
    def __init__(self, cfg: SwissConfig):
        cfg.validate()
        self.cfg = cfg
        self._tax_index_factor_overrides: dict[int, float] = {}

    def set_tax_index_factor_overrides(self, overrides: dict[int, float] | None) -> None:
        self._tax_index_factor_overrides = {} if overrides is None else dict(overrides)

    def _tax_parameter_index_factor(self, year: int) -> float:
        return self._tax_index_factor_overrides.get(year, self.cfg.tax_parameter_index_factor(year))

    def _index_amount(self, amount: float, year: int) -> float:
        return amount * self._tax_parameter_index_factor(year)

    def _ifd_base_for_year(self, year: int, income: float) -> float:
        income = _floor_to_step(income, 100.0)
        if income <= 0.0:
            return 0.0
        factor = self._tax_parameter_index_factor(year)
        cap_threshold = IFD_CONST_CAP_THRESHOLD * factor
        if income >= cap_threshold:
            return _apply_ifd_minimum_tax(_round_down_to_0_05(IFD_CONST_CAP_RATE * income))
        return _apply_ifd_minimum_tax(
            _round_down_to_0_05(
                _apply_bracket_table(_scale_brackets(IFD_BAREME_BASE, factor), income)
            )
        )

    def _ifd_married_for_year(self, year: int, income: float) -> float:
        income = _floor_to_step(income, 100.0)
        if income <= 0.0:
            return 0.0
        factor = self._tax_parameter_index_factor(year)
        cap_threshold = IFD_MARRIED_CAP_THRESHOLD * factor
        if income >= cap_threshold:
            return _apply_ifd_minimum_tax(_round_down_to_0_05(IFD_CONST_CAP_RATE * income))
        return _apply_ifd_minimum_tax(
            _round_down_to_0_05(
                _apply_bracket_table(_scale_brackets(IFD_BAREME_MARRIED, factor), income)
            )
        )

    def _ifd_parental_for_year(self, year: int, income: float, n_children: int) -> float:
        child_credit = self._index_amount(IFD_PARENTAL_PER_CHILD_CREDIT, year)
        return _apply_ifd_minimum_tax(
            max(0.0, self._ifd_married_for_year(year, income) - child_credit * n_children)
        )

    def _vaud_icc_simple_for_year(self, year: int, income: float) -> float:
        return _apply_bracket_table(
            _scale_brackets(VAUD_ICC_SIMPLE_BRACKETS, self._tax_parameter_index_factor(year)),
            _floor_to_step(income, 100.0),
        )

    def _vaud_wealth_simple_for_year(self, year: int, net_taxable_wealth: float) -> float:
        return _apply_bracket_table(
            _scale_brackets(VAUD_WEALTH_SIMPLE_BRACKETS, self._tax_parameter_index_factor(year)),
            _floor_to_step(net_taxable_wealth, 1_000.0),
        )

    def _vaud_wealth_simple_married_for_year(self, year: int, net_taxable_wealth: float) -> float:
        taxable_wealth = _floor_to_step(net_taxable_wealth, 1_000.0)
        if taxable_wealth <= 0.0:
            return 0.0
        married_threshold = self._index_amount(VAUD_WEALTH_MARRIED_NO_TAX_THRESHOLD, year)
        if taxable_wealth < married_threshold:
            return 0.0
        return self._vaud_wealth_simple_for_year(year, taxable_wealth)

    def _da1_credit_from_recomputed_income_tax(
        self,
        *,
        year: int,
        total_dividends: float,
        tax_with_dividends: PartnerTax,
        recompute_income_tax_without_eligible,
    ) -> float:
        c = self.cfg
        if total_dividends <= 0.0 or c.da1_eligible_dividend_share <= 0.0:
            return 0.0
        eligible_dividends = total_dividends * c.da1_eligible_dividend_share
        if eligible_dividends <= 0.0 or c.da1_non_refundable_withholding_rate <= 0.0:
            return 0.0
        non_refundable_tax = eligible_dividends * c.da1_non_refundable_withholding_rate
        minimum_claim = c.da1_minimum_non_refundable_tax
        if non_refundable_tax <= minimum_claim:
            return 0.0
        tax_without_eligible = recompute_income_tax_without_eligible(
            max(0.0, total_dividends - eligible_dividends)
        )
        attributable_income_tax = tax_with_dividends.income_tax_total - tax_without_eligible.income_tax_total
        return min(non_refundable_tax, max(0.0, attributable_income_tax))

    def _first_time_buyer_deduction(
        self,
        year: int,
        interest_paid: float,
        eligible: bool,
        years_used_before_start: int = 0,
        married: bool = False,
    ) -> float:
        c = self.cfg
        if not eligible or year < c.reform_year:
            return 0.0
        elapsed_since_purchase = max(0, year - c.start_year) + years_used_before_start
        factor = max(0.0, 1.0 - (elapsed_since_purchase / c.first_time_buyer_years))
        cap_base = (
            c.first_time_buyer_interest_deduction_married_max
            if married
            else c.first_time_buyer_interest_deduction_single_max
        )
        cap = cap_base * factor
        return min(interest_paid, cap)

    def _capped_private_interest_deduction(
        self,
        year: int,
        requested_interest: float,
        gross_wealth_income: float,
    ) -> float:
        if requested_interest <= 0.0:
            return 0.0
        cap = max(0.0, gross_wealth_income) + self._index_amount(
            PRIVATE_DEBT_INTEREST_ADDITIONAL_ALLOWANCE,
            year,
        )
        return min(requested_interest, cap)

    def _childcare_spend_is_active(self, year: int) -> bool:
        t_since_start = year - self.cfg.start_year
        return (
            self.cfg.n_children > 0
            and 0 <= t_since_start < self.cfg.child_dependent_years
            and t_since_start < self.cfg.childcare_deduction_years
        )

    def _childcare_deduction_for_spend(
        self,
        year: int,
        actual_spend: float,
        child_cap_fraction: float,
        *,
        federal: bool,
    ) -> float:
        if actual_spend <= 0.0 or child_cap_fraction <= 0.0:
            return 0.0
        per_child_cap = (
            self._index_amount(self.cfg.fed_deduction_childcare_per_child, year)
            if federal
            else self._index_amount(self.cfg.cant_deduction_childcare_per_child, year)
        )
        return min(actual_spend, per_child_cap * self.cfg.n_children * child_cap_fraction)

    def _federal_insurance_deduction_single(
        self,
        year: int,
        has_modeled_pension_contributions: bool,
    ) -> float:
        c = self.cfg
        amount = (
            c.fed_deduction_insurance_single
            if has_modeled_pension_contributions
            else c.fed_deduction_insurance_single_without_pillars
        )
        return self._index_amount(amount, year)

    def _federal_insurance_deduction_married(
        self,
        year: int,
        has_modeled_pension_contributions: bool,
    ) -> float:
        c = self.cfg
        amount = (
            c.fed_deduction_insurance_married
            if has_modeled_pension_contributions
            else c.fed_deduction_insurance_married_without_pillars
        )
        return self._index_amount(amount, year)

    def _cantonal_income_tax_from_rate_income(
        self,
        year: int,
        taxable_income: float,
        rate_income: float,
    ) -> float:
        if taxable_income <= 0.0 or rate_income <= 0.0:
            return 0.0
        rate_income = _floor_to_step(rate_income, 100.0)
        if rate_income <= 0.0:
            return 0.0
        simple_income = self._vaud_icc_simple_for_year(year, rate_income) * (taxable_income / rate_income)
        c = self.cfg
        reduction_factor = 1.0 - c.cantonal_income_tax_reduction_for_year(year)
        cantonal_income_tax = (
            simple_income
            * c.canton_multiplier
            * reduction_factor
        )
        communal_income_tax = simple_income * c.commune_multiplier
        return cantonal_income_tax + communal_income_tax

    def _federal_double_income_deduction(
        self,
        year: int,
        earned_income_p1: float,
        earned_income_p2: float,
    ) -> float:
        c = self.cfg
        if earned_income_p1 <= 0.0 or earned_income_p2 <= 0.0:
            return 0.0
        lower_income = min(earned_income_p1, earned_income_p2)
        deduction = max(
            self._index_amount(c.fed_deduction_double_income_min, year),
            min(self._index_amount(c.fed_deduction_double_income_max, year), 0.5 * lower_income),
        )
        return min(deduction, lower_income)

    def _cantonal_double_income_deduction(
        self,
        year: int,
        activity_income_p1: float,
        activity_income_p2: float,
    ) -> float:
        c = self.cfg
        if activity_income_p1 <= 0.0 or activity_income_p2 <= 0.0:
            return 0.0
        lower_income = min(activity_income_p1, activity_income_p2)
        deduction = min(self._index_amount(c.cant_deduction_double_income_max, year), 0.5 * lower_income)
        if c.cant_deduction_double_income_min > 0.0:
            deduction = max(self._index_amount(c.cant_deduction_double_income_min, year), deduction)
        return min(deduction, lower_income)

    @staticmethod
    def _interpolate_child_table_value(
        effective_child_count: float,
        official_values: dict[int, float],
    ) -> float:
        """Scale official per-child tables to shared-child cases such as 0.25/0.25."""
        if effective_child_count <= 0.0:
            return 0.0
        keys = sorted(official_values)
        if effective_child_count <= keys[0]:
            return official_values[keys[0]] * (effective_child_count / keys[0])
        for lower_key, upper_key in zip(keys, keys[1:]):
            if effective_child_count <= upper_key:
                span = upper_key - lower_key
                ratio = (effective_child_count - lower_key) / span
                return official_values[lower_key] + ratio * (
                    official_values[upper_key] - official_values[lower_key]
                )
        last_key = keys[-1]
        prev_key = keys[-2]
        slope = (official_values[last_key] - official_values[prev_key]) / (
            last_key - prev_key
        )
        return official_values[last_key] + slope * (effective_child_count - last_key)

    def _vaud_family_deduction(
        self,
        year: int,
        net_income_code_650: float,
        *,
        married: bool,
        single_parent_household: bool,
        effective_child_count: float,
    ) -> float:
        if married:
            base = self._index_amount(VAUD_FAMILY_DEDUCTION_BASE_MARRIED, year)
        elif single_parent_household and effective_child_count > 0.0:
            base = self._index_amount(VAUD_FAMILY_DEDUCTION_BASE_SINGLE_PARENT, year)
        else:
            base = 0.0
        per_child = self._index_amount(VAUD_FAMILY_DEDUCTION_PER_CHILD, year)
        max_deduction = base + per_child * effective_child_count
        if max_deduction <= 0.0:
            return 0.0
        phaseout_start = self._index_amount(VAUD_FAMILY_DEDUCTION_PHASEOUT_START, year)
        phaseout_mid = self._index_amount(VAUD_FAMILY_DEDUCTION_PHASEOUT_MID, year)
        step_below_mid = self._index_amount(VAUD_FAMILY_DEDUCTION_PHASEOUT_STEP_BELOW_MID, year)
        step_above_mid = self._index_amount(VAUD_FAMILY_DEDUCTION_PHASEOUT_STEP_ABOVE_MID, year)
        deduction_step = self._index_amount(100.0, year)
        if net_income_code_650 <= phaseout_start:
            return max_deduction
        reduction_steps = int(
            (min(net_income_code_650, phaseout_mid) - phaseout_start)
            // step_below_mid
        )
        if net_income_code_650 > phaseout_mid:
            reduction_steps += int(
                (net_income_code_650 - phaseout_mid)
                // step_above_mid
            )
        return max(0.0, max_deduction - deduction_step * reduction_steps)

    def _separate_vaud_rate_income(
        self,
        year: int,
        taxable_income: float,
        effective_child_count: float,
        single_parent_household: bool,
    ) -> float:
        if taxable_income <= 0.0:
            return 0.0
        if effective_child_count <= 0.0:
            return taxable_income
        base_part = 1.3 if single_parent_household else 1.0
        total_parts = base_part + 0.5 * effective_child_count
        uncapped_rate = taxable_income / total_parts
        cap_table = (
            VAUD_QUOTIENT_SINGLE_PARENT_MAX_DEDUCTION
            if single_parent_household
            else VAUD_QUOTIENT_SINGLE_MAX_DEDUCTION
        )
        indexed_cap_table = {key: self._index_amount(value, year) for key, value in cap_table.items()}
        capped_relief = self._interpolate_child_table_value(effective_child_count, indexed_cap_table)
        capped_rate = taxable_income / base_part - capped_relief
        return max(uncapped_rate, capped_rate)

    def _married_vaud_rate_income(
        self,
        year: int,
        taxable_income: float,
        n_children: int,
    ) -> float:
        if taxable_income <= 0.0:
            return 0.0
        if n_children <= 0:
            return taxable_income / 1.8
        limit = self._index_amount(VAUD_QUOTIENT_LIMITS_WITH_CHILDREN[n_children], year)
        if taxable_income <= limit:
            return taxable_income / (1.8 + 0.5 * n_children)
        return taxable_income / 1.8 - self._index_amount(
            VAUD_QUOTIENT_MARRIED_MAX_DEDUCTION[n_children],
            year,
        )

    def _married_household_tax(
        self,
        year: int,
        salary_total: float,
        p1_salary: float,
        p2_salary: float,
        portfolio: float,
        house_val: float,
        debt: float,
        is_owner: bool,
        pillar_3a_contribution_p1: float,
        pillar_3a_contribution_p2: float,
        market_rent_annual: float,
        interest_rate_override: float | None = None,
        wealth_portfolio: float | None = None,
        wealth_house_val: float | None = None,
        wealth_debt: float | None = None,
        annual_childcare_spend_household: float | None = None,
        dividend_income_override: float | None = None,
        compute_da1_credit: bool = True,
    ) -> TaxResult:
        c = self.cfg
        interest_rate = c.interest_rate if interest_rate_override is None else interest_rate_override
        post_reform = year >= c.reform_year
        t_since_start = year - c.start_year
        child_dependent = c.n_children > 0 and 0 <= t_since_start < c.child_dependent_years
        n_child_deductions = c.n_children if child_dependent else 0
        actual_childcare_spend = (
            0.0
            if not self._childcare_spend_is_active(year)
            else (
                c.annual_childcare_spend_household
                if annual_childcare_spend_household is None
                else annual_childcare_spend_household
            )
        )
        wealth_portfolio = portfolio if wealth_portfolio is None else wealth_portfolio
        wealth_house_val = house_val if wealth_house_val is None else wealth_house_val
        wealth_debt = debt if wealth_debt is None else wealth_debt

        sal_det_total = salary_total * (1.0 - c.social_security_rate)
        sal_det_p1 = p1_salary * (1.0 - c.social_security_rate)
        sal_det_p2 = p2_salary * (1.0 - c.social_security_rate)
        dividend_income = max(
            0.0,
            portfolio * c.dividend_yield if dividend_income_override is None else dividend_income_override,
        )

        if is_owner:
            vl_fed = market_rent_annual * c.vl_factor_federal
            vl_cant = market_rent_annual * c.vl_factor_cantonal
            interest_paid = debt * interest_rate
            maint_fed = vl_fed * c.maintenance_deduction_rate_federal
            maint_cant = vl_cant * c.maintenance_deduction_rate_cantonal
        else:
            vl_fed = vl_cant = interest_paid = maint_fed = maint_cant = 0.0

        if not post_reform:
            owner_income_fed = vl_fed
            owner_deduct_fed = self._capped_private_interest_deduction(
                year,
                interest_paid,
                dividend_income + owner_income_fed,
            ) + maint_fed
            owner_income_cant = vl_cant
            owner_deduct_cant = self._capped_private_interest_deduction(
                year,
                interest_paid,
                dividend_income + owner_income_cant,
            ) + maint_cant
        else:
            owner_income_fed = 0.0
            owner_income_cant = 0.0
            first_time_buyer = self._first_time_buyer_deduction(
                year,
                interest_paid,
                c.first_time_home_buyer_married,
                c.first_time_buyer_years_used_before_start_married,
                married=True,
            )
            owner_deduct_fed = first_time_buyer
            owner_deduct_cant = first_time_buyer

        def _work_deductions(
            salary_gross: float,
            salary_net: float,
        ) -> tuple[float, float, float, float, float, float]:
            if salary_gross <= 0.0:
                return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
            prof_fed = max(
                self._index_amount(c.fed_deduction_professional_flat, year) * 0.5,
                min(salary_net * 0.03, self._index_amount(c.fed_deduction_professional_flat, year)),
            )
            prof_cant = max(
                self._index_amount(c.cant_deduction_professional_min, year),
                min(
                    salary_net * c.cant_deduction_professional_rate,
                    self._index_amount(c.cant_deduction_professional_max, year),
                ),
            )
            return (
                prof_fed,
                prof_cant,
                self._index_amount(c.fed_deduction_transport, year),
                self._index_amount(c.cant_deduction_transport, year),
                self._index_amount(c.fed_deduction_meals, year),
                self._index_amount(c.cant_deduction_meals, year),
            )

        (
            p1_prof_fed,
            p1_prof_cant,
            p1_transport_fed,
            p1_transport_cant,
            p1_meals_fed,
            p1_meals_cant,
        ) = _work_deductions(p1_salary, sal_det_p1)
        (
            p2_prof_fed,
            p2_prof_cant,
            p2_transport_fed,
            p2_transport_cant,
            p2_meals_fed,
            p2_meals_cant,
        ) = _work_deductions(p2_salary, sal_det_p2)

        fed_double_income = self._federal_double_income_deduction(
            year,
            max(
                0.0,
                sal_det_p1
                - p1_prof_fed
                - p1_transport_fed
                - p1_meals_fed
                - pillar_3a_contribution_p1,
            ),
            max(
                0.0,
                sal_det_p2
                - p2_prof_fed
                - p2_transport_fed
                - p2_meals_fed
                - pillar_3a_contribution_p2,
            ),
        )
        cant_double_income = self._cantonal_double_income_deduction(
            year,
            max(
                0.0,
                sal_det_p1
                - p1_prof_cant
                - p1_transport_cant
                - p1_meals_cant
                - pillar_3a_contribution_p1,
            ),
            max(
                0.0,
                sal_det_p2
                - p2_prof_cant
                - p2_transport_cant
                - p2_meals_cant
                - pillar_3a_contribution_p2,
            ),
        )
        has_modeled_pension_contributions = any(
            amount > 0.0
            for amount in (
                p1_salary if c.p1_pillar2_affiliated else 0.0,
                p2_salary if c.p2_pillar2_affiliated else 0.0,
                pillar_3a_contribution_p1,
                pillar_3a_contribution_p2,
            )
        )
        fed_childcare_deduction = self._childcare_deduction_for_spend(
            year,
            actual_childcare_spend,
            1.0 if n_child_deductions > 0 else 0.0,
            federal=True,
        )
        cant_childcare_deduction = self._childcare_deduction_for_spend(
            year,
            actual_childcare_spend,
            1.0 if n_child_deductions > 0 else 0.0,
            federal=False,
        )

        ded_fed = (
            pillar_3a_contribution_p1
            + pillar_3a_contribution_p2
            + p1_prof_fed
            + p2_prof_fed
            + p1_transport_fed
            + p2_transport_fed
            + p1_meals_fed
            + p2_meals_fed
            + self._federal_insurance_deduction_married(year, has_modeled_pension_contributions)
            + self._index_amount(c.fed_deduction_insurance_child_supplement, year) * n_child_deductions
            + fed_childcare_deduction
            + self._index_amount(c.fed_deduction_per_child, year) * n_child_deductions
            + self._index_amount(c.fed_deduction_married, year)
            + fed_double_income
        )
        ded_cant = (
            pillar_3a_contribution_p1
            + pillar_3a_contribution_p2
            + p1_prof_cant
            + p2_prof_cant
            + p1_transport_cant
            + p2_transport_cant
            + p1_meals_cant
            + p2_meals_cant
            + self._index_amount(c.cant_deduction_insurance_married, year)
            + self._index_amount(c.cant_deduction_insurance_child_supplement, year) * n_child_deductions
            + cant_childcare_deduction
            + cant_double_income
        )
        net_income_code_650 = _floor_to_step(
            max(0.0, sal_det_total + dividend_income + owner_income_cant - owner_deduct_cant - ded_cant),
            100.0,
        )
        family_deduction = self._vaud_family_deduction(
            year,
            net_income_code_650,
            married=True,
            single_parent_household=False,
            effective_child_count=float(n_child_deductions),
        )
        ded_cant += self._index_amount(c.cant_deduction_per_child, year) * n_child_deductions + family_deduction

        taxable_fed = _floor_to_step(
            max(0.0, sal_det_total + dividend_income + owner_income_fed - owner_deduct_fed - ded_fed),
            100.0,
        )
        taxable_cant = _floor_to_step(
            max(0.0, sal_det_total + dividend_income + owner_income_cant - owner_deduct_cant - ded_cant),
            100.0,
        )

        ifd = self._ifd_parental_for_year(year, taxable_fed, n_child_deductions)
        rate_income = self._married_vaud_rate_income(year, taxable_cant, n_child_deductions)
        icc_income = self._cantonal_income_tax_from_rate_income(
            year,
            taxable_cant,
            rate_income,
        )

        house_wealth = wealth_house_val * c.wealth_tax_value_ratio - wealth_debt if is_owner else 0.0
        taxable_wealth = _floor_to_step(max(0.0, wealth_portfolio + house_wealth), 1_000.0)
        simple_wealth = self._vaud_wealth_simple_married_for_year(year, taxable_wealth)
        icc_wealth = simple_wealth * (c.canton_multiplier + c.commune_multiplier)

        household_tax = PartnerTax(
            ifd=ifd,
            icc_income=icc_income,
            icc_wealth=icc_wealth,
            taxable_income_fed=taxable_fed,
            taxable_income_cant=taxable_cant,
            taxable_wealth=taxable_wealth,
        )

        wht_credit = 0.0
        if compute_da1_credit:
            dividends_total = portfolio * c.dividend_yield
            wht_credit = self._da1_credit_from_recomputed_income_tax(
                year=year,
                total_dividends=dividends_total,
                tax_with_dividends=household_tax,
                recompute_income_tax_without_eligible=lambda remaining_dividends: self._married_household_tax(
                    year=year,
                    salary_total=salary_total,
                    p1_salary=p1_salary,
                    p2_salary=p2_salary,
                    portfolio=portfolio,
                    house_val=house_val,
                    debt=debt,
                    is_owner=is_owner,
                    pillar_3a_contribution_p1=pillar_3a_contribution_p1,
                    pillar_3a_contribution_p2=pillar_3a_contribution_p2,
                    market_rent_annual=market_rent_annual,
                    interest_rate_override=interest_rate_override,
                    wealth_portfolio=wealth_portfolio,
                    wealth_house_val=wealth_house_val,
                    wealth_debt=wealth_debt,
                    annual_childcare_spend_household=actual_childcare_spend,
                    dividend_income_override=remaining_dividends,
                    compute_da1_credit=False,
                ).household,
            )
        return TaxResult(household=household_tax, foreign_dividend_wht_credit=wht_credit)

    def _partner_tax(
        self,
        gross_salary: float,
        portfolio_share: float,
        house_val_share: float,
        debt_share: float,
        is_owner: bool,
        year: int,
        use_parental_tariff: bool,
        child_deduction_fraction: float,
        vaud_child_part_fraction: float,
        single_parent_household: bool,
        pillar2_affiliated: bool,
        first_time_home_buyer: bool,
        first_time_buyer_years_used_before_start: int,
        pillar_3a_contribution: float,
        market_rent_annual_share: float,
        interest_rate_override: float | None = None,
        wealth_portfolio_share: float | None = None,
        wealth_house_val_share: float | None = None,
        wealth_debt_share: float | None = None,
        annual_childcare_spend_share: float = 0.0,
        childcare_cap_fraction: float = 0.0,
        dividend_income_override: float | None = None,
    ) -> PartnerTax:
        c = self.cfg
        interest_rate = c.interest_rate if interest_rate_override is None else interest_rate_override
        post_reform = year >= c.reform_year
        child_deduction_fraction = max(0.0, min(1.0, child_deduction_fraction))
        vaud_child_part_fraction = max(0.0, min(1.0, vaud_child_part_fraction))
        childcare_cap_fraction = max(0.0, min(1.0, childcare_cap_fraction))
        wealth_portfolio_share = (
            portfolio_share if wealth_portfolio_share is None else wealth_portfolio_share
        )
        wealth_house_val_share = (
            house_val_share if wealth_house_val_share is None else wealth_house_val_share
        )
        wealth_debt_share = debt_share if wealth_debt_share is None else wealth_debt_share

        sal_det = gross_salary * (1.0 - c.social_security_rate)
        dividend_income = max(
            0.0,
            portfolio_share * c.dividend_yield if dividend_income_override is None else dividend_income_override,
        )

        if is_owner:
            vl_fed = market_rent_annual_share * c.vl_factor_federal
            vl_cant = market_rent_annual_share * c.vl_factor_cantonal
            interest_paid = debt_share * interest_rate
            maint_fed = vl_fed * c.maintenance_deduction_rate_federal
            maint_cant = vl_cant * c.maintenance_deduction_rate_cantonal
        else:
            vl_fed = vl_cant = interest_paid = maint_fed = maint_cant = 0.0

        if not post_reform:
            owner_income_fed = vl_fed
            owner_deduct_fed = self._capped_private_interest_deduction(
                year,
                interest_paid,
                dividend_income + owner_income_fed,
            ) + maint_fed
            owner_income_cant = vl_cant
            owner_deduct_cant = self._capped_private_interest_deduction(
                year,
                interest_paid,
                dividend_income + owner_income_cant,
            ) + maint_cant
        else:
            owner_income_fed = 0.0
            owner_income_cant = 0.0
            first_time_buyer = self._first_time_buyer_deduction(
                year,
                interest_paid,
                first_time_home_buyer,
                first_time_buyer_years_used_before_start,
            )
            owner_deduct_fed = first_time_buyer
            owner_deduct_cant = first_time_buyer

        prof_forfait_fed = 0.0
        prof_forfait_cant = 0.0
        transport_ded_fed = 0.0
        transport_ded_cant = 0.0
        meals_ded_fed = 0.0
        meals_ded_cant = 0.0
        if gross_salary > 0.0:
            prof_forfait_fed = max(
                self._index_amount(c.fed_deduction_professional_flat, year) * 0.5,
                min(sal_det * 0.03, self._index_amount(c.fed_deduction_professional_flat, year)),
            )
            prof_forfait_cant = max(
                self._index_amount(c.cant_deduction_professional_min, year),
                min(
                    sal_det * c.cant_deduction_professional_rate,
                    self._index_amount(c.cant_deduction_professional_max, year),
                ),
            )
            transport_ded_fed = self._index_amount(c.fed_deduction_transport, year)
            transport_ded_cant = self._index_amount(c.cant_deduction_transport, year)
            meals_ded_fed = self._index_amount(c.fed_deduction_meals, year)
            meals_ded_cant = self._index_amount(c.cant_deduction_meals, year)

        child_count_weighted = c.n_children * child_deduction_fraction
        fed_childcare_deduction = self._childcare_deduction_for_spend(
            year,
            annual_childcare_spend_share,
            childcare_cap_fraction,
            federal=True,
        )
        cant_childcare_deduction = self._childcare_deduction_for_spend(
            year,
            annual_childcare_spend_share,
            childcare_cap_fraction,
            federal=False,
        )
        has_modeled_pension_contributions = (
            (gross_salary > 0.0 and pillar2_affiliated) or pillar_3a_contribution > 0.0
        )

        ded_fed = (
            pillar_3a_contribution
            + prof_forfait_fed
            + transport_ded_fed
            + meals_ded_fed
            + self._federal_insurance_deduction_single(year, has_modeled_pension_contributions)
            + self._index_amount(c.fed_deduction_insurance_child_supplement, year) * child_count_weighted
            + fed_childcare_deduction
            + self._index_amount(c.fed_deduction_per_child, year) * child_count_weighted
        )
        ded_cant = (
            pillar_3a_contribution
            + prof_forfait_cant
            + transport_ded_cant
            + meals_ded_cant
            + self._index_amount(c.cant_deduction_insurance_single, year)
            + self._index_amount(c.cant_deduction_insurance_child_supplement, year) * child_count_weighted
            + cant_childcare_deduction
        )
        net_income_code_650 = _floor_to_step(
            max(0.0, sal_det + dividend_income + owner_income_cant - owner_deduct_cant - ded_cant),
            100.0,
        )
        effective_child_count_for_family = c.n_children * vaud_child_part_fraction
        family_deduction = self._vaud_family_deduction(
            year,
            net_income_code_650,
            married=False,
            single_parent_household=single_parent_household,
            effective_child_count=effective_child_count_for_family,
        )
        ded_cant += self._index_amount(c.cant_deduction_per_child, year) * child_count_weighted + family_deduction

        taxable_fed_raw = (
            sal_det + dividend_income + owner_income_fed - owner_deduct_fed - ded_fed
        )
        taxable_cant_raw = (
            sal_det + dividend_income + owner_income_cant - owner_deduct_cant - ded_cant
        )
        taxable_fed = _floor_to_step(max(0.0, taxable_fed_raw), 100.0)
        taxable_cant = _floor_to_step(max(0.0, taxable_cant_raw), 100.0)

        if use_parental_tariff:
            ifd = self._ifd_parental_for_year(year, taxable_fed, c.n_children)
        else:
            ifd = self._ifd_base_for_year(year, taxable_fed)

        effective_child_count_for_quotient = c.n_children * vaud_child_part_fraction
        rate_income = self._separate_vaud_rate_income(
            year,
            taxable_cant,
            effective_child_count_for_quotient,
            single_parent_household,
        )
        icc_income = self._cantonal_income_tax_from_rate_income(
            year,
            taxable_cant,
            rate_income,
        )

        if is_owner:
            house_wealth = wealth_house_val_share * c.wealth_tax_value_ratio - wealth_debt_share
        else:
            house_wealth = 0.0
        gross_wealth = max(0.0, wealth_portfolio_share + house_wealth)
        taxable_wealth = _floor_to_step(gross_wealth, 1_000.0)
        simple_wealth = self._vaud_wealth_simple_for_year(year, taxable_wealth)
        icc_wealth = simple_wealth * (c.canton_multiplier + c.commune_multiplier)

        return PartnerTax(
            ifd=ifd,
            icc_income=icc_income,
            icc_wealth=icc_wealth,
            taxable_income_fed=taxable_fed,
            taxable_income_cant=taxable_cant,
            taxable_wealth=taxable_wealth,
        )

    def calculate_household_tax(
        self,
        year: int,
        salary_total: float,
        portfolio: float,
        house_val: float,
        debt: float,
        is_owner: bool,
        pillar_3a_contribution_p1: float,
        pillar_3a_contribution_p2: float,
        market_rent_annual: float,
        interest_rate_override: float | None = None,
        wealth_portfolio: float | None = None,
        wealth_house_val: float | None = None,
        wealth_debt: float | None = None,
        annual_childcare_spend_household_override: float | None = None,
    ) -> TaxResult:
        c = self.cfg

        p1_salary = salary_total * c.salary_split
        p2_salary = salary_total * (1.0 - c.salary_split)
        p1_portfolio = portfolio * c.portfolio_split
        p2_portfolio = portfolio * (1.0 - c.portfolio_split)
        wealth_portfolio = portfolio if wealth_portfolio is None else wealth_portfolio
        wealth_house_val = house_val if wealth_house_val is None else wealth_house_val
        wealth_debt = debt if wealth_debt is None else wealth_debt
        actual_childcare_spend_household = (
            c.annual_childcare_spend_household
            if annual_childcare_spend_household_override is None
            else annual_childcare_spend_household_override
        )
        p1_wealth_portfolio = wealth_portfolio * c.portfolio_split
        p2_wealth_portfolio = wealth_portfolio * (1.0 - c.portfolio_split)

        if is_owner:
            p1_house = house_val * c.ownership_split
            p1_debt = debt * c.ownership_split
            p2_house = house_val * (1.0 - c.ownership_split)
            p2_debt = debt * (1.0 - c.ownership_split)
            p1_market_rent = market_rent_annual * c.ownership_split
            p2_market_rent = market_rent_annual * (1.0 - c.ownership_split)
            p1_wealth_house = wealth_house_val * c.ownership_split
            p2_wealth_house = wealth_house_val * (1.0 - c.ownership_split)
            p1_wealth_debt = wealth_debt * c.ownership_split
            p2_wealth_debt = wealth_debt * (1.0 - c.ownership_split)
        else:
            p1_house = p1_debt = p2_house = p2_debt = 0.0
            p1_market_rent = p2_market_rent = 0.0
            p1_wealth_house = p2_wealth_house = 0.0
            p1_wealth_debt = p2_wealth_debt = 0.0

        if c.household_status == "married":
            return self._married_household_tax(
                year=year,
                salary_total=salary_total,
                p1_salary=p1_salary,
                p2_salary=p2_salary,
                portfolio=portfolio,
                house_val=house_val if is_owner else 0.0,
                debt=debt if is_owner else 0.0,
                is_owner=is_owner,
                pillar_3a_contribution_p1=pillar_3a_contribution_p1,
                pillar_3a_contribution_p2=pillar_3a_contribution_p2,
                market_rent_annual=market_rent_annual if is_owner else 0.0,
                interest_rate_override=interest_rate_override,
                wealth_portfolio=wealth_portfolio,
                wealth_house_val=wealth_house_val,
                wealth_debt=wealth_debt,
                annual_childcare_spend_household=actual_childcare_spend_household,
            )

        t_since_start = year - c.start_year
        child_dependent = c.n_children > 0 and 0 <= t_since_start < c.child_dependent_years

        cohabiting_shared_child_case = child_dependent and not c.vaud_single_parent_household
        if cohabiting_shared_child_case:
            # ESTV KS 30 treats the common cohabiting-with-common-child case as a shared-deduction
            # case, with the parental tariff generally going to the higher-income parent.
            if math.isclose(p1_salary, p2_salary, abs_tol=1e-9):
                p1_parental = c.child_claimed_by_p1
            else:
                p1_parental = p1_salary > p2_salary
            p2_parental = not p1_parental
        else:
            p1_parental = c.child_claimed_by_p1 and child_dependent
            p2_parental = (not c.child_claimed_by_p1) and child_dependent
        p1_single_parent = c.vaud_single_parent_household and p1_parental
        p2_single_parent = c.vaud_single_parent_household and p2_parental
        if cohabiting_shared_child_case:
            p1_child_fraction = 0.5
            p2_child_fraction = 0.5
        else:
            p1_child_fraction = c.child_deduction_split_to_p1 if child_dependent else 0.0
            p2_child_fraction = (1.0 - c.child_deduction_split_to_p1) if child_dependent else 0.0
        childcare_spend_active = self._childcare_spend_is_active(year)
        if cohabiting_shared_child_case and childcare_spend_active:
            p1_childcare_cap_fraction = 0.5
            p2_childcare_cap_fraction = 0.5
        else:
            p1_childcare_cap_fraction = (
                c.childcare_spend_split_to_p1 if childcare_spend_active else 0.0
            )
            p2_childcare_cap_fraction = (
                1.0 - c.childcare_spend_split_to_p1
            ) if childcare_spend_active else 0.0
        p1_childcare_spend = (
            actual_childcare_spend_household * p1_childcare_cap_fraction
            if childcare_spend_active
            else 0.0
        )
        p2_childcare_spend = (
            actual_childcare_spend_household * p2_childcare_cap_fraction
            if childcare_spend_active
            else 0.0
        )
        p1_vaud_child_fraction = c.vaud_child_quotient_share_to_p1 if child_dependent else 0.0
        p2_vaud_child_fraction = (
            1.0 - c.vaud_child_quotient_share_to_p1
        ) if child_dependent else 0.0

        p1_tax = self._partner_tax(
            gross_salary=p1_salary,
            portfolio_share=p1_portfolio,
            house_val_share=p1_house,
            debt_share=p1_debt,
            is_owner=is_owner,
            year=year,
            use_parental_tariff=p1_parental,
            child_deduction_fraction=p1_child_fraction,
            vaud_child_part_fraction=p1_vaud_child_fraction,
            single_parent_household=p1_single_parent,
            pillar2_affiliated=c.p1_pillar2_affiliated,
            first_time_home_buyer=c.first_time_home_buyer_p1,
            first_time_buyer_years_used_before_start=c.first_time_buyer_years_used_before_start_p1,
            pillar_3a_contribution=pillar_3a_contribution_p1,
            market_rent_annual_share=p1_market_rent,
            interest_rate_override=interest_rate_override,
            wealth_portfolio_share=p1_wealth_portfolio,
            wealth_house_val_share=p1_wealth_house,
            wealth_debt_share=p1_wealth_debt,
            annual_childcare_spend_share=p1_childcare_spend,
            childcare_cap_fraction=p1_childcare_cap_fraction,
        )
        p2_tax = self._partner_tax(
            gross_salary=p2_salary,
            portfolio_share=p2_portfolio,
            house_val_share=p2_house,
            debt_share=p2_debt,
            is_owner=is_owner,
            year=year,
            use_parental_tariff=p2_parental,
            child_deduction_fraction=p2_child_fraction,
            vaud_child_part_fraction=p2_vaud_child_fraction,
            single_parent_household=p2_single_parent,
            pillar2_affiliated=c.p2_pillar2_affiliated,
            first_time_home_buyer=c.first_time_home_buyer_p2,
            first_time_buyer_years_used_before_start=c.first_time_buyer_years_used_before_start_p2,
            pillar_3a_contribution=pillar_3a_contribution_p2,
            market_rent_annual_share=p2_market_rent,
            interest_rate_override=interest_rate_override,
            wealth_portfolio_share=p2_wealth_portfolio,
            wealth_house_val_share=p2_wealth_house,
            wealth_debt_share=p2_wealth_debt,
            annual_childcare_spend_share=p2_childcare_spend,
            childcare_cap_fraction=p2_childcare_cap_fraction,
        )

        p1_dividends = p1_portfolio * c.dividend_yield
        p2_dividends = p2_portfolio * c.dividend_yield
        p1_wht_credit = self._da1_credit_from_recomputed_income_tax(
            year=year,
            total_dividends=p1_dividends,
            tax_with_dividends=p1_tax,
            recompute_income_tax_without_eligible=lambda remaining_dividends: self._partner_tax(
                gross_salary=p1_salary,
                portfolio_share=p1_portfolio,
                house_val_share=p1_house,
                debt_share=p1_debt,
                is_owner=is_owner,
                year=year,
                use_parental_tariff=p1_parental,
                child_deduction_fraction=p1_child_fraction,
                vaud_child_part_fraction=p1_vaud_child_fraction,
                single_parent_household=p1_single_parent,
                pillar2_affiliated=c.p1_pillar2_affiliated,
                first_time_home_buyer=c.first_time_home_buyer_p1,
                first_time_buyer_years_used_before_start=c.first_time_buyer_years_used_before_start_p1,
                pillar_3a_contribution=pillar_3a_contribution_p1,
                market_rent_annual_share=p1_market_rent,
                interest_rate_override=interest_rate_override,
                wealth_portfolio_share=p1_wealth_portfolio,
                wealth_house_val_share=p1_wealth_house,
                wealth_debt_share=p1_wealth_debt,
                annual_childcare_spend_share=p1_childcare_spend,
                childcare_cap_fraction=p1_childcare_cap_fraction,
                dividend_income_override=remaining_dividends,
            ),
        )
        p2_wht_credit = self._da1_credit_from_recomputed_income_tax(
            year=year,
            total_dividends=p2_dividends,
            tax_with_dividends=p2_tax,
            recompute_income_tax_without_eligible=lambda remaining_dividends: self._partner_tax(
                gross_salary=p2_salary,
                portfolio_share=p2_portfolio,
                house_val_share=p2_house,
                debt_share=p2_debt,
                is_owner=is_owner,
                year=year,
                use_parental_tariff=p2_parental,
                child_deduction_fraction=p2_child_fraction,
                vaud_child_part_fraction=p2_vaud_child_fraction,
                single_parent_household=p2_single_parent,
                pillar2_affiliated=c.p2_pillar2_affiliated,
                first_time_home_buyer=c.first_time_home_buyer_p2,
                first_time_buyer_years_used_before_start=c.first_time_buyer_years_used_before_start_p2,
                pillar_3a_contribution=pillar_3a_contribution_p2,
                market_rent_annual_share=p2_market_rent,
                interest_rate_override=interest_rate_override,
                wealth_portfolio_share=p2_wealth_portfolio,
                wealth_house_val_share=p2_wealth_house,
                wealth_debt_share=p2_wealth_debt,
                annual_childcare_spend_share=p2_childcare_spend,
                childcare_cap_fraction=p2_childcare_cap_fraction,
                dividend_income_override=remaining_dividends,
            ),
        )
        wht_credit = p1_wht_credit + p2_wht_credit

        return TaxResult(p1=p1_tax, p2=p2_tax, foreign_dividend_wht_credit=wht_credit)


def vaud_igi_rate(holding_years: int, schedule) -> float:
    """Return the IGI rate for a given holding period in completed years."""
    rate = schedule[0][1]
    for threshold, candidate in schedule:
        if holding_years >= threshold:
            rate = candidate
        else:
            break
    return rate
