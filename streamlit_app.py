import os
import re
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

try:
    import snowflake.connector
except Exception:  # pragma: no cover
    snowflake = None  # type: ignore


# ---------- Configuration helpers ----------

def get_snowflake_config() -> Dict[str, Any]:
    """Return Snowflake connection configuration from Streamlit secrets or environment variables."""
    cfg: Dict[str, Any] = {}

    # Prefer Streamlit secrets if available
    if hasattr(st, "secrets") and "snowflake" in st.secrets:
        sf = st.secrets["snowflake"]
        cfg = {
            "account": sf.get("account"),
            "user": sf.get("user"),
            "password": sf.get("password"),
            "warehouse": sf.get("warehouse"),
            "database": sf.get("database"),
            "schema": sf.get("schema"),
            "role": sf.get("role"),
        }
    else:
        cfg = {
            "account": os.getenv("SNOWFLAKE_ACCOUNT"),
            "user": os.getenv("SNOWFLAKE_USER"),
            "password": os.getenv("SNOWFLAKE_PASSWORD"),
            "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE"),
            "database": os.getenv("SNOWFLAKE_DATABASE"),
            "schema": os.getenv("SNOWFLAKE_SCHEMA"),
            "role": os.getenv("SNOWFLAKE_ROLE"),
        }

    # Validate minimal required fields
    required = ["account", "user", "password", "warehouse", "database", "schema"]
    missing = [k for k in required if not cfg.get(k)]
    if missing:
        raise RuntimeError(
            f"Missing Snowflake configuration values: {', '.join(missing)}. "
            "Provide them in Streamlit secrets under [snowflake] or as environment variables."
        )

    return cfg


def get_app_config() -> Dict[str, Any]:
    """Return app-level configuration like table/column names, with sensible defaults.

    These can be overridden via Streamlit secrets in [app] section or environment variables.
    """
    defaults: Dict[str, Any] = {
        "contact_table": os.getenv("APP_CONTACT_TABLE", "CONTACTS"),
        "id_column": os.getenv("APP_ID_COLUMN", "ID"),
        "first_name_column": os.getenv("APP_FIRST_NAME_COLUMN", "FIRST_NAME"),
        "last_name_column": os.getenv("APP_LAST_NAME_COLUMN", "LAST_NAME"),
        "email_column": os.getenv("APP_EMAIL_COLUMN", "EMAIL"),
        "phone_column": os.getenv("APP_PHONE_COLUMN", "PHONE"),
        "address1_column": os.getenv("APP_ADDRESS1_COLUMN", "ADDRESS_LINE1"),
        "address2_column": os.getenv("APP_ADDRESS2_COLUMN", "ADDRESS_LINE2"),
        "city_column": os.getenv("APP_CITY_COLUMN", "CITY"),
        "state_column": os.getenv("APP_STATE_COLUMN", "STATE"),
        "postal_code_column": os.getenv("APP_POSTAL_CODE_COLUMN", "POSTAL_CODE"),
        "country_column": os.getenv("APP_COUNTRY_COLUMN", "COUNTRY"),
        "max_results": int(os.getenv("APP_MAX_RESULTS", "200")),
    }

    if hasattr(st, "secrets") and "app" in st.secrets:
        for key, value in st.secrets["app"].items():
            defaults[key] = value

    return defaults


# ---------- Database Access Layer ----------

