# Configuration & Dashboard Guide

This file explains every setting in `src/config.py` in plain language.

If a word feels too technical, check the glossary first.

The goal is simple:
- you should be able to tell what each variable means,
- which ones are real tax-law inputs and which ones are only modeling assumptions,
- and which ones are especially important to check with your real household numbers.

## Quick Glossary

`P1` / `P2`
- Partner 1 and Partner 2.

`CHF`
- Swiss francs.

`USD`
- United States dollars.

`ETF`
- Exchange-traded fund. In plain language, a fund that holds many investments at once and trades on the stock market.

`TER`
- Total expense ratio. In plain language, the yearly fee drag inside a fund or investment product.

`CPI`
- Consumer price index. In plain language, one standard way to measure overall inflation.

`VL`
- `Valeur locative`, often translated as imputed rental value. In plain language, a made-up rent amount that Swiss tax law can treat as taxable income for people living in their own home before the 2029 reform.

`LTV`
- Loan-to-value ratio. In plain language, mortgage debt divided by the home value.

`DA-1`
- The Swiss form sometimes used to claim back part of foreign tax kept from a dividend before you receive it.

`SARON`
- Swiss Average Rate Overnight. In plain language, a widely used Swiss short-term interest-rate benchmark.

`Eligible`
- In plain language, this means "really counts for this rule" rather than "might sound similar."

`Tax deduction`
- An amount that is subtracted before tax is calculated.

`Tax cap`
- The maximum amount the model lets you deduct or claim.

## How To Run It

Dashboard:

```bash
streamlit run src/visualizer.py
```

Checks:

```bash
python src/test_sanity.py
```

## The Core Mental Model

The dashboard compares two futures:
- `Buy`: you buy the home and invest whatever cash is left after taxes and yearly costs.
- `Rent`: you keep renting and invest the money that stays free.

Changing one setting can affect:
- taxes,
- cash left to invest each year,
- mortgage balance,
- pillar 3a savings,
- and final wealth.

## Run Controls

### `start_year`

The calendar year when the simulation starts.

This matters because:
- tax rules can change over time,
- child-related windows are counted from this starting point,
- and the 2029 reform is compared against this year.

### `years`

How many years the model runs forward.

This is the planning horizon, not the mortgage term written by a bank.

### `iterations`

How many random simulation paths are run.

More iterations usually mean more stable charts, but also slower runs.

### `rng_seed`

The random seed.

This does not change the economics. It only makes repeated runs reproducible.

### `parallel_workers`

How many CPU worker processes to use for the Monte Carlo path calculation.

The default is `-1`, which lets joblib use all available CPUs. Use `1` for serial execution.

## Household Profile

### `household_status`

Whether the project treats the two adults as:
- `unmarried`: taxed separately,
- `married`: taxed jointly.

This is one of the most important settings in the whole dashboard because it changes:
- the federal tax table,
- the Vaud family-parts rule,
- some deduction caps,
- the first-time-buyer deduction handling,
- and whether several child-allocation controls are even used.

### `salary_total`

Combined salary before payroll deductions.

In plain language:
- this is salary before payroll deductions are taken off,
- not take-home pay.

### `salary_split`

How much of `salary_total` belongs to P1.

Examples:
- `0.55` means 55% for P1 and 45% for P2.
- `0.50` means an even split.

This matters because unmarried partners are taxed separately.

In married mode, the salary split also matters for each person's work-related tax deductions, pillar 3a eligibility, and the married double-income deduction.

### `ownership_split`

How much of the home and mortgage legally belongs to P1.

Examples:
- `0.50` means equal co-ownership.
- `0.60` means P1 owns 60% and P2 owns 40%.

This is meant to reflect the legal ownership share, not who happens to pay groceries or school fees.

Important:
- in unmarried mode, this also controls how owner-side tax items are allocated between P1 and P2,
- in married mode, taxes are computed jointly, so this field matters much less.

### `portfolio_split`

How much of the taxable investment account belongs to P1.

This is the split used for tax allocation of the regular invested savings outside pillar 3a.

In married mode, the household is taxed jointly, so this split mainly matters for consistency of the scenario description rather than for the tax result itself.

## Child-Related Settings

### `n_children`

Number of children in the household.

Current built-in limit:
- `married` mode supports up to `5` children with the shipped official Vaud cap table,
- `unmarried` mode supports up to `3` because Vaud's published separately taxed cap table stops there.

### `child_claimed_by_p1`

Who gets the special lower federal tax table for one parent with a child.

This only matters in `unmarried` mode.

