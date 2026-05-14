"""
visualizer.py
Streamlit dashboard for the Vaud buy-vs-rent simulator.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path
import sys

import numpy as np
import plotly.graph_objects as go
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import SwissConfig, TAX_PARAMETER_REFERENCE_YEAR
from src.simulator import SimulationResult, run_simulation
from src.vaud_communes import get_vaud_commune, infer_vaud_commune_name, load_vaud_communes_2026

st.set_page_config(layout="wide", page_title="Vaud Buy vs Rent")


@st.cache_data(show_spinner="Running Monte Carlo…")
def _run_cached(cfg_items: tuple) -> SimulationResult:
    cfg = SwissConfig(**dict(cfg_items))
    return run_simulation(cfg)


def run_cached(cfg: SwissConfig) -> SimulationResult:
    key = tuple(sorted(dataclasses.asdict(cfg).items()))
    return _run_cached(key)


def _fan_chart(
    years: np.ndarray,
    data: np.ndarray,
    title: str,
    color: str,
    unit_suffix: str = "",
) -> go.Figure:
    p10 = np.percentile(data, 10, axis=0)
    p50 = np.percentile(data, 50, axis=0)
    p90 = np.percentile(data, 90, axis=0)
    rgba_fill = {
        "blue": "rgba(0, 90, 200, 0.15)",
        "green": "rgba(0, 160, 60, 0.15)",
        "orange": "rgba(220, 110, 0, 0.15)",
    }.get(color, "rgba(120, 120, 120, 0.2)")
    line = {"blue": "#005ac8", "green": "#00a03c", "orange": "#dc6e00"}.get(color, "#777")

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=years, y=p50, name="Median", line=dict(color=line, width=3)))
    fig.add_trace(go.Scatter(x=years, y=p90, line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(
        go.Scatter(
            x=years,
            y=p10,
            fill="tonexty",
            fillcolor=rgba_fill,
            name="Pointwise 10th–90th percentile",
            line=dict(width=0),
            hoverinfo="skip",
        )
    )
    fig.update_layout(
        title=title,
        template="plotly_white",
        hovermode="x unified",
        yaxis_title=f"CHF{unit_suffix}",
        xaxis_title="Year",
        margin=dict(l=30, r=10, t=60, b=30),
    )
    return fig


def _overlay_fan(
    years: np.ndarray,
    buy: np.ndarray,
    rent: np.ndarray,
    title: str,
    unit_suffix: str = "",
) -> go.Figure:
    b50, b10, b90 = (np.percentile(buy, q, axis=0) for q in (50, 10, 90))
    r50, r10, r90 = (np.percentile(rent, q, axis=0) for q in (50, 10, 90))
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=years, y=r90, line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(
        go.Scatter(
            x=years,
            y=r10,
            fill="tonexty",
            fillcolor="rgba(0, 160, 60, 0.15)",
            name="Rent pointwise 10–90 %",
            line=dict(width=0),
            hoverinfo="skip",
        )
    )
    fig.add_trace(go.Scatter(x=years, y=b90, line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(
        go.Scatter(
            x=years,
            y=b10,
            fill="tonexty",
            fillcolor="rgba(0, 90, 200, 0.15)",
            name="Buy pointwise 10–90 %",
            line=dict(width=0),
            hoverinfo="skip",
        )
    )
    fig.add_trace(go.Scatter(x=years, y=r50, name="Rent median", line=dict(color="#00a03c", width=3)))
    fig.add_trace(go.Scatter(x=years, y=b50, name="Buy median", line=dict(color="#005ac8", width=3)))
    fig.update_layout(
        title=title,
        template="plotly_white",
        hovermode="x unified",
        yaxis_title=f"CHF{unit_suffix}",
        xaxis_title="Year",
        margin=dict(l=30, r=10, t=60, b=30),
    )
    return fig


def _delta_histogram(buy_term: np.ndarray, rent_term: np.ndarray, unit_suffix: str = "") -> go.Figure:
    delta = buy_term - rent_term
    fig = go.Figure(go.Histogram(x=delta, nbinsx=60, marker_color="#5a6dd8"))
    fig.add_vline(x=0, line_dash="dash", line_color="black", annotation_text="Break-even")
    fig.add_vline(
        x=np.median(delta),
        line_dash="dot",
        line_color="#c0392b",
        annotation_text=f"Median = {np.median(delta):,.0f}",
    )
    fig.update_layout(
        title=f"Horizon wealth after liquidation: Buy − Rent (CHF{unit_suffix})",
        template="plotly_white",
        xaxis_title=f"Buy − Rent at horizon (CHF{unit_suffix})",
        yaxis_title="Iterations",
        margin=dict(l=30, r=10, t=60, b=30),
    )
    return fig


def _expected_shortfall(values: np.ndarray, tail: float) -> float:
    count = max(1, int(np.ceil(values.size * tail)))
    return float(np.mean(np.sort(values)[:count]))


def _split_signed_median(paths: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return the median path plus its positive and negative parts."""
    median_path = np.median(paths, axis=0)
    return median_path, np.maximum(median_path, 0.0), np.minimum(median_path, 0.0)


def _deflate_paths(data: np.ndarray, deflator: np.ndarray) -> np.ndarray:
    return data / deflator


def _format_children(n_children: int) -> str:
    return f"{n_children} child" if n_children == 1 else f"{n_children} children"


def _allowed_child_share_options(n_children: int) -> list[float]:
    if n_children <= 0:
        return [0.0]
    return [step / (2 * n_children) for step in range(0, 2 * n_children + 1)]


def _nearest_allowed_child_share(value: float, n_children: int) -> float:
    options = _allowed_child_share_options(n_children)
    return min(options, key=lambda option: abs(option - value))


def _format_child_share_option(share: float, n_children: int) -> str:
    if n_children <= 0:
        return "No child allocation"
    p1_children = share * n_children
    p2_children = n_children - p1_children

    def _fmt(value: float) -> str:
        rounded = round(value)
        if abs(value - rounded) < 1e-9:
            return str(int(rounded))
        return f"{value:.1f}".rstrip("0").rstrip(".")

    if n_children == 1:
        if abs(share - 1.0) < 1e-9:
            return "All to P1"
        if abs(share - 0.5) < 1e-9:
            return "50 / 50 split"
        if abs(share) < 1e-9:
            return "All to P2"
    return f"P1 {_fmt(p1_children)} / P2 {_fmt(p2_children)} child shares"


def _rate_options(min_value: float, max_value: float, step: float) -> list[float]:
    count = int(round((max_value - min_value) / step))
    return [round(min_value + idx * step, 10) for idx in range(count + 1)]


def _nearest_option(value: float, options: list[float]) -> float:
    return min(options, key=lambda option: abs(option - value))


def _percent_format_for_step(step: float) -> str:
    pct_step = abs(step) * 100.0
    decimals = 0 if pct_step >= 1.0 else (1 if pct_step >= 0.1 else 2)
    return f"{{:.{decimals}%}}"


def _rate_slider(
    label: str,
    min_value: float,
    max_value: float,
    value: float,
    step: float,
    *,
    key: str | None = None,
    help: str | None = None,
) -> float:
    options = _rate_options(min_value, max_value, step)
    shown_value = _nearest_option(value, options)
    fmt = _percent_format_for_step(step)
    if key is None:
        return st.select_slider(
            label,
            options=options,
            value=shown_value,
            format_func=lambda option: fmt.format(option),
            help=help,
        )
    current_value = st.session_state.get(key, shown_value)
    st.session_state[key] = _nearest_option(float(current_value), options)
    return st.select_slider(
        label,
        options=options,
        key=key,
        format_func=lambda option: fmt.format(option),
        help=help,
    )


_PRESET_WIDGET_FIELDS = (
    "inflation",
    "inflation_volatility",
    "inflation_min",
    "inflation_max",
    "rent_reference_rate_current",
    "rent_reference_rate_smoothing",
    "rent_cpi_passthrough",
    "interest_rate",
    "mortgage_rate_volatility",
    "mortgage_rate_min",
    "mortgage_rate_max",
    "salary_growth_volatility",
    "market_rent_real_growth",
    "rent_growth_volatility",
    "stress_event_probability",
    "stress_persistence",
    "stress_stock_drawdown",
    "stress_house_drawdown",
    "stress_salary_hit",
    "stress_rent_jump",
    "stress_rate_jump",
    "force_buy_sale_on_liquidity_crisis",
    "liquidity_crisis_buffer_months",
    "forced_sale_extra_cost_chf",
    "forced_sale_transition_months",
    "forced_sale_rental_deposit_months",
    "first_time_buyer_years_used_before_start_p1",
    "first_time_buyer_years_used_before_start_p2",
    "first_time_buyer_years_used_before_start_married",
    "index_tax_parameters_with_inflation",
    "use_official_cantonal_income_tax_reduction_schedule",
)
MANUAL_VAUD_COMMUNE = "Manual / custom"


def _ensure_preset_widget_state(default_cfg: SwissConfig) -> None:
    for field in _PRESET_WIDGET_FIELDS:
        st.session_state.setdefault(field, getattr(default_cfg, field))
    st.session_state.setdefault("decision_preset_name", "Reset to shipped baseline")


