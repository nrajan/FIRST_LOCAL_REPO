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


def main() -> None:
    st.set_page_config(page_title="SiS OAuth File Downloader", page_icon="⬇️", layout="centered")
    st.title("SiS OAuth File Downloader")

    session = None
    try:
        session = get_active_session()
    except Exception:
        session = None

    token = get_oauth_token_from_session(session)
    if not token:
        st.error(
            "Could not retrieve an OAuth access token from the current Snowflake session. "
            "Ensure users authenticate to Snowflake via OAuth and that this app is running inside SiS."
        )
        st.stop()

    st.caption(f"OAuth token detected: {mask_token(token)}")

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
        help="The HTTPS endpoint to fetch using the Bearer token from your Snowflake OAuth session.",
    )

    auto = st.checkbox("Auto-download after successful fetch", value=True)

    fetch = st.button("Fetch file now")

    if fetch:
        if not url:
            st.warning("Please provide a valid BUILD_STAGE_FILE_URL.")
            st.stop()

        headers = {"Authorization": f"Bearer {token}"}
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


if __name__ == "__main__":
    main()