Important:
- for the common cohabiting-with-common-child case, the federal parental tariff goes to the higher-income parent,
- this field acts as the tie-breaker when both modeled salaries are equal,
- and it still matters in non-standard unmarried cases that are handled manually.

### `child_deduction_split_to_p1`

How much of the normal child-related tax deductions go to P1.

Important:
- for the common cohabiting-with-common-child case, the federal child-deduction split is `50 / 50`,
- this control is mainly for non-standard unmarried cases that you are modeling deliberately,
- and the dashboard shows it only when that manual choice is relevant.

The simulator restricts this to **whole-child or half-child** allocations.

Examples with one child:
- `0.50` means split equally.
- `1.00` means all to P1.
- `0.00` means all to P2.

Examples with two children:
- `0.75` means the equivalent of one and a half children allocated to P1 and half a child to P2.

This only matters in `unmarried` mode.

### `vaud_single_parent_household`

Whether the special Vaud single-parent tax-splitting rule is used.

For a cohabiting unmarried couple living together, this usually stays off.

If this is on, the simulator applies the special Vaud `1.3` base to the same adult selected by `child_claimed_by_p1`.

This setting is ignored in `married` mode.

### `vaud_child_quotient_share_to_p1`

How the child's extra Vaud family-parts share is split between P1 and P2.

This only matters in `unmarried` mode.

The simulator restricts this to **whole-child or half-child** allocations instead of arbitrary percentages.

The project also uses this split for Vaud’s family-deduction allocation, because Vaud links that deduction to the child share.

For shared-child cases, the simulator also splits Vaud’s published cap proportionally instead of forgetting it.

### `child_dependent_years`

How many simulation years the child is treated as a general dependent child for tax purposes.

This affects the broad child-related tax deductions.

### `childcare_deduction_years`

How many simulation years the project assumes the childcare **tax deduction** applies.

Important:
- this only controls how many years the childcare tax deduction is available,
- it does **not** automatically reduce the cash childcare spending hidden inside `annual_other_consumption`,
- and it is separate from `child_dependent_years` because deductible childcare usually stops much earlier than general child dependency.

### `annual_childcare_spend_household`

The household's real yearly childcare bill that might be deductible for tax purposes.

Important:
- this is the actual spending assumption,
- the simulator then applies the published federal and Vaud caps on top of it,
- and in long simulations the dashboard treats this as a start-year CHF amount and lets it rise with the same inflation path used elsewhere.

### `childcare_spend_split_to_p1`

In `unmarried` mode, which share of the modeled childcare bill is treated as paid by P1.

Important:
- for the common cohabiting-with-common-child case, this split is `50 / 50`,
- because the federal guidance treats that shared-household case as a shared deduction case unless another split is proved,
- and the dashboard shows this control only when you are modeling a non-standard unmarried case by hand.

## Property And Rent

### `house_price`

Purchase price of the home.

### `initial_liquid_assets`

Cash and taxable investments available before choosing whether to buy or rent.

This includes cash and taxable investment accounts that can realistically be used for the downpayment, buying costs, or the renter's starting portfolio.

It does **not** include:
- existing pillar 3a savings,
- second-pillar / pension assets,
- current home equity,
- locked rental deposits,
- or other wealth that is not available as ordinary liquid cash or taxable investments at the start.

Enter existing pillar 3a savings under `initial_pillar_3a_assets`.

The buyer uses `initial_liquid_assets` for the downpayment and buying costs. The renter keeps the same starting cash and taxable investments invested.

If the buyer's downpayment plus modeled buying costs are higher than `initial_liquid_assets`, the simulator uses `initial_pillar_3a_assets` where possible. It applies the simplified `pillar_3a_withdrawal_tax_rate`, so only the money left after estimated withdrawal tax can help with the purchase.

If `initial_liquid_assets` plus the available 3a money is still not enough, the simulator stops and asks for different inputs.

Keep this fixed when testing different buyer downpayment amounts if you want to isolate leverage rather than change the household's starting wealth.

### `downpayment`

Cash put in at purchase.

The project rejects impossible cases where the downpayment is larger than the house price.

### `buying_costs_pct`

One-off purchase costs as a share of the home price.

In Vaud, this usually includes things like:
- transfer tax,
- notary costs,
- and land-registry costs.

For the official transfer-tax part, Vaud charges `2.2%`, and the commune can add up to another `1.1%`.

So a common full-rate transfer-tax assumption is `3.3%`. Anything above that in `buying_costs_pct` is for the other purchase costs, such as notary, land registry, mortgage setup, and any safety buffer you want to include.

### `sale_cost_pct`

Selling costs as a share of the eventual sale price.