def _ensure_commune_selector_state(default_cfg: SwissConfig) -> None:
    st.session_state.setdefault("commune_multiplier", default_cfg.commune_multiplier)
    st.session_state.setdefault(
        "communal_property_tax_per_mille_ui",
        default_cfg.communal_property_tax_rate * 1_000.0,
    )
    default_commune_name = (
        infer_vaud_commune_name(
            default_cfg.commune_multiplier,
            default_cfg.communal_property_tax_rate,
            preferred_name="Lausanne",
        )
        or MANUAL_VAUD_COMMUNE
    )
    st.session_state.setdefault("selected_vd_commune_name", default_commune_name)
    st.session_state.setdefault("applied_vd_commune_name", default_commune_name)


def _apply_selected_vd_commune(commune_name: str) -> None:
    row = get_vaud_commune(commune_name)
    st.session_state["commune_multiplier"] = row.commune_multiplier
    st.session_state["communal_property_tax_per_mille_ui"] = row.property_tax_per_mille
    st.session_state["applied_vd_commune_name"] = commune_name


def _decision_presets(default_cfg: SwissConfig) -> dict[str, dict[str, float | bool]]:
    baseline = {field: getattr(default_cfg, field) for field in _PRESET_WIDGET_FIELDS}
    return {
        "Reset to shipped baseline": baseline,
        "High inflation + high rates": {
            **baseline,
            "inflation": 0.03,
            "inflation_volatility": 0.015,
            "inflation_min": 0.0,
            "inflation_max": 0.08,
            "interest_rate": 0.035,
            "mortgage_rate_volatility": 0.01,
            "mortgage_rate_min": 0.01,
            "mortgage_rate_max": 0.08,
            "salary_growth_volatility": 0.015,
            "rent_growth_volatility": 0.02,
            "index_tax_parameters_with_inflation": True,
        },
        "Bracket creep stress": {
            **baseline,
            "inflation": 0.03,
            "inflation_volatility": 0.015,
            "inflation_min": 0.0,
            "inflation_max": 0.08,
            "interest_rate": 0.03,
            "mortgage_rate_volatility": 0.008,
            "mortgage_rate_min": 0.01,
            "mortgage_rate_max": 0.07,
            "salary_growth_volatility": 0.015,
            "rent_growth_volatility": 0.02,
            "index_tax_parameters_with_inflation": False,
        },
        "Asset crash + income hit": {
            **baseline,
            "inflation": 0.015,
            "inflation_volatility": 0.01,
            "inflation_min": -0.01,
            "inflation_max": 0.05,
            "interest_rate": 0.025,
            "mortgage_rate_volatility": 0.008,
            "mortgage_rate_min": 0.0,
            "mortgage_rate_max": 0.08,
            "salary_growth_volatility": 0.02,
            "rent_growth_volatility": 0.015,
            "stress_event_probability": 0.15,
            "stress_persistence": 0.55,
            "stress_stock_drawdown": 0.35,
            "stress_house_drawdown": 0.15,
            "stress_salary_hit": 0.15,
            "stress_rent_jump": 0.08,
            "stress_rate_jump": 0.02,
            "force_buy_sale_on_liquidity_crisis": True,
            "liquidity_crisis_buffer_months": 6.0,
            "index_tax_parameters_with_inflation": True,
        },
        "Owner forced-sale risk": {
            **baseline,
            "inflation": 0.02,
            "inflation_volatility": 0.015,
            "inflation_min": -0.01,
            "inflation_max": 0.06,
            "interest_rate": 0.035,
            "mortgage_rate_volatility": 0.012,
            "mortgage_rate_min": 0.01,
            "mortgage_rate_max": 0.09,
            "salary_growth_volatility": 0.025,
            "rent_growth_volatility": 0.02,
            "stress_event_probability": 0.2,
            "stress_persistence": 0.65,
            "stress_stock_drawdown": 0.30,
            "stress_house_drawdown": 0.20,
            "stress_salary_hit": 0.20,
            "stress_rent_jump": 0.10,
            "stress_rate_jump": 0.025,
            "force_buy_sale_on_liquidity_crisis": True,
            "liquidity_crisis_buffer_months": 3.0,
            "index_tax_parameters_with_inflation": True,
        },
    }


def _apply_preset(updates: dict[str, float | bool]) -> None:
    for field, value in updates.items():
        st.session_state[field] = value


default_cfg = SwissConfig()
_ensure_preset_widget_state(default_cfg)
_ensure_commune_selector_state(default_cfg)
decision_presets = _decision_presets(default_cfg)
vaud_commune_rows = load_vaud_communes_2026()
vaud_commune_names = sorted(row.commune_name for row in vaud_commune_rows)
vaud_commune_multiplier_min = min((row.commune_multiplier for row in vaud_commune_rows), default=0.0)
vaud_commune_multiplier_max = max((row.commune_multiplier for row in vaud_commune_rows), default=1.0)

c = SwissConfig()

st.sidebar.title("Simulation controls")
st.sidebar.caption(
    "The simulator uses sourced 2026 Vaud tax scales and sourced 2026 federal "
    "IFD tariffs, but some household-specific deductions require manual checking."
)

with st.sidebar.expander("Decision presets"):
    st.selectbox(
        "Preset bundle",
        options=list(decision_presets),
        key="decision_preset_name",
        help="These presets are stress-test starting points, not forecasts. Apply one, then adjust the household-specific inputs manually.",
    )
    if st.button("Apply preset to sidebar controls", use_container_width=True):
        _apply_preset(decision_presets[st.session_state["decision_preset_name"]])
        st.rerun()
    st.caption(
        "Useful shortcut: compare `High inflation + high rates` against `Bracket creep stress` "
        "to see the difference between inflation with tax indexing and inflation with frozen tax thresholds."
    )

with st.sidebar.expander("Run settings", expanded=True):
    c.iterations = st.select_slider(
        "Monte Carlo iterations",
        options=[500, 1_000, 2_000, 5_000, 10_000, 25_000, 50_000],
        value=c.iterations,
    )
    c.years = st.slider("Horizon (years)", 10, 50, c.years)
    c.rng_seed = st.number_input("Random seed", 0, 10_000, c.rng_seed)
    worker_options = [-1, 1, 2, 4, 8]
    if c.parallel_workers not in worker_options:
        worker_options.insert(0, c.parallel_workers)
    c.parallel_workers = st.selectbox(
        "CPU workers",
        worker_options,
        index=worker_options.index(c.parallel_workers),
        format_func=lambda n: "All available" if n == -1 else f"{n}",
        help="Use 1 for serial execution. Higher values split Monte Carlo paths across joblib worker processes.",
    )
    c.start_year = st.number_input(
        "Start year",
        TAX_PARAMETER_REFERENCE_YEAR,
        2040,
        c.start_year,
        help="The embedded official tax tables start at 2026.",
    )
    show_real = st.checkbox(
        "Show amounts in start-year CHF (inflation-adjusted)",
        value=False,
    )
    st.caption(
        "This display toggle only changes how results are shown. The separate tax-law "
        "indexing assumption is configured below."
    )

