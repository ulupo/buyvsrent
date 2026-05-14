"""
simulator.py
Monte Carlo buy-vs-rent simulator for a Vaud / commune household.
"""
from __future__ import annotations

from dataclasses import dataclass
import os

import numpy as np
from joblib import Parallel, delayed

from src.config import SwissConfig, IGI_SCHEDULE
from src.tax_engine import VaudTaxEngine, vaud_igi_rate


@dataclass
class SimulationResult:
    """Year-by-year mark-to-market paths plus horizon wealth after assumed liquidation."""

    years_axis: np.ndarray
    buy_net_worth: np.ndarray
    rent_net_worth: np.ndarray
    buy_terminal_liquid: np.ndarray
    rent_terminal_liquid: np.ndarray
    buy_portfolio: np.ndarray
    rent_portfolio: np.ndarray
    buy_pillar_3a: np.ndarray
    rent_pillar_3a: np.ndarray
    house_val: np.ndarray
    debt: np.ndarray
    buy_tax: np.ndarray
    rent_tax: np.ndarray
    buy_surplus: np.ndarray
    rent_surplus: np.ndarray
    buy_rental_deposit: np.ndarray
    buy_ruin_any: np.ndarray
    rent_ruin_any: np.ndarray
    buy_forced_sale_any: np.ndarray
    inflation_rate: np.ndarray
    inflation_index: np.ndarray
    tax_index_factor: np.ndarray
    cfg: SwissConfig

    @property
    def buy_cash_crisis_any(self) -> np.ndarray:
        """Buyer paths with either unresolved negative cash or a forced-sale crisis."""
        return np.logical_or(self.buy_ruin_any, self.buy_forced_sale_any)

    @property
    def rent_cash_crisis_any(self) -> np.ndarray:
        """Renter paths with unresolved negative cash in at least one year."""
        return self.rent_ruin_any


@dataclass(frozen=True)
class _SimulationShocks:
    portfolio_gf: np.ndarray
    house_gf: np.ndarray
    pillar_3a_gf: np.ndarray
    inflation_shocks: np.ndarray
    salary_growth_shocks: np.ndarray
    rent_growth_shocks: np.ndarray
    mortgage_rate_shocks: np.ndarray
    stress_events: np.ndarray


@dataclass(frozen=True)
class _SimulationChunk:
    buy_net_worth: np.ndarray
    rent_net_worth: np.ndarray
    buy_terminal_liquid: np.ndarray
    rent_terminal_liquid: np.ndarray
    buy_portfolio: np.ndarray
    rent_portfolio: np.ndarray
    buy_pillar_3a: np.ndarray
    rent_pillar_3a: np.ndarray
    house_val: np.ndarray
    debt: np.ndarray
    buy_tax: np.ndarray
    rent_tax: np.ndarray
    buy_surplus: np.ndarray
    rent_surplus: np.ndarray
    buy_rental_deposit: np.ndarray
    buy_ruin_any: np.ndarray
    rent_ruin_any: np.ndarray
    buy_forced_sale_any: np.ndarray
    inflation_rate: np.ndarray
    inflation_index: np.ndarray
    tax_index_factor: np.ndarray


def _effective_parallel_workers(parallel_workers: int, iterations: int) -> int:
    if parallel_workers == -1:
        return max(1, min(iterations, os.cpu_count() or 1))
    return max(1, min(iterations, parallel_workers))


def _chunk_ranges(iterations: int, worker_count: int) -> list[tuple[int, int]]:
    worker_count = max(1, min(iterations, worker_count))
    edges = np.linspace(0, iterations, worker_count + 1, dtype=int)
    return [
        (int(start), int(stop))
        for start, stop in zip(edges[:-1], edges[1:])
        if start < stop
    ]


def _combine_chunks(cfg: SwissConfig, chunks: list[_SimulationChunk]) -> SimulationResult:
    years_axis = np.arange(cfg.start_year, cfg.start_year + cfg.years)

    def concat(name: str) -> np.ndarray:
        return np.concatenate([getattr(chunk, name) for chunk in chunks], axis=0)

    return SimulationResult(
        years_axis=years_axis,
        buy_net_worth=concat("buy_net_worth"),
        rent_net_worth=concat("rent_net_worth"),
        buy_terminal_liquid=concat("buy_terminal_liquid"),
        rent_terminal_liquid=concat("rent_terminal_liquid"),
        buy_portfolio=concat("buy_portfolio"),
        rent_portfolio=concat("rent_portfolio"),
        buy_pillar_3a=concat("buy_pillar_3a"),
        rent_pillar_3a=concat("rent_pillar_3a"),
        house_val=concat("house_val"),
        debt=concat("debt"),
        buy_tax=concat("buy_tax"),
        rent_tax=concat("rent_tax"),
        buy_surplus=concat("buy_surplus"),
        rent_surplus=concat("rent_surplus"),
        buy_rental_deposit=concat("buy_rental_deposit"),
        buy_ruin_any=concat("buy_ruin_any"),
        rent_ruin_any=concat("rent_ruin_any"),
        buy_forced_sale_any=concat("buy_forced_sale_any"),
        inflation_rate=concat("inflation_rate"),
        inflation_index=concat("inflation_index"),
        tax_index_factor=concat("tax_index_factor"),
        cfg=cfg,
    )


