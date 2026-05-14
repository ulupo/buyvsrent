# How the Simulator Works

This file explains the model step by step.

## What Kind of Model This Is

The project is a **Monte Carlo** simulator.

That means it does not produce one single future.

Instead, it creates many possible futures:
- some good,
- some average,
- some bad.

In plain language, it rolls the dice many times and compares buy versus rent across all those runs.

The dashboard percentages are counts inside those simulated futures.

For example, if the dashboard says buying wins `60%` of the time, that means buying won in 60% of the imaginary futures created from the current settings.

It does not prove that buying has a real-world 60% chance of winning.

The result is only as good as the assumptions used to make those imaginary futures.

## What Happens Each Year

For each simulated year, the model does this:

1. A yearly inflation rate is set from the baseline inflation assumption plus any configured inflation shock.
2. Salary moves using that year's inflation plus any configured salary shock.
3. The renter's contract rent is adjusted using the Swiss rent-reference mechanism, optional limited pass-through from the consumer price index (CPI), and any one-year stress jump.
4. The separate market-rent path moves using inflation, the configured market-rent growth above inflation, and any market-rent shock. If the buyer is forced to sell later, this market-rent path sets the starting rent of the buyer's new lease.
5. Mortgage interest for that year is set from the baseline rate plus any configured random-rate shock.
6. If a configured stress year hits, stocks, house prices, salary, rent, and mortgage rates can all take a hit together. Depending on the settings, those bad years can happen one by one or come in runs.
7. Opening house value moves according to the house-return assumption.
8. Opening investment and pillar-3a balances move according to their market assumptions.
9. If that option is turned on, the built-in 2026 tax CHF amounts also move upward with the inflation already observed before that year starts.
10. Mortgage interest and amortization are paid.
11. Taxes are calculated for that exact year.
12. Whatever cash is left is added to savings and to any pillar-3a contributions that year can **actually afford**, at the **end** of the year.

## Tax Logic Inside the Year

The simulator calls `src/tax_engine.py` every year.

That engine:
- branches on `household_status`,
- applies joint federal and Vaud taxation for married households,
- applies separate taxation for unmarried adults,
- applies the CHF `263` federal per-child tax reduction in married mode,
- applies the special lower federal tax table for one parent in unmarried mode,
- allows child deductions and Vaud child tax-splitting benefits to be split in unmarried mode,
- applies Vaud's official cap on those child tax-splitting benefits in both unmarried and married cases,
- applies Vaud's extra family deduction (`code 725`),
- applies the married Vaud family-parts system in married mode,
- applies Vaud's official cantonal income-tax reduction schedule, with `5%` in 2026 and `7%` from 2027 onward by default,
- uses official 2026 Vaud tax scales,
- uses the official 2026 federal tax table,
- can move those built-in 2026 tax CHF amounts upward with the realized inflation path,
- keeps DA-1 OFF by default unless the user explicitly says some dividends should count for that foreign-tax-credit feature,
- switches to the post-2029 owner rules at the right date,
- and uses the actual simulated mortgage rate for owner interest deductions.

For shared-child cases such as `0.25 / 0.25` in unmarried mode, the simulator also splits the official Vaud cap proportionally instead of forgetting it.

## The Buy Path

The buy path includes:
- the initial cash and taxable investments left after paying the downpayment and purchase costs,
- mortgage interest,
- maintenance cash costs,
- amortization,
- owner taxes,
- pillar 3a contributions,
- all other household spending.

At the end, the model sells the home and subtracts:
- selling costs,
- Vaud real-estate capital-gains tax, using Vaud's official rule where the tax rate gets lower the longer you owned the home.

## The Rent Path

The rent path includes:
- yearly contract rent,
- renter taxes,
- pillar 3a contributions,
- all other household spending.

The renter keeps the same initial cash and taxable investments invested from day one. `initial_liquid_assets` means cash and taxable investment accounts available at the start; it does not include existing pillar 3a balances, second-pillar assets, home equity, rental deposits, or other illiquid wealth. The buyer's downpayment only changes the buyer's debt/equity/liquidity split unless you also change `initial_liquid_assets` or make the downpayment large enough that the buyer has to use starting pillar 3a savings.