with st.sidebar.expander("Household income", expanded=True):
    household_labels = {
        "unmarried": "Unmarried / separately taxed",
        "married": "Married / jointly taxed",
    }
    selected_household_label = st.selectbox(
        "Household tax status",
        options=list(household_labels.values()),
        index=list(household_labels.keys()).index(c.household_status),
        help=(
            "Choose whether the adults are modeled as unmarried taxpayers filing separately "
            "or as a married couple filing jointly. This changes the federal tariff, Vaud "
            "quotient logic, first-home deduction handling, and some deduction caps."
        ),
    )
    c.household_status = next(
        key for key, label in household_labels.items() if label == selected_household_label
    )
    c.salary_total = st.number_input(
        "Combined gross salary (CHF)",
        100_000,
        2_000_000,
        int(c.salary_total),
        step=5_000,
    )
    c.salary_split = st.slider("Salary split (P1 share)", 0.0, 1.0, c.salary_split)
    c.ownership_split = st.slider(
        "Ownership split (P1 legal share)",
        0.0,
        1.0,
        c.ownership_split,
        0.05,
        help=(
            "Relevant especially in unmarried mode, where owner-side tax items are allocated "
            "between P1 and P2 using the legal ownership share."
        ),
    )
    c.portfolio_split = st.slider(
        "Taxable portfolio split (P1 share)",
        0.0,
        1.0,
        c.portfolio_split,
        0.05,
        help=(
            "Relevant especially in unmarried mode, where dividend income and wealth tax are "
            "allocated using this taxable-account ownership split."
        ),
    )
    c.salary_growth = _rate_slider(
        "Extra salary growth above inflation",
        0.0,
        0.03,
        c.salary_growth,
        0.001,
        help="Use 0% if you want salary to rise only with inflation. Positive values mean salary also grows in purchasing power.",
    )
    c.social_security_rate = _rate_slider(
        "Social deductions as share of gross salary",
        0.05,
        0.20,
        c.social_security_rate,
        0.005,
    )
    child_count_max = 5 if c.household_status == "married" else 3
    c.n_children = min(c.n_children, child_count_max)
    c.n_children = st.number_input(
        "Number of children",
        0,
        child_count_max,
        c.n_children,
        help=(
            "Married mode supports up to 5 children with the shipped official Vaud cap table. "
            "Unmarried mode supports up to 3 because the published separately taxed Vaud cap table stops there."
        ),
    )
    if c.household_status == "unmarried":
        if c.n_children > 0:
            c.vaud_single_parent_household = st.checkbox(
                "Vaud single-parent household quotient applies",
                value=c.vaud_single_parent_household,
                help="Leave this OFF for a cohabiting unmarried couple; Vaud's special 1.3 part does not apply in that case.",
            )
            child_share_options = _allowed_child_share_options(c.n_children)
            if c.vaud_single_parent_household:
                c.child_claimed_by_p1 = st.checkbox(
                    "Federal parental tariff claimed by P1 (else P2)",
                    value=c.child_claimed_by_p1,
                )
                c.child_deduction_split_to_p1 = st.select_slider(
                    "Child-deduction allocation to P1",
                    options=child_share_options,
                    value=_nearest_allowed_child_share(c.child_deduction_split_to_p1, c.n_children),
                    format_func=lambda share: _format_child_share_option(share, c.n_children),
                    help=(
                        "Use this only for a non-standard unmarried filing case. For the common "
                        "cohabiting-with-common-child case, the simulator uses the usual official "
                        "federal pattern for this type of household."
                    ),
                )
            else:
                if abs(c.salary_split - 0.5) < 1e-9:
                    federal_parental_to_p1 = c.child_claimed_by_p1
                else:
                    federal_parental_to_p1 = c.salary_split > 0.5
                c.child_claimed_by_p1 = federal_parental_to_p1
                c.child_deduction_split_to_p1 = 0.5
                c.childcare_spend_split_to_p1 = 0.5
                st.caption(
                    "For a cohabiting unmarried couple with a common child and no maintenance "
                    "payments, the simulator follows the official common federal default: child "
                    "deductions and childcare are split 50 / 50, and the parental tariff goes to "
                    f"{'P1' if federal_parental_to_p1 else 'P2'} as the higher-income parent."
                )
            c.vaud_child_quotient_share_to_p1 = st.select_slider(
                "Vaud child-quotient allocation to P1",
                options=child_share_options,
                value=_nearest_allowed_child_share(c.vaud_child_quotient_share_to_p1, c.n_children),
                format_func=lambda share: _format_child_share_option(share, c.n_children),
                help=(
                    "Only whole-child or half-child allocations are offered here. With one child, "
                    "that means all to P1, all to P2, or a 50 / 50 split of the child's 0.5 Vaud part."
                ),
            )
        else:
            st.caption("Child-allocation controls appear once at least one child is modeled.")
    else:
        st.caption(
            "In married mode, federal child deductions are applied to the jointly taxed "
            "household, the federal parental tariff selector is ignored, and Vaud uses "
            "the married quotient of 1.8 plus 0.5 per dependent child with the official cap."
        )
    c.child_dependent_years = st.slider(
        "Years child is treated as tax-dependent",
        0,
        30,
        c.child_dependent_years,
    )
    c.childcare_deduction_years = st.slider(
        "Years childcare tax deduction is assumed to apply",
        0,
        20,
        c.childcare_deduction_years,
        help=(
            "This only controls how many years the childcare tax deduction is available. "
            "Enter the real yearly childcare "
            "spending just below. It does not automatically remove childcare cash "
            "costs from `annual_other_consumption`."
        ),
    )
    c.annual_childcare_spend_household = st.number_input(
        "Actual yearly childcare spending that may be deductible (CHF)",
        0,
        100_000,
        int(c.annual_childcare_spend_household),
        500,
        help=(
            "Think of this as the household's real third-party childcare bill in the start "
            "year. The simulator then applies the federal and Vaud deduction caps on top of it."
        ),
    )
    if c.household_status == "unmarried" and c.n_children > 0:
        if c.vaud_single_parent_household:
            c.childcare_spend_split_to_p1 = st.slider(
                "Childcare-spending share paid by P1",
                0.0,
                1.0,
                c.childcare_spend_split_to_p1,
                0.05,
                help=(
                    "Use this only for a non-standard unmarried filing case. In the common "
                    "cohabiting-with-common-child case, the simulator defaults to a 50 / 50 "
                    "split unless you have proof for another federal allocation."
                ),
            )
        else:
            c.childcare_spend_split_to_p1 = 0.5

with st.sidebar.expander("Consumption & rent"):
    c.annual_other_consumption = st.number_input(
        "Other annual consumption (CHF)",
        0,
        500_000,
        int(c.annual_other_consumption),
        5_000,
    )
    c.base_rent_monthly = st.number_input(
        "Monthly current contract rent if renting (CHF)",
        500,
        20_000,
        int(c.base_rent_monthly),
        50,
    )
    c.rent_reference_rate_current = _rate_slider(
        "Current Swiss rent reference rate",
        0.0,
        0.05,
        c.rent_reference_rate_current,
        0.0025,
        key="rent_reference_rate_current",
        help="Default is 1.25%, matching the nationwide official reference rate in force on March 3, 2026.",
    )
    c.rent_reference_rate_smoothing = st.slider(
        "How slowly contract-rent reference rates react to mortgage-rate changes",
        0.0,
        1.0,
        step=0.05,
        key="rent_reference_rate_smoothing",
        help="Swiss existing-lease rent usually reacts slowly because the legal rent reference rate moves more slowly than live mortgage offers.",
    )
    c.rent_cpi_passthrough = _rate_slider(
        "Contract-rent inflation pass-through",
        0.0,
        0.40,
        c.rent_cpi_passthrough,
        0.01,
        key="rent_cpi_passthrough",
        help="Swiss landlords can usually pass through at most 40% of increases in the consumer price index (CPI), but in many existing leases the practical pass-through is much smaller or zero for long periods.",
    )
    c.inflation = _rate_slider("Inflation", -0.02, 0.08, c.inflation, 0.001, key="inflation")
    c.inflation_volatility = _rate_slider(
        "Inflation volatility",
        0.0,
        0.05,
        c.inflation_volatility,
        0.001,
        key="inflation_volatility",
        help="Adds year-to-year inflation uncertainty around the baseline inflation assumption.",
    )
    c.inflation_min = _rate_slider(
        "Inflation floor",
        -0.05,
        0.08,
        c.inflation_min,
        0.001,
        key="inflation_min",
        help="This is the lowest yearly inflation/deflation rate the simulator will allow.",
    )
    c.inflation_max = _rate_slider(
        "Inflation cap",
        max(c.inflation_min, -0.05),
        0.12,
        c.inflation_max,
        0.001,
        key="inflation_max",
        help="This is the highest yearly inflation rate the simulator will allow.",
    )
    st.caption(
        "The renter path treats `base_rent_monthly` as an existing Swiss lease rent: by default it stays sticky "
        "unless the legal rent reference rate moves. `house_market_rent_monthly` is a separate market-rent proxy used "
        "for VL and to set the buyer's starting rent if a forced sale later turns the buyer into a renter."
    )

with st.sidebar.expander("Property"):
    c.house_price = st.number_input(
        "Purchase price (CHF)",
        500_000,
        5_000_000,
        int(c.house_price),
        25_000,
    )
    c.initial_liquid_assets = st.number_input(
        "Initial cash and taxable investments (CHF)",
        0,
        10_000_000,
        int(c.initial_liquid_assets),
        10_000,
        help=(
            "Cash and taxable investment accounts available before choosing buy versus rent. "
            "This excludes existing pillar 3a, pension assets, home equity, and other illiquid wealth; "
            "enter existing pillar 3a in the Pillar 3a section. "
            "The buyer uses this money for the downpayment and buying costs; the renter keeps it invested."
        ),
    )
    c.downpayment = st.number_input(
        "Downpayment (CHF)",
        100_000,
        3_000_000,
        int(c.downpayment),
        10_000,
    )
    c.buying_costs_pct = _rate_slider(
        "Buying costs (% of price)",
        0.02,
        0.06,
        c.buying_costs_pct,
        0.001,
    )
    c.sale_cost_pct = _rate_slider(
        "Sale costs on any modeled house sale (% of house value)",
        0.01,
        0.06,
        c.sale_cost_pct,
        0.001,
    )
    c.house_market_rent_monthly = st.number_input(
        "Estimated monthly market rent for VL / re-renting (CHF)",
        500,
        20_000,
        int(c.house_market_rent_monthly),
        50,
    )
    c.maintenance_rate = _rate_slider(
        "Annual maintenance cash cost (% of house value)",
        0.0,
        0.03,
        c.maintenance_rate,
        0.001,
    )
    c.maintenance_deduction_rate_federal = _rate_slider(
        "Pre-2029 federal flat maintenance tax deduction",
        0.0,
        0.20,
        c.maintenance_deduction_rate_federal,
        0.01,
        help=(
            "For direct federal tax, the usual flat rule is 10% if the building is "
            "10 years old or less and 20% if it is older. Choose the bucket that "
            "matches the property you want to model."
        ),
    )
    c.maintenance_deduction_rate_cantonal = _rate_slider(
        "Pre-2029 Vaud flat maintenance tax deduction",
        0.0,
        0.30,
        c.maintenance_deduction_rate_cantonal,
        0.01,
        help=(
            "For Vaud owner-occupied homes, the usual flat rule is 20% if the "
            "property is under 20 years old and 30% if it is older. This is kept "
            "separate from the federal rule because the published buckets differ."
        ),
    )

