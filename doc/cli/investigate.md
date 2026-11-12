
Template test results preserve safe step diagnostics in compact output:
completeness, typed reasons, row/count summaries and judge label/confidence/model.
Table and CSV rows also show prior/posterior, applied evidence and pricing status.
`unpriced` means USD is only the priced subtotal; it does not mean the model was
free. Finished inconclusive samples are counted separately from decided samples.
`--include-steps` additionally retains the full step records and timing.