If the buyer's downpayment plus modeled buying costs are higher than initial cash and taxable investments, the simulator uses `initial_pillar_3a_assets` where possible. That 3a money is reduced by the simplified withdrawal-tax estimate before it helps with the purchase. If cash, taxable investments, and available 3a money are still not enough, the simulator stops and asks for different inputs.

Important:
- the renter's current lease rent is treated more like a Swiss existing lease than like “straight consumer price index (CPI) growth every year,”
- so it reacts mainly to the legal rent reference rate, plus any optional limited inflation pass-through from that index and any one-year stress jump.

## How Investment Returns Are Drawn

The simulator uses a standard random-return method for stocks and housing.

Why that matters:
- values stay positive,
- compounding behaves more realistically,
- the average yearly return settings continue to match what the sliders say they mean.

For stocks, the dashboard separates two ideas:
- the average return of a broad world stock ETF in USD,
- and the average yearly change of CHF versus USD.

The simulator then converts that USD stock return into a CHF stock return before applying ETF fees and yearly random shocks.

Pillar 3a can be handled in two ways:
- it can reuse the same return process as the taxable stock portfolio,
- or it can use its own average return, volatility, and correlation settings.

Both paths start with the same `initial_pillar_3a_assets`, then build from there with growth and yearly modeled contributions. That starting 3a balance is separate from `initial_liquid_assets`: it is not part of cash or taxable investment wealth, and it is not counted in modeled Vaud wealth tax.

For the buyer, part of the starting 3a balance can be used at purchase if cash and taxable investments are not enough for the downpayment and buying costs. Otherwise it stays invested as pillar 3a wealth. The starting 3a balance is not automatically treated as already pledged for indirect amortization.

The contribution side is also household-specific:
- if a person is modeled as affiliated to a pension institution, the standard employee cap is used,
- otherwise the simulator uses the Swiss fallback rule based on a share of earned income, up to the higher non-affiliated maximum.
- if the path cannot really fund the full modeled cap from that year's cash, the simulator scales the 3a contribution down instead of forcing the household to "borrow to max 3a".

That makes it possible to model a more conservative or differently invested 3a portfolio instead of forcing it to behave exactly like the taxable account.

## Stochastic Inflation vs Tax Indexing

These are two different ideas:

- **Stochastic inflation** means prices do not move in a straight line forever. One year can be low, another year can be high.
- **Tax indexing** means the model also moves tax brackets, deduction caps, wealth thresholds, and the pillar-3a cap instead of freezing them forever at 2026 CHF amounts.

If stochastic inflation is ON but tax indexing is OFF:
- wages, rent, and spending can rise,
- but the tax CHF amounts stay frozen,
- so the model shows stronger bracket-creep pressure.

If both are ON:
- wages, rent, and spending follow the random inflation path,
- and the tax CHF amounts also move,
- but with a conservative lagged rule: a year's tax CHF amounts reflect inflation already observed before that year starts.

One extra Swiss-specific detail matters:
- the renter's **contract rent** is not the same thing as the **market rent** used for owner tax inputs,
- so inflation can affect those two paths differently.

## Two Ways to Show Money

The dashboard can show money in two ways:
- **future CHF**: the raw francs expected in that future year,
- **start-year purchasing power**: future francs translated back into what they are worth in the configured `start_year` after allowing for inflation.

Example:
- if prices rise over time, CHF 100,000 in 2040 does not buy as much as CHF 100,000 today,
- the inflation-adjusted view tries to make that comparison easier.

The inflation-adjusted view converts the year-by-year paths using each simulation's own realized inflation path.

Important:
- this display conversion is separate from the tax-law indexing assumption,
- changing the chart display does not turn the "move tax amounts up with inflation" setting on or off.

## What Happens If Cash Goes Negative

If liquid cash goes negative:
- positive liquid balances compound at the portfolio return,
- negative liquid balances grow at a separate shortfall rate instead.
- those negative balances are also passed into the tax engine instead of being clipped away for wealth-tax purposes.

If the buyer's negative liquid balance becomes severe enough and the forced-sale safeguard is ON:
- the model sells the home,
- pays sale costs and Vaud real-estate capital-gains tax,
- clears the mortgage,
- pays the configured forced-sale moving and emergency costs,
- pays the configured transition rent for the move/search period,
- locks the new rental deposit as a separate asset that counts toward wealth,
- and continues the rest of the path as a renter-style household, with the new lease starting from the modeled market-rent level at that point.