with st.sidebar.expander("Mortgage"):
    c.interest_rate = _rate_slider("Mortgage rate", 0.0, 0.08, c.interest_rate, 0.001, key="interest_rate")
    c.mortgage_rate_volatility = _rate_slider(
        "Mortgage-rate volatility (% points/yr)",
        0.0,
        0.03,
        c.mortgage_rate_volatility,
        0.0005,
        key="mortgage_rate_volatility",
        help=(
            "Adds year-to-year uncertainty around the mortgage rate. If this is zero and stress-rate "
            "jumps are off, the modeled rate stays at the entered mortgage rate as long as the floor "
            "and cap include it."
        ),
    )
    c.mortgage_rate_min = _rate_slider(
        "Mortgage-rate floor",
        0.0,
        0.08,
        c.mortgage_rate_min,
        0.001,
        key="mortgage_rate_min",
        help="Lowest allowed modeled mortgage rate. It must not be above the entered mortgage rate.",
    )
    c.mortgage_rate_max = _rate_slider(
        "Mortgage-rate cap",
        max(0.01, c.mortgage_rate_min),
        0.15,
        c.mortgage_rate_max,
        0.001,
        key="mortgage_rate_max",
        help="Highest allowed modeled mortgage rate. It must not be below the entered mortgage rate.",
    )
    c.amortization_annual = st.number_input(
        "Annual amortization amount (CHF)",
        0,
        100_000,
        int(c.amortization_annual),
        1_000,
        help="This is the yearly amount used for bank-required amortization. If voluntary amortization is turned on, the same amount is also used after the bank-required stop level has been reached.",
    )
    c.voluntary_amortization = st.checkbox(
        "Continue voluntary direct amortization after required amortization stops",
        value=c.voluntary_amortization,
        help="If ON, once bank-required amortization has stopped, the model continues repaying the mortgage directly by the same annual amount until the debt reaches zero.",
    )
    c.ltv_floor = st.slider(
        "Bank-required amortization stop level (LTV share)",
        0.50,
        0.80,
        c.ltv_floor,
        0.005,
    )
    c.amortization_strategy = st.selectbox(
        "Required-amortization strategy",
        options=["direct", "indirect_3a"],
        format_func=lambda value: {
            "direct": "Direct amortization",
            "indirect_3a": "Indirect amortization via pillar 3a",
        }[value],
        index=0 if c.amortization_strategy == "direct" else 1,
        help="This affects bank-required amortization while the mortgage is above the bank-required stop level. Voluntary amortization after that point is modeled as direct debt repayment.",
    )
    example_house_price = 1_000_000.0
    example_floor = example_house_price * c.ltv_floor
    st.caption(
        f"Example: assuming a CHF {example_house_price:,.0f} purchase price, a stop level of "
        f"{c.ltv_floor:.1%} of purchase price means bank-required amortization stops once the "
        f"mortgage reaches CHF {example_floor:,.0f}."
    )
    if c.house_price - c.downpayment <= c.house_price * c.ltv_floor:
        start_debt = c.house_price - c.downpayment
        amortization_floor = c.house_price * c.ltv_floor
        if c.voluntary_amortization:
            st.caption(
                f"With the current purchase price, downpayment, and chosen stop level, the starting mortgage "
                f"(CHF {start_debt:,.0f}) is already below the model's bank-required amortization stop level "
                f"(CHF {amortization_floor:,.0f}). Required amortization is therefore zero, but because "
                f"voluntary amortization is ON the model repays up to CHF {c.amortization_annual:,.0f} "
                f"per year directly."
            )
        else:
            st.caption(
                f"With the current purchase price, downpayment, and chosen stop level, the starting mortgage "
                f"(CHF {start_debt:,.0f}) is already below the model's bank-required amortization stop level "
                f"(CHF {amortization_floor:,.0f}). In that case required amortization is zero, so "
                f"changing the annual amortization amount or the required-amortization strategy will not change the results "
                f"unless you turn voluntary amortization ON."
            )

with st.sidebar.expander("Markets"):
    c.stock_growth_world_usd = _rate_slider(
        "Average world stock ETF return in USD",
        -0.02,
        0.12,
        c.stock_growth_world_usd,
        0.001,
        help="Think of this as the long-run total return of something like VT measured in USD before ETF fees.",
    )
    c.chf_appreciation_vs_usd = _rate_slider(
        "Average CHF strengthening vs USD",
        -0.04,
        0.04,
        c.chf_appreciation_vs_usd,
        0.001,
        help="Positive values mean the CHF strengthens against the USD, which reduces the CHF return of a USD-priced ETF. Negative values mean the CHF weakens.",
    )
    st.caption(
        f"These two settings imply an average stock return of {c.stock_growth_chf:.2%}/yr in CHF before ETF fees."
    )
    c.stock_volatility = _rate_slider("Stock volatility", 0.0, 0.30, c.stock_volatility, 0.005)
    c.house_growth = _rate_slider("Average home-price growth", -0.02, 0.08, c.house_growth, 0.001)
    c.house_volatility = _rate_slider("House volatility", 0.0, 0.15, c.house_volatility, 0.005)
    c.asset_correlation = st.slider("Stock-house correlation", -1.0, 1.0, c.asset_correlation, 0.05)
    c.salary_growth_volatility = _rate_slider(
        "Salary-growth volatility",
        0.0,
        0.10,
        c.salary_growth_volatility,
        0.0025,
        key="salary_growth_volatility",
        help="Adds year-to-year uncertainty around the real salary-growth assumption.",
    )
    c.rent_growth_volatility = _rate_slider(
        "Market-rent growth volatility",
        0.0,
        0.10,
        c.rent_growth_volatility,
        0.0025,
        key="rent_growth_volatility",
        help="Applies to the market-rent path used for VL / re-renting, not to a protected existing lease rent all by itself.",
    )
    c.market_rent_real_growth = _rate_slider(
        "Market-rent growth above inflation",
        -0.03,
        0.05,
        c.market_rent_real_growth,
        0.001,
        key="market_rent_real_growth",
        help=(
            "Applies to the market-rent path used for VL and for the buyer's rent after a forced sale. "
            "It is separate from the current-lease rent in the renter path."
        ),
    )
    c.dividend_yield = _rate_slider(
        "Taxable dividend yield",
        0.0,
        0.05,
        c.dividend_yield,
        0.001,
    )

with st.sidebar.expander("Fees"):
    c.portfolio_ter = _rate_slider("Portfolio TER", 0.0, 0.02, c.portfolio_ter, 0.0005)
    c.pillar_3a_ter = _rate_slider("Pillar 3a TER", 0.0, 0.02, c.pillar_3a_ter, 0.0005)
    c.liquidity_shortfall_rate = _rate_slider(
        "Interest rate applied to negative cash balances",
        0.0,
        0.10,
        c.liquidity_shortfall_rate,
        0.001,
        help="Negative balances compound at this shortfall rate rather than at stock-market returns.",
    )

with st.sidebar.expander("Pillar 3a"):
    c.initial_pillar_3a_assets = st.number_input(
        "Initial pillar 3a savings (CHF)",
        0,
        5_000_000,
        int(c.initial_pillar_3a_assets),
        10_000,
        help=(
            "Existing household pillar 3a balance at the start of the simulation. "
            "It is kept separate from cash and taxable investments, grows with the pillar 3a return process, "
            "and is shown after estimated withdrawal tax. If the buyer's cash and taxable investments "
            "are not enough for the purchase, the model uses this 3a money."
        ),
    )
    c.pillar_3a_annual_per_person = st.number_input(
        "Annual pillar 3a cap for a person with a pension institution (CHF)",
        0,
        15_000,
        int(c.pillar_3a_annual_per_person),
        100,
        help=(
            "This is the standard Swiss employee cap used when that person is affiliated to a "
            "pension institution (2nd pillar). If tax-law indexation is ON below, the simulator "
            "projects this CHF amount forward with inflation in later years."
        ),
    )
    c.p1_pillar2_affiliated = st.checkbox(
        "P1 is affiliated to a pension institution",
        value=c.p1_pillar2_affiliated,
        help=(
            "If ON, P1 can use the standard employee 3a cap above. If OFF, the simulator uses "
            "the Swiss fallback rule of 20% of modeled post-social earned income, up to the "
            "higher official max for people without a pension institution."
        ),
    )
    c.p2_pillar2_affiliated = st.checkbox(
        "P2 is affiliated to a pension institution",
        value=c.p2_pillar2_affiliated,
        help=(
            "Use OFF for a self-employed or otherwise non-affiliated case that should follow "
            "the higher 20%-of-earned-income style rule instead of the standard employee cap."
        ),
    )
    c.pillar_3a_withdrawal_tax_rate = _rate_slider(
        "Withdrawal tax rate approximation",
        0.03,
        0.15,
        c.pillar_3a_withdrawal_tax_rate,
        0.005,
    )
    separate_3a_process = st.checkbox(
        "Model pillar 3a with a separate return process",
        value=(
            c.pillar_3a_growth_chf is not None
            or c.pillar_3a_volatility is not None
            or c.pillar_3a_correlation_to_portfolio != 1.0
        ),
        help="Useful if your 3a allocation is more conservative than your taxable ETF portfolio.",
    )
    if separate_3a_process:
        default_3a_growth = c.stock_growth_chf if c.pillar_3a_growth_chf is None else c.pillar_3a_growth_chf
        default_3a_vol = c.stock_volatility if c.pillar_3a_volatility is None else c.pillar_3a_volatility
        c.pillar_3a_growth_chf = _rate_slider(
            "Pillar 3a average return in CHF",
            -0.02,
            0.12,
            default_3a_growth,
            0.001,
        )
        c.pillar_3a_volatility = _rate_slider(
            "Pillar 3a volatility",
            0.0,
            0.30,
            default_3a_vol,
            0.005,
        )
        c.pillar_3a_correlation_to_portfolio = st.slider(
            "Pillar 3a correlation to taxable portfolio",
            -1.0,
            1.0,
            c.pillar_3a_correlation_to_portfolio,
            0.05,
        )
    else:
        c.pillar_3a_growth_chf = None
        c.pillar_3a_volatility = None
        c.pillar_3a_correlation_to_portfolio = 1.0

