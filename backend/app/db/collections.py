"""Collection names. The first three intentionally match the names Mongoose
auto-generated (Facility -> facilities, Asset -> assets, Submission ->
submissions) so existing data in the `carbon_ops` database is reused as-is."""

FACILITIES = "facilities"
ASSETS = "assets"
SUBMISSIONS = "submissions"

ENERGY_RECORDS = "energy_records"
EMISSION_RECORDS = "emission_records"
EMISSION_FACTORS = "emission_factors"
INITIATIVES = "initiatives"
DOCUMENTS = "documents"
USERS = "users"
AUDIT_LOG = "audit_log"
REFRESH_TOKENS = "refresh_tokens"
REFERENCE_DATA = "reference_data"
SCOPE3_ENTRIES = "scope3_entries"

ALL = [
    FACILITIES, ASSETS, SUBMISSIONS, ENERGY_RECORDS, EMISSION_RECORDS, EMISSION_FACTORS,
    INITIATIVES, DOCUMENTS, USERS, AUDIT_LOG, REFRESH_TOKENS, REFERENCE_DATA, SCOPE3_ENTRIES,
]