This matters when the model sells the house at the end of the simulation horizon or in a forced-sale scenario.

### `base_rent_monthly`

The monthly **current contract rent** used in the `rent and invest` path.

Important:
- this is treated like an existing Swiss lease rent rather than like a rent that automatically follows the consumer price index (CPI),
- so by default it can stay flat for long periods if the legal rent reference rate does not move,
- and any inflation pass-through from the consumer price index (CPI) is controlled separately by `rent_cpi_passthrough`.

### `house_market_rent_monthly`

Estimated monthly market rent of the home you would buy.

This is especially important before 2029 because it is used as a proxy for the owner's tax on the tax office's made-up rent number.

Important:
- this is not the rent you pay in the renter path,
- it is the estimated market rent of the property you would own,
- it is not the same thing as the official imputed-rent base for a real property,
- it is also the rent level the model uses if the buyer is forced to sell and then re-rent,
- and it follows a separate market-rent growth assumption.

For a real buying decision, try to replace this proxy with the best estimate you can get for the specific property's official imputed-rent base.

### `rent_reference_rate_current`

The starting Swiss legal rent reference rate used for existing-lease rent adjustments.

As of **March 3, 2026**, the nationwide official reference rate is `1.25%`.

This setting matters because Swiss existing-lease rent usually reacts much more to this legal reference rate than to general inflation measured by the consumer price index (CPI).

### `rent_reference_rate_smoothing`

How slowly the model lets the rent reference rate react to the simulated mortgage-rate path.

Plain-language idea:
- live mortgage offers can move quickly,
- but the Swiss legal rent reference rate moves much more slowly,
- so this setting stops contract rent from reacting as fast as a live SARON short-term mortgage benchmark quote.

### `rent_cpi_passthrough`

How much of positive inflation, measured here with the consumer price index (CPI), is allowed to flow into existing-lease rent.

Important:
- Swiss practice is not “rent always rises one-for-one with the consumer price index (CPI),”
- the official rent guidance allows only limited pass-through from that inflation measure,
- and the shipped default is `0.0`, which means no automatic inflation pass-through unless you deliberately turn it on.

## Other Spending

### `annual_other_consumption`

All yearly household spending that is not already modeled elsewhere.

In plain language, this usually includes things like:
- food,
- health insurance,
- transport,
- clothing,
- childcare bills,
- holidays,
- subscriptions,
- restaurants,
- and day-to-day family spending.

It does not include:
- rent,
- mortgage interest,
- maintenance,
- taxes,
- or pillar 3a contributions.

The model treats this as a starting-year amount and then increases it with inflation over time.

## Mortgage Settings

### `interest_rate`

Starting mortgage interest rate used in the simulation.

Important:
- if `mortgage_rate_volatility` is `0`, this stays constant,
- otherwise the yearly rate moves around this starting rate within the configured floor and cap,
- and a configured stress year can push it up further.

The `interest_rate` must be between `mortgage_rate_min` and `mortgage_rate_max`. If it is outside that range, the simulator stops instead of quietly replacing it with the floor or cap.

### `amortization_annual`

Yearly mortgage principal repayment amount.

This amount is used:
- for bank-required amortization while debt is above the stop level,
- and also for voluntary amortization after that point if `voluntary_amortization` is turned on.

### `ltv_floor`

The loan-to-value stop level below which the model assumes bank-required amortization stops.

In plain language:
- once the mortgage is low enough relative to the purchase price, the model treats the bank-required yearly paydown as finished.

### `amortization_strategy`

How required amortization is handled while the mortgage is above the stop level.

Possible values:
- `direct`: the mortgage itself is repaid directly.
- `indirect_3a`: pillar 3a contributions are treated as satisfying the required amortization first, and only any remaining shortfall is repaid directly.

### `voluntary_amortization`

Whether the household keeps repaying the mortgage even after the bank-required stop level has been reached.

If `False`, amortization stops once the debt is at or below that stop level.

If `True`, the model keeps paying down the mortgage directly by `amortization_annual`.

### `maintenance_rate`

Actual yearly cash cost of home upkeep as a share of the home value.

This is a cash-spending assumption, not a tax deduction.

### `mortgage_rate_volatility`

How much the yearly mortgage rate can move around `interest_rate`.

Higher values mean more uncertainty in yearly interest cost.

### `mortgage_rate_min` and `mortgage_rate_max`

Lowest and highest allowed modeled mortgage rate.

These stop the random-rate process from drifting into impossible values. They can also limit a stress-rate jump.

If `mortgage_rate_volatility` is `0` and no stress-rate jump is active, changing these floor/cap values should not change results as long as `interest_rate` stays inside them.

