# Limitations & Stress Scenarios

This file answers two practical questions:

1. What does the simulator handle reasonably well already?
2. What needs manual stress testing because it is simplified or not modeled?

The goal is not to make the project sound worse than it is.

The goal is to make sure you do not mistake a clean chart for a complete picture.

## Modeled Reasonably Well

These areas are handled in a fairly structured way:

- Swiss federal and Vaud tax logic for the cases documented in `DOC_1_TAX_AND_LAW_101.md`
- Married versus unmarried filing logic
- Owner versus renter cash flows
- Mortgage amortization rules used by this project
- Optional separate pillar-3a return process
- Optional stochastic inflation, salary, rent, and mortgage-rate paths
- Swiss-style sticky contract rent for the renter path
- Optional lagged tax indexing of the built-in 2026 CHF tax amounts
- Optional joint stress years across assets, salary, rent, and mortgage rates
- Optional forced sale after a severe buyer liquidity crisis

That does **not** mean these areas are perfect.

It means they are modeled explicitly rather than being hand-waved away.

## What The Percentages Mean

The dashboard shows numbers such as:
- `P(Buy > Rent at horizon)`,
- the 10th to 90th percentile range,
- and the chance of a liquidity shortfall or forced sale.

These percentages are useful, but they are easy to read too literally.

They do **not** mean the simulator knows the true odds of your future.

In plain language, the simulator works like this:
- you choose assumptions about returns, rent, salary, inflation, house prices, mortgage rates, and stress years,
- the computer makes many imaginary futures using those assumptions,
- then it counts what happened inside those imaginary futures.

So if the dashboard says `P(Buy > Rent at horizon) = 62%`, it means:

"In 62% of the imaginary futures made from the settings you entered, buying ended with more wealth than renting."

It does **not** mean:

"There is a proven 62% chance that buying will beat renting in real life."

The difference matters.

If the assumptions are too cheerful, the percentages can look too cheerful.

If the assumptions are too harsh, the percentages can look too harsh.

There is also normal Monte Carlo sampling noise.

In plain language:
- if you run only a small number of imaginary futures, the displayed percentage can wobble just because of the random draw,
- near a close decision, it is worth rerunning with more iterations and trying more than one random seed.

This is why the best use of the dashboard is not to trust one number. The better use is to ask:
- Does the answer stay similar when I make the assumptions worse?
- Does the conclusion depend on one fragile guess?
- What would have to go wrong for the preferred choice to become dangerous?

### Percentiles

A percentile is a way to describe the spread of the imaginary futures.

For example, the 10th percentile is a weak outcome, but not the absolute worst one.

It means about 10% of the simulated futures were worse than that number, and about 90% were better.

Percentiles are helpful for seeing the downside, but they still come from the assumptions you entered.

On the time charts, these are **pointwise** percentiles.

That means the 10th percentile line is built year by year. It is not necessarily one single simulated family path that stayed at the 10th percentile from start to finish.

## Modeled Roughly

These areas are included, but in a simplified way:

### Inflation and tax indexing

The simulator can let inflation move around year by year.

It can also move tax brackets, deduction caps, wealth thresholds, and the pillar-3a cap along with inflation.

But it does this with a simple lagged rule, not with a full legal model of exactly when each future official tax table would be published.

### Downside liquidity stress

The simulator can show:
- negative liquid balances,
- a separate interest rate on those negative balances,
- and a forced sale if the buyer's cash crisis gets severe enough.

But that forced sale is a simple mechanical rule.

Real life is messier:
- families borrow from relatives,
- cut spending,
- sell investments first,
- refinance,
- or react late.

There is also a timing simplification.

The model charges each year's taxes in a simple yearly way.

Real Vaud tax cash flow is more spread out:
- monthly or periodic advance payments,
- later final settlement,
- and possible catch-up payments.

That matters most when you are reading the charts as a **liquidity stress** tool rather than just a long-run net-worth comparison.

### Joint stress years