purchase_cash_outlay = c.purchase_cash_outlay()
initial_3a_purchase_withdrawal = c.initial_pillar_3a_withdrawal_for_purchase()
if initial_3a_purchase_withdrawal > 0.0 and np.isfinite(initial_3a_purchase_withdrawal):
    initial_3a_purchase_net = initial_3a_purchase_withdrawal * (
        1.0 - c.pillar_3a_withdrawal_tax_rate
    )
    st.sidebar.info(
        "The buyer uses initial pillar 3a savings for the purchase: "
        f"CHF {initial_3a_purchase_withdrawal:,.0f} withdrawn, "
        f"CHF {initial_3a_purchase_net:,.0f} left after estimated withdrawal tax."
    )

with st.sidebar.expander("Stress & downside"):
    c.stress_event_probability = _rate_slider(
        "Average share of stress years",
        0.0,
        0.20,
        c.stress_event_probability,
        0.005,
        key="stress_event_probability",
        help=(
            "When stress clustering is 0, each year is drawn on its own. With higher stress "
            "clustering, bad years can bunch together into runs."
        ),
    )
    c.stress_persistence = _rate_slider(
        "How much stress years bunch together",
        0.0,
        0.90,
        c.stress_persistence,
        0.05,
        key="stress_persistence",
        help=(
            "0 means each year is drawn on its own. Higher values make one stress year more "
            "likely to be followed by another."
        ),
    )
    c.stress_stock_drawdown = _rate_slider(
        "Stress-year extra stock haircut",
        0.0,
        0.60,
        c.stress_stock_drawdown,
        0.01,
        key="stress_stock_drawdown",
        help="This is an extra haircut applied on top of that year's normally drawn stock return, not a target total return for the year.",
    )
    c.stress_house_drawdown = _rate_slider(
        "Stress-year extra house-price haircut",
        0.0,
        0.40,
        c.stress_house_drawdown,
        0.01,
        key="stress_house_drawdown",
        help="This is an extra haircut applied on top of that year's normally drawn house-price return, not a target total return for the year.",
    )
    c.stress_salary_hit = _rate_slider(
        "Stress-year salary hit",
        0.0,
        0.50,
        c.stress_salary_hit,
        0.01,
        key="stress_salary_hit",
        help="A one-year salary cut applied only in the stress year itself.",
    )
    c.stress_rent_jump = _rate_slider(
        "Stress-year rent jump",
        0.0,
        0.30,
        c.stress_rent_jump,
        0.01,
        key="stress_rent_jump",
        help=(
            "A one-year extra rent increase applied to any rent paid in that stress year "
            "and to the owner's market-rent proxy."
        ),
    )
    c.stress_rate_jump = _rate_slider(
        "Stress-year mortgage-rate jump",
        0.0,
        0.05,
        c.stress_rate_jump,
        0.001,
        key="stress_rate_jump",
    )
    c.force_buy_sale_on_liquidity_crisis = st.checkbox(
        "Force a home sale after a buyer liquidity crisis",
        key="force_buy_sale_on_liquidity_crisis",
        help=(
            "If the buyer's liquid balance drops below the configured multi-month cash buffer, "
            "the model sells the home, applies the forced-sale friction settings below, and "
            "continues the path as a renter."
        ),
    )
    c.liquidity_crisis_buffer_months = st.slider(
        "Buyer liquidity buffer before forced sale (months of current outflows)",
        0.0,
        24.0,
        step=0.5,
        key="liquidity_crisis_buffer_months",
    )
    c.forced_sale_extra_cost_chf = st.number_input(
        "Forced-sale moving and emergency costs (CHF)",
        min_value=0,
        max_value=100_000,
        step=1_000,
        key="forced_sale_extra_cost_chf",
        help=(
            "One-off costs that are lost for good if the buyer has to sell under stress, "
            "such as moving, urgent paperwork, or failed-refinancing costs."
        ),
    )
    c.forced_sale_transition_months = st.slider(
        "Forced-sale overlap / transition rent (months)",
        0.0,
        6.0,
        step=0.5,
        key="forced_sale_transition_months",
        help=(
            "Extra months of market rent paid during the move and search period after a "
            "forced sale."
        ),
    )
    c.forced_sale_rental_deposit_months = st.slider(
        "Forced-sale rental deposit (months of new rent)",
        0.0,
        3.0,
        step=0.5,
        key="forced_sale_rental_deposit_months",
        help=(
            "Locked cash for the new lease after a forced sale. This hurts liquidity but "
            "counts as household wealth."
        ),
    )

with st.sidebar.expander("Vaud / commune taxes"):
    selected_vd_commune_name = st.selectbox(
        "Official 2026 Vaud commune",
        options=[MANUAL_VAUD_COMMUNE, *vaud_commune_names],
        key="selected_vd_commune_name",
        help=(
            "Choose a commune to fill the official 2026 total commune coefficient and "
            "the separate communal `impôt foncier`. The fields below stay editable."
        ),
    )
    selected_vd_commune = None
    if selected_vd_commune_name == MANUAL_VAUD_COMMUNE:
        st.session_state["applied_vd_commune_name"] = MANUAL_VAUD_COMMUNE
    else:
        if st.session_state.get("applied_vd_commune_name") != selected_vd_commune_name:
            _apply_selected_vd_commune(selected_vd_commune_name)
        selected_vd_commune = get_vaud_commune(selected_vd_commune_name)
        st.caption(
            "Official Vaud 2026 table: "
            f"{selected_vd_commune.district}, total commune coefficient "
            f"{selected_vd_commune.total_pct:.1f}% ({selected_vd_commune.commune_multiplier:.3f}), "
            f"`impôt foncier` {selected_vd_commune.property_tax_per_mille:.2f}‰."
        )
        if selected_vd_commune.notes:
            st.caption(f"Official note: {selected_vd_commune.notes}")
    if st.button(
        "Re-apply selected commune values",
        use_container_width=True,
        disabled=selected_vd_commune is None,
    ):
        _apply_selected_vd_commune(selected_vd_commune_name)
        st.rerun()
    st.caption(
        "The selector uses the official Vaud 2026 commune table as a starting point. "
        "You can override the numbers below if you need a manual scenario."
    )
    c.index_tax_parameters_with_inflation = st.checkbox(
        "Move built-in tax CHF amounts up with inflation",
        key="index_tax_parameters_with_inflation",
        help=(
            "When ON, the simulator also moves its built-in 2026 tax brackets, deduction "
            "limits, wealth thresholds, and yearly pillar-3a cap upward with the realized "
            "inflation path up to the start of each year. If OFF, those CHF amounts stay frozen "
            "at their 2026 values. This is a modeling choice, not a promise about future tax tables."
        ),
    )
    st.caption(
        "The built-in tax tables are 2026 values. If this box is ON, the simulator moves those "
        "CHF amounts upward over time instead of leaving them frozen forever at 2026 levels. "
        "With stochastic inflation, that indexing follows the realized inflation path rather "
        "than a single flat inflation assumption."
    )
    c.commune_multiplier = st.number_input(
        "Commune income/wealth-tax coefficient",
        min_value=min(0.0, vaud_commune_multiplier_min),
        max_value=max(1.0, vaud_commune_multiplier_max),
        step=0.005,
        key="commune_multiplier",
        help=(
            "For the official Vaud commune selector above, this uses the published "
            "`pour-cent total` rather than only the base percentage. Manual scenarios "
            "can use any value within the full bundled official range."
        ),
    )
    communal_property_tax_per_mille = st.slider(
        "Commune property-tax rate (per mille of fiscal value)",
        min_value=0.0,
        max_value=1.5,
        step=0.05,
        key="communal_property_tax_per_mille_ui",
        help=(
            "This is Vaud's separate communal `impôt foncier`. Enter the rate from your "
            "commune's `arrêté d'imposition`. The simulator applies it to the property-tax "
            "fiscal-value proxy below."
        ),
    )
    c.communal_property_tax_rate = communal_property_tax_per_mille / 1_000.0
    c.canton_multiplier = st.number_input(
        "Vaud canton coefficient",
        1.0,
        2.0,
        c.canton_multiplier,
        0.005,
    )
    c.use_official_cantonal_income_tax_reduction_schedule = st.checkbox(
        "Use official Vaud income-tax reduction schedule",
        key="use_official_cantonal_income_tax_reduction_schedule",
        help=(
            "The official schedule modeled by default is 5% for tax year 2026 "
            "and 7% from tax year 2027 onward. It reduces only the cantonal "
            "income-tax part, not commune tax and not wealth tax."
        ),
    )
    if c.use_official_cantonal_income_tax_reduction_schedule:
        st.caption(
            "Official schedule used: 2026 = 5% cantonal income-tax reduction; "
            "2027 onward = 7%."
        )
    else:
        c.cantonal_income_tax_reduction_rate = _rate_slider(
            "Manual flat cantonal income-tax reduction",
            0.0,
            0.10,
            c.cantonal_income_tax_reduction_rate,
            0.01,
            help=(
                "Manual scenario override. This applies one flat reduction only inside "
                "the year window below."
            ),
        )
        c.cantonal_income_tax_reduction_start_year = st.number_input(
            "Manual reduction start year",
            2020,
            2040,
            c.cantonal_income_tax_reduction_start_year,
        )
        c.cantonal_income_tax_reduction_end_year = st.number_input(
            "Manual reduction end year",
            2020,
            2040,
            c.cantonal_income_tax_reduction_end_year,
        )
    c.wealth_tax_value_ratio = st.slider(
        "Wealth-tax fiscal-value proxy / market value ratio",
        0.50,
        1.0,
        c.wealth_tax_value_ratio,
        0.01,
        help=(
            "Used for Vaud wealth tax on the home. This is separated from the property-tax "
            "fiscal-value proxy because the real fiscal assessment must be checked for the specific property."
        ),
    )
    c.property_tax_value_ratio = st.slider(
        "Property-tax fiscal-value proxy / market value ratio",
        0.50,
        1.0,
        c.property_tax_value_ratio,
        0.01,
        help=(
            "Used only for the separate communal impôt foncier. Enter the closest proxy to "
            "the property's official fiscal assessment at 1 January."
        ),
    )
    c.vl_factor_cantonal = st.slider("VL factor — cantonal", 0.40, 0.90, c.vl_factor_cantonal, 0.01)
    c.vl_factor_federal = st.slider("VL factor — federal", 0.40, 0.90, c.vl_factor_federal, 0.01)

