# DISCLAIMER: THIS IS A VIBE-CODED PROJECT. IT HAS NOT BEEN VERIFIED BY EXPERTS. DO NOT MAKE IMPORTANT FINANCIAL DECISIONS BASED ON ITS OUTPUTS.

# Vaud Buy vs Rent Simulator

This project compares two long-term household-finance paths for a family living in Vaud, Switzerland:
- `buy and invest`
- `rent and invest`

It includes a Streamlit dashboard, a Swiss/Vaud tax calculator, a simulator that explores many possible futures, and documentation written for non-specialists.

## Documentation

The main documentation files are:
- [DOC_1_TAX_AND_LAW_101.md](./DOC_1_TAX_AND_LAW_101.md): plain-language background on the Swiss and Vaud tax rules used by the project
- [DOC_2_CONFIGURATION_GUIDE.md](./DOC_2_CONFIGURATION_GUIDE.md): explanation of every setting in `src/config.py`
- [DOC_3_SIMULATION_LOGIC.md](./DOC_3_SIMULATION_LOGIC.md): how the simulator and dashboard work
- [DOC_4_LIMITATIONS_AND_STRESS_SCENARIOS.md](./DOC_4_LIMITATIONS_AND_STRESS_SCENARIOS.md): what is simplified or unmodeled, plus suggested stress tests

## Installation

Create and activate a Python environment, using whichever environment manager you prefer.

```bash
python -m venv .venv
source .venv/bin/activate
```

Install or update dependencies in the active environment:

```bash
pip install -r requirements.txt
```

## Run The Dashboard

```bash
streamlit run src/visualizer.py
```

## Run The Sanity Checks

```bash
python src/test_sanity.py
```

## Project Layout

- `src/config.py`: default assumptions and tax tables
- `src/tax_engine.py`: Swiss federal and Vaud / commune tax logic
- `src/simulator.py`: buy-vs-rent simulation that explores many possible futures
- `src/visualizer.py`: Streamlit dashboard
- `src/vaud_communes.py`: official 2026 Vaud commune-rate loader for the selector
- `src/test_sanity.py`: regression and sanity checks
- `data/vaud_communes_2026.csv`: versioned official 2026 Vaud commune tax table used at runtime

## Important Note

This tool is meant to help you think carefully about scenarios, not to be followed blindly. Several inputs remain household-specific approximations, especially around the property's fiscal tax value for wealth tax and `impôt foncier`, future commune-rate changes beyond the built-in 2026 Vaud table, the property-specific base behind the tax office's "made-up rent" for people living in their own home before 2029, childcare eligibility, and future mortgage conditions.

The shipped baseline:
- moves the built-in 2026 tax CHF amounts up over time with the simulator's inflation assumption,
- can also let inflation vary randomly from year to year instead of staying flat forever,
- uses a conservative lagged rule when inflation-linked tax CHF amounts follow that realized inflation path,
- models commune-specific `impôt foncier` separately from the usual canton/commune income-and-wealth coefficients,
- includes a built-in official 2026 Vaud commune selector that fills both the total commune coefficient and the separate `impôt foncier`,
- applies the official Vaud cantonal income-tax reduction schedule by default: `5%` in 2026 and `7%` from 2027 onward,
- uses actual entered childcare spending up to the published federal and Vaud caps instead of automatically granting the full cap,
- treats the renter path more like a Swiss existing lease instead of assuming rent always tracks general inflation measured by the consumer price index (CPI),
- leaves the DA-1 foreign-tax credit at zero unless you deliberately turn it on,
- can model optional stochastic salary, rent, and mortgage-rate paths,
- can apply optional stress years that can bunch together across assets and household cash flows,
- can give pillar 3a its own return process instead of forcing it to mirror the taxable portfolio,
- can represent a first-home tax deduction that started before the model starts and has only some years left,
- and can force an early sale after a severe buyer liquidity crisis, including configurable moving / overlap costs and a locked rental deposit.

The tax engine supports both:
- unmarried two-adult households taxed separately,
- married two-adult households taxed jointly.

Those two filing modes do not use the same tax logic, so the `household_status` setting in `src/config.py` and the matching dashboard control matter.
