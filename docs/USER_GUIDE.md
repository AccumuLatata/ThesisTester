# ThesisTester User Guide

User-facing how-tos for classic pages and Research Assistant Help.
This file is the primary Help corpus home for workflow questions (HC-series).
**Not yet allowlisted for Help retrieval** until HC-1+ fills sections and amends
RQ §7.1 + `HELP_CORPUS_MANIFEST` in the same PR. Stub sections below are
structure only — do not treat them as shipped how-tos.

Deep metric definitions stay in `docs/METRICS_GLOSSARY.md`. Engine honesty and
limits stay in `docs/ASSUMPTIONS_AND_LIMITATIONS.md`. Operator/agent runbooks
(`docs/AGENT_GUIDE.md`) are never part of user Help.

## Purpose and honesty

ThesisTester is a research-screening backtester for futures day-trading
workflows (levels → setups → signals → backtest / grid / validation). Help
answers from allowlisted docs only; it does not invent run metrics, prove OOS
edge, or place live trades. Performance questions belong in **Discuss results**.

## Classic workflow overview

_Stub (HC-0)._ Typical path: Data → Levels → Setup Builder → Signals → Backtest,
then Grid / Time / Validation / Report / Bundles / Portfolio as needed. Research
Assistant holds thesis draft, Discuss results, and Help.

## Data

_Stub (HC-0)._ How to import data, choose instrument/interval/timezone/format,
and understand dataset identity. Filled in HC-1.

## Levels

_Stub (HC-0)._ How to build session levels and what regenerate means. Filled in
HC-1.

## Setup Builder

_Stub (HC-0)._ How to configure a setup (confluence, tolerance, naked, trigger,
direction) and link or create a thesis. Filled in HC-1.

## Signals

_Stub (HC-0)._ How to generate signals and what confluence zones mean. Filled in
HC-1.

## Backtest

_Stub (HC-0)._ How to run a backtest and what costs, slippage, exposure, and
intrabar assumptions mean at a user level. Filled in HC-1.

## Grid Search

_Stub (HC-0)._ How to run a grid search, choose ranking metric / min trades, and
read the best cell without treating IS selection as proof. Filled in HC-2.

## Time Analysis

_Stub (HC-0)._ How to use time buckets and the limits of “best entry” language.
Filled in HC-2.

## Validation and robustness

_Stub (HC-0)._ How to run WFA / Monte Carlo / robustness batteries as
diagnostics, not proof. Filled in HC-2.

## Report Export

_Stub (HC-0)._ What exports contain and how they relate to research bundles.
Filled in HC-2.

## Research Bundles

_Stub (HC-0)._ How to import/export bundles, hash identity, and restore vs
recompute. Filled in HC-2.

## Portfolio

_Stub (HC-0)._ Multi-setup portfolio scope and honesty limits. Filled in HC-2.

## Research Assistant (draft, Discuss, Help)

_Stub (HC-0)._ Thesis draft vs Discuss results vs Help; confirm/run gates.
Filled in HC-3.

## Research mode on classic pages

_Stub (HC-0)._ How to link a thesis and record/discuss a classic run. Filled in
HC-3.

## When to use Help vs Discuss results

_Stub (HC-0)._ Help = product/how-to from docs; Discuss = bound run metrics.
Filled in HC-3.
