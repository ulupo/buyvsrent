# Swiss Property & Tax 101 for This Project

This file explains the tax ideas behind the simulator in plain language.

## Read This First

The simulator is a model built from official 2026 Vaud and federal tax sources.

It includes:
- 2026 Vaud income-tax and wealth-tax scales checked against official sources,
- the 2026 federal tax table checked against official sources,
- separate handling for unmarried separate filing and married joint filing in Vaud,
- and 2029 reform logic aligned with the published reform timeline.

Some facts depend on your exact household and your exact property, so you need to check those by hand.

The biggest remaining items to verify manually are:
- the **imputed rental value** of the specific property you may buy,
  meaning the tax office's own "made-up rent" number for a home you live in before 2029,
- the property's **fiscal tax value** and your commune's separate **impôt foncier** rate,
- which **federal** and **Vaud** flat maintenance-deduction bucket fits the property's age before 2029,
- whether you qualify for the **first-time-buyer** deduction after 1 January 2029,
- how much of your real childcare spending can really lower tax,
- whether any of your investment income could really qualify for **DA-1**,
- the exact tax on future **pillar 3a** withdrawals.

## The Main Acronyms and Terms

- **IFD** = *Impôt fédéral direct*. This is the Swiss federal income tax.
- **ICC** = *Impôt cantonal et communal*. This is the Vaud canton tax plus your commune's normal income and wealth tax.
- **VL** = *Valeur locative*. This is the fake rental income Switzerland adds when you live in your own home.
- **Pillar 3a** = tax-advantaged private retirement savings.
- **IGI** = *Impôt sur les gains immobiliers*. This is Vaud tax on profit when you sell a property.
- **Impôt foncier** = a separate commune property tax on the property's fiscal tax value.
- **TER** = *Total Expense Ratio*. This is the yearly fee drag inside an investment fund.
- **LTV** = *Loan-to-value*. This is the mortgage balance divided by the property value or purchase price.
- **DA-1** = the Swiss form sometimes used to claim back part of foreign tax kept from a dividend before you receive it.
- **Tax deduction** = an amount that is subtracted before tax is calculated.
- **Tax cap** = the maximum amount the model lets you deduct or claim.
- **Tax table / tariff** = the official list that says how tax grows as income grows.

## How Swiss Tax Works Here

The project compares two paths:
- **Buy & invest**: buy the home, pay mortgage interest, maintenance, taxes, and invest the remaining cash.
- **Rent & invest**: rent the home, keep more money invested, and pay the renter tax profile instead.

For the household, the simulator applies three tax layers:
- Swiss federal income tax.
- Vaud cantonal income and wealth tax.
- Commune-level income and wealth tax.

If you own the home, the simulator can also add a fourth layer:
- the commune's separate **impôt foncier**, based on the property's fiscal tax value at the start of the year.

## Your Family Situation Matters a Lot

The project supports two household tax modes:
- **Unmarried**: the two adults are taxed separately.
- **Married**: the two adults are taxed jointly.

That choice changes the tax logic in important ways.

### Federal level

At federal level:
- unmarried partners are taxed separately,
- married couples are taxed on their combined taxable income and use the married tax table.

For an unmarried couple with a child:
- only one parent usually gets the special lower federal tax table for a parent with a child,
- in the common cohabiting-with-common-child case, the main child-related federal deductions are split **50 / 50**,
- the higher-income parent is often the one who gets that lower tax table when both parents support the child.

For a married couple:
- the household is taxed jointly,
- the married federal tax table is applied to the combined taxable income,
- the married-couple deduction and, when both spouses work, the federal double-income deduction can apply,
- and the federal tax amount is then reduced by **CHF 263 per dependent child**.

### Vaud level

Vaud also has a family tax rule based on "parts".

In plain language:
- the tax office can divide income by a number of parts before working out the tax rate,
- more parts usually mean a lower tax bill.

Those Vaud rules differ sharply by household type.

For an unmarried couple taxed separately:
- a couple living together without being married **does not** get the special **1.3 single-parent part** just because they have a child,
- the child’s extra **0.5 part** may be shared **by half** between the two parents in the reserved cases where they are taxed separately and both support the child,
- and this Vaud tax break has an official maximum size here too.