with st.sidebar.expander("Foreign withholding / DA-1"):
    c.da1_eligible_dividend_share = _rate_slider(
        "Share of dividends that might qualify for DA-1",
        0.0,
        1.0,
        c.da1_eligible_dividend_share,
        0.01,
        help=(
            "Leave this at 0 unless you specifically want to model foreign dividends that "
            "might generate a Swiss tax credit. The simulator does not assume that every "
            "ETF or foreign dividend automatically does that."
        ),
    )
    c.da1_non_refundable_withholding_rate = _rate_slider(
        "Foreign tax kept before you receive the dividend",
        0.0,
        0.35,
        c.da1_non_refundable_withholding_rate,
        0.005,
    )
    c.da1_minimum_non_refundable_tax = st.number_input(
        "Minimum foreign tax before the model gives any DA-1 credit (CHF)",
        0,
        1_000,
        int(c.da1_minimum_non_refundable_tax),
        10,
    )
    st.caption(
        "Simple version: some foreign countries keep part of a dividend before it reaches you. "
        "This section lets you model a possible Swiss tax credit for that loss, but the default "
        "is zero."
    )

with st.sidebar.expander("2029 reform"):
    c.reform_year = st.number_input("Reform year", 2026, 2040, c.reform_year)
    c.first_time_buyer_years = st.number_input(
        "Years before the first-time-buyer deduction phases to zero",
        1,
        20,
        c.first_time_buyer_years,
    )
    first_time_years_max = int(c.first_time_buyer_years)
    for first_time_key in (
        "first_time_buyer_years_used_before_start_p1",
        "first_time_buyer_years_used_before_start_p2",
        "first_time_buyer_years_used_before_start_married",
    ):
        if first_time_key in st.session_state:
            st.session_state[first_time_key] = min(
                int(st.session_state[first_time_key]),
                first_time_years_max,
            )
    if c.household_status == "married":
        c.first_time_home_buyer_married = st.checkbox(
            "Married household likely qualifies for Swiss first-home deduction",
            value=c.first_time_home_buyer_married,
            help=(
                "Official reform materials set a joint starting cap of CHF 10,000 for married "
                "couples and say the deduction is tied to buying a first home in Switzerland "
                "that you live in yourselves. Prior owner-occupation abroad does not by "
                "itself appear to disqualify that deduction."
            ),
        )
        st.caption(
            "In married mode the simulator applies one jointly taxed first-home deduction cap. "
            "Official reform materials say prior owner-occupation abroad does not by itself "
            "block the deduction for a first home in Switzerland that you live in yourselves."
        )
        c.first_time_buyer_interest_deduction_married_max = st.number_input(
            "First-time-buyer annual interest deduction cap for married household (CHF)",
            0,
            20_000,
            int(c.first_time_buyer_interest_deduction_married_max),
            100,
        )
        c.first_time_buyer_years_used_before_start_married = st.number_input(
            "Deduction years already used before the start year",
            min_value=0,
            max_value=first_time_years_max,
            step=1,
            key="first_time_buyer_years_used_before_start_married",
            help=(
                "Use this only if the qualifying first home in Switzerland that you lived in "
                "was bought before the simulation start year and some of the deduction years "
                "has already been used up."
            ),
        )
    else:
        c.first_time_home_buyer_p1 = st.checkbox(
            "P1 likely qualifies for Swiss first-home deduction",
            value=c.first_time_home_buyer_p1,
            help="In unmarried mode this is tracked per taxpayer. Official reform materials indicate that prior owner-occupation abroad does not by itself block the deduction; the key question is whether P1 is buying a first home in Switzerland that P1 will live in.",
        )
        c.first_time_home_buyer_p2 = st.checkbox(
            "P2 likely qualifies for Swiss first-home deduction",
            value=c.first_time_home_buyer_p2,
            help="In unmarried mode this is tracked per taxpayer. Official reform materials indicate that prior owner-occupation abroad does not by itself block the deduction; the key question is whether P2 is buying a first home in Switzerland that P2 will live in.",
        )
        st.caption(
            "In unmarried mode the simulator tracks first-home eligibility per taxpayer. "
            "Official reform materials also indicate that prior owner-occupation abroad does "
            "not by itself disqualify a first home in Switzerland that you live in."
        )
        c.first_time_buyer_interest_deduction_single_max = st.number_input(
            "First-time-buyer annual interest deduction cap per unmarried taxpayer (CHF)",
            0,
            10_000,
            int(c.first_time_buyer_interest_deduction_single_max),
            100,
        )
        c.first_time_buyer_years_used_before_start_p1 = st.number_input(
            "P1 deduction years already used before the start year",
            min_value=0,
            max_value=first_time_years_max,
            step=1,
            key="first_time_buyer_years_used_before_start_p1",
            help=(
                "Use this only if P1's qualifying first Swiss home was bought "
                "before the simulation start year."
            ),
        )
        c.first_time_buyer_years_used_before_start_p2 = st.number_input(
            "P2 deduction years already used before the start year",
            min_value=0,
            max_value=first_time_years_max,
            step=1,
            key="first_time_buyer_years_used_before_start_p2",
            help=(
                "Use this only if P2's qualifying first Swiss home was bought "
                "before the simulation start year."
            ),
        )
    st.caption(
        "These 'already used' fields only shorten the remaining post-2029 deduction years. "
        "They do not turn the whole buy path into a home that was already owned before the start year."
    )


st.title("Vaud Buy vs Rent — Monte Carlo comparison")
household_caption = (
    "Married jointly taxed household"
    if c.household_status == "married"
    else "Unmarried cohabiting household"
)
if c.household_status == "unmarried" and c.n_children > 0 and not c.vaud_single_parent_household:
    if abs(c.salary_split - 0.5) < 1e-9:
        federal_parental_to_p1 = c.child_claimed_by_p1
    else:
        federal_parental_to_p1 = c.salary_split > 0.5
else:
    federal_parental_to_p1 = c.child_claimed_by_p1
child_caption = (
    "Federal/Vaud taxes computed jointly."
    if c.household_status == "married"
    else (
        (
            "Federal cohabiting-parent default: child deductions and childcare are split 50 / 50, "
            f"and the parental tariff goes to {'P1' if federal_parental_to_p1 else 'P2'}."
        )
        if c.n_children > 0 and not c.vaud_single_parent_household
        else (
            f"Federal parental tariff claimed by {'P1' if c.child_claimed_by_p1 else 'P2'}."
            if c.n_children > 0
            else "No child-related federal/Vaud split is active."
        )
    )
)
st.caption(
    f"{household_caption}, {_format_children(c.n_children)}, commune coefficient {c.commune_multiplier:.3f}, "
    f"commune property tax {c.communal_property_tax_rate * 1_000.0:.2f}‰. "
    f"{child_caption} "
    f"Purchase assumed at start year {c.start_year}. "
    f"Required amortization: {'indirect via pillar 3a' if c.amortization_strategy == 'indirect_3a' else 'direct'}. "
    f"Voluntary amortization after required amortization stops: {'on' if c.voluntary_amortization else 'off'}."
)

try:
    result = run_cached(c)
except ValueError as exc:
    st.error(str(exc))
    st.stop()

display_deflator = result.inflation_index
flow_deflator = np.ones_like(display_deflator)
flow_deflator[:, 1:] = display_deflator[:, :-1]

if show_real:
    buy_nw = _deflate_paths(result.buy_net_worth, display_deflator)
    rent_nw = _deflate_paths(result.rent_net_worth, display_deflator)
    buy_portfolio_paths = _deflate_paths(result.buy_portfolio, display_deflator)
    buy_rental_deposit_paths = _deflate_paths(result.buy_rental_deposit, display_deflator)
    rent_portfolio_paths = _deflate_paths(result.rent_portfolio, display_deflator)
    buy_p3a_paths = _deflate_paths(result.buy_pillar_3a, display_deflator)
    rent_p3a_paths = _deflate_paths(result.rent_pillar_3a, display_deflator)
    house_val_paths = _deflate_paths(result.house_val, display_deflator)
    debt_paths = _deflate_paths(result.debt, display_deflator)
    buy_tax_paths = _deflate_paths(result.buy_tax, flow_deflator)
    rent_tax_paths = _deflate_paths(result.rent_tax, flow_deflator)
    buy_surplus_paths = _deflate_paths(result.buy_surplus, flow_deflator)
    rent_surplus_paths = _deflate_paths(result.rent_surplus, flow_deflator)
    terminal_deflator = display_deflator[:, -1]
    buy_term = result.buy_terminal_liquid / terminal_deflator
    rent_term = result.rent_terminal_liquid / terminal_deflator
    suffix = f" (in {c.start_year} purchasing power)"
