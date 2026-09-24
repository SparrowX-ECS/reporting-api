# Reporting API repository structure

The Reporting API follows the shared SparrowX backend structure without database files. `src/config.py` owns runtime settings, `src/schemas.py` owns report models, and `src/routes/reports.py` owns upstream aggregation. The application starts from `src.main:app`.
