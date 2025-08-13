## SiS OAuth File Downloader

This Streamlit-in-Snowflake (SiS) app retrieves the current user's Snowflake OAuth access token and uses it to fetch a file from `BUILD_STAGE_FILE_URL` via HTTPS GET. The file is then offered for download to the user's local machine (with an optional auto-download).

### Files
- `sis_app/app.py`: Streamlit app entrypoint
- `.streamlit/secrets.toml`: local-only placeholder for `BUILD_STAGE_FILE_URL`
- `requirements.txt`: local-only dependencies (SiS manages its own runtime)

### Prerequisites (Snowflake)
1. Ensure users authenticate to Snowflake using OAuth (OIDC/OpenID). The app attempts to read the OAuth bearer token from the active Snowflake session.
2. Allow egress to the `BUILD_STAGE_FILE_URL` host using an External Access Integration (EAI):

```sql
-- Replace <host> with the hostname from BUILD_STAGE_FILE_URL (no scheme), e.g., files.example.com
CREATE OR REPLACE NETWORK RULE sis_build_stage_rule
  TYPE = HOST_PORT
  MODE = EGRESS
  VALUE_LIST = ('<host>:443');

CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION sis_build_stage_eai
  ALLOWED_NETWORK_RULES = (sis_build_stage_rule)
  ENABLED = TRUE;
```

3. Stage the app code and create/update the SiS app:

```sql
-- Stage your app files (adjust local path and stage as needed)
CREATE OR REPLACE STAGE app_stage;
PUT file:///local/path/to/sis_app/app.py @app_stage AUTO_COMPRESS=FALSE OVERWRITE=TRUE;

-- Create or replace the Streamlit app
CREATE OR REPLACE STREAMLIT sis_oauth_downloader
  ROOT_LOCATION = '@app_stage/'
  MAIN_FILE = 'app.py'
  QUERY_WAREHOUSE = <YOUR_WAREHOUSE>
  EXTERNAL_ACCESS_INTEGRATIONS = (sis_build_stage_eai)
  PACKAGES = ('requests');

-- Provide the file endpoint as a secret
ALTER STREAMLIT sis_oauth_downloader SET SECRETS = (
  BUILD_STAGE_FILE_URL = 'https://<host>/path/to/file'
);
```

4. Open the SiS app in Snowsight and click "Fetch file now". Toggle "Auto-download" to automatically trigger the download after fetch.

### Notes
- The app reads the OAuth token from private connector attributes of the current session, which may vary by connector version. If retrieval fails, ensure authentication is via OAuth and update the attribute paths in `get_oauth_token_from_session` as needed.
- Streamlit cannot force a browser file save without a user gesture in all cases. The app offers a standard `Download file` button and an optional JavaScript-based auto-download best-effort.
- For large files, prefer using the `Download file` button instead of auto-download.