else:
    buy_nw = result.buy_net_worth
    rent_nw = result.rent_net_worth
    buy_portfolio_paths = result.buy_portfolio
    buy_rental_deposit_paths = result.buy_rental_deposit
    rent_portfolio_paths = result.rent_portfolio
    buy_p3a_paths = result.buy_pillar_3a
    rent_p3a_paths = result.rent_pillar_3a
    house_val_paths = result.house_val
    debt_paths = result.debt
    buy_tax_paths = result.buy_tax
    rent_tax_paths = result.rent_tax
    buy_surplus_paths = result.buy_surplus
    rent_surplus_paths = result.rent_surplus
    buy_term = result.buy_terminal_liquid
    rent_term = result.rent_terminal_liquid
    suffix = " (future CHF)"

delta = buy_term - rent_term
p_buy_wins = float((delta > 0).mean())
p_buy_wins_margin = float(1.96 * np.sqrt(p_buy_wins * (1.0 - p_buy_wins) / delta.size))
median_buy = float(np.median(buy_term))
median_rent = float(np.median(rent_term))
median_delta = float(np.median(delta))
p5_delta = float(np.percentile(delta, 5))
p95_delta = float(np.percentile(delta, 95))
buy_ruin = float(result.buy_ruin_any.mean())
rent_ruin = float(result.rent_ruin_any.mean())
buy_forced_sale = float(result.buy_forced_sale_any.mean())
buy_cash_crisis = float(result.buy_cash_crisis_any.mean())
delta_expected_shortfall_10 = _expected_shortfall(delta, 0.10)
delta_expected_shortfall_01 = _expected_shortfall(delta, 0.01)

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("P(Buy > Rent at horizon)", f"{p_buy_wins:.1%}")
m2.metric(
    f"Median Buy − Rent horizon wealth{suffix}",
    f"{median_delta:,.0f} CHF",
    delta=f"{'favors buy' if median_delta > 0 else 'favors rent'}",
)
m3.metric(f"Median Buy horizon wealth{suffix}", f"{median_buy:,.0f} CHF")
m4.metric(f"Median Rent horizon wealth{suffix}", f"{median_rent:,.0f} CHF")
m5.metric(
    "Buyer cash crisis (any year)",
    f"{buy_cash_crisis:.1%}",
    delta=f"Rent unresolved: {rent_ruin:.1%}",
    delta_color="inverse",
)
st.caption(
    "The KPI row and the histogram use horizon wealth after liquidation. For the buyer, that means "
    "the home is sold at the horizon if it is still owned, and the net cash after sale costs, IGI, "
    "and mortgage payoff is counted. "
    "For both paths, pillar 3a is shown after the modeled withdrawal tax. The fan charts below use end-of-year "
    "running net worth, not a separate liquidation event. The percentages are counts inside the simulated futures "
    "made from your settings; they are not proven odds for real life. The buyer cash-crisis metric counts both "
    "unresolved negative liquid balances and forced sales triggered by a liquidity crisis. At the current "
    f"{delta.size:,} iterations, plain Monte Carlo sampling noise around P(Buy > Rent) is roughly "
    f"±{p_buy_wins_margin:.1%}; near break-even, rerun with more iterations or a few seeds."
)
if show_real:
    st.caption(
        "In the inflation-adjusted view, stock and net-worth balances use end-of-year purchasing power. "
        "Annual cash-flow charts use start-of-year purchasing power because most modeled yearly cash "
        "flows are paid through that year; tax and forced-sale aggregates can mix several timings, so "
        "read those real-CHF annual values as practical approximations."
    )

tab_main, tab_delta, tab_compose, tab_diag, tab_assume = st.tabs(
    ["Overview", "Delta (Buy − Rent)", "Composition", "Diagnostics", "Assumptions"]
)

with tab_main:
    st.plotly_chart(
        _overlay_fan(
            result.years_axis,
            buy_nw,
            rent_nw,
            f"Net worth: Buy vs Rent{suffix}",
            suffix,
        ),
        width="stretch",
    )
    st.caption(
        "The fan shows the 10th to 90th percentile across simulations. "
        "These are pointwise yearly percentiles, not one single simulated family path. "
        "Each point is an end-of-year net-worth value, not a start-of-year balance or cash you could "
        "necessarily realize without selling immediately. The top KPI row instead assumes the "
        "strategies are settled at the horizon, so those numbers will not match this chart exactly. "
        "Percentiles describe the imaginary futures generated by the model, not a guarantee of what will happen."
    )

with tab_delta:
    delta_paths = buy_nw - rent_nw
    st.plotly_chart(
        _fan_chart(
            result.years_axis,
            delta_paths,
            f"Buy − Rent net worth over time{suffix}",
            "orange",
            suffix,
        ),
        width="stretch",
    )
    st.caption(
        "This fan chart is the year-by-year end-of-year net-worth gap. The histogram and "
        "the horizon metrics below switch to wealth after liquidation at the horizon."
    )
    st.plotly_chart(_delta_histogram(buy_term, rent_term, suffix), width="stretch")
    c1, c2, c3 = st.columns(3)
    c1.metric("P(Buy > Rent) at horizon", f"{p_buy_wins:.1%}")
    c2.metric(f"5th percentile horizon gap{suffix}", f"{p5_delta:,.0f} CHF")
    c3.metric(f"95th percentile horizon gap{suffix}", f"{p95_delta:,.0f} CHF")

with tab_compose:
    st.subheader(f"Buyer wealth composition{suffix}")
    st.caption(
        "The year labels here are end-of-year values. So the point marked 2026 already "
        "includes the first year's saving and investing. 'Liquid balance' means the "
        "buyer's regular liquid account outside the home and outside pillar 3a. It can be "
        "negative, and after a forced sale it can include cash left from selling the home. "
        "House equity uses the median signed value, so if the median buyer is "
        "underwater the red area drops below zero instead of being clipped away. If a "
        "forced sale happens, a locked rental deposit can appear as a separate asset. "
        "Each stacked layer is its own median, so the stack is a component snapshot rather "
        "than an exact decomposition of median net worth."
    )
    house_equity = house_val_paths - debt_paths
    _, house_equity_positive_med, house_equity_negative_med = _split_signed_median(
        house_equity
    )
    buy_port_med = np.median(buy_portfolio_paths, axis=0)
    buy_deposit_med = np.median(buy_rental_deposit_paths, axis=0)
    rent_port_med = np.median(rent_portfolio_paths, axis=0)
    buy_p3a_after = (1.0 - c.pillar_3a_withdrawal_tax_rate) * buy_p3a_paths
    rent_p3a_after = (1.0 - c.pillar_3a_withdrawal_tax_rate) * rent_p3a_paths
    buy_p3a_after_med = np.median(buy_p3a_after, axis=0)
    rent_p3a_after_med = np.median(rent_p3a_after, axis=0)

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=result.years_axis,
            y=house_equity_positive_med,
            name="House equity",
            stackgroup="one",
            line=dict(width=0.5, color="#005ac8"),
        )
    )
    if np.any(house_equity_negative_med < 0.0):
        fig.add_trace(
            go.Scatter(
                x=result.years_axis,
                y=house_equity_negative_med,
                name="Underwater home equity",
                fill="tozeroy",
                line=dict(width=0.5, color="#c0392b"),
            )
        )
    fig.add_hline(y=0.0, line_color="#999", line_width=1)
    fig.add_trace(
        go.Scatter(
            x=result.years_axis,
            y=buy_port_med,
            name="Liquid balance",
            stackgroup="one",
            line=dict(width=0.5, color="#00a03c"),
        )
    )
    if np.any(buy_deposit_med > 0.0):
        fig.add_trace(
            go.Scatter(
                x=result.years_axis,
                y=buy_deposit_med,
                name="Locked rental deposit",
                stackgroup="one",
                line=dict(width=0.5, color="#008b8b"),
            )
        )
    fig.add_trace(
        go.Scatter(
            x=result.years_axis,
            y=buy_p3a_after_med,
            name="Pillar 3a (after withdrawal tax)",
            stackgroup="one",
            line=dict(width=0.5, color="#dc6e00"),
        )
    )
    fig.update_layout(
        template="plotly_white",
        hovermode="x unified",
        yaxis_title=f"CHF{suffix}",
        title="Buyer wealth composition",
        margin=dict(l=30, r=10, t=60, b=30),
    )
    st.plotly_chart(fig, width="stretch")
    underwater_prob = np.mean(house_equity < 0.0, axis=0)
    st.caption(
        f"Highest simulated probability that the mortgage exceeds the house value at any year: "
        f"{float(underwater_prob.max()):.1%}. Because this chart uses medians, this probability "
        "is the better quick read on underwater tail risk."
    )

    st.subheader(f"Renter wealth composition (medians,{suffix.strip()})")
    st.caption(
        "For the renter, the wealth buckets are the liquid balance plus pillar 3a. The liquid "
        "balance can be negative in stressed paths. There is no home-equity layer on this side."
    )
    fig_rent = go.Figure()
    fig_rent.add_trace(
        go.Scatter(
            x=result.years_axis,
            y=rent_port_med,
            name="Liquid balance",
            stackgroup="one",
            line=dict(width=0.5, color="#00a03c"),
        )
    )
    fig_rent.add_trace(
        go.Scatter(
            x=result.years_axis,
            y=rent_p3a_after_med,
            name="Pillar 3a (after withdrawal tax)",
            stackgroup="one",
            line=dict(width=0.5, color="#dc6e00"),
        )
    )
    fig_rent.update_layout(
        template="plotly_white",
        hovermode="x unified",
        yaxis_title=f"CHF{suffix}",
        title="Renter wealth composition",
        margin=dict(l=30, r=10, t=60, b=30),
    )
    st.plotly_chart(fig_rent, width="stretch")

    st.subheader(f"Debt vs house value (medians,{suffix.strip()})")
    ltv_floor_line = np.full(c.years, c.house_price * c.ltv_floor, dtype=float)
    if show_real:
        ltv_floor_line = np.median(
            np.full_like(display_deflator, c.house_price * c.ltv_floor) / display_deflator,
            axis=0,
        )
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=result.years_axis, y=np.median(house_val_paths, axis=0), name="House value"))
    fig2.add_trace(go.Scatter(x=result.years_axis, y=np.median(debt_paths, axis=0), name="Debt remaining"))
    fig2.add_trace(
        go.Scatter(
            x=result.years_axis,
            y=ltv_floor_line,
            name=f"Bank-required stop level ({c.ltv_floor:.0%} of purchase price)",
            line=dict(dash="dash", color="grey"),
        )
    )
    fig2.update_layout(
        template="plotly_white",
        hovermode="x unified",
        yaxis_title=f"CHF{suffix}",
        margin=dict(l=30, r=10, t=60, b=30),
    )
    st.plotly_chart(fig2, width="stretch")
    st.caption(
        "Grey line = the bank-required amortization stop level in the model, fixed as the chosen "
        "LTV share of the purchase price. It is not a moving percentage of each year's market "
        "house value. In indirect pillar-3a mode, the bank-required reduction can be satisfied "
        "before raw debt reaches this grey line because pledged 3a balances also count toward "
        "the stop condition. If voluntary amortization is ON, debt can keep falling below "
        "the effective stop level afterward."
    )

