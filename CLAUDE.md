# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## About This Codebase

This is an Odoo addon for managing electricity subscriptions ("Souscriptions") for French energy providers. The codebase targets **Odoo 19**.

The rebuild is guided by `AUDIT_REFONTE.md` and tracked in the GitHub milestone "Refonte Odoo 19" (issues #10–#22). **Division of responsibility**: all domain/métier logic (Enedis flux ingestion, périmètre, energy by cadran, TURPE, accise) lives in [electricore](https://github.com/Energie-De-Nantes/electricore), deployed with a REST API. This Odoo module keeps only legal accounting, price grids, invoicing, the customer portal, and the raccordement workflow. electricore feeds the billing periods via its API.

## Module Architecture

### Souscriptions Module
**Purpose**: Replacement for Odoo's standard subscription module (`abonnement`), which is not adapted for electricity supply management

**Why Replace Odoo's Subscription Module**:
- Standard Odoo subscriptions cannot handle electricity contract tracking
- No support for on-demand price changes during contract lifecycle
- Cannot handle time-varying prices with historical price billing
- Lacks support for smoothed/monthly billing contract regularization with retroactive pricing

**Implementation**: Contract management (`souscription.souscription`), billing periods (`souscription.periode`), price grids (`grille.prix`), invoice integration via an extended `account.move`, customer portal, and a kanban raccordement workflow.

> The former in-Odoo "Métier" module (readonly Enedis mirrors + Parquet importers using pandas/fastparquet) was removed in favor of electricore. Do not reintroduce pandas/parquet imports here — consume electricore's API instead.

## Development Environment

### Odoo Version Requirements
**Odoo 19** — the module is validated against the `odoo:19.0` Docker image.

### Standard Development Commands
```bash
# Install/upgrade addon (module technical name: souscriptions_odoo)
odoo -d your_database -i souscriptions_odoo
odoo -d your_database -u souscriptions_odoo

# Development mode with OWL debugging
odoo -d your_database --dev=reload,qweb,werkzeug,xml
```

### Testing
The suite lives in `tests/` (TransactionCase + HttpCase). Run it against Odoo 19:

```bash
odoo -d test_db -i souscriptions_odoo --test-enable --test-tags /souscriptions_odoo --stop-after-init
```

## Key Technical Considerations

### French Electricity Market Context
- PDL (Point de Livraison) as central identifier for electricity delivery points
- TURPE tariffs (French grid access costs) integration
- Support for different billing patterns (Base, HP/HC peak/off-peak hours)
- Integration with Enedis historical data through Métier models

### Electricity-Specific Billing Requirements
Unlike standard subscriptions, electricity supply requires:
- Dynamic price changes during contract lifecycle
- Historical price application for regularization periods
- Smoothed billing with retroactive adjustments
- Complex tariff structures with time-varying components

## Development Guidelines

### Exploratory Phase Considerations
- Functionality is still being defined - avoid hardcoding business assumptions
- Focus on flexible architecture that can adapt to changing requirements
- Maintain clear separation between subscription management and Enedis data integration

### File Organization
- `models/core/`: subscription, billing periods, price grids, account.move extension
- `models/raccordement/`: connection-request kanban workflow
- `controllers/`: customer portal routes
- `views/`, `reports/`: XML view and QWeb report definitions
- `data/`: default configuration data; `demo/`: demo-only data
- `security/`: access control rules

## Dependencies
- **Odoo Core**: base, mail, contacts, account, portal (Odoo 19)
- **Localization**: babel.dates for French date formatting
- **External service**: electricore REST API for all métier calculations

## Agent skills

### Issue tracker

Issues are tracked in GitHub Issues for `Energie-De-Nantes/souscriptions_odoo` via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Canonical role names (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`), reusing the existing `wontfix` label. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.