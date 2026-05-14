"""
config.py
Single source of truth for the simulator parameters.

Important note:
- Several 2026 Vaud values below come from official Vaud publications.
- Several 2026 federal values below come from the official ESTV tariff.
- Some assumptions still depend on household-specific facts that the simulator
  cannot infer safely on its own.

For life-defining decisions, validate the final assumptions against the official
tax-return instructions and, ideally, a Swiss tax professional.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Tuple


# ---------------------------------------------------------------------------
# Tax brackets
# ---------------------------------------------------------------------------

Bracket = Tuple[float, float, float]  # (lower_bound, base_tax, marginal_rate)
TAX_PARAMETER_REFERENCE_YEAR = 2026


# Federal direct tax (IFD), 2026.
# Source: official ESTV Form 58c 2026.
IFD_BAREME_BASE: list[Bracket] = [
    (0.0, 0.0, 0.0),
    (15_200.0, 0.0, 0.0077),
    (33_200.0, 138.60, 0.0088),
    (43_500.0, 229.20, 0.0264),
    (58_000.0, 612.00, 0.0297),
    (76_200.0, 1_152.50, 0.0594),
    (82_100.0, 1_502.95, 0.0660),
    (108_900.0, 3_271.75, 0.0880),
    (141_500.0, 6_140.55, 0.1100),
    (185_100.0, 10_936.55, 0.1320),
]

# Federal "married / single-parent" tariff, 2026.
# The 2026 breakpoints below match the official ESTV table.
IFD_BAREME_MARRIED: list[Bracket] = [
    (0.0, 0.0, 0.0),
    (29_700.0, 0.0, 0.0100),
    (53_400.0, 237.0, 0.0200),
    (61_300.0, 395.0, 0.0300),
    (79_100.0, 929.0, 0.0400),
    (94_900.0, 1_561.0, 0.0500),
    (108_700.0, 2_251.0, 0.0600),
    (120_600.0, 2_965.0, 0.0700),
    (130_500.0, 3_658.0, 0.0800),
    (138_400.0, 4_290.0, 0.0900),
    (144_300.0, 4_821.0, 0.1000),
    (148_300.0, 5_221.0, 0.1100),
    (150_400.0, 5_452.0, 0.1200),
    (152_400.0, 5_692.0, 0.1300),
]

# Above these thresholds the constitutional whole-income cap applies.
IFD_CONST_CAP_THRESHOLD = 794_000.0
IFD_CONST_CAP_RATE = 0.1150
IFD_MARRIED_CAP_THRESHOLD = 941_400.0
IFD_PARENTAL_PER_CHILD_CREDIT = 263.0
PRIVATE_DEBT_INTEREST_ADDITIONAL_ALLOWANCE = 50_000.0


# Vaud quotient familial caps from the official cantonal instructions.
VAUD_QUOTIENT_LIMITS_WITH_CHILDREN: dict[int, float] = {
    1: 212_900.0,
    2: 236_500.0,
    3: 260_100.0,
    4: 283_700.0,
    5: 307_300.0,
}
VAUD_QUOTIENT_MARRIED_MAX_DEDUCTION: dict[int, float] = {
    1: 25_713.0,
    2: 46_925.0,
    3: 65_682.0,
    4: 82_953.0,
    5: 99_257.0,
}
VAUD_QUOTIENT_SINGLE_PARENT_MAX_DEDUCTION: dict[int, float] = {
    1: 45_491.0,
    2: 79_097.0,
    3: 107_184.0,
}
VAUD_QUOTIENT_SINGLE_MAX_DEDUCTION: dict[int, float] = {
    1: 70_967.0,
    2: 118_250.0,
    3: 156_060.0,
}

# Vaud family-deduction ("code 725") parameters, 2026.
# Source: 2026 Vaud deductions table and the detailed 2025 instructions.
VAUD_FAMILY_DEDUCTION_BASE_MARRIED = 1_300.0
VAUD_FAMILY_DEDUCTION_BASE_SINGLE_PARENT = 2_800.0
VAUD_FAMILY_DEDUCTION_PER_CHILD = 1_000.0
VAUD_FAMILY_DEDUCTION_PHASEOUT_START = 126_400.0
VAUD_FAMILY_DEDUCTION_PHASEOUT_MID = 164_200.0
VAUD_FAMILY_DEDUCTION_PHASEOUT_STEP_BELOW_MID = 2_100.0
VAUD_FAMILY_DEDUCTION_PHASEOUT_STEP_ABOVE_MID = 1_000.0


# Vaud income tax, coefficient 100 %, 2026.
# Source: "Tableau des principales déductions vaudoises 2026".
VAUD_ICC_SIMPLE_BRACKETS: list[Bracket] = [
    (0.0, 0.0, 0.0),
    (100.0, 1.00, 0.0100),
    (1_600.0, 16.00, 0.0200),
    (3_400.0, 52.00, 0.0300),
    (5_100.0, 103.00, 0.0400),
    (8_300.0, 231.00, 0.0500),
    (11_900.0, 411.00, 0.0600),
    (15_100.0, 603.00, 0.0700),
    (23_600.0, 1_198.00, 0.0800),
    (40_500.0, 2_550.00, 0.0900),
    (57_200.0, 4_053.00, 0.1000),
    (74_400.0, 5_773.00, 0.1100),
    (91_200.0, 7_621.00, 0.1200),
    (108_100.0, 9_649.00, 0.1250),
    (135_000.0, 13_011.50, 0.1300),
    (162_000.0, 16_521.50, 0.1350),
    (192_500.0, 20_639.00, 0.1400),
    (223_000.0, 24_909.00, 0.1450),
    (256_000.0, 29_694.00, 0.1500),
    (291_700.0, 35_049.00, 0.1550),
]


# Vaud wealth tax, coefficient 100 %, 2026.
# Source: "Barème de l'impôt sur la fortune 2026" / Vaud 2026 deductions table.
VAUD_WEALTH_SIMPLE_BRACKETS: list[Bracket] = [
    (0.0, 0.0, 0.0),
    (60_000.0, 32.65, 0.00097),
    (95_000.0, 66.60, 0.00169),
    (120_000.0, 108.85, 0.00169),
    (177_000.0, 205.20, 0.00242),
    (355_000.0, 635.95, 0.00315),
    (711_000.0, 1_757.35, 0.00339),
]
VAUD_WEALTH_MARRIED_NO_TAX_THRESHOLD = 120_000.0


# Vaud real-estate capital-gains tax (IGI) schedule.
# Thresholds are the lower bound of each completed holding-period band from the
# official Vaud gains-immobiliers form.
IGI_SCHEDULE: list[tuple[int, float]] = [
    (0, 0.30),
    (1, 0.27),
    (2, 0.24),
    (3, 0.22),
    (4, 0.20),
    (5, 0.18),
    (6, 0.17),
    (7, 0.16),
    (8, 0.15),
    (10, 0.14),
    (12, 0.13),
    (14, 0.12),
    (16, 0.11),
    (18, 0.10),
    (20, 0.09),
    (22, 0.08),
    (24, 0.07),
]

DEFAULT_HOUSE_PRICE = 1_000_000.0
DEFAULT_DOWNPAYMENT = 100_000.0
DEFAULT_BUYING_COSTS_PCT = 0.045
DEFAULT_INITIAL_LIQUID_ASSETS = (
    DEFAULT_DOWNPAYMENT + DEFAULT_HOUSE_PRICE * DEFAULT_BUYING_COSTS_PCT
)


@dataclass
class SwissConfig:
    # --- Timeframe / reproducibility ---
    start_year: int = 2026
    years: int = 25
    iterations: int = 10_000
    rng_seed: int = 42
    parallel_workers: int = -1  # -1 = all available CPUs via joblib; 1 = serial

    # --- Household profile ---
    household_status: str = "unmarried"  # "unmarried" (separate) or "married" (joint)
    # salary_total is combined gross employment income before social deductions.
    salary_total: float = 200_000.0
    salary_split: float = 0.5
    ownership_split: float = 0.5
    portfolio_split: float = 0.5

    # Child-related assumptions.
    # `child_claimed_by_p1` controls who receives the federal parental tariff.
    # For unmarried parents filing separately, many child deductions can still be
    # shared. These allocation controls are intentionally limited to whole-child
    # and half-child steps so the defaults stay closer to the published Swiss /
    # Vaud child-sharing cases. They are ignored in married mode, where the
    # household is taxed jointly.
    n_children: int = 1
    child_claimed_by_p1: bool = False
    child_deduction_split_to_p1: float = 0.5
    vaud_single_parent_household: bool = False
    vaud_child_quotient_share_to_p1: float = 0.5
    child_dependent_years: int = 22
    # Third-party childcare deduction should not run for the whole dependency
    # window. For this family's default case (one child almost 3 at start), 11
    # modeled tax years is a reasonable under-14 approximation.
    childcare_deduction_years: int = 11
    # This is the household's actual yearly childcare spending that might be
    # eligible for a tax deduction. The tax engine then applies the published
    # federal and Vaud deduction caps on top of this amount.
    annual_childcare_spend_household: float = 0.0
    childcare_spend_split_to_p1: float = 0.5

    # --- Property & rent ---
    house_price: float = DEFAULT_HOUSE_PRICE
    # Cash and taxable investments available before choosing buy versus rent.
    # This is not opening pillar 3a or pension savings.
    # The buyer spends the downpayment and buying costs from this amount; the renter does not.
    initial_liquid_assets: float = DEFAULT_INITIAL_LIQUID_ASSETS
    downpayment: float = DEFAULT_DOWNPAYMENT
    buying_costs_pct: float = DEFAULT_BUYING_COSTS_PCT
    sale_cost_pct: float = 0.03
    base_rent_monthly: float = 2_000.0
    house_market_rent_monthly: float = 3_000.0
    rent_reference_rate_current: float = 0.0125
    rent_reference_rate_smoothing: float = 0.20
    rent_reference_rate_step: float = 0.0025
    rent_reference_rate_increase_per_step: float = 0.03
    rent_reference_rate_decrease_per_step: float = 0.0291
    rent_cpi_passthrough: float = 0.0

    # --- Other household consumption ---
    annual_other_consumption: float = 60_000.0

    # --- Mortgage ---
    interest_rate: float = 0.018
    amortization_annual: float = 5_000.0
    ltv_floor: float = 0.667
    amortization_strategy: str = "direct"  # "direct" or "indirect_3a"
    voluntary_amortization: bool = False
    maintenance_rate: float = 0.01

    # --- Market assumptions ---
    inflation: float = 0.01
    inflation_volatility: float = 0.01
    inflation_min: float = -0.02
    inflation_max: float = 0.08
    # When ON, the simulator projects the CHF-denominated 2026 tax-law amounts
    # forward with the same inflation assumption used for salary/rent/etc. This
    # keeps the long-horizon nominal simulation internally consistent, but it is
    # still a modeling assumption rather than a promise of future published values.
    index_tax_parameters_with_inflation: bool = True
    # Expected return of a broad world stock ETF measured in USD.
    stock_growth_world_usd: float = 0.06
    # Average yearly CHF strengthening versus USD. Negative values mean the CHF weakens.
    chf_appreciation_vs_usd: float = 0.015
    stock_volatility: float = 0.16
    house_growth: float = 0.02
    house_volatility: float = 0.05
    asset_correlation: float = 0.3
    salary_growth: float = 0.005
    salary_growth_volatility: float = 0.02
    # Applies to the separate market-rent path used for VL and forced-sale re-renting.
    # The protected/current-lease renter path is controlled by the reference-rate logic.
    market_rent_real_growth: float = 0.0
    rent_growth_volatility: float = 0.01
    mortgage_rate_volatility: float = 0.005
    mortgage_rate_min: float = 0.0
    mortgage_rate_max: float = 0.10
    stress_event_probability: float = 0.0
    # 0 means each year's stress draw is independent. Higher values keep the
    # same long-run share of stress years but make them cluster into runs.
    stress_persistence: float = 0.35
    stress_stock_drawdown: float = 0.25
    stress_house_drawdown: float = 0.10
    stress_salary_hit: float = 0.10
    stress_rent_jump: float = 0.05
    stress_rate_jump: float = 0.015

    # --- Fees ---
    portfolio_ter: float = 0.001
    pillar_3a_ter: float = 0.0075

    # --- Dividend treatment ---
    dividend_yield: float = 0.015
    # DA-1 is OFF by default. The user must explicitly enter how much of the
    # modeled dividend stream is personally claimable as DA-1-eligible foreign
    # income. A blanket 15 % credit on all dividends is too generous.
    da1_eligible_dividend_share: float = 0.0
    da1_non_refundable_withholding_rate: float = 0.15
    da1_minimum_non_refundable_tax: float = 100.0

    # --- Pillar 3a ---
    # Household pillar 3a balance already accumulated before the simulation starts.
    initial_pillar_3a_assets: float = 0.0
    pillar_3a_annual_per_person: float = 7_258.0
    # If a partner is not affiliated to a pension institution, the simulator
    # falls back to the Swiss "20% of net earned income" rule instead of the
    # standard employee cap.
    p1_pillar2_affiliated: bool = True
    p2_pillar2_affiliated: bool = True
    pillar_3a_unaffiliated_rate: float = 0.20
    pillar_3a_unaffiliated_max: float = 36_288.0
    pillar_3a_withdrawal_tax_rate: float = 0.08  # still a simplified approximation
    pillar_3a_growth_chf: float | None = None
    pillar_3a_volatility: float | None = None
    pillar_3a_correlation_to_portfolio: float = 1.0

    # --- Tax framework (Vaud / commune) ---
    social_security_rate: float = 0.13  # blended household assumption
    canton_multiplier: float = 1.55
    # Shipped baseline defaults below correspond to Lausanne's published 2026
    # rates. The Streamlit commune selector can replace them with another Vaud
    # commune's official 2026 values.
    commune_multiplier: float = 0.785
    # Official Vaud income-tax reduction schedule adopted by the Grand Council:
    # 5% for tax year 2026, then 7% from tax year 2027 onward.
    use_official_cantonal_income_tax_reduction_schedule: bool = True
    official_cantonal_income_tax_reduction_schedule: tuple[tuple[int, float], ...] = (
        (2026, 0.05),
        (2027, 0.07),
    )
    # Manual flat override used only when the official schedule flag is off.
    cantonal_income_tax_reduction_rate: float = 0.05
    cantonal_income_tax_reduction_start_year: int = 2026
    cantonal_income_tax_reduction_end_year: int = 2026
    # Separate communal impôt foncier on the property's fiscal value.
    # The shipped baseline uses Lausanne's official 2026 rate.
    communal_property_tax_rate: float = 0.0015
    wealth_tax_value_ratio: float = 0.75
    # Impôt foncier is based on the property's fiscal assessment at 1 January.
    # Keep this separate from wealth-tax value so each can be stress-tested.
    property_tax_value_ratio: float = 0.75
    vl_factor_cantonal: float = 0.65
    vl_factor_federal: float = 0.90

    # User-set flat maintenance deduction assumptions before 2029. Federal
    # direct tax and Vaud do not use the same age buckets, so the simulator
    # keeps them separate instead of pretending one rate fits both systems.
    maintenance_deduction_rate_federal: float = 0.10
    maintenance_deduction_rate_cantonal: float = 0.20

    # --- Fixed deductions (simplified where case-specific) ---
    fed_deduction_professional_flat: float = 4_000.0
    cant_deduction_professional_rate: float = 0.03
    cant_deduction_professional_min: float = 2_000.0
    cant_deduction_professional_max: float = 4_000.0
    fed_deduction_transport: float = 3_300.0
    cant_deduction_transport: float = 3_200.0  # simplifying assumption
    fed_deduction_meals: float = 1_600.0
    cant_deduction_meals: float = 1_600.0
    # Federal insurance caps differ depending on whether pillar-2 / pillar-3a
    # contributions exist. The shipped defaults match the official 2026
    # ESTV amounts, but they are still caps rather than your actual premiums.
    fed_deduction_insurance_single: float = 1_800.0
    fed_deduction_insurance_single_without_pillars: float = 2_700.0
    fed_deduction_insurance_married: float = 3_700.0
    fed_deduction_insurance_married_without_pillars: float = 5_550.0
    cant_deduction_insurance_single: float = 5_000.0
    cant_deduction_insurance_married: float = 9_900.0
    fed_deduction_insurance_child_supplement: float = 700.0
    cant_deduction_insurance_child_supplement: float = 1_300.0
    # These are the deduction caps. Actual deductible childcare spending can be
    # lower in real life.
    fed_deduction_childcare_per_child: float = 25_800.0
    cant_deduction_childcare_per_child: float = 15_200.0
    fed_deduction_per_child: float = 6_800.0
    cant_deduction_per_child: float = 13_200.0
    fed_deduction_married: float = 2_800.0
    fed_deduction_double_income_min: float = 8_600.0
    fed_deduction_double_income_max: float = 14_100.0
    # Vaud's 2026 married double-income deduction has no official minimum.
    cant_deduction_double_income_min: float = 0.0
    cant_deduction_double_income_max: float = 1_700.0

    # --- 2029 reform ---
    reform_year: int = 2029
    # The shipped baseline keeps these ON because the default household assumes
    # both unmarried partners are buying their first owner-occupied home in
    # Switzerland. This still needs manual confirmation in real life.
    first_time_home_buyer_p1: bool = True
    first_time_home_buyer_p2: bool = True
    # In married mode, the shipped baseline also assumes likely eligibility.
    first_time_home_buyer_married: bool = True
    first_time_buyer_years: int = 10
    # These fields let the model represent a deduction window that was already
    # partly used before the simulation start year, without pretending the whole
    # ownership path began earlier.
    first_time_buyer_years_used_before_start_p1: int = 0
    first_time_buyer_years_used_before_start_p2: int = 0
    first_time_buyer_years_used_before_start_married: int = 0
    first_time_buyer_interest_deduction_single_max: float = 5_000.0
    first_time_buyer_interest_deduction_married_max: float = 10_000.0

    # --- Liquidity shortfall modelling ---
    liquidity_shortfall_rate: float = 0.03
    force_buy_sale_on_liquidity_crisis: bool = True
    liquidity_crisis_buffer_months: float = 6.0
    # Simple forced-sale friction layer: some cash is lost for good, some rent
    # is paid during the move/search transition, and the new rental deposit is
    # locked cash rather than a permanent wealth loss.
    forced_sale_extra_cost_chf: float = 10_000.0
    forced_sale_transition_months: float = 2.0
    forced_sale_rental_deposit_months: float = 3.0

    def purchase_cash_outlay(self) -> float:
        """Return money the buyer needs at purchase for downpayment plus buying costs."""
        return self.downpayment + self.house_price * self.buying_costs_pct

    def initial_pillar_3a_withdrawal_for_purchase(self) -> float:
        """Return gross opening 3a withdrawal needed for the buyer purchase."""
        shortfall = max(0.0, self.purchase_cash_outlay() - self.initial_liquid_assets)
        if shortfall <= 0.0:
            return 0.0
        net_fraction = 1.0 - self.pillar_3a_withdrawal_tax_rate
        if net_fraction <= 0.0:
            return math.inf
        return min(self.initial_pillar_3a_assets, shortfall / net_fraction)

    def validate(self) -> None:
        """Raise ValueError on inconsistent or numerically unsafe inputs."""
        for name, value in self.__dict__.items():
            if isinstance(value, bool) or value is None:
                continue
            if isinstance(value, (int, float)) and not math.isfinite(float(value)):
                raise ValueError(f"{name} must be finite, got {value!r}")

        if self.start_year < TAX_PARAMETER_REFERENCE_YEAR:
            raise ValueError(
                f"start_year must be {TAX_PARAMETER_REFERENCE_YEAR} or later; "
                "the embedded tax tables are not historical tables"
            )
        if self.rng_seed < 0:
            raise ValueError("rng_seed must be non-negative")
        if self.parallel_workers == 0 or self.parallel_workers < -1:
            raise ValueError("parallel_workers must be positive, or -1 for all CPUs")

        bounded_zero_one = (
            "salary_split",
            "ownership_split",
            "portfolio_split",
            "child_deduction_split_to_p1",
            "childcare_spend_split_to_p1",
            "vaud_child_quotient_share_to_p1",
            "ltv_floor",
            "buying_costs_pct",
            "sale_cost_pct",
            "rent_reference_rate_smoothing",
            "rent_cpi_passthrough",
            "rent_reference_rate_increase_per_step",
            "rent_reference_rate_decrease_per_step",
            "social_security_rate",
            "maintenance_rate",
            "maintenance_deduction_rate_federal",
            "maintenance_deduction_rate_cantonal",
            "inflation_volatility",
            "salary_growth_volatility",
            "rent_growth_volatility",
            "mortgage_rate_volatility",
            "portfolio_ter",
            "pillar_3a_ter",
            "pillar_3a_unaffiliated_rate",
            "pillar_3a_withdrawal_tax_rate",
            "cant_deduction_professional_rate",
            "cantonal_income_tax_reduction_rate",
            "da1_eligible_dividend_share",
            "da1_non_refundable_withholding_rate",
            "stress_event_probability",
            "stress_persistence",
            "stress_stock_drawdown",
            "stress_house_drawdown",
            "stress_salary_hit",
            "stress_rent_jump",
            "stress_rate_jump",
        )
        for name in bounded_zero_one:
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1, got {value!r}")

        non_negative_amounts = (
            "salary_total",
            "initial_liquid_assets",
            "interest_rate",
            "amortization_annual",
            "dividend_yield",
            "initial_pillar_3a_assets",
            "pillar_3a_annual_per_person",
            "fed_deduction_professional_flat",
            "cant_deduction_professional_min",
            "cant_deduction_professional_max",
            "fed_deduction_transport",
            "cant_deduction_transport",
            "fed_deduction_meals",
            "cant_deduction_meals",
            "fed_deduction_insurance_single",
            "fed_deduction_insurance_single_without_pillars",
            "fed_deduction_insurance_married",
            "fed_deduction_insurance_married_without_pillars",
            "cant_deduction_insurance_single",
            "cant_deduction_insurance_married",
            "fed_deduction_insurance_child_supplement",
            "cant_deduction_insurance_child_supplement",
            "fed_deduction_childcare_per_child",
            "cant_deduction_childcare_per_child",
            "fed_deduction_per_child",
            "cant_deduction_per_child",
            "fed_deduction_married",
            "fed_deduction_double_income_min",
            "fed_deduction_double_income_max",
            "cant_deduction_double_income_min",
            "cant_deduction_double_income_max",
        )
        for name in non_negative_amounts:
            value = getattr(self, name)
            if value < 0.0:
                raise ValueError(f"{name} must be non-negative")

        if self.house_price <= 0.0:
            raise ValueError("house_price must be strictly positive")
        if not 0.0 <= self.downpayment <= self.house_price:
            raise ValueError("downpayment must be between 0 and house_price")
        if self.mortgage_rate_min > self.mortgage_rate_max:
            raise ValueError("mortgage_rate_min must be less than or equal to mortgage_rate_max")
        if not self.mortgage_rate_min <= self.interest_rate <= self.mortgage_rate_max:
            raise ValueError(
                "interest_rate must be between mortgage_rate_min and mortgage_rate_max; "
                "with zero volatility, the floor and cap should not change the mortgage rate"
            )
        purchase_cash_outlay = self.purchase_cash_outlay()
        usable_initial_3a = self.initial_pillar_3a_assets * (
            1.0 - self.pillar_3a_withdrawal_tax_rate
        )
        if purchase_cash_outlay > self.initial_liquid_assets + usable_initial_3a + 1e-9:
            raise ValueError(
                "downpayment plus buying costs are higher than initial cash and taxable "
                "investments plus initial 3a savings after estimated withdrawal tax; "
                "increase initial_liquid_assets or initial_pillar_3a_assets, or lower "
                "downpayment/buying costs"
            )
        if self.base_rent_monthly < 0.0 or self.house_market_rent_monthly < 0.0:
            raise ValueError("rent inputs must be non-negative")
        if self.annual_other_consumption < 0.0:
            raise ValueError("annual_other_consumption must be non-negative")
        if self.iterations <= 0 or self.years <= 0:
            raise ValueError("iterations and years must be strictly positive")
        if self.stock_growth_world_usd <= -1.0 or self.house_growth <= -1.0:
            raise ValueError("growth assumptions must be greater than -100%")
        if self.pillar_3a_growth_chf is not None and self.pillar_3a_growth_chf <= -1.0:
            raise ValueError("pillar_3a_growth_chf must be greater than -100%")
        if self.chf_appreciation_vs_usd <= -1.0:
            raise ValueError("chf_appreciation_vs_usd must be greater than -100%")
        if self.inflation <= -1.0:
            raise ValueError("inflation must be greater than -100%")
        if self.inflation < self.inflation_min or self.inflation > self.inflation_max:
            raise ValueError("inflation must lie between inflation_min and inflation_max")
        if self.salary_growth <= -1.0:
            raise ValueError("salary_growth must be greater than -100%")
        if self.market_rent_real_growth <= -1.0:
            raise ValueError("market_rent_real_growth must be greater than -100%")
        if self.stock_volatility < 0.0 or self.house_volatility < 0.0:
            raise ValueError("volatilities must be non-negative")
        if self.pillar_3a_volatility is not None and self.pillar_3a_volatility < 0.0:
            raise ValueError("pillar_3a_volatility must be non-negative")
        if self.stock_volatility > 2.0 or self.house_volatility > 2.0:
            raise ValueError("stock_volatility and house_volatility must be 200% or lower")
        if self.pillar_3a_volatility is not None and self.pillar_3a_volatility > 2.0:
            raise ValueError("pillar_3a_volatility must be 200% or lower")
        if not -1.0 <= self.asset_correlation <= 1.0:
            raise ValueError("asset_correlation must be between -1 and 1")
        if not -1.0 <= self.pillar_3a_correlation_to_portfolio <= 1.0:
            raise ValueError("pillar_3a_correlation_to_portfolio must be between -1 and 1")
        if self.n_children < 0:
            raise ValueError("n_children must be non-negative")
        if self.household_status == "married" and self.n_children > 5:
            raise ValueError("married mode currently supports at most 5 children")
        if self.household_status == "unmarried" and self.n_children > 3:
            raise ValueError(
                "unmarried mode currently supports at most 3 children because the "
                "published Vaud quotient-cap table stops there"
            )
        if self.child_dependent_years < 0:
            raise ValueError("child_dependent_years must be non-negative")
        if self.childcare_deduction_years < 0:
            raise ValueError("childcare_deduction_years must be non-negative")
        if self.annual_childcare_spend_household < 0.0:
            raise ValueError("annual_childcare_spend_household must be non-negative")
        if self.household_status not in {"unmarried", "married"}:
            raise ValueError("household_status must be 'unmarried' or 'married'")
        if self.canton_multiplier < 0.0:
            raise ValueError("canton_multiplier must be non-negative")
        if self.commune_multiplier < 0.0:
            raise ValueError("commune_multiplier must be non-negative")
        if self.first_time_buyer_years <= 0:
            raise ValueError("first_time_buyer_years must be strictly positive")
        for name in (
            "first_time_buyer_years_used_before_start_p1",
            "first_time_buyer_years_used_before_start_p2",
            "first_time_buyer_years_used_before_start_married",
        ):
            value = getattr(self, name)
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
            if value > self.first_time_buyer_years:
                raise ValueError(
                    f"{name} cannot exceed first_time_buyer_years "
                    f"({self.first_time_buyer_years}), got {value!r}"
                )
        if self.first_time_buyer_interest_deduction_single_max < 0.0:
            raise ValueError(
                "first_time_buyer_interest_deduction_single_max must be non-negative"
            )
        if self.first_time_buyer_interest_deduction_married_max < 0.0:
            raise ValueError(
                "first_time_buyer_interest_deduction_married_max must be non-negative"
            )
        if (
            self.cantonal_income_tax_reduction_start_year
            > self.cantonal_income_tax_reduction_end_year
        ):
            raise ValueError(
                "cantonal_income_tax_reduction_start_year must be less than or equal to "
                "cantonal_income_tax_reduction_end_year"
            )
        if not self.official_cantonal_income_tax_reduction_schedule:
            raise ValueError("official_cantonal_income_tax_reduction_schedule must not be empty")
        last_start_year: int | None = None
        for start_year, rate in self.official_cantonal_income_tax_reduction_schedule:
            if not math.isfinite(float(start_year)):
                raise ValueError(
                    "official_cantonal_income_tax_reduction_schedule years must be finite"
                )
            if start_year < TAX_PARAMETER_REFERENCE_YEAR:
                raise ValueError(
                    "official_cantonal_income_tax_reduction_schedule cannot start before "
                    f"{TAX_PARAMETER_REFERENCE_YEAR}"
                )
            if not math.isfinite(float(rate)):
                raise ValueError(
                    "official_cantonal_income_tax_reduction_schedule rates must be finite"
                )
            if last_start_year is not None and start_year <= last_start_year:
                raise ValueError(
                    "official_cantonal_income_tax_reduction_schedule must be sorted by "
                    "strictly increasing start year"
                )
            if not 0.0 <= rate <= 1.0:
                raise ValueError(
                    "official_cantonal_income_tax_reduction_schedule rates must be between 0 and 1"
                )
            last_start_year = start_year
        if self.cant_deduction_professional_min < 0.0:
            raise ValueError("cant_deduction_professional_min must be non-negative")
        if self.cant_deduction_professional_max < self.cant_deduction_professional_min:
            raise ValueError(
                "cant_deduction_professional_max must be greater than or equal to the minimum"
            )
        if self.da1_minimum_non_refundable_tax < 0.0:
            raise ValueError("da1_minimum_non_refundable_tax must be non-negative")
        if self.pillar_3a_unaffiliated_max < 0.0:
            raise ValueError("pillar_3a_unaffiliated_max must be non-negative")
        if self.amortization_strategy not in {"direct", "indirect_3a"}:
            raise ValueError("amortization_strategy must be 'direct' or 'indirect_3a'")
        if self.rent_reference_rate_current < 0.0:
            raise ValueError("rent_reference_rate_current must be non-negative")
        if self.rent_reference_rate_step <= 0.0:
            raise ValueError("rent_reference_rate_step must be strictly positive")
        if self.rent_reference_rate_increase_per_step < 0.0:
            raise ValueError("rent_reference_rate_increase_per_step must be non-negative")
        if self.rent_reference_rate_decrease_per_step < 0.0:
            raise ValueError("rent_reference_rate_decrease_per_step must be non-negative")
        if not 0.0 <= self.communal_property_tax_rate <= 0.0015:
            raise ValueError(
                "communal_property_tax_rate must be between 0 and 0.0015 "
                "(0 to 1.5 per mille)"
            )
        if not 0.0 <= self.wealth_tax_value_ratio <= 1.0:
            raise ValueError("wealth_tax_value_ratio must be between 0 and 1")
        if not 0.0 <= self.property_tax_value_ratio <= 1.0:
            raise ValueError("property_tax_value_ratio must be between 0 and 1")
        if self.mortgage_rate_min < 0.0 or self.mortgage_rate_max < 0.0:
            raise ValueError("mortgage rate bounds must be non-negative")
        if self.mortgage_rate_min > self.mortgage_rate_max:
            raise ValueError("mortgage_rate_min must be less than or equal to mortgage_rate_max")
        if self.inflation_min <= -1.0 or self.inflation_max <= -1.0:
            raise ValueError("inflation bounds must be greater than -100%")
        if self.inflation_min > self.inflation_max:
            raise ValueError("inflation_min must be less than or equal to inflation_max")
        if self.liquidity_shortfall_rate < 0.0:
            raise ValueError("liquidity_shortfall_rate must be non-negative")
        if self.liquidity_crisis_buffer_months < 0.0:
            raise ValueError("liquidity_crisis_buffer_months must be non-negative")
        if self.forced_sale_extra_cost_chf < 0.0:
            raise ValueError("forced_sale_extra_cost_chf must be non-negative")
        if self.forced_sale_transition_months < 0.0:
            raise ValueError("forced_sale_transition_months must be non-negative")
        if not 0.0 <= self.forced_sale_rental_deposit_months <= 3.0:
            raise ValueError(
                "forced_sale_rental_deposit_months must be between 0 and 3 months"
            )
        if self.household_status == "unmarried" and self.n_children > 0:
            for name in ("child_deduction_split_to_p1", "vaud_child_quotient_share_to_p1"):
                value = getattr(self, name)
                half_child_steps = value * self.n_children * 2.0
                if not math.isclose(half_child_steps, round(half_child_steps), abs_tol=1e-9):
                    raise ValueError(
                        f"{name} must allocate children in whole-child or half-child increments; "
                        f"for n_children={self.n_children}, got {value!r}"
                    )

    @property
    def stock_growth_chf(self) -> float:
        """Effective stock return in CHF after translating a USD return into CHF."""
        return (1.0 + self.stock_growth_world_usd) / (1.0 + self.chf_appreciation_vs_usd) - 1.0

    def tax_parameter_index_factor(self, year: int) -> float:
        """Project CHF-denominated 2026 tax-law amounts into a simulation year."""
        if not self.index_tax_parameters_with_inflation:
            return 1.0
        if year <= TAX_PARAMETER_REFERENCE_YEAR:
            return 1.0
        return (1.0 + max(0.0, self.inflation)) ** (year - TAX_PARAMETER_REFERENCE_YEAR)

    def indexed_tax_amount(self, amount: float, year: int) -> float:
        return amount * self.tax_parameter_index_factor(year)

    def indexed_pillar_3a_cap(self, year: int) -> float:
        return self.indexed_tax_amount(self.pillar_3a_annual_per_person, year)

    def cantonal_income_tax_reduction_for_year(self, year: int) -> float:
        """Return the Vaud cantonal income-tax reduction rate for one tax year."""
        if not self.use_official_cantonal_income_tax_reduction_schedule:
            if self.cantonal_income_tax_reduction_start_year <= year <= self.cantonal_income_tax_reduction_end_year:
                return self.cantonal_income_tax_reduction_rate
            return 0.0

        rate = 0.0
        for start_year, candidate_rate in self.official_cantonal_income_tax_reduction_schedule:
            if year < start_year:
                break
            rate = candidate_rate
        return rate