## Market Assumptions

### `inflation`

Baseline yearly price inflation.

This pushes up:
- rent,
- other household spending,
- and salary in francs.

If `inflation_volatility` is above zero, the actual simulated inflation can bounce around this baseline from year to year instead of following one flat line forever.

### `inflation_volatility`

How much yearly inflation can wobble around the baseline `inflation` setting.

Plain-language idea:
- if this is `0`, inflation is a straight line,
- if this is higher, each year can come in above or below the baseline.

The shipped default is nonzero because a perfectly flat inflation path is not realistic over long horizons.

### `inflation_min` and `inflation_max`

Lower and upper bounds for the simulated yearly inflation rate.

These stop the random inflation process from drifting into absurd values.

### `index_tax_parameters_with_inflation`

Whether the simulator moves its built-in **2026** tax CHF amounts upward over time with inflation.

Plain-language idea:
- if prices rise over time, many tax CHF amounts usually do not stay frozen forever,
- this setting tells the simulator to move its built-in 2026 tax CHF amounts upward too.

When this is `True`, the model carries forward:
- the main federal and Vaud tax brackets,
- the main deduction caps,
- the main wealth-tax thresholds,
- and the yearly pillar 3a cap.

Important:
- if inflation is stochastic, the simulator uses the **realized inflation path** rather than one flat inflation number,
- but it does so with a conservative lagged rule: a year's tax CHF amounts reflect inflation already observed before that year starts,
- if this is `False`, the tax CHF amounts stay frozen at their 2026 values even if wages, rents, and prices rise.

It does **not** silently change the explicit post-2029 first-time-buyer reform caps. Those stay at the values you enter.

Important:
- this is a **scenario assumption**,
- not a guarantee that future official published values will equal simple consumer price index (CPI) growth from 2026.

### `stock_growth_world_usd`

Average yearly return of a broad world stock ETF measured in USD.

Think of this as the long-run USD return of something like VT before ETF fees.

### `chf_appreciation_vs_usd`

Average yearly strengthening of the Swiss franc against the US dollar.

Positive values reduce the CHF return of a USD-priced ETF.

Negative values mean the Swiss franc weakens against the US dollar.

### Effective CHF Stock Return

The simulator converts the USD ETF return into a CHF return with this formula:

`(1 + stock_growth_world_usd) / (1 + chf_appreciation_vs_usd) - 1`

This is more accurate than simply subtracting one percentage from the other.

### `stock_volatility`

How much stock returns jump around from year to year.

Higher values mean a rougher ride.

### `house_growth`

Average yearly home-price growth.

### `house_volatility`

How much home-price growth varies from year to year.

### `asset_correlation`

How much stock returns and home-price returns tend to move together.

The simulator handles edge cases like `1.0`, `0.0`, and zero volatility safely.

### `salary_growth`

Extra salary growth above inflation.

Examples:
- `0.0` means salary only keeps up with inflation.
- `0.005` means salary grows by about 0.5% more than inflation each year.

### `salary_growth_volatility`

How much yearly salary growth can wobble around the baseline salary-growth assumption.

This is not a full unemployment or disability model.

It simply makes earned income less smooth from year to year.

### `market_rent_real_growth`

Expected growth of the **market-rent** path above inflation.

This affects:
- the estimated market rent used as a proxy for owner tax inputs,
- and the rent level used if the buyer is forced to sell and re-rent.

It does **not** change the renter path's current Swiss lease rent by itself.

Example:
- `0.01` means the modeled market rent grows about 1% faster than inflation before random shocks.

### `rent_growth_volatility`

How much the **market-rent** path can wobble around its baseline growth assumption.

This affects both:
- the estimated market-rent path used for owner tax inputs,
- and the rent level used if the buyer is forced to sell and re-rent.

It does **not** by itself make an existing Swiss lease rent jump around every year.

### `stress_event_probability`

Average share of years that count as stress years.

In a stress year, the model can hit several variables at once instead of moving them independently.

If `stress_persistence` is `0`, each year is drawn on its own.

If `stress_persistence` is above `0`, bad years can bunch together into runs.

### `stress_persistence`

How likely one stress year is to be followed by another.

Plain-language idea:
- `0.0` means each year's stress draw is independent,
- higher values make stress years bunch together into longer bad patches,
- while keeping the same average stress share set by `stress_event_probability`.

### `stress_stock_drawdown`

Extra one-year stock-market haircut applied during a stress year.

Important:
- this is applied on top of that year's normally drawn stock return,
- so `25%` means "subtract an extra 25% from that year's result,"
- not "force the whole year to be exactly -25%."