So the dashboard’s buyer cash-crisis indicator counts two things:
- a negative liquid balance that remains unresolved in a simulated year,
- or a forced home sale triggered by a severe buyer cash problem.

## Direct vs indirect amortization

The simulator supports two mortgage styles for the buyer:
- **Direct amortization**: the mortgage balance itself is reduced each year.
- **Indirect amortization via pillar 3a**: the yearly pillar 3a contributions are treated as satisfying the bank's amortization requirement first, and only any remaining shortfall is paid directly.

In indirect mode:
- the mortgage balance stays higher for longer,
- interest usually stays higher for longer,
- the pillar 3a pot grows as an invested 3a asset,
- the tax deduction for pillar 3a stays in place,
- and when that "move tax amounts up with inflation" setting is ON the annual pillar 3a cap is also projected forward with inflation,
- and the model tracks how much of the bank-required reduction has already been covered by pillar 3a contributions, so required direct paydown stops once that requirement is met.

Only modeled contributions made during the simulation count toward that indirect-amortization credit. Existing starting 3a savings are tracked as 3a wealth, or used for the purchase if needed, but they are not automatically counted as already pledged collateral.

This matters especially for a purchase before 2029, and potentially after 2029 as well if the household qualifies for the special rule for people who bought before the reform.

## What the Main Outputs Mean

### `P(Buy > Rent at horizon)`

This is the share of simulations where buying ends with more wealth than renting under the model's common horizon-settlement rule.

### `Median Buy − Rent horizon wealth`

This is the middle result across all simulated futures for the wealth left at the horizon after the model settles each strategy.

It is not the best case and not the worst case.

### Fan charts

The fan charts show ranges such as:
- 10th percentile,
- median,
- 90th percentile.

These are not one single path followed through time. They are yearly snapshots across many simulations.

Important:
- the KPI row and the histogram use **horizon wealth after liquidation**,
  meaning the wealth left after the model settles the strategy at the horizon,
- for the buyer, that means the home is sold at the horizon if it is still owned, and the net cash after sale costs, IGI, and mortgage payoff is counted,
- while the fan charts use yearly **mark-to-market net worth**,
  meaning your running paper wealth during the journey,
- so those nearby dashboard elements are related but not identical measures.

### Composition charts

The composition charts also use yearly medians.

For the buyer, home equity is shown as a **signed** median:
- if median home equity is positive, it appears as the blue stacked layer,
- if median home equity is negative, it appears below zero as underwater equity instead of being clipped to zero.

The dashboard also reports the highest simulated probability of being underwater in any year, because a positive median can hide bad but less common cases.

## What the Model Simplifies

The simulator simplifies several real-life things:
- tax law may change again after 2029,
- the dashboard probabilities and percentiles are counts from the simulated futures, not proven odds for real life,
- social-insurance, pension, work, transport, meal, and insurance deductions are simplified settings rather than a full tax-return interview,
- childcare tax treatment is simplified even though the model uses your entered spending up to the published caps,
- even with stress years that can bunch together, the economy is much simpler than real life and does not tell a full story of several hard years in a row,
- the random yearly inflation, salary, rent, and mortgage-rate shocks are not automatically correlated with each other unless you use the explicit stress-year settings,
- mortgage rates are drawn as yearly scenario rates, not as fixed mortgage contracts with renewal dates,
- hard floors and caps, such as minimum mortgage rates and inflation bounds, can make the average simulated outcome differ slightly from the plain input average,
- tax indexing uses a simple lagged rule instead of trying to predict the exact legal publication timing of future tax tables,
- Swiss rent law is simplified: the reference-rate mechanism is modeled as a slow approximation, not as a full legal notice-by-notice lease history,
- DA-1 depends on the user correctly entering which share of dividends might really qualify,
- pillar 3a withdrawal taxation is simplified,
- forced sale is handled as a single mechanical rule rather than a full legal or behavioral default process,
- the exact tax office "made-up rent" number for a real property is not filled in automatically,
- the exact tax value of a real property is not filled in automatically,
- the simulator does not model your second-pillar pension growing over time.

So the simulator is useful for structured comparison and stress testing, but not as a substitute for a full tax filing or professional Swiss financial planning advice.
