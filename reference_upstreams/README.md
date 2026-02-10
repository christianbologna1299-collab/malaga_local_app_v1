\# Upstream Reference Models (Read-Only)



These repositories are used as \*\*conceptual and structural references\*\* for

Banker Analytics — Equity Research \& Investment Banking Engine.



They are NOT imported as runtime dependencies.

All logic is re-implemented in a deterministic, auditable Python engine.



---



\## 1. FinancialAnalysis — 3 Statement Financial Model

\*\*Author:\*\* arnavchaturvedi17  

\*\*URL:\*\* https://github.com/arnavchaturvedi17/FinancialAnalysis-3\_Statement\_Financial\_Model  

\*\*License:\*\* Public (Excel-based reference)



\*\*Used for:\*\*

\- Three-statement linkage structure

\- Forecast period layout

\- Accounting flow logic (NI → RE → Cash)

\- Best-practice financial modeling structure



\*\*Assets consumed:\*\*

\- Excel workbook (formulas + schedules)

\- README narrative (context only)



---



\## 2. FinancialAnalysis — Discounted Cash Flow (DCF)

\*\*Author:\*\* arnavchaturvedi17  

\*\*URL:\*\* https://github.com/arnavchaturvedi17/FinancialAnalysis-Discounted-Cash-Flow-DCF-Valuation-Financial-Model



\*\*Used for:\*\*

\- FCFF calculation structure

\- Terminal value methodology

\- DCF sensitivity layout



\*\*Assets consumed:\*\*

\- Excel workbook

\- Valuation math structure



---



\## 3. FinancialAnalysis — Sensitivity \& Scenario Model

\*\*Author:\*\* arnavchaturvedi17  

\*\*URL:\*\* https://github.com/arnavchaturvedi17/FinancialAnalysis-Sensitivity-and-Scenario-Financial-Model



\*\*Used for:\*\*

\- Scenario toggles

\- Sensitivity table logic

\- Stress testing patterns



\*\*Assets consumed:\*\*

\- Excel workbook only



---



\## Design Principle



\- No Excel formulas are executed at runtime.

\- All math is re-implemented in Python.

\- Excel exports are outputs, not engines.

\- Outputs must match reference workbooks for identical inputs.