### `stress_house_drawdown`

Extra one-year home-price haircut applied during a stress year.

As with stocks, this is applied on top of that year's normally drawn home-price return.

### `stress_salary_hit`

Temporary salary reduction applied during a stress year.

### `stress_rent_jump`

Temporary extra rent increase applied during a stress year.

This affects:
- the renter's current lease rent for that stress year,
- and the estimated market rent used in the owner tax path.

### `stress_rate_jump`

Temporary extra mortgage-rate increase applied during a stress year.

## Fees And Investment Income

### `portfolio_ter`

Yearly fee drag on the regular taxable investment account.

This is where a low-cost brokerage ETF fee assumption belongs.

### `pillar_3a_ter`

Yearly fee drag on pillar 3a investments.

This is separate because pillar 3a products often have higher fees than a plain brokerage ETF portfolio.

### `dividend_yield`

Share of the taxable portfolio that is assumed to be paid out each year as taxable dividends.

This matters for the tax engine because dividends are taxed even though capital gains on private movable assets are normally not.

### `da1_eligible_dividend_share`

Share of modeled dividends that you deliberately want to treat as possibly claimable through **DA-1**.

Plain-language idea:
- if you think none of your dividends should generate a Swiss DA-1 credit, leave this at `0`,
- if you think half of them might qualify, use `0.50`.

The shipped default is `0.0`.

That means:
- the simulator does **not** assume this foreign-tax credit by default,
- because not every ETF or foreign dividend really leads to a DA-1 credit.

### `da1_non_refundable_withholding_rate`

The foreign tax rate assumed to be taken away from that dividend slice before you receive the money.

Example:
- `0.15` means the model assumes CHF 15 is kept abroad for every CHF 100 of dividends in that chosen DA-1 slice.

The shipped default is `15%`, but it only matters if `da1_eligible_dividend_share` is above zero.

### `da1_minimum_non_refundable_tax`

Minimum modeled non-refundable foreign tax before the simulator grants any DA-1 credit.

In plain language:
- if the modeled foreign tax is smaller than this floor, the simulator gives no DA-1 credit.

The shipped default is `CHF 100`.

## Pillar 3a

### `initial_pillar_3a_assets`

Existing household pillar 3a savings at the start of the simulation.

This is separate from `initial_liquid_assets` because pillar 3a is not ordinary cash or a taxable investment account:
- it is not available as normal spending cash,
- it is not treated as part of the renter's taxable brokerage portfolio,
- it is not included in modeled Vaud wealth tax,
- and it is shown in net worth after the simplified withdrawal-tax estimate.

Both the buy and rent paths start with the same `initial_pillar_3a_assets`. The balance then grows with the pillar 3a return process and receives any modeled yearly 3a contributions.

Important:
- if the buyer's initial cash and taxable investments are not enough for downpayment plus buying costs, the simulator uses this starting 3a balance,
- any 3a money used for the purchase is reduced by the simplified `pillar_3a_withdrawal_tax_rate`,
- and it is not automatically treated as already pledged for indirect amortization.

### `pillar_3a_annual_per_person`

Maximum yearly pillar 3a contribution for one person who is both employed and affiliated to a pension institution.

The simulator gives this standard cap only to a partner who:
- has positive modeled employment income in that year,
- and is marked as affiliated to a pension institution.

If a partner has employment income but is **not** affiliated to a pension institution, the simulator uses a different Swiss rule:
- `20%` of modeled post-social earned income,
- up to the higher official maximum for non-affiliated people.

If `index_tax_parameters_with_inflation` is `True`, the model also projects this cap forward with inflation instead of freezing it forever at the 2026 amount.

Important:
- this is a **cap**, not a promise that the household always contributes the full amount,
- modeled 3a contributions are limited by the cash available in that year's path.

### `p1_pillar2_affiliated` and `p2_pillar2_affiliated`

These tell the simulator whether each adult is treated as affiliated to a pension institution.

In plain language:
- if this is `True`, that person uses the standard employee 3a cap,
- if this is `False`, that person uses the non-affiliated `20% of earned income` style rule instead,
- and this setting also affects which federal insurance-deduction cap is used.

### `pillar_3a_unaffiliated_rate` and `pillar_3a_unaffiliated_max`

These control the fallback Swiss 3a rule for a person who has earned income but no pension-institution affiliation.

The shipped 2026 defaults are:
- `20%` of modeled post-social earned income,
- capped at `CHF 36,288`.

### `pillar_3a_withdrawal_tax_rate`

Simplified tax rate used when pillar 3a money is withdrawn at the end.

