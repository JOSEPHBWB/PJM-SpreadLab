# Methodology and limits

This file is handwritten methodology, separate from generated numerical reports.

The primary purpose is to measure whether a signal adds value after modeled costs while exposing its tail losses. The rules in research_config.json were fixed before the first strategy-result run in this iteration; they are not a preregistration made before the underlying 2022–2025 sample was seen.

Prices: Western Hub total LMP, settlements-verified outcome labels. UTC is the key; local time supplies calendar features. The research target is the complete hub-total DA–RT spread.

Costs: historical published monthly Schedule 9 rates and daily preliminary operating reserve rates. Apply current rows only for Schedule 9; preserve historical month mapping and February 2023 PSI split. The base scenario applies RTO plus East deviation, and DA operating reserve for DEC only. PJM official BOR mapping updated September 16, 2026 marks WESTERN HUB as East. Its historical 2022–2025 continuity is assumed; no contemporaneous mapping archive was obtained. The former max(East, West) surcharge is retained as stress, not a region assignment. Invoice overhead is separately varied. Per-segment fees do not scale down when risk sizing scales MW down. Bid rejection and extra submissions are not modeled.

Some reserve-shortage withdrawal deviations can be exempt; this reconstruction does not implement that interval-level exemption. Current manuals establish the broad accounting mechanics, but historical rule versions, final reconciliation and other bill components remain unverified. Do not label outputs as final net P&L.

Predictors: target calendar only; no contemporaneous realized load, prices or final costs. Monthly expanding training excludes the last 60 days before month start. The training ledger proves chronological separation, not historical publication/version availability. Backfilled final labels are still a limitation even with this buffer.

Calendar groups are hour x weekend x quarter. Means shrink toward same-hour means (which shrink toward the global mean), with 72 pseudo observations. Cost thresholds use training-period averages. Risk scaling uses the larger of hour-specific and overall training direction ES99, with a $50 hourly loss-budget parameter and a 1 MW cap. This is not a guaranteed cap or an actionable stop after the hour has cleared.

All three signal variants and all baselines are reported, with no best-model selection. Costs stress frozen positions, rather than retuning to each realized scenario. Equal-volume INC controls separate reduced turnover from simple timing value, but do not claim matched risk or credit use. Paired seven-day circular block bootstrap is descriptive, assumes approximate local stationarity, and does not correct post-selection inference.

Untouched future data and point-in-time forecast/vintage records are required before an executable-alpha claim. No future run or monitoring has been scheduled by these scripts.

## Review revision

Version 2 corrects the accounting base to East and reruns the original strategy rules without changing model hyperparameters. v1_results.json retains the original stress-accounting run. The Elliott influence check removes December 23–24, 2022 from training only, keeps all evaluation prices, and compares subsequent DEC assignments. This is a post-hoc diagnostic, not an executable emergency filter or evidence that those dates could be known as exclusions beforehand. No median/trimmed-mean model is selected from this review.

Median targets a typical outcome rather than expected cash profit. Trimming changes the contribution of tail outcomes and must not erase actual tail losses from performance accounting.

Hourly mean inference uses Bartlett Newey–West lags 168 (24/336 sensitivity); daily paired bootstrap uses circular seven-day blocks and 2,000 draws. ES95 daily includes no-trade days; maximum drawdown is hourly. Hour ending is local hour beginning + 1; repeated DST hours remain separate via UTC. Fixed invoices are charged on the last active hour per month as an accounting convention, not their true payment time.

## Load signal pilot

The first load-signal run uses 10:00 EPT on D-1, ahead of the documented 11:00 DA close. This was specified before the first model fit after auditing that 09:00 excludes the 09:45 forecast update. Forecast evaluated_at is creation time, not an independently logged publication time; the 15-minute availability buffer is an assumption. Missing forecast hours are excluded from ALL pilot strategy comparisons, including unconditional baselines. This changes the comparison universe relative to the full-price baseline and is disclosed in signal_results.json.

Historical load forecasts retain multiple issue timestamps. Wind/solar forecast feeds retain only 30 days, so they are not used in the 2022–2025 pilot. No realized wind/solar series substitutes for a forecast. RTO actual load is constructed from the ten non-overlapping preliminary areas AEP, AP, ATSI, DAY, DEOK, DOM, DUQ, EKPC, MIDATL and NI, requiring all ten values in each hour. It is a telemetry-based, approximate RTO load label, not a final meter settlement label. No same-delivery actual load is used as a trade feature.

Target-day forecast levels, forecast profile features and pre-cutoff revisions are known-input features. Realized error (actual minus selected forecast) is a training label and a retrospective explanatory variable. A separate forecast model predicts error from known inputs; a training-period regression of spread on realized error plus calendar is evaluated by replacing error with its forecast. Its result is a plug-in mechanism diagnostic, not a causal estimate. Models and their parameters in signal_config.json are frozen before first strategy results, and all variants are reported.

Monthly expanding fits omit the most recent 90 days of labels. This conservative buffer does not establish vintage-correct settlement data. The pilot does not claim an untouched holdout. Bootstrap is the same exploratory paired seven-day block procedure as the first milestone. Point-in-time publication archives and future frozen-rule evaluation are still needed before claiming executable alpha.

## Frozen v2 follow-on evaluation

v2 was specified after reviewing v1 and is a post-hoc research variant. The primary model changes to absolute_error HGB and INC/no-trade, using training-average cost plus $0.50/MWh as entry threshold. All tree parameters and features remain fixed. Controls include calendar absolute INC, squared-loss load INC with the same threshold, and the original squared-loss load two-way rule. Absolute loss estimates the conditional median, not expected money; profit is evaluated with original untrimmed outcome tails.

Configuration and implementation hashes were stored before any 2026 numeric spread outcomes were downloaded in this project. A separate availability step requested timestamps/counts only, and fixed the end from common complete source months, not performance. 2026 DA prices had previously been used in other work; no completely untouched blind sample is claimed. Earlier 2026 labels can enter later monthly fits after 90 days under the pre-specified policy; this is prequential evaluation, not one static model trained once at year start. Outputs retain all controls and the program refuses to evaluate again when its numerical results file exists.

The v1 direction and load-quintile tables are post-hoc diagnostics based on the entire evaluation sample. They support identifying where losses happened, not causal attribution to a loss function. Failing to beat zero-error MAE does not prove mean-unbiased forecasts. Tree predictions are piecewise-constant leaf estimates; extreme predicted values do not by themselves demonstrate mathematical extrapolation beyond training labels.