Implementation note:
- Vaud publishes official tables showing the maximum size of this tax break for a full child share.
- the simulator restricts these unmarried child allocations to whole-child or half-child steps instead of accepting arbitrary percentages.
- when the project models a shared child part such as **0.25 / 0.25**, it also splits that official maximum instead of forgetting it.

For a married couple taxed jointly:
- Vaud starts married households at **1.8 parts** even without children,
- each dependent child adds **0.5** more part,
- the child-related tax break is capped using Vaud’s official married-household table,
- and Vaud’s separate **family deduction (code 725)** can also reduce taxable income.

## Before 1 January 2029

Before the reform starts:
- the home owner is taxed on **VL**,
- mortgage interest can be subtracted before tax,
- maintenance can also be subtracted, but the published federal and Vaud flat-rate rules are different and both depend on the property's age,
- wealth tax applies to taxable net wealth.

In unmarried mode, the model splits the home, debt, and VL between the two taxpayers instead of charging the full home twice. In married mode, those items are taxed at household level.

## From 1 January 2029

Following the September 2025 vote, the Federal Council fixed the reform start date at **1 January 2029**.

For a home you live in yourself, the simulator assumes:
- **VL ends**,
- the ordinary maintenance deduction for a home you live in ends,
- ordinary private mortgage-interest deduction for the self-used home ends,
- a **first-time-buyer interest deduction** may exist for buyers who qualify.

Important detail:
- if someone bought their first home before 2029, a special rule can let them use the remaining years of that deduction after 2029,
- but only if they really qualify as a first-time buyer and ownership stayed uninterrupted.
- official reform materials describe the cap by filing status: married couples start at CHF 10,000 and single taxpayers at CHF 5,000.
- the federal explanatory report also says already having owned and lived in a home **abroad** does **not** by itself block the deduction for a first home you live in **in Switzerland**.

In the simulator:
- married mode applies one joint first-time-buyer cap to the jointly taxed household,
- unmarried mode tracks eligibility separately for P1 and P2.
- if part of that special deduction was already used before the model starts, the model can reduce the remaining years through dedicated `years already used before start year` inputs.

The shipped baseline sets those eligibility flags to `True`.

Both are manual assumptions worth confirming with the tax office or a Swiss tax adviser before relying on them.

Important limit:
- those inputs shorten only the remaining years of that special deduction,
- they do **not** turn the whole buy path into a model of a home that was already owned before the start year.

## Vaud Income-Tax Reduction Schedule

Vaud adopted a reduction of the basic cantonal income tax for individuals.

For the years covered by the simulator, the official schedule is:
- `5%` for tax year `2026`,
- `7%` from tax year `2027` onward.

That matters because:
- it reduces only the **cantonal income-tax** portion,
- not the city-level portion,
- and not wealth tax.

The simulator uses that official schedule by default.

There is also a manual override for scenario testing. If you turn off the official schedule, you can enter one flat reduction rate and a start/end year window yourself.

Official basis:
- Vaud's 2026 tax materials state the `5%` reduction for tax year `2026`.
- The Grand Council record for the final 2024 vote says the law was adopted definitively after keeping the second-debate text. That text set `5%` for tax year `2026` and `7%` from tax year `2027`.