Important:
- this is only an approximation,
- real tax depends on canton, amount withdrawn, and whether withdrawals are staggered.
- use a number between `0` and `1`, so `0.08` means an `8%` withdrawal tax assumption.

### `pillar_3a_growth_chf`

Optional average yearly CHF return assumption for pillar 3a.

If you leave this empty, the simulator uses the same average CHF return as the taxable stock portfolio.

If you fill it in, pillar 3a can follow its own long-run return assumption instead.

### `pillar_3a_volatility`

Optional year-to-year volatility assumption for pillar 3a.

If you leave this empty, pillar 3a uses the same volatility as the taxable stock portfolio.

### `pillar_3a_correlation_to_portfolio`

How tightly the pillar-3a return shocks move with the taxable portfolio shocks.

Examples:
- `1.0` means they move together almost perfectly,
- `0.0` means they move independently,
- negative values mean they tend to move in opposite directions.

## Vaud / Commune Tax Framework

### `social_security_rate`

Share of gross salary lost to payroll-style social deductions before the household can spend or invest the money.

This is a household payroll assumption, not an income-tax bracket.

### `canton_multiplier`

Vaud cantonal tax coefficient.

This scales the cantonal base tax into the actual cantonal amount.

### `commune_multiplier`

Commune tax multiplier for the ordinary income and wealth tax.

This is commune-specific.

The shipped baseline value matches Lausanne's official 2026 total commune percentage.

In the Streamlit app, the official 2026 Vaud commune selector fills this from the published **total** commune percentage (`pour-cent total`), not just the base column.

The manual field in the app accepts the full range of bundled official 2026 commune coefficients.

If you are taxed in another Vaud commune, this is one of the first settings to revisit.

### `communal_property_tax_rate`

Separate commune property-tax rate, also called **impôt foncier**.

The shipped baseline value matches Lausanne's official 2026 rate.

Important:
- this is **not** the same thing as `commune_multiplier`,
- it is an extra yearly tax that only matters on the owner path,
- and the simulator applies it to the property-tax fiscal-value proxy at the **start** of each year.

In the Streamlit app, the official 2026 Vaud commune selector can fill this automatically from the canton’s published commune table.

### `use_official_cantonal_income_tax_reduction_schedule`

Whether the simulator uses the official Vaud cantonal income-tax reduction schedule.

The shipped default is `True`.

For years covered by the simulator, that means:
- `5%` for tax year `2026`,
- `7%` from tax year `2027` onward.

Important:
- it applies to cantonal income tax,
- not to city-level income tax,
- and not to wealth tax.

### `cantonal_income_tax_reduction_rate`

Manual flat Vaud reduction applied to cantonal income tax when `use_official_cantonal_income_tax_reduction_schedule` is `False`.

Important:
- it applies to cantonal income tax,
- not to city-level income tax,
- and not to wealth tax.

The shipped manual value is `5%`, but it is ignored while the official schedule is turned on.

### `cantonal_income_tax_reduction_start_year`
### `cantonal_income_tax_reduction_end_year`

The manual year window used only when `use_official_cantonal_income_tax_reduction_schedule` is `False`.

The shipped manual defaults are both `2026`.

For the official basis behind the default schedule, see the `Vaud Income-Tax Reduction Schedule` section in `DOC_1_TAX_AND_LAW_101.md`.

### `wealth_tax_value_ratio`

Assumed tax value of the home as a share of market value for wealth-tax purposes.

This is one of the most important property-specific approximations in the whole model.

It is not a universal legal constant for every property.

In plain language:
- if this ratio is too high, owner wealth tax will be overstated,
- if it is too low, owner wealth tax will be understated.

### `property_tax_value_ratio`

Assumed tax value of the home as a share of market value for the separate commune property tax, also called `impôt foncier`.

This setting is separate from `wealth_tax_value_ratio` on purpose.

In many ordinary cases you may choose the same number for both, but keeping two settings makes the assumption visible instead of hiding it.

In plain language:
- `wealth_tax_value_ratio` affects owner wealth tax,
- `property_tax_value_ratio` affects the separate yearly `impôt foncier`,
- and both should be checked against the real property assessment whenever possible.

### `vl_factor_cantonal`

Assumed share of the imputed-rent proxy used as taxable imputed rent for Vaud and commune tax before 2029.

The shipped default is `65%`, matching Vaud's published percentage of the indexed imputed-rent base.

Important:
- the `65%` factor is official,
- but the model still needs a property-specific base before applying it,
- and the shipped model uses `house_market_rent_monthly` as that base proxy.

### `vl_factor_federal`

Assumed share of the imputed-rent proxy used as taxable imputed rent for direct federal tax before 2029.