Stress years are useful because they can hit several things at once.

The model can draw those stress years one by one or let them bunch together into multi-year bad patches.

That is helpful when you want to test several hard years in a row.

It is a shortcut.

Real recessions do not repeat one neat pattern year after year.

Jobs, inflation, house prices, and interest rates can all get worse and recover at different speeds.

So this setting is useful for stress testing, but it is not a full model of the economy.

Outside the explicit stress-year switch, the yearly inflation, salary, rent, and mortgage-rate surprises are drawn separately.

That keeps the model understandable, but it also means you should manually test combined bad cases, such as weak salary growth together with high mortgage rates and a soft housing market.

### Mortgage-rate paths

The simulator draws a yearly mortgage rate for each simulated future.

That is good for broad stress testing.

It is not the same as a real Swiss mortgage plan with fixed-rate tranches, renewal dates, early-repayment penalties, and a bank affordability review at refinancing time.

If your real plan uses fixed mortgages, it is worth manually testing a few renewal-rate cases rather than trusting only the smooth yearly rate path.

The simulator also does not yet model a bank reacting to a lower house value by demanding extra amortization or refusing a renewal because the mortgage is suddenly too high compared with the new market value.

That means owner downside paths can still be optimistic when house prices fall sharply.

### Tax-return detail

The tax engine is built from sourced federal and Vaud inputs, and it models the main owner-versus-renter tax differences explicitly.

But it is not a full tax-return program.

Real tax filings can depend on details that the simulator does not know automatically, such as:
- exact social-insurance and pension deductions,
- exact transport and meal deductions,
- actual health-insurance and insurance-premium facts,
- whether a childcare bill really qualifies for the deduction,
- whether a dividend really qualifies for DA-1,
- the official property-specific tax value,
- and the tax office's exact owner-occupied rental value before 2029.

The simulator uses explicit settings for many of these items, but those settings still need to match your real situation.

If a setting is only a rough stand-in, the result is also only a rough stand-in.

For a final decision, the tax-sensitive inputs should be checked against your real documents or a Swiss tax professional.

### Horizon settlement convention

The headline horizon comparison uses one common end point for both strategies.

For the buyer, that means the model assumes the home is sold at the horizon if it is still owned and counts the net cash after:
- sale costs,
- mortgage payoff,
- and Vaud real-estate capital-gains tax.

That is useful if you want a clean "what is left at the horizon?" comparison.

But it is not the same thing as asking what your paper net worth would be if you simply kept living in the home beyond the horizon.

### Swiss rent law

The renter path is closer to Swiss reality than a simple rent rule that automatically follows the consumer price index (CPI).

But it is a simplified model.

The simulator does **not** track:
- the exact notice history of one real lease,
- formal landlord notices,
- lease-specific clauses,
- or litigation around a contested rent increase.

This exact limitation is also repeated in `DOC_3_SIMULATION_LOGIC.md` so it is visible both in the high-level caveats and in the step-by-step simulator description.

## Not Modeled; Test Manually

These areas are important enough to think about, but they are outside the current model.

### Major property surprises

Examples:
- roof replacement,
- facade work,
- heating-system replacement,
- legal defect,
- water damage,
- co-ownership dispute,
- or a special assessment in a PPE / condo structure.

The simulator has normal yearly maintenance.

It does **not** yet model big one-off property shocks.

### Family-life changes

Examples:
- another child,
- childcare ending earlier or later than expected,
- one parent reducing work,
- parental leave changes,
- part-time work becoming permanent,
- or separation into two households.

These can matter a lot, especially for an unmarried couple with a child.

They should not be treated as tiny edge cases.

### Commune inputs

The simulator is commune-aware in two separate ways:
- the ordinary commune tax multiplier,
- and the separate communal `impôt foncier`.

The app ships with an official built-in 2026 Vaud commune table, which reduces a lot of plain typing risk.

But there is some input risk:
- if you deliberately override the official values,
- if the commune changes its rates after the built-in table year,
- or if you are testing a future manual scenario.