class SnowflakeRepository:
    """Encapsulates Snowflake access for search and details queries."""

    def __init__(self, connection_params: Dict[str, Any], app_cfg: Dict[str, Any]) -> None:
        self.connection_params = connection_params
        self.app_cfg = app_cfg

    def _connect(self):  # type: ignore[no-untyped-def]
        if snowflake is None:
            raise RuntimeError("snowflake-connector-python is not installed.")
        return snowflake.connector.connect(
            account=self.connection_params["account"],
            user=self.connection_params["user"],
            password=self.connection_params["password"],
            warehouse=self.connection_params["warehouse"],
            database=self.connection_params["database"],
            schema=self.connection_params["schema"],
            role=self.connection_params.get("role"),
            client_session_keep_alive=True,
        )

    def search_by_name(self, name_query: str) -> pd.DataFrame:
        """Search contacts by name using ILIKE on first, last, and full name."""
        cfg = self.app_cfg
        table = cfg["contact_table"]
        id_col = cfg["id_column"]
        first = cfg["first_name_column"]
        last = cfg["last_name_column"]
        email = cfg["email_column"]
        phone = cfg["phone_column"]
        max_results = cfg["max_results"]

        like = f"%{name_query}%"
        sql = f"""
            SELECT {id_col} AS PERSON_ID,
                   {first} AS FIRST_NAME,
                   {last} AS LAST_NAME,
                   {email} AS EMAIL,
                   {phone} AS PHONE
            FROM {table}
            WHERE {first} ILIKE %s
               OR {last} ILIKE %s
               OR CONCAT({first}, ' ', {last}) ILIKE %s
            LIMIT {max_results}
        """
        params = (like, like, like)
        return self._execute_to_df(sql, params)

    def search_by_email(self, email_query: str) -> pd.DataFrame:
        cfg = self.app_cfg
        table = cfg["contact_table"]
        id_col = cfg["id_column"]
        first = cfg["first_name_column"]
        last = cfg["last_name_column"]
        email = cfg["email_column"]
        phone = cfg["phone_column"]
        max_results = cfg["max_results"]

        like = f"%{email_query}%"
        sql = f"""
            SELECT {id_col} AS PERSON_ID,
                   {first} AS FIRST_NAME,
                   {last} AS LAST_NAME,
                   {email} AS EMAIL,
                   {phone} AS PHONE
            FROM {table}
            WHERE {email} ILIKE %s
            LIMIT {max_results}
        """
        params = (like,)
        return self._execute_to_df(sql, params)

    def search_by_phone(self, phone_query: str) -> pd.DataFrame:
        cfg = self.app_cfg
        table = cfg["contact_table"]
        id_col = cfg["id_column"]
        first = cfg["first_name_column"]
        last = cfg["last_name_column"]
        email = cfg["email_column"]
        phone = cfg["phone_column"]
        max_results = cfg["max_results"]

        normalized = re.sub(r"\D+", "", phone_query)
        like = f"%{normalized}%"
        # Normalize the phone column by stripping non-digits for comparison
        sql = f"""
            SELECT {id_col} AS PERSON_ID,
                   {first} AS FIRST_NAME,
                   {last} AS LAST_NAME,
                   {email} AS EMAIL,
                   {phone} AS PHONE
            FROM {table}
            WHERE REGEXP_REPLACE({phone}, '[^0-9]', '') ILIKE %s
            LIMIT {max_results}
        """
        params = (like,)
        return self._execute_to_df(sql, params)

    def get_person_by_id(self, person_id: Any) -> Optional[Dict[str, Any]]:
        cfg = self.app_cfg
        table = cfg["contact_table"]
        id_col = cfg["id_column"]

        sql = f"SELECT * FROM {table} WHERE {id_col} = %s"
        with self._connect() as conn:
            cur = conn.cursor(snowflake.connector.DictCursor)  # type: ignore[attr-defined]
            cur.execute(sql, (person_id,))
            row = cur.fetchone()
            cur.close()
        if not row:
            return None
        # Convert keys to plain strings
        return {str(k): v for k, v in row.items()}

    def _execute_to_df(self, sql: str, params: Tuple[Any, ...]) -> pd.DataFrame:
        with self._connect() as conn:
            cur = conn.cursor()
            try:
                cur.execute(sql, params)
                try:
                    df = cur.fetch_pandas_all()
                except Exception:
                    rows = cur.fetchall()
                    columns = [c[0] for c in cur.description]
                    df = pd.DataFrame(rows, columns=columns)
            finally:
                cur.close()
        return df


# ---------- UI Helpers ----------

def set_query_param(name: str, value: Optional[str]) -> None:
    try:
        # Newer Streamlit API
        qp = st.query_params
        if value is None:
            qp.clear()
        else:
            qp[name] = value
    except Exception:
        # Fallback to experimental API
        if value is None:
            st.experimental_set_query_params()
        else:
            st.experimental_set_query_params(**{name: value})


def get_query_param(name: str) -> Optional[str]:
    try:
        qp = st.query_params
        return qp.get(name)
    except Exception:
        params = st.experimental_get_query_params()
        vals = params.get(name)
        if not vals:
            return None
        return vals[0] if isinstance(vals, list) else vals