def _draw_correlated_lognormal_factors(
    rng: np.random.Generator,
    iterations: int,
    years: int,
    mu_stock: float,
    sigma_stock: float,
    mu_house: float,
    sigma_house: float,
    correlation: float,
    ter_stock: float,
    ter_house: float = 0.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Draw annual growth factors for stocks and housing."""
    if correlation >= 1.0:
        z_stock = rng.standard_normal(size=(iterations, years))
        z_house = z_stock
    elif correlation <= -1.0:
        z_stock = rng.standard_normal(size=(iterations, years))
        z_house = -z_stock
    else:
        corr = np.array([[1.0, correlation], [correlation, 1.0]])
        chol = np.linalg.cholesky(corr)
        z = rng.standard_normal(size=(2, iterations, years))
        z_corr = np.einsum("ij,jnt->int", chol, z)
        z_stock = z_corr[0]
        z_house = z_corr[1]

    drift_stock = np.log1p(mu_stock) - 0.5 * sigma_stock**2 - ter_stock
    drift_house = np.log1p(mu_house) - 0.5 * sigma_house**2 - ter_house
    gf_stock = np.exp(drift_stock + sigma_stock * z_stock)
    gf_house = np.exp(drift_house + sigma_house * z_house)
    return gf_stock, gf_house


def _draw_lognormal_factors_same_shocks(
    shocks: np.ndarray,
    mu: float,
    sigma: float,
    ter: float,
) -> np.ndarray:
    drift = np.log1p(mu) - 0.5 * sigma**2 - ter
    return np.exp(drift + sigma * shocks)


def _correlate_with_reference_shocks(
    rng: np.random.Generator,
    reference_shocks: np.ndarray,
    correlation: float,
) -> np.ndarray:
    if (
        not np.all(np.isfinite(reference_shocks))
        or np.nanstd(reference_shocks) <= 1e-12
    ):
        if correlation >= 1.0 or correlation <= -1.0:
            return np.zeros_like(reference_shocks)
        return rng.standard_normal(size=reference_shocks.shape)
    if correlation >= 1.0:
        return reference_shocks
    if correlation <= -1.0:
        return -reference_shocks
    independent = rng.standard_normal(size=reference_shocks.shape)
    return correlation * reference_shocks + np.sqrt(1.0 - correlation**2) * independent


def _recover_stock_shocks_from_factors(
    gf: np.ndarray,
    mu: float,
    sigma: float,
    ter: float,
) -> np.ndarray:
    if sigma == 0.0:
        return np.zeros_like(gf)
    drift = np.log1p(mu) - 0.5 * sigma**2 - ter
    finite_gf = np.nan_to_num(
        gf,
        nan=np.finfo(float).tiny,
        posinf=np.finfo(float).max,
        neginf=np.finfo(float).tiny,
    )
    finite_gf = np.clip(finite_gf, np.finfo(float).tiny, np.finfo(float).max)
    return (np.log(finite_gf) - drift) / sigma


def _compound_liquid_balance(
    balance_before_growth: float,
    growth_factor: float,
    shortfall_rate: float,
) -> float:
    """Positive balances compound in risky assets; negative balances do not."""
    if balance_before_growth >= 0.0:
        return balance_before_growth * growth_factor
    return balance_before_growth * (1.0 + shortfall_rate)


def _split_amortization(
    required_amortization: float,
    household_3a: float,
    strategy: str,
) -> tuple[float, float]:
    """Return the split of required amortization between direct cash and pillar 3a."""
    if strategy != "indirect_3a" or required_amortization <= 0.0:
        return required_amortization, 0.0
    indirect_amortization = min(required_amortization, household_3a)
    direct_amortization = required_amortization - indirect_amortization
    return direct_amortization, indirect_amortization


def _scale_household_3a_contributions(
    p1_cap: float,
    p2_cap: float,
    total_contribution: float,
) -> tuple[float, float]:
    """Scale partner caps down proportionally when the full household cap is unaffordable."""
    cap_total = p1_cap + p2_cap
    if cap_total <= 0.0 or total_contribution <= 0.0:
        return 0.0, 0.0
    if total_contribution >= cap_total:
        return p1_cap, p2_cap
    scale = total_contribution / cap_total
    return p1_cap * scale, p2_cap * scale


def _solve_affordable_household_3a_total(
    max_total: float,
    cash_after_tax_for_total,
) -> float:
    """Find the largest modeled 3a contribution that does not push liquid cash below zero."""
    if max_total <= 0.0:
        return 0.0
    if cash_after_tax_for_total(0.0) <= 0.0:
        return 0.0
    if cash_after_tax_for_total(max_total) >= 0.0:
        return max_total
    lo = 0.0
    hi = max_total
    for _ in range(48):
        mid = 0.5 * (lo + hi)
        if cash_after_tax_for_total(mid) >= 0.0:
            lo = mid
        else:
            hi = mid
    return lo


def _pillar_3a_contribution_cap(
    gross_salary: float,
    *,
    pillar2_affiliated: bool,
    tax_index_factor: float,
    cfg: SwissConfig,
) -> float:
    """Return the modeled yearly 3a contribution cap for one adult."""
    if gross_salary <= 0.0:
        return 0.0
    if pillar2_affiliated:
        return cfg.pillar_3a_annual_per_person * tax_index_factor
    earned_income_proxy = max(0.0, gross_salary * (1.0 - cfg.social_security_rate))
    return min(
        earned_income_proxy * cfg.pillar_3a_unaffiliated_rate,
        cfg.pillar_3a_unaffiliated_max * tax_index_factor,
    )


def _clamp_growth_rate(value: float) -> float:
    return max(-0.95, value)


def _clamp_rate(value: float, minimum: float, maximum: float) -> float:
    return min(maximum, max(minimum, value))


def _round_to_step_nearest(value: float, step: float) -> float:
    if step <= 0.0:
        return value
    return max(0.0, round(value / step) * step)


def _swiss_contract_rent_growth(
    previous_reference_rate: float,
    next_reference_rate: float,
    inflation_t: float,
    cfg: SwissConfig,
) -> float:
    step_change = int(
        round((next_reference_rate - previous_reference_rate) / cfg.rent_reference_rate_step)
    )
    growth_factor = 1.0
    if step_change > 0:
        growth_factor *= (1.0 + cfg.rent_reference_rate_increase_per_step) ** step_change
    elif step_change < 0:
        growth_factor *= (1.0 - cfg.rent_reference_rate_decrease_per_step) ** (-step_change)
    if inflation_t > 0.0 and cfg.rent_cpi_passthrough > 0.0:
        growth_factor *= 1.0 + cfg.rent_cpi_passthrough * inflation_t
    return growth_factor - 1.0


def _communal_property_tax_for_year(
    beginning_house_value: float,
    cfg: SwissConfig,
) -> float:
    """Vaud impôt foncier uses the property's fiscal value at the start of the year."""
    if beginning_house_value <= 0.0 or cfg.communal_property_tax_rate <= 0.0:
        return 0.0
    fiscal_value_proxy = beginning_house_value * cfg.property_tax_value_ratio
    return fiscal_value_proxy * cfg.communal_property_tax_rate


def _stress_transition_probabilities(
    stress_probability: float,
    persistence: float,
) -> tuple[float, float]:
    """Return transition probabilities that preserve the long-run stress share."""
    if stress_probability <= 0.0:
        return 0.0, 0.0
    if stress_probability >= 1.0:
        return 1.0, 1.0
    persistence = min(1.0, max(0.0, persistence))
    enter_prob = stress_probability * (1.0 - persistence)
    stay_prob = stress_probability + (1.0 - stress_probability) * persistence
    return enter_prob, stay_prob


def _draw_stress_events_from_uniforms(
    uniforms: np.ndarray,
    stress_probability: float,
    persistence: float,
) -> np.ndarray:
    """Turn uniform draws into clustered or independent yearly stress events."""
    n_iter, years = uniforms.shape
    stress_events = np.zeros((n_iter, years), dtype=bool)
    if years == 0:
        return stress_events
    enter_prob, stay_prob = _stress_transition_probabilities(stress_probability, persistence)
    stress_events[:, 0] = uniforms[:, 0] < stress_probability
    for t in range(1, years):
        probs = np.where(stress_events[:, t - 1], stay_prob, enter_prob)
        stress_events[:, t] = uniforms[:, t] < probs
    return stress_events


def _simulate_chunk(
    cfg: SwissConfig,
    start: int,
    stop: int,
    shocks: _SimulationShocks,
) -> _SimulationChunk:
    n_iter, years = stop - start, cfg.years
    portfolio_gf = shocks.portfolio_gf
    house_gf = shocks.house_gf
    pillar_3a_gf = shocks.pillar_3a_gf
    inflation_shocks = shocks.inflation_shocks
    salary_growth_shocks = shocks.salary_growth_shocks
    rent_growth_shocks = shocks.rent_growth_shocks
    mortgage_rate_shocks = shocks.mortgage_rate_shocks
    stress_events = shocks.stress_events

    engine = VaudTaxEngine(cfg)

    buy_net_worth = np.zeros((n_iter, years))
    rent_net_worth = np.zeros((n_iter, years))
    buy_portfolio = np.zeros((n_iter, years))
    rent_portfolio = np.zeros((n_iter, years))
    buy_pillar_3a = np.zeros((n_iter, years))
    rent_pillar_3a = np.zeros((n_iter, years))
    house_val_arr = np.zeros((n_iter, years))
    debt_arr = np.zeros((n_iter, years))
    buy_tax_arr = np.zeros((n_iter, years))
    rent_tax_arr = np.zeros((n_iter, years))
    buy_surplus_arr = np.zeros((n_iter, years))
    rent_surplus_arr = np.zeros((n_iter, years))
    buy_rental_deposit_arr = np.zeros((n_iter, years))
    inflation_rate_arr = np.zeros((n_iter, years))
    inflation_index_arr = np.zeros((n_iter, years))
    tax_index_factor_arr = np.zeros((n_iter, years))
    buy_ruin = np.zeros(n_iter, dtype=bool)
    rent_ruin = np.zeros(n_iter, dtype=bool)
    buy_forced_sale = np.zeros(n_iter, dtype=bool)
    buy_terminal = np.zeros(n_iter)
    rent_terminal = np.zeros(n_iter)
    purchase_cash_outlay = cfg.purchase_cash_outlay()
    initial_3a_purchase_withdrawal = cfg.initial_pillar_3a_withdrawal_for_purchase()
    initial_3a_purchase_net = initial_3a_purchase_withdrawal * (
        1.0 - cfg.pillar_3a_withdrawal_tax_rate
    )

    for row, it in enumerate(range(start, stop)):
        buyer_portfolio_cash = (
            cfg.initial_liquid_assets + initial_3a_purchase_net - purchase_cash_outlay
        )
        renter_portfolio_cash = cfg.initial_liquid_assets
        buyer_3a = cfg.initial_pillar_3a_assets - initial_3a_purchase_withdrawal
        renter_3a = cfg.initial_pillar_3a_assets
        house_value = cfg.house_price
        debt = cfg.house_price - cfg.downpayment
        indirect_amortization_credit = 0.0
        buyer_rental_deposit = 0.0
        buyer_is_owner = True
        salary_t = cfg.salary_total
        renter_rent_t = cfg.base_rent_monthly * 12.0
        buyer_rent_t = cfg.house_market_rent_monthly * 12.0
        market_rent_annual = cfg.house_market_rent_monthly * 12.0
        rent_reference_rate_average = cfg.rent_reference_rate_current
        rent_reference_rate_t = _round_to_step_nearest(
            rent_reference_rate_average,
            cfg.rent_reference_rate_step,
        )
        price_level = 1.0
        tax_index_factor_t = cfg.tax_parameter_index_factor(cfg.start_year)

        for t in range(years):
            year = cfg.start_year + t
            stress_active = bool(stress_events[it, t])
            inflation_t = _clamp_rate(
                cfg.inflation + inflation_shocks[it, t] * cfg.inflation_volatility,
                cfg.inflation_min,
                cfg.inflation_max,
            )
            stock_factor_t = portfolio_gf[it, t]
            house_factor_t = house_gf[it, t]
            if stress_active:
                stock_factor_t *= 1.0 - cfg.stress_stock_drawdown
                house_factor_t *= 1.0 - cfg.stress_house_drawdown
            engine.set_tax_index_factor_overrides({year: tax_index_factor_t})
            inflation_rate_arr[row, t] = inflation_t
            tax_index_factor_arr[row, t] = tax_index_factor_t
            buyer_was_owner = buyer_is_owner
            salary_effective = salary_t * (1.0 - cfg.stress_salary_hit if stress_active else 1.0)
            cash_salary_t = salary_effective * (1.0 - cfg.social_security_rate)
            p1_salary_t = salary_effective * cfg.salary_split
            p2_salary_t = salary_effective * (1.0 - cfg.salary_split)
            stress_rent_multiplier = 1.0 + cfg.stress_rent_jump if stress_active else 1.0
            renter_rent_effective = renter_rent_t * stress_rent_multiplier
            buyer_rent_effective = buyer_rent_t * stress_rent_multiplier
            market_rent_effective = market_rent_annual * (
                stress_rent_multiplier
            )
            interest_rate_t = _clamp_rate(
                cfg.interest_rate
                + mortgage_rate_shocks[it, t] * cfg.mortgage_rate_volatility
                + (cfg.stress_rate_jump if stress_active else 0.0),
                cfg.mortgage_rate_min,
                cfg.mortgage_rate_max,
            )

            p1_3a = _pillar_3a_contribution_cap(
                p1_salary_t,
                pillar2_affiliated=cfg.p1_pillar2_affiliated,
                tax_index_factor=tax_index_factor_t,
                cfg=cfg,
            )
            p2_3a = _pillar_3a_contribution_cap(
                p2_salary_t,
                pillar2_affiliated=cfg.p2_pillar2_affiliated,
                tax_index_factor=tax_index_factor_t,
                cfg=cfg,
            )
            max_household_3a = p1_3a + p2_3a
            opening_buy_portfolio = buyer_portfolio_cash
            opening_rent_portfolio = renter_portfolio_cash
            opening_house_value = house_value
            opening_debt = debt
            childcare_spend_t = cfg.annual_childcare_spend_household * price_level

            buyer_grown_opening = _compound_liquid_balance(
                opening_buy_portfolio,
                stock_factor_t,
                cfg.liquidity_shortfall_rate,
            )
            renter_grown_opening = _compound_liquid_balance(
                opening_rent_portfolio,
                stock_factor_t,
                cfg.liquidity_shortfall_rate,
            )
            other_consumption = cfg.annual_other_consumption * price_level
            communal_property_tax = (
                _communal_property_tax_for_year(opening_house_value, cfg) if buyer_is_owner else 0.0
            )
            interest_paid = opening_debt * interest_rate_t if buyer_is_owner else 0.0
            maintenance_cash = (
                opening_house_value * cfg.maintenance_rate if buyer_is_owner else 0.0
            )
            house_value_end = opening_house_value * house_factor_t if buyer_is_owner else 0.0

            def _evaluate_buy_path(total_3a: float) -> dict[str, float]:
                buy_p1_3a, buy_p2_3a = _scale_household_3a_contributions(p1_3a, p2_3a, total_3a)
                buy_household_3a = buy_p1_3a + buy_p2_3a
                if buyer_is_owner:
                    ltv_debt_floor = cfg.house_price * cfg.ltv_floor
                    effective_debt_for_floor = max(
                        0.0,
                        opening_debt - indirect_amortization_credit,
                    )
                    if effective_debt_for_floor > ltv_debt_floor:
                        required_amortization = min(
                            cfg.amortization_annual,
                            effective_debt_for_floor - ltv_debt_floor,
                        )
                        voluntary_direct_amortization = 0.0
                    else:
                        required_amortization = 0.0
                        voluntary_direct_amortization = (
                            min(cfg.amortization_annual, opening_debt)
                            if cfg.voluntary_amortization
                            else 0.0
                        )
                    required_direct_amortization, indirect_amortization = _split_amortization(
                        required_amortization,
                        buy_household_3a,
                        cfg.amortization_strategy,
                    )
                    amortization = required_direct_amortization + voluntary_direct_amortization
                    debt_after = opening_debt - amortization
                    indirect_credit_after = min(
                        debt_after,
                        indirect_amortization_credit + indirect_amortization,
                    )
                    non_tax_outflow = (
                        interest_paid
                        + maintenance_cash
                        + amortization
                        + other_consumption
                    )
                else:
                    amortization = 0.0
                    debt_after = 0.0
                    indirect_credit_after = 0.0
                    non_tax_outflow = buyer_rent_effective + other_consumption

                liquid_before_tax = (
                    buyer_grown_opening
                    + cash_salary_t
                    - buy_household_3a
                    - non_tax_outflow
                )
                ordinary_tax_result = engine.calculate_household_tax(
                    year=year,
                    salary_total=salary_effective,
                    portfolio=opening_buy_portfolio,
                    house_val=opening_house_value if buyer_is_owner else 0.0,
                    debt=opening_debt if buyer_is_owner else 0.0,
                    is_owner=buyer_is_owner,
                    pillar_3a_contribution_p1=buy_p1_3a,
                    pillar_3a_contribution_p2=buy_p2_3a,
                    market_rent_annual=market_rent_effective if buyer_is_owner else 0.0,
                    interest_rate_override=interest_rate_t,
                    wealth_portfolio=liquid_before_tax + buyer_rental_deposit,
                    wealth_house_val=house_value_end if buyer_is_owner else 0.0,
                    wealth_debt=debt_after if buyer_is_owner else 0.0,
                    annual_childcare_spend_household_override=childcare_spend_t,
                )
                ordinary_tax = ordinary_tax_result.total
                total_tax = ordinary_tax + communal_property_tax
                return {
                    "p1_3a": buy_p1_3a,
                    "p2_3a": buy_p2_3a,
                    "household_3a": buy_household_3a,
                    "non_tax_outflow": non_tax_outflow,
                    "liquid_before_tax": liquid_before_tax,
                    "ordinary_tax": ordinary_tax,
                    "tax": total_tax,
                    "cash_after_tax": liquid_before_tax - total_tax,
                    "debt_after": debt_after,
                    "indirect_credit_after": indirect_credit_after,
                }

            non_tax_outflow_rent = renter_rent_effective + other_consumption

            def _evaluate_rent_path(total_3a: float) -> dict[str, float]:
                rent_p1_3a, rent_p2_3a = _scale_household_3a_contributions(p1_3a, p2_3a, total_3a)
                rent_household_3a = rent_p1_3a + rent_p2_3a
                liquid_before_tax = (
                    renter_grown_opening
                    + cash_salary_t
                    - rent_household_3a
                    - non_tax_outflow_rent
                )
                total_tax = engine.calculate_household_tax(
                    year=year,
                    salary_total=salary_effective,
                    portfolio=opening_rent_portfolio,
                    house_val=0.0,
                    debt=0.0,
                    is_owner=False,
                    pillar_3a_contribution_p1=rent_p1_3a,
                    pillar_3a_contribution_p2=rent_p2_3a,
                    market_rent_annual=0.0,
                    interest_rate_override=interest_rate_t,
                    wealth_portfolio=liquid_before_tax,
                    annual_childcare_spend_household_override=childcare_spend_t,
                ).total
                return {
                    "p1_3a": rent_p1_3a,
                    "p2_3a": rent_p2_3a,
                    "household_3a": rent_household_3a,
                    "tax": total_tax,
                    "cash_after_tax": liquid_before_tax - total_tax,
                }

            buy_household_3a = _solve_affordable_household_3a_total(
                max_household_3a,
                lambda total: _evaluate_buy_path(total)["cash_after_tax"],
            )
            rent_household_3a = _solve_affordable_household_3a_total(
                max_household_3a,
                lambda total: _evaluate_rent_path(total)["cash_after_tax"],
            )
            buy_state = _evaluate_buy_path(buy_household_3a)
            rent_state = _evaluate_rent_path(rent_household_3a)

            buyer_portfolio_cash = buy_state["cash_after_tax"]
            renter_portfolio_cash = rent_state["cash_after_tax"]
            tax_buy = buy_state["tax"]
            tax_rent = rent_state["tax"]
            debt_after = buy_state["debt_after"]
            indirect_amortization_credit = buy_state["indirect_credit_after"]
            surplus_buy = buyer_portfolio_cash - buyer_grown_opening
            surplus_rent = renter_portfolio_cash - renter_grown_opening
            pillar_3a_factor_t = pillar_3a_gf[it, t]
            if stress_active:
                pillar_3a_factor_t *= 1.0 - cfg.stress_stock_drawdown
            buyer_3a = buyer_3a * pillar_3a_factor_t + buy_state["household_3a"]
            renter_3a = renter_3a * pillar_3a_factor_t + rent_state["household_3a"]
            house_value = house_value_end
            debt = debt_after

            if buyer_is_owner and cfg.force_buy_sale_on_liquidity_crisis:
                crisis_limit = max(
                    0.0,
                    (
                        (buy_state["non_tax_outflow"] + tax_buy)
                        / 12.0
                    ) * cfg.liquidity_crisis_buffer_months,
                )
                if buyer_portfolio_cash < -crisis_limit:
                    holding_years = t + 1
                    igi_rate = vaud_igi_rate(holding_years, IGI_SCHEDULE)
                    buying_costs_paid = cfg.house_price * cfg.buying_costs_pct
                    sale_gross = house_value * (1.0 - cfg.sale_cost_pct)
                    gain = max(0.0, sale_gross - (cfg.house_price + buying_costs_paid))
                    igi_tax = gain * igi_rate
                    house_cash_out = sale_gross - debt - igi_tax
                    transition_rent_cost = (
                        market_rent_effective * cfg.forced_sale_transition_months / 12.0
                    )
                    buyer_rental_deposit = (
                        market_rent_effective * cfg.forced_sale_rental_deposit_months / 12.0
                    )
                    buyer_portfolio_cash += house_cash_out
                    buyer_portfolio_cash -= cfg.forced_sale_extra_cost_chf
                    buyer_portfolio_cash -= transition_rent_cost
                    buyer_portfolio_cash -= buyer_rental_deposit
                    post_sale_wealth_portfolio = (
                        buy_state["liquid_before_tax"]
                        + sale_gross
                        - debt
                        - igi_tax
                        - cfg.forced_sale_extra_cost_chf
                        - transition_rent_cost
                    )
                    # Income tax still reflects ownership during the year, while
                    # Vaud wealth tax uses the post-sale 31 December assets.
                    post_sale_tax_result = engine.calculate_household_tax(
                        year=year,
                        salary_total=salary_effective,
                        portfolio=opening_buy_portfolio,
                        house_val=opening_house_value,
                        debt=opening_debt,
                        is_owner=True,
                        pillar_3a_contribution_p1=buy_state["p1_3a"],
                        pillar_3a_contribution_p2=buy_state["p2_3a"],
                        market_rent_annual=market_rent_effective,
                        interest_rate_override=interest_rate_t,
                        wealth_portfolio=post_sale_wealth_portfolio,
                        wealth_house_val=0.0,
                        wealth_debt=0.0,
                        annual_childcare_spend_household_override=childcare_spend_t,
                    )
                    post_sale_ordinary_tax = post_sale_tax_result.total
                    buyer_portfolio_cash -= (
                        post_sale_ordinary_tax - buy_state["ordinary_tax"]
                    )
                    tax_buy = post_sale_ordinary_tax + communal_property_tax + igi_tax
                    buyer_is_owner = False
                    buy_forced_sale[row] = True
                    house_value = 0.0
                    debt = 0.0
                    indirect_amortization_credit = 0.0
                    surplus_buy = buyer_portfolio_cash - buyer_grown_opening

            house_val_arr[row, t] = house_value
            debt_arr[row, t] = debt
            buy_portfolio[row, t] = buyer_portfolio_cash
            rent_portfolio[row, t] = renter_portfolio_cash
            buy_pillar_3a[row, t] = buyer_3a
            rent_pillar_3a[row, t] = renter_3a
            buy_tax_arr[row, t] = tax_buy
            rent_tax_arr[row, t] = tax_rent
            buy_surplus_arr[row, t] = surplus_buy
            rent_surplus_arr[row, t] = surplus_rent
            buy_rental_deposit_arr[row, t] = buyer_rental_deposit

            p3a_after_tax = buyer_3a * (1.0 - cfg.pillar_3a_withdrawal_tax_rate)
            buy_net_worth[row, t] = (
                buyer_portfolio_cash
                + buyer_rental_deposit
                + (house_value - debt)
                + p3a_after_tax
            )
            rent_net_worth[row, t] = (
                renter_portfolio_cash
                + renter_3a * (1.0 - cfg.pillar_3a_withdrawal_tax_rate)
            )

            if buyer_portfolio_cash < 0.0:
                buy_ruin[row] = True
            if renter_portfolio_cash < 0.0:
                rent_ruin[row] = True

            next_price_level = price_level * (1.0 + inflation_t)
            inflation_index_arr[row, t] = next_price_level
            salary_growth_t = _clamp_growth_rate(
                (1.0 + inflation_t)
                * (1.0 + cfg.salary_growth + salary_growth_shocks[it, t] * cfg.salary_growth_volatility)
                - 1.0
            )
            salary_t = max(0.0, salary_t * (1.0 + salary_growth_t))
            market_rent_growth_t = _clamp_growth_rate(
                (1.0 + inflation_t)
                * (
                    1.0
                    + cfg.market_rent_real_growth
                    + rent_growth_shocks[it, t] * cfg.rent_growth_volatility
                )
                - 1.0
            )
            next_market_rent_annual = max(
                0.0,
                market_rent_annual * (1.0 + market_rent_growth_t),
            )
            rent_reference_rate_average = max(
                0.0,
                rent_reference_rate_average
                + cfg.rent_reference_rate_smoothing * (interest_rate_t - rent_reference_rate_average),
            )
            next_rent_reference_rate = _round_to_step_nearest(
                rent_reference_rate_average,
                cfg.rent_reference_rate_step,
            )
            contract_rent_growth_t = _swiss_contract_rent_growth(
                rent_reference_rate_t,
                next_rent_reference_rate,
                inflation_t,
                cfg,
            )
            renter_rent_t = max(0.0, renter_rent_t * (1.0 + contract_rent_growth_t))
            if buyer_was_owner:
                buyer_rent_t = next_market_rent_annual
            else:
                buyer_rent_t = max(0.0, buyer_rent_t * (1.0 + contract_rent_growth_t))
            market_rent_annual = next_market_rent_annual
            rent_reference_rate_t = next_rent_reference_rate
            price_level = next_price_level
            if cfg.index_tax_parameters_with_inflation:
                tax_index_factor_t *= 1.0 + max(0.0, inflation_t)

        # Horizon comparison assumes both strategies are settled at the end of the
        # simulation. For the buyer, that means selling the home and counting the
        # net cash after sale costs, mortgage payoff, and IGI.
        holding_years = years
        igi_rate = vaud_igi_rate(holding_years, IGI_SCHEDULE)
        buying_costs_paid = cfg.house_price * cfg.buying_costs_pct
        if buyer_is_owner:
            sale_gross = house_value * (1.0 - cfg.sale_cost_pct)
            gain = max(0.0, sale_gross - (cfg.house_price + buying_costs_paid))
            igi_tax = gain * igi_rate
            house_cash_out = sale_gross - debt - igi_tax
        else:
            house_cash_out = 0.0

        buyer_3a_after_tax = buyer_3a * (1.0 - cfg.pillar_3a_withdrawal_tax_rate)
        renter_3a_after_tax = renter_3a * (1.0 - cfg.pillar_3a_withdrawal_tax_rate)
        buy_terminal[row] = (
            buyer_portfolio_cash
            + buyer_rental_deposit
            + house_cash_out
            + buyer_3a_after_tax
        )
        rent_terminal[row] = renter_portfolio_cash + renter_3a_after_tax

    return _SimulationChunk(
        buy_net_worth=buy_net_worth,
        rent_net_worth=rent_net_worth,
        buy_terminal_liquid=buy_terminal,
        rent_terminal_liquid=rent_terminal,
        buy_portfolio=buy_portfolio,
        rent_portfolio=rent_portfolio,
        buy_pillar_3a=buy_pillar_3a,
        rent_pillar_3a=rent_pillar_3a,
        house_val=house_val_arr,
        debt=debt_arr,
        buy_tax=buy_tax_arr,
        rent_tax=rent_tax_arr,
        buy_surplus=buy_surplus_arr,
        rent_surplus=rent_surplus_arr,
        buy_rental_deposit=buy_rental_deposit_arr,
        buy_ruin_any=buy_ruin,
        rent_ruin_any=rent_ruin,
        buy_forced_sale_any=buy_forced_sale,
        inflation_rate=inflation_rate_arr,
        inflation_index=inflation_index_arr,
        tax_index_factor=tax_index_factor_arr,
    )


def run_simulation(cfg: SwissConfig) -> SimulationResult:
    cfg.validate()
    rng = np.random.default_rng(cfg.rng_seed)
    n_iter, years = cfg.iterations, cfg.years
    stock_growth_chf = cfg.stock_growth_chf

    portfolio_gf, house_gf = _draw_correlated_lognormal_factors(
        rng=rng,
        iterations=n_iter,
        years=years,
        mu_stock=stock_growth_chf,
        sigma_stock=cfg.stock_volatility,
        mu_house=cfg.house_growth,
        sigma_house=cfg.house_volatility,
        correlation=cfg.asset_correlation,
        ter_stock=cfg.portfolio_ter,
        ter_house=0.0,
    )
    stock_shocks = _recover_stock_shocks_from_factors(
        portfolio_gf,
        stock_growth_chf,
        cfg.stock_volatility,
        cfg.portfolio_ter,
    )
    pillar_3a_mu = stock_growth_chf if cfg.pillar_3a_growth_chf is None else cfg.pillar_3a_growth_chf
    pillar_3a_sigma = cfg.stock_volatility if cfg.pillar_3a_volatility is None else cfg.pillar_3a_volatility
    pillar_3a_shocks = _correlate_with_reference_shocks(
        rng,
        stock_shocks,
        cfg.pillar_3a_correlation_to_portfolio,
    )
    pillar_3a_gf = _draw_lognormal_factors_same_shocks(
        pillar_3a_shocks,
        pillar_3a_mu,
        pillar_3a_sigma,
        cfg.pillar_3a_ter,
    )
    inflation_shocks = rng.standard_normal(size=(n_iter, years))
    salary_growth_shocks = rng.standard_normal(size=(n_iter, years))
    rent_growth_shocks = rng.standard_normal(size=(n_iter, years))
    mortgage_rate_shocks = rng.standard_normal(size=(n_iter, years))
    stress_uniforms = rng.random(size=(n_iter, years))
    stress_events = _draw_stress_events_from_uniforms(
        stress_uniforms,
        cfg.stress_event_probability,
        cfg.stress_persistence,
    )

    shocks = _SimulationShocks(
        portfolio_gf=portfolio_gf,
        house_gf=house_gf,
        pillar_3a_gf=pillar_3a_gf,
        inflation_shocks=inflation_shocks,
        salary_growth_shocks=salary_growth_shocks,
        rent_growth_shocks=rent_growth_shocks,
        mortgage_rate_shocks=mortgage_rate_shocks,
        stress_events=stress_events,
    )
    worker_count = _effective_parallel_workers(cfg.parallel_workers, n_iter)
    ranges = _chunk_ranges(n_iter, worker_count)
    if worker_count == 1:
        chunks = [_simulate_chunk(cfg, 0, n_iter, shocks)]
    else:
        chunks = Parallel(n_jobs=cfg.parallel_workers)(
            delayed(_simulate_chunk)(cfg, start, stop, shocks)
            for start, stop in ranges
        )

    return _combine_chunks(cfg, chunks)