If one of those numbers is wrong or stale, the long-run owner versus renter comparison can shift more than you might expect.

It is wise to sanity-check both numbers against the current official Vaud commune information before trusting a result, especially if you are not using the built-in 2026 selector as-is.

### Fiscal tax value of the home

The simulator needs an estimated fiscal tax value for the property.

That number matters in more than one place.

It affects:
- owner-side wealth tax,
- and the separate communal `impôt foncier`.

The simulator keeps these as two visible settings:
- `wealth_tax_value_ratio` for owner wealth tax,
- and `property_tax_value_ratio` for the separate communal `impôt foncier`.

In many scenarios those two settings may be the same. They are separate because the official property-specific assessment is too important to hide behind one automatic shortcut.

If either estimate is too low or too high, it can bias the owner path.

This is one of the most useful sensitivity checks to run manually.

### Second-pillar pension (`pillar 2`)

The simulator does not model your second-pillar balance growing over time, being pledged, or being withdrawn.

If you plan to use pillar 2 for the purchase, this becomes much more important and should not be ignored.

### Renter legal/default path

The renter path can show severe negative cash outcomes.

But it does **not** try to model the legal sequence of missed rent, arrears, enforcement, moving, or emergency family support.

Treat a deeply negative renter path as a red warning flag rather than a literal forecast of exactly what would happen.

### Forced-sale frictions

The buyer path can force a sale after a severe liquidity crisis.

That is helpful as a warning mechanism.

The model includes a simple forced-sale friction layer:
- moving and emergency costs,
- transition rent during the move/search period,
- and a locked rental deposit for the new lease.

But the exit is smoother than real life.

The model does **not** separately track:
- a detailed failed-refinancing process,
- the legal timing of notices and overlap,
- or a long rental search with several failed attempts.

So a forced-sale path should be read as somewhat optimistic.

## Suggested Stress Scenarios

The dashboard includes some preset bundles as shortcuts.

These are not forecasts.

They are meant to help you ask better questions.

### `High inflation + high rates`

Use this to test:
- whether buying works when mortgage costs stay uncomfortable,
- whether rent stays manageable,
- and whether tax indexing softens some of the damage.

### `Bracket creep stress`

Use this to isolate one important idea:
- prices, rent, and wages rise,
- but tax CHF thresholds stay frozen.

This is the cleanest way to see why “stochastic inflation” and “stochastic inflation plus tax indexing” are not the same thing.

### `Asset crash + income hit`

Use this to test whether buying makes sense if:
- stocks drop,
- the house market weakens,
- and salary takes a hit at the same time.

### `Owner forced-sale risk`

Use this to test whether the buyer path becomes fragile when:
- rates are jumpy,
- salary is less stable,
- stress years are more frequent,
- and the emergency cash buffer is smaller.

### `Several hard years in a row`

Build this manually by combining:
- lower expected returns,
- higher stress-year probability,
- weaker salary growth,
- weaker house-price growth,
- and tighter liquidity settings.

Use it to ask a harder question than "Can we survive one bad year?"

Ask instead: "What if the family gets three to five hard years in a row?"

## Good Manual Tests To Run Anyway

Even after using the presets, it is worth manually testing at least these extra cases:

- one parent works 60% for several years
- a second child arrives
- childcare costs stay high longer than expected
- one-off property shock of CHF 50k to CHF 150k
- the same home with a younger-age and older-age maintenance-deduction bucket before 2029
- delayed sale into a weak housing market
- a move to a different Vaud commune with both a different communal coefficient and a different `impôt foncier`
- the same home with a meaningfully lower and higher fiscal tax value
- forced sale with harsher-than-baseline moving, deposit, and overlap frictions
- three to five consecutive weak years instead of one isolated stress year

## Bottom Line

The simulator is useful for structured financial stress testing.

But there is a difference between:
- **modeled risk**, where the code really explores it,
- and **life risk**, where you need to think through your own household story manually.
