# D&Y Finanzas

Desktop business-management application for a waterproofing and maintenance operation, built with **Python, PySide6 and SQLite**.

The project was created around a real operational need: keeping clients, measurements, jobs, materials, crews, payroll, cash flow, debts and reporting synchronized in one local desktop application.

> **Portfolio note:** this public repository contains a **fully synthetic demo database**. No real customer, employee, supplier, address, phone number or financial record is included.

## What the application manages

- Clients and job history
- Roof and parapet measurements
- Editable measurement breakdowns and quotations
- WhatsApp-ready budget text
- Job lifecycle: measured, confirmed, in progress and completed
- Work crews and payroll calculations
- Materials, purchases, inventory movements and consumption
- Material sales and inventory reconciliation
- Income, expenses, debts and receivables
- Cash ledger and cash-flow reporting
- Worker and financial reports
- PDF report generation
- Configurable interface theme and font size

## Technical highlights

- **Python** application organized into database, repository, service and UI layers
- **PySide6** desktop interface
- **SQLite** with foreign keys, transactions and schema initialization/migrations
- Business rules for inventory, payroll, job status transitions and cash flow
- Measurement parsing and calculation workflow
- PDF generation with **ReportLab**
- Automated regression tests for core business rules
- Local-first architecture with database import/export support
- Reproducible synthetic dataset for portfolio review

## Demo database

The repository includes `data/demo.db`, a synthetic SQLite database created specifically for this public portfolio.

It contains fictional examples of:

- 15 demo clients
- Measurements and job records across multiple months
- All main job states: **Medido, Confirmado, En Progreso and Finalizado**
- Two work crews and generic worker records
- Payroll entries
- Material purchases, inventory consumption and a material sale
- Customer payments
- General expenses
- Supplier and manual debts
- A receivable loan and repayment
- Manual cash movements
- A maintenance-alert scenario

### Run with demo data on Windows

1. Run `instalar.bat` once to create the virtual environment and install dependencies.
2. Run `ejecutar_demo.bat`.

`ejecutar_demo.bat` copies `data/demo.db` to the local working database `data/impercontrol.db` and then starts the application.

> `data/impercontrol.db` is ignored by Git so local or real operational data is never intended to be committed.

To restore the demo database from the command line:

```bash
python scripts/reset_demo.py
```

To rebuild `data/demo.db` entirely from synthetic source data:

```bash
python scripts/create_demo_db.py
```

The demo generator does **not** read or transform any production database.

## Project structure

```text
.
├── main.py
├── requirements.txt
├── instalar.bat
├── iniciar.bat
├── ejecutar_demo.bat
├── data/
│   └── demo.db
├── scripts/
│   ├── create_demo_db.py
│   └── reset_demo.py
├── impercontrol/
│   ├── database.py
│   ├── repositories.py
│   ├── services.py
│   ├── logic.py
│   ├── pages.py
│   ├── dialogs.py
│   ├── charts.py
│   ├── pdf_reports.py
│   └── ...
└── tests/
    └── test_core.py
```

## Running locally

### Windows helper scripts

```text
1. instalar.bat
2. iniciar.bat            -> starts with the current local database
   or
   ejecutar_demo.bat      -> resets to the synthetic demo and starts the app
```

### Command line

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python scripts/reset_demo.py
python main.py
```

## Tests

The project includes automated tests covering measurement calculations, job workflows, payroll, materials, inventory reconciliation, payments, cash flow and financial summaries.

```bash
python -m unittest tests.test_core -q
```

The public portfolio version was validated with **50 automated tests passing**.

## Privacy and portfolio fidelity

The production database is **not included**. Local database files, virtual environments, caches and build artifacts are excluded through `.gitignore`.

The public version preserves the working project's core application logic. Personal worker names embedded in the original source were replaced with generic role-based identifiers solely for privacy. The demo records are fully synthetic.

## Development approach

This application was developed iteratively around real business requirements and operational feedback. I defined workflows, business rules, acceptance criteria and test scenarios, while using AI-assisted development as part of implementation and debugging.

The project has been useful for practicing:

- Translating real business requirements into software behavior
- Relational data modeling with SQLite
- Desktop UI development
- Debugging and regression testing
- Inventory and financial consistency
- Privacy-safe demo-data preparation

## Current status

Active personal/business project. This repository is the privacy-safe portfolio edition.

---

**Author:** Daisniel Perez Breto  
[LinkedIn](https://www.linkedin.com/in/daisniel-perez-breto)
