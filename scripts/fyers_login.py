#!/usr/bin/env python3
"""Generate a FYERS v3 access token without printing credentials."""
from __future__ import annotations

import os
from pathlib import Path

from wickhunter.env import load_local_env


def main() -> None:
    load_local_env()
    app_id = os.environ.get("FYERS_APP_ID")
    secret = os.environ.get("FYERS_APP_SECRET")
    redirect = os.environ.get("FYERS_REDIRECT_URI")
    if not app_id or not secret or not redirect:
        raise SystemExit("Set FYERS_APP_ID, FYERS_APP_SECRET and FYERS_REDIRECT_URI in .env")

    from fyers_apiv3 import fyersModel

    session = fyersModel.SessionModel(
        client_id=app_id,
        secret_key=secret,
        redirect_uri=redirect,
        response_type="code",
        grant_type="authorization_code",
    )
    print("Open this URL in your browser:\n")
    print(session.generate_authcode())
    auth_code = input("\nPaste the auth_code from the redirect URL: ").strip()
    if not auth_code:
        raise SystemExit("auth_code is required")
    session.set_token(auth_code)
    response = session.generate_token()
    token = response.get("access_token") if isinstance(response, dict) else None
    if not token:
        raise SystemExit(f"FYERS token generation failed: {response}")
    Path(os.environ.get("FYERS_TOKEN_FILE", ".fyers_token")).write_text(token, encoding="utf-8")
    print("FYERS access token saved locally.")


if __name__ == "__main__":
    main()
