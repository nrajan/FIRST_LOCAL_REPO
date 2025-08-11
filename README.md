## Contact Search Streamlit App

This Streamlit app searches a Snowflake database for contacts by name, email, or phone. Results are shown with clickable links that open a full person report including complete contact information and address.

### 1) Install dependencies

```bash
pip install -r requirements.txt
```

### 2) Configure Snowflake credentials

Provide Snowflake credentials via Streamlit secrets (recommended) or environment variables.

- Using Streamlit secrets: create `.streamlit/secrets.toml` next to `requirements.txt`:

```toml
[snowflake]
account = "<your_account>"           # e.g. xy12345.eu-central-1
user = "<your_user>"
password = "<your_password>"
warehouse = "<your_warehouse>"
database = "<your_database>"
schema = "<your_schema>"
role = "<optional_role>"

[app]
# Optional overrides for table/column names and limits
contact_table = "CONTACTS"
id_column = "ID"
first_name_column = "FIRST_NAME"
last_name_column = "LAST_NAME"
email_column = "EMAIL"
phone_column = "PHONE"
address1_column = "ADDRESS_LINE1"
address2_column = "ADDRESS_LINE2"
city_column = "CITY"
state_column = "STATE"
postal_code_column = "POSTAL_CODE"
country_column = "COUNTRY"
max_results = 200
```

- Or, using environment variables:

```bash
export SNOWFLAKE_ACCOUNT=xy12345.eu-central-1
export SNOWFLAKE_USER=...
export SNOWFLAKE_PASSWORD=...
export SNOWFLAKE_WAREHOUSE=...
export SNOWFLAKE_DATABASE=...
export SNOWFLAKE_SCHEMA=...
export SNOWFLAKE_ROLE=...           # optional

# Optional app overrides
export APP_CONTACT_TABLE=CONTACTS
export APP_ID_COLUMN=ID
export APP_FIRST_NAME_COLUMN=FIRST_NAME
export APP_LAST_NAME_COLUMN=LAST_NAME
export APP_EMAIL_COLUMN=EMAIL
export APP_PHONE_COLUMN=PHONE
export APP_ADDRESS1_COLUMN=ADDRESS_LINE1
export APP_ADDRESS2_COLUMN=ADDRESS_LINE2
export APP_CITY_COLUMN=CITY
export APP_STATE_COLUMN=STATE
export APP_POSTAL_CODE_COLUMN=POSTAL_CODE
export APP_COUNTRY_COLUMN=COUNTRY
export APP_MAX_RESULTS=200
```

### 3) Table schema assumptions

By default, the app assumes a `CONTACTS` table with columns:
- `ID` (primary key)
- `FIRST_NAME`, `LAST_NAME`
- `EMAIL`, `PHONE`
- `ADDRESS_LINE1`, `ADDRESS_LINE2`, `CITY`, `STATE`, `POSTAL_CODE`, `COUNTRY`

Adjust names in the `[app]` section if your schema differs.

### 4) Run the app

```bash
streamlit run streamlit_app.py
```

Open the URL shown in the terminal. Use the search bar, then click "Open" to view the full person report.

### Notes
- Searches use parameterized queries and `ILIKE` for case-insensitive matching.
- Phone search normalizes digits (removes non-digits) for matching.
- Links use query parameters (e.g., `?person_id=123`) to open the report view.