The shipped default is `90%`, matching Vaud's property instructions for federal tax.

Important:
- the `90%` factor is official,
- but the model still needs the property-specific base before applying it,
- and the shipped model uses `house_market_rent_monthly` as that base proxy.

### `maintenance_deduction_rate_federal`

Federal flat-rate tax deduction assumption for maintenance before 2029.

For direct federal tax, the usual flat-rate rule depends on the building age:
- `10%` if the building is `10` years old or less,
- `20%` if it is older.

### `maintenance_deduction_rate_cantonal`

Vaud flat-rate tax deduction assumption for maintenance before 2029.

For a home you live in in Vaud, the usual flat-rate rule depends on the property age:
- `20%` if the property is under `20` years old,
- `30%` if the property is older.

These two settings are separate on purpose.

Why:
- the published federal and Vaud flat-rate buckets are not the same,
- so one shared setting would quietly mix two different tax systems.

Because the simulator cannot infer the age of your target home, both settings must be chosen manually.

## Fixed Deductions

These settings are mostly tax-deduction caps or simple stand-ins used by the tax engine.

### `fed_deduction_professional_flat`

Federal flat deduction for general work expenses.

### `cant_deduction_professional_rate`
### `cant_deduction_professional_min`
### `cant_deduction_professional_max`

These three settings define the Vaud deduction for ordinary work expenses:
- the percentage rate,
- the minimum amount,
- and the maximum amount.

### `fed_deduction_transport` and `cant_deduction_transport`

Simple stand-ins for work-travel deductions.

Important:
- these are not universal truths about your household,
- the real tax saving depends on the real commute,
- and the deductions apply only to a partner who actually has salary income.

The shipped federal default matches the official 2026 direct-federal ceiling of `CHF 3,300`.

### `fed_deduction_meals` and `cant_deduction_meals`

Simple stand-ins for work-meal deductions.

These are meant to capture meals away from home linked to work.

### `fed_deduction_double_income_min` / `fed_deduction_double_income_max`

Lower and upper bounds for the federal married double-income deduction.

The shipped 2026 defaults are the official federal values:
- minimum `CHF 8,600`,
- maximum `CHF 14,100`.

Inside the model, that federal deduction is applied to the lower spouse's modeled earned income **after** work-expense deductions and modeled pillar-3a contributions, instead of using raw gross salary.

### `cant_deduction_double_income_min` / `cant_deduction_double_income_max`

Lower and upper bounds for the Vaud married double-income deduction.

The shipped 2026 defaults are:
- minimum `CHF 0`,
- maximum `CHF 1,700`.

That Vaud amount is much smaller than the federal one and is only relevant in `married` mode.

### `fed_deduction_insurance_single`, `fed_deduction_insurance_single_without_pillars`, and `cant_deduction_insurance_single`

Insurance-deduction caps for one separately taxed adult.

For the federal side, the official cap is different depending on whether pension contributions exist.

The simulator uses:
- `fed_deduction_insurance_single` when that partner has modeled pension contributions through pillar 2 or pillar 3a,
- `fed_deduction_insurance_single_without_pillars` otherwise.

### `fed_deduction_insurance_married`, `fed_deduction_insurance_married_without_pillars`, and `cant_deduction_insurance_married`

Insurance-deduction caps used in `married` mode for the jointly taxed household.

Again, the federal cap depends on whether the household has modeled pension contributions through pillar 2 or pillar 3a.

### `fed_deduction_insurance_child_supplement` and `cant_deduction_insurance_child_supplement`

Extra insurance-deduction amounts for each child.

### `fed_deduction_childcare_per_child` and `cant_deduction_childcare_per_child`

Maximum childcare deduction per child.

Important:
- the shipped 2026 defaults are `CHF 25,800` federally and `CHF 15,200` for Vaud,
- these are caps, not your actual childcare bill,
- and they only run for `childcare_deduction_years`, not for the whole dependency window.

### `fed_deduction_per_child` and `cant_deduction_per_child`

Ordinary child deductions for each child.

These are separate from the childcare deduction.

### `fed_deduction_married`

Federal married-couple deduction used only in `married` mode.

## 2029 Reform

### `reform_year`

Year when the new home-tax system starts in the model.

### `first_time_home_buyer_p1` and `first_time_home_buyer_p2`

Whether each partner individually qualifies for the first-time-buyer interest deduction after the reform.

This is modeled per taxpayer because an unmarried couple files separately.

These fields are only used in `unmarried` mode.

Official reform materials say owning a home abroad earlier does not by itself block that deduction.

The shipped baseline sets both of these to `True`.