with tab_diag:
    d1, d2, d3 = st.columns(3)
    d1.metric("Buyer forced sale (any year)", f"{buy_forced_sale:.1%}")
    d2.metric(f"Mean worst 10% horizon gap{suffix}", f"{delta_expected_shortfall_10:,.0f} CHF")
    d3.metric(f"Mean worst 1% horizon gap{suffix}", f"{delta_expected_shortfall_01:,.0f} CHF")
    st.caption(
        "These two numbers average the worst horizon buy-minus-rent outcomes, "
        "rather than showing only the cutoff percentile."
    )
    st.subheader("Inflation path and tax-law index path")
    fig_infl = go.Figure()
    fig_infl.add_trace(
        go.Scatter(
            x=result.years_axis,
            y=100.0 * np.median(result.inflation_rate, axis=0),
            name="Median annual inflation",
            line=dict(color="#dc6e00"),
        )
    )
    if c.index_tax_parameters_with_inflation:
        fig_infl.add_trace(
            go.Scatter(
                x=result.years_axis,
                y=100.0 * (np.median(result.tax_index_factor, axis=0) - 1.0),
                name="Median tax-law CHF uplift vs 2026",
                line=dict(color="#005ac8"),
            )
        )
    fig_infl.update_layout(
        template="plotly_white",
        hovermode="x unified",
        yaxis_title="Percent",
        title="Inflation and indexed tax-law amounts",
        margin=dict(l=30, r=10, t=60, b=30),
    )
    st.plotly_chart(fig_infl, width="stretch")
    st.caption(
        "The orange line is the median yearly inflation path used by the simulator. The blue line shows the "
        "median upward move in the built-in 2026 tax-law CHF amounts. That blue line uses a conservative "
        "lagged rule: a year's tax thresholds reflect inflation already observed before that year starts."
    )
    st.subheader(f"Annual tax burden (medians,{suffix.strip()})")
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=result.years_axis,
            y=np.median(buy_tax_paths, axis=0),
            name="Buyer tax",
            line=dict(color="#005ac8"),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=result.years_axis,
            y=np.median(rent_tax_paths, axis=0),
            name="Renter tax",
            line=dict(color="#00a03c"),
        )
    )
    fig.add_vline(
        x=c.reform_year,
        line_dash="dash",
        line_color="grey",
        annotation_text=f"Reform year {c.reform_year}",
    )
    fig.update_layout(
        template="plotly_white",
        hovermode="x unified",
        yaxis_title=f"CHF/yr{suffix}",
        title="Tax burden by year",
        margin=dict(l=30, r=10, t=60, b=30),
    )
    st.plotly_chart(fig, width="stretch")
    st.caption(
        "Buyer tax includes ordinary federal / Vaud income-and-wealth taxes plus the separate "
        "communal `impôt foncier` when you enter a non-zero commune property-tax rate. "
        "In a forced-sale year it can also include Vaud IGI on that early sale. The separate horizon "
        "settlement used by the headline wealth comparison can also subtract sale costs and IGI, but "
        "that horizon settlement is not drawn as an annual tax point here."
    )

    st.subheader(
        f"Net cash added to liquid balances after taxes, housing, other consumption, and pillar 3a "
        f"(medians,{suffix.strip()})"
    )
    fig2 = go.Figure()
    fig2.add_trace(
        go.Scatter(
            x=result.years_axis,
            y=np.median(buy_surplus_paths, axis=0),
            name="Buyer surplus",
            line=dict(color="#005ac8"),
        )
    )
    fig2.add_trace(
        go.Scatter(
            x=result.years_axis,
            y=np.median(rent_surplus_paths, axis=0),
            name="Renter surplus",
            line=dict(color="#00a03c"),
        )
    )
    fig2.update_layout(
        template="plotly_white",
        hovermode="x unified",
        yaxis_title=f"CHF/yr{suffix}",
        title="Net cash added to liquid balance",
        margin=dict(l=30, r=10, t=60, b=30),
    )
    st.plotly_chart(fig2, width="stretch")
    st.caption(
        "This is the net amount that actually lands in liquid balances during the year after taxes, "
        "housing, other consumption, and pillar 3a. In forced-sale years it also reflects the sale's "
        "cash proceeds and the one-off forced-sale frictions."
    )

with tab_assume:
    st.subheader("Effective configuration")
    st.caption(
        "These are the values the simulator actually used. Barèmes are embedded in "
        "`src/config.py`, not shown in this table."
    )
    cfg_dict = dataclasses.asdict(c)
    st.dataframe(
        {"field": list(cfg_dict.keys()), "value": [str(v) for v in cfg_dict.values()]},
        width="stretch",
        height=600,
    )
    st.info(
        "Implemented in the model:\n"
        "- Vaud 2026 income and wealth scales\n"
        "- Vaud 2026 insurance and childcare deductions, plus Vaud family deduction (code 725)\n"
        "- Vaud separately taxed and married quotient-familial cap logic\n"
        "- Vaud official cantonal income-tax reduction schedule: 5% in 2026 and 7% from 2027 onward, with a manual flat override option\n"
        "- Vaud IGI holding-period schedule for end-of-horizon or forced-sale tax\n"
        "- Commune coefficient plus separate commune `impôt foncier` input for Vaud municipalities\n"
        "- Federal 2026 IFD tariff, parental child credit, and childcare cap\n"
        "- Optional stochastic inflation paths\n"
        "- Inflation indexing of the embedded 2026 CHF tax-law amounts and annual pillar-3a cap when that scenario option is ON, using the realized inflation path with a conservative lagged rule\n"
        "- 2029 reform start, ending the tax office's made-up rent on your own home and the ordinary maintenance deduction\n\n"
        "Model options:\n"
        "- Married couple filing jointly\n"
        "- Unmarried two-adult household filing separately\n"
        "- Direct amortization\n"
        "- Indirect amortization via pillar 3a\n"
        "- Optional voluntary direct amortization after the bank-required stop level\n"
        "- Optional stochastic inflation with floor and cap controls\n"
        "- Swiss-style sticky contract rent for the renter path, linked mainly to the legal reference-rate mechanism instead of moving one-for-one with the consumer price index (CPI)\n"
        "- Optional stochastic salary, market-rent, and mortgage-rate paths\n"
        "- Stress years can happen one by one or come in bunches across assets, salary, rent, and mortgage rates\n"
        "- Optional forced home sale if the buyer runs out of cash, with moving costs, temporary overlap costs, and a locked rental deposit\n"
        "- Joint first-time-buyer deduction cap for married households\n"
        "- Separate first-time-buyer eligibility flags for P1 and P2 in unmarried mode\n"
        "- Optional already-used first-time-buyer years before the simulation start year\n"
        "- Unmarried whole-child / half-child child-allocation controls\n\n"
        "Still household-specific and worth checking manually:\n"
        "- Exact imputed rental value for your property\n"
        "- Whether the childcare spending you entered is really eligible for deduction in your specific case\n"
        "- Your commune's exact `impôt foncier` rate and the tax office's fiscal estimate for your property\n"
        "- How your bank would react if a house-price fall makes the mortgage look large compared with the new home value; the simulator does not model a fresh bank credit decision at renewal\n"
        "- Linked bad macro scenarios outside the explicit stress-year switch; ordinary inflation, salary, market-rent, and mortgage-rate shocks are not a full economic crisis model\n"
        "- Whether any of your investment income is really DA-1 eligible at the personal-taxpayer level\n"
        "- Whether the household really qualifies for the first-time-buyer deduction after 2029, even though prior owner-occupation abroad does not seem to disqualify the deduction on its own\n"
        "- Whether a future political change replaces the current Vaud cantonal income-tax reduction schedule\n"
        "- Exact pillar-3a withdrawal taxation and any withdrawal staggering strategy"
    )