def format_full_name(row: Dict[str, Any], cfg: Dict[str, Any]) -> str:
    first = row.get(cfg["first_name_column"]) or row.get("FIRST_NAME") or ""
    last = row.get(cfg["last_name_column"]) or row.get("LAST_NAME") or ""
    full = f"{first} {last}".strip()
    return full or "Unknown"


def format_address(row: Dict[str, Any], cfg: Dict[str, Any]) -> str:
    parts = [
        str(row.get(cfg["address1_column"], "") or "").strip(),
        str(row.get(cfg["address2_column"], "") or "").strip(),
        " ".join(
            p for p in [
                str(row.get(cfg["city_column"], "") or "").strip(),
                str(row.get(cfg["state_column"], "") or "").strip(),
            ]
            if p
        ).strip(),
        str(row.get(cfg["postal_code_column"], "") or "").strip(),
        str(row.get(cfg["country_column"], "") or "").strip(),
    ]
    parts = [p for p in parts if p]
    return "\n".join(parts) if parts else "—"


# ---------- Streamlit App ----------

st.set_page_config(page_title="Contact Search", page_icon="🔎", layout="wide")

st.title("🔎 Contact Search")

# Load configuration and repository
try:
    sf_cfg = get_snowflake_config()
    app_cfg = get_app_config()
    repo = SnowflakeRepository(sf_cfg, app_cfg)
except Exception as e:
    st.error("Snowflake is not configured. See the README for setup details.")
    st.exception(e)
    st.stop()

person_id = get_query_param("person_id")

if person_id:
    # ----- Person report page -----
    record = repo.get_person_by_id(person_id)
    if not record:
        st.warning("No record found for the requested person.")
        if st.button("Back to search"):
            set_query_param("person_id", None)
        st.stop()

    with st.sidebar:
        if st.button("← Back to search"):
            set_query_param("person_id", None)

    # Header
    st.header("Person Report")

    # Top summary
    left, right = st.columns([2, 1])
    with left:
        st.subheader(format_full_name(record, app_cfg))
        email_val = record.get(app_cfg["email_column"]) or record.get("EMAIL") or "—"
        phone_val = record.get(app_cfg["phone_column"]) or record.get("PHONE") or "—"
        st.write(f"**Email:** {email_val}")
        st.write(f"**Phone:** {phone_val}")
    with right:
        st.caption("Address")
        st.write(format_address(record, app_cfg))

    st.divider()

    # Key-value details
    st.subheader("Full details")
    # Display nicely: two columns of key/value pairs
    items = list(record.items())
    left_col, right_col = st.columns(2)
    for idx, (key, value) in enumerate(items):
        target = left_col if idx % 2 == 0 else right_col
        display_val = "—" if value in (None, "") else value
        target.write(f"**{key}**\n\n{display_val}")

else:
    # ----- Search page -----
    with st.sidebar:
        st.info("Search by name, email, or phone. Click a result to open the full report.")

    with st.form("search_form", clear_on_submit=False):
        search_type = st.segmented_control(
            "Search by",
            options=["Name", "Email", "Phone"],
            default="Name",
        )
        query = st.text_input("Search query", placeholder="e.g., Jane Doe, jane@company.com, or (555) 123-4567")
        submitted = st.form_submit_button("Search")

    if submitted:
        if not query.strip():
            st.warning("Please enter a search query.")
            st.stop()

        with st.spinner("Searching..."):
            if search_type == "Name":
                df = repo.search_by_name(query.strip())
            elif search_type == "Email":
                df = repo.search_by_email(query.strip())
            else:
                df = repo.search_by_phone(query.strip())

        if df.empty:
            st.info("No results found.")
            st.stop()

        # Create a link column to open the report using query params
        base_links: List[str] = [f"?person_id={pid}" for pid in df["PERSON_ID"].astype(str).tolist()]
        df_links = df.copy()
        df_links.insert(0, "OPEN", base_links)

        st.success(f"Found {len(df_links)} result(s).")
        st.dataframe(
            df_links,
            hide_index=True,
            use_container_width=True,
            column_config={
                "OPEN": st.column_config.LinkColumn("Open", help="Open person report"),
            },
        )

        st.caption("Tip: Click 'Open' to view a detailed report.")