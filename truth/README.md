# truth/

`planted_errors.csv` is written by `src/flow/inject_errors.py` and read by
`score` in `src/flow/audit.py` and by nothing else. No dbt model, test or macro may
read this folder: the audit rules must find the planted errors without being
told where they are. The file is regenerated from the seed and is not committed.
