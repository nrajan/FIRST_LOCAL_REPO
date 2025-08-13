import os
import re
import base64
import streamlit as st
import requests
from typing import Optional

try:
    from snowflake.snowpark.context import get_active_session
except Exception:
    # Fallback for local testing where Snowpark might not be installed
    def get_active_session():  # type: ignore
        return None


def try_get_attr(obj: object, path: str) -> Optional[object]:
    current = obj
    for part in path.split("."):
        if not hasattr(current, part):
            return None
        current = getattr(current, part)
    return current


def get_oauth_token_from_session(session) -> Optional[str]:
    if session is None:
        return None

    candidate_paths = [
        "_conn._rest._token",
        "_conn._rest._auth_token",
        "_conn._rest._id_token",
        "_conn._conn._token",
        "_conn._conn.rest._token",
        "_conn._rest.token",
        "_conn._rest._jwt_token",
        "_conn.rest._token",
        "_conn._jwtToken",
        "_conn._token",
    ]

    for path in candidate_paths:
        try:
            value = try_get_attr(session, path)
            if isinstance(value, str) and len(value) > 20:
                return value
        except Exception:
            continue

    # Last attempt: look for a connector connection object and probe its rest client
    try:
        conn = getattr(session, "connection", None)
        if conn is not None:
            for rest_attr in ("_rest", "rest"):
                rest_client = getattr(conn, rest_attr, None)
                if rest_client is None:
                    continue
                for token_attr in ("_token", "token", "_auth_token"):
                    token_value = getattr(rest_client, token_attr, None)
                    if isinstance(token_value, str) and len(token_value) > 20:
                        return token_value
    except Exception:
        pass

    return None


def mask_token(token: str) -> str:
    if not token:
        return ""
    if len(token) <= 12:
        return "***"
    return f"{token[:6]}...{token[-6:]}"