### `first_time_home_buyer_married`

Whether the married household qualifies for the joint first-time-buyer interest deduction after the reform.

This is only used in `married` mode.

The shipped baseline sets this to `True`.

### `first_time_buyer_years`

How many years the first-time-buyer deduction takes to phase down to zero.

The simulator uses this setting.

### `first_time_buyer_years_used_before_start_p1`
### `first_time_buyer_years_used_before_start_p2`
### `first_time_buyer_years_used_before_start_married`

How many years of that first-time-buyer deduction were already used before the model starts.

Use these only if the qualifying first home in Switzerland that you bought and lived in was bought before `start_year` and you want the model to keep only the deduction years that are left.

Important:
- these settings shorten only the remaining years of that deduction,
- they do **not** turn the whole buy path into a home that was already owned before `start_year`.

### `first_time_buyer_interest_deduction_single_max`

Starting annual cap used for one unmarried taxpayer’s first-time-buyer interest deduction.

This is only used in `unmarried` mode.

### `first_time_buyer_interest_deduction_married_max`

Starting annual cap used for the married household’s joint first-time-buyer interest deduction.

This is only used in `married` mode.

## Cash-Shortfall Handling

### `liquidity_shortfall_rate`

If the household runs out of liquid cash, the negative balance compounds at the configured shortfall rate rather than at stock-market returns.

Instead, it grows at this shortfall rate.

That is much more realistic than pretending a negative cash balance grows like a normal investment account.

Important:
- the negative liquid balance also flows into taxable wealth instead of being clipped to zero,
- so a cash shortfall can reduce modeled wealth tax,
- and if forced-sale protection is ON, a severe buyer shortfall can trigger a sale of the home.

### `force_buy_sale_on_liquidity_crisis`

Whether a severe buyer cash crisis forces the model to sell the home early.

If triggered, the model:
- sells the property at the end of that year,
- pays sale costs and Vaud real-estate capital-gains tax,
- pays the configured forced-sale moving and emergency cost,
- pays the configured transition rent for the move/search period,
- locks the configured rental deposit for the new lease as non-liquid cash,
- clears the mortgage,
- and continues the remaining years as a renter-style path.

This is meant as a downside safeguard, not as a prediction of how every real family would react.

### `liquidity_crisis_buffer_months`

How large the buyer's negative-cash buffer can become before that forced sale is triggered.

The threshold is expressed in months of the buyer's current yearly outflows.

Higher values make forced sale less likely.

### `forced_sale_extra_cost_chf`

One-off cash cost lost for good if the buyer is forced to sell under stress.

This is where moving costs, urgent paperwork, or a failed refinancing attempt can be represented in one simple number.

### `forced_sale_transition_months`

Extra months of market rent paid during the move/search transition after a forced sale.

This is a real cost, not just locked cash.

### `forced_sale_rental_deposit_months`

Rental deposit for the new lease after a forced sale, measured in months of the new rent.

Important:
- in Switzerland, residential rent deposits are usually capped at `3` months,
- this hurts liquidity because the cash gets locked,
- but it counts as household wealth because the money is yours.

## Which Settings Are Most Important To Check Manually?

For real-life decision-making, these are the most important settings to verify with your real situation:
- `house_market_rent_monthly`
- `wealth_tax_value_ratio`
- `property_tax_value_ratio`
- `vl_factor_cantonal`
- `vl_factor_federal`
- `maintenance_deduction_rate_federal`
- `maintenance_deduction_rate_cantonal`
- `base_rent_monthly`
- `annual_other_consumption`
- `interest_rate`
- `mortgage_rate_volatility`
- `household_status`
- `first_time_home_buyer_p1` and `first_time_home_buyer_p2` or `first_time_home_buyer_married`
- `first_time_buyer_years_used_before_start_p1` / `first_time_buyer_years_used_before_start_p2` or `first_time_buyer_years_used_before_start_married`
- `stress_event_probability`
- `stress_persistence`
- `stress_stock_drawdown`
- `stress_house_drawdown`
- `stress_salary_hit`
- `stress_rent_jump`
- `stress_rate_jump`
- `forced_sale_extra_cost_chf`
- `forced_sale_transition_months`
- `forced_sale_rental_deposit_months`
- `pillar_3a_withdrawal_tax_rate`

## Final Warning

This project uses sourced 2026 tax inputs and explicit household-finance logic, but it contains simplifications.

The simulator is best treated as:
- a structured planning tool,
- a way to compare scenarios,
- and a way to discover which assumptions matter most.

It is not a substitute for:
- a real property tax estimate,
- a real mortgage offer,
- or a full household budget built from actual spending records.