Sources:
- [Payer mes impôts | État de Vaud](https://www.vd.ch/etat-droit-finances/impots/impots-pour-les-individus/payer-mes-impots)
- [Barèmes des impôts à la source 2026 | État de Vaud](https://www.vd.ch/actualites/decisions-du-conseil-detat/seance-du-conseil-detat/decision/id/dbad77e3-0394-4561-89c9-967adb9415ab)
- [Grand Council final vote on the LRIPP amendment | État de Vaud](https://www.vd.ch/gc/seances-du-grand-conseil/point-seance/point/607e799f-00a0-4d74-9007-5bab95903e01/meeting/1026872)
- [Grand Council second-debate text showing 5% in 2026 and 7% from 2027 | État de Vaud](https://www.vd.ch/gc/seances-du-grand-conseil/point-seance/point/119f5484-3f79-44b4-afb5-23efd4e9ae4d/meeting/1026870)

## Wealth Tax

Vaud also taxes wealth.

In plain language:
- if you have taxable assets, Vaud taxes them every year,
- debt reduces taxable wealth,
- the home does not count at full market value in the model because wealth tax usually uses a lower tax value than market value.

For married households, the model treats the CHF 120,000 threshold as a no-tax threshold rather than subtracting it from all taxable wealth.

## Inflation And Future Tax-Law Amounts

The simulator uses embedded **2026** federal and Vaud tax tables.

For a long simulation, that creates a choice:
- either leave all those tax CHF amounts frozen forever,
- or move them up over time as prices rise.

The shipped baseline chooses the second option.

In plain language:
- if prices go up, salary, rent, and other spending in the simulator also go up in francs,
- so the simulator also moves the main tax CHF amounts upward with the same inflation setting,
- this includes the main tax brackets, deduction caps, wealth thresholds, and the yearly pillar 3a cap,
- but the separately entered post-2029 first-time-buyer caps stay at the values you choose.

Why this matters:
- imagine salary goes from CHF 100,000 to CHF 101,000 only because prices rose by 1%,
- if the tax brackets stayed frozen forever at 2026 CHF, the simulator would slowly make future tax look too high for no good reason.

Important:
- this is a **scenario assumption**,
- not a claim that the real published tax tables in 2034 or 2046 will exactly equal simple consumer price index (CPI) growth from 2026.

This is not a random guess:
- the federal tax office says these federal tax numbers are adjusted over time because of inflation,
- and Vaud says its tax tables and deductions also move with inflation from year to year.

## DA-1 Foreign Withholding Credit

This topic is easy to overcomplicate, so here is the simple version first.

Sometimes a foreign country keeps part of your dividend before the money reaches you.

Example:
- a company or fund pays you CHF 100 of foreign dividends,
- but only CHF 85 reaches your account,
- because CHF 15 was kept abroad as tax.

In some cases, Swiss tax law lets you claim back part of that loss on your Swiss tax return.

The form used for that is called **DA-1**.

The simulator uses a conservative rule:
- the shipped default assumes **no DA-1 credit at all**,
- you must explicitly enter what share of modeled dividends you want to treat as the kind that might qualify for DA-1,
- the simulator then limits the credit so it is not bigger than the Swiss tax linked to that dividend slice,
- and it gives no credit if the modeled foreign tax is too small to clear the minimum threshold.

Why this is more careful:
- DA-1 is not a blanket tax refund on every foreign or ETF dividend,
- it depends on the real investment, the real country, and the real tax paperwork.

For a real-life decision:
- leave this at zero unless you already know why some of your dividends should qualify,
- or ask a Swiss tax adviser before turning it on.

## What Still Depends on Manual Judgment

### Imputed rental value

Before the 2029 reform, Swiss tax can treat an owner-occupied home as if it produced rental income for you.

Vaud's property instructions say the taxable imputed rental value is:
- `65%` of the indexed imputed-rent base for Vaud and commune tax,
- `90%` of the indexed imputed-rent base for direct federal tax.

The simulator does not know the tax office's property-specific base. It uses `house_market_rent_monthly` as a proxy and then applies the Vaud and federal factors.

That is only a proxy.

For a real decision, you should try to estimate:
- the likely actual Vaud tax value of the property,
- the likely actual imputed-rent base used by the tax authorities,
- which federal and Vaud flat maintenance-deduction bucket matches the property's age.

### Childcare deductions

The simulator uses the published **2026 federal cap of CHF 25,800 per child** and the published **2026 Vaud cap of CHF 15,200 per child**.

But your real tax saving depends on:
- your real childcare bills,
- which parent paid them,
- and the detailed tax rules.

### Pillar 3a

The simulator only gives the yearly pillar 3a contribution to a partner who actually has positive employment income in that year.

If the tax-law indexing option is left on, that annual cap is also projected forward with inflation instead of staying frozen at the 2026 amount forever.

But the withdrawal tax at the end is a simplified flat approximation.

## Official Sources Used for This Audit

You do not need to read this section to use the simulator.

It is here so you can check where the numbers and rules came from.

- [Federal Council press release, 1 April 2026](https://www.efd.admin.ch/fr/newnsb/yGTqBPowRqyVh0zPokW-q)
- [EFD reform dossier and Q&A](https://www.efd.admin.ch/de/abstimmung-reform-wohneigentumsbesteuerung)
- [Official federal vote result, 28 September 2025](https://www.bk.admin.ch/ch/d/pore/va/20250928/index.html)
- [ESTV 2026 federal direct-tax tariff (Form 58c)](https://www.estv.admin.ch/dam/fr/sd-web/gnde9CmEsalK/dbst-tairfe-58c-2026-dfi.pdf)
- [ESTV Rundschreiben 215 for 2026 federal deductions](https://www.estv.admin.ch/dam/de/sd-web/vFK3ntWLQ4s4/2-215-D-2025-d.pdf)
- [ESTV page on direct-federal deductions, rates, and tariffs](https://www.estv.admin.ch/de/abzuege-ansaetze-tarife-direkte-bundessteuer)
- [ESTV page on annual pillar-3a maximum deductions](https://www.estv.admin.ch/de/zinssaetze-hoechstabzuege-saeule-3a-direkte-bundessteuer)
- [Vaud 2026 deductions table](https://www.vd.ch/fileadmin/user_upload/organisation/dfin/aci/fichiers_pdf/Tableau_des_d%C3%A9ductions_2026.pdf)
- [Vaud 2025 general instructions](https://www.vd.ch/fileadmin/user_upload/organisation/dfin/aci/fichiers_pdf/21001_2025.pdf)
- [Vaud 2026 income-tax barème](https://www.vd.ch/fileadmin/user_upload/organisation/dfin/aci/fichiers_pdf/Bar%C3%A8mes_Revenu_2026.pdf)
- [Vaud 2026 wealth-tax barème](https://www.vd.ch/fileadmin/user_upload/organisation/dfin/aci/fichiers_pdf/Bar%C3%A8mes_Fortune_2026.pdf)
- [Vaud page on paying taxes, including the 2026 5% cantonal income-tax reduction](https://www.vd.ch/etat-droit-finances/impots/impots-pour-les-individus/payer-mes-impots)
- [Vaud page on the 2026 indexed source-tax barèmes](https://www.vd.ch/actualites/decisions-du-conseil-detat/seance-du-conseil-detat/decision/id/dbad77e3-0394-4561-89c9-967adb9415ab)
- [Vaud Grand Council final vote on the LRIPP amendment](https://www.vd.ch/gc/seances-du-grand-conseil/point-seance/point/607e799f-00a0-4d74-9007-5bab95903e01/meeting/1026872)
- [Vaud Grand Council second-debate text for the 2026 and 2027 reductions](https://www.vd.ch/gc/seances-du-grand-conseil/point-seance/point/119f5484-3f79-44b4-afb5-23efd4e9ae4d/meeting/1026870)
- [Vaud property-tax instructions, including imputed rental value](https://www.vd.ch/fileadmin/user_upload/organisation/dfin/aci/fichiers_pdf/21004_2025.pdf)
- [ESTV DA-1 form](https://www.estv.admin.ch/dam/de/sd-web/lHoSrqmLYYR5/dbst-form-da-1-2025-de.pdf)
- [ESTV DA-M memo](https://www.estv.admin.ch/dam/estv/de/dokumente/verrechnungssteuer/merkblaetter/da-m.pdf.download.pdf/da-m.pdf)
- [Vaud page on impôt foncier](https://www.vd.ch/etat-droit-finances/impots/impots-pour-les-individus/les-impots-les-differents-types-dimpots/impot-foncier)
- [Vaud communal tax tables / arrêtés d’imposition](https://www.vd.ch/etat-droit-finances/communes/finances-communales/arretes-dimposition-et-tableaux-des-impots-communaux)