def infer_filename(url: str, headers: dict) -> str:
    content_disposition = headers.get("Content-Disposition") or headers.get("content-disposition", "")
    if content_disposition:
        match = re.search(r"filename\*?=(?:UTF-8''|\")?([^\";]+)", content_disposition, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    # Fallback to URL path
    path_no_query = re.sub(r"[?#].*$", "", url)
    last_segment = path_no_query.rstrip("/").split("/")[-1]
    return last_segment or "download.bin"


def auto_download_via_js(file_bytes: bytes, filename: str, mime: str) -> None:
    b64 = base64.b64encode(file_bytes).decode()
    safe_filename = filename.replace('"', '')
    html = f"""
<div></div>
<script>
(function() {{
  try {{
    const b64 = "{b64}";
    const mime = "{mime}";
    const fname = "{safe_filename}";
    const a = document.createElement('a');
    a.href = "data:" + mime + ";base64," + b64;
    a.download = fname;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }} catch (e) {{
    console.error(e);
  }}
}})();
</script>
"""
    st.components.v1.html(html, height=0, scrolling=False)


def get_secret_bearer_token() -> Optional[str]:
    try:
        val = st.secrets.get("AUTH_BEARER_TOKEN")  # type: ignore[attr-defined]
        if isinstance(val, str) and val:
            return val
    except Exception:
        pass
    env_val = os.getenv("AUTH_BEARER_TOKEN")
    if env_val:
        return env_val
    return None


def generate_presigned_url(session, stage_name: str, file_path: str, expiration_seconds: int = 3600) -> Optional[str]:
    if session is None:
        return None
    try:
        df = session.sql(
            "select get_presigned_url(?, ?, ?)",
        ).bind((stage_name, file_path, expiration_seconds)).to_pandas()
        if not df.empty:
            url_val = df.iloc[0, 0]
            if isinstance(url_val, str) and url_val:
                return url_val
    except Exception as ex:
        st.error("Failed to generate presigned URL. Ensure the stage and file exist and privileges are granted.")
        st.exception(ex)
    return None


def main() -> None:
    st.set_page_config(page_title="SiS OAuth File Downloader", page_icon="⬇️", layout="centered")
    st.title("SiS OAuth File Downloader")

    session = None
    try:
        session = get_active_session()
    except Exception:
        session = None

    # Best-effort attempt (not supported by Snowflake officially) to detect a Snowflake auth token
    session_token = get_oauth_token_from_session(session)

    if session_token:
        st.caption(f"Detected a Snowflake session token (masked): {mask_token(session_token)}")
    else:
        st.info(
            "Snowflake does not expose the user's OAuth/SSO token to Streamlit apps. "
            "Use one of the supported options below."
        )

    tab1, tab2 = st.tabs(["HTTP GET with Bearer", "Presigned URL (Stage)"])

    with tab1:
        default_url = None
        try:
            if "BUILD_STAGE_FILE_URL" in st.secrets:
                default_url = st.secrets["BUILD_STAGE_FILE_URL"]
        except Exception:
            default_url = None
        if not default_url:
            default_url = os.getenv("BUILD_STAGE_FILE_URL", "")

        url = st.text_input(
            label="BUILD_STAGE_FILE_URL",
            value=default_url or "",
            placeholder="https://<host>/path/to/file",
            help=(
                "The HTTPS endpoint to fetch. Authorization header will use the Bearer token from "
                "AUTH_BEARER_TOKEN secret or env."
            ),
        )

        token_choice = st.radio(
            "Bearer token source",
            ["AUTH_BEARER_TOKEN (secret/env)", "Paste manually"],
            horizontal=True,
        )

        bearer = None
        if token_choice == "AUTH_BEARER_TOKEN (secret/env)":
            bearer = get_secret_bearer_token()
            if bearer:
                st.caption(f"Using AUTH_BEARER_TOKEN (masked): {mask_token(bearer)}")
            else:
                st.warning("No AUTH_BEARER_TOKEN found in secrets or environment. Switch to 'Paste manually'.")
        else:
            bearer = st.text_input("Paste Bearer token", value="", type="password")

        auto = st.checkbox("Auto-download after successful fetch", value=True, key="auto1")
        fetch = st.button("Fetch file now", key="fetch1")

        if fetch:
            if not url:
                st.warning("Please provide a valid BUILD_STAGE_FILE_URL.")
                st.stop()
            if not bearer:
                st.warning("No Bearer token provided.")
                st.stop()

            headers = {"Authorization": f"Bearer {bearer}"}
            try:
                with st.spinner("Fetching file via HTTPS GET..."):
                    resp = requests.get(url, headers=headers, timeout=90)
            except Exception as ex:
                st.error("Network error while fetching the file. Ensure external network access is allowed for this app.")
                st.exception(ex)
                st.stop()

            if 200 <= resp.status_code < 300:
                filename = infer_filename(url, resp.headers)
                mime = resp.headers.get("Content-Type", "application/octet-stream")
                data = resp.content

                st.success(f"Fetched {filename} ({len(data)} bytes)")
                st.download_button(
                    label="Download file",
                    data=data,
                    file_name=filename,
                    mime=mime,
                )

                if auto:
                    auto_download_via_js(data, filename, mime)
            else:
                st.error(f"Request failed: {resp.status_code} {resp.reason}")
                if resp.text:
                    st.code(resp.text[:4000])

    with tab2:
        st.write("Generate a time-bound link to a file in a Snowflake stage.")
        stage_name = st.text_input("Stage name (e.g., @mystage)", value="@mystage")
        file_path = st.text_input("File path in stage (e.g., folder/file.ext)", value="")
        expiration = st.number_input("Expiration (seconds)", min_value=60, max_value=86400, value=3600, step=60)

        auto_open = st.checkbox("Auto-open link after generation", value=False, key="auto2")
        gen = st.button("Generate presigned URL", key="gen2")

        if gen:
            if not stage_name.startswith("@"):
                st.warning("Stage name must start with '@'.")
                st.stop()
            if not file_path:
                st.warning("Please provide a file path.")
                st.stop()

            url_val = generate_presigned_url(session, stage_name, file_path, int(expiration))
            if url_val:
                st.success("Presigned URL generated.")
                st.markdown(f"[Download file]({url_val})")
                if auto_open:
                    html = f"""
<script>
try {{ window.open('{url_val}', '_blank'); }} catch (e) {{ console.error(e); }}
</script>
"""
                    st.components.v1.html(html, height=0, scrolling=False)
            else:
                st.error("Failed to generate a presigned URL.")


if __name__ == "__main__":
    main()