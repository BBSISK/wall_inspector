import os
import secrets
import random
import urllib.parse
from datetime import datetime, timedelta, timezone
import requests

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

MS_AUTH_URL_TEMPLATE = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize"
MS_TOKEN_URL_TEMPLATE = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
MS_USERINFO_URL = "https://graph.microsoft.com/v1.0/me"

def get_oauth_authorization_url(provider, redirect_uri, state, client_id, tenant="common"):
    """Builds the OAuth 2.0 authorization URL for Google or Microsoft."""
    if provider == "google":
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "online",
            "prompt": "select_account"
        }
        return f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"
    elif provider == "microsoft":
        auth_url = MS_AUTH_URL_TEMPLATE.format(tenant=tenant)
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile User.Read",
            "state": state,
            "response_mode": "query"
        }
        return f"{auth_url}?{urllib.parse.urlencode(params)}"
    else:
        raise ValueError(f"Unsupported OAuth provider: {provider}")

def exchange_oauth_code(provider, code, redirect_uri, client_id, client_secret, tenant="common"):
    """
    Exchanges an OAuth authorization code for tokens and queries the provider's
    userinfo endpoint to retrieve email, name, and subject identifier.
    """
    if provider == "google":
        token_resp = requests.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code"
            },
            timeout=10
        )
        token_data = token_resp.json()
        if "error" in token_data or "access_token" not in token_data:
            return None, token_data.get("error_description") or token_data.get("error") or "Failed to exchange token with Google."

        access_token = token_data["access_token"]
        user_resp = requests.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10
        )
        user_data = user_resp.json()
        email = user_data.get("email", "").lower().strip()
        name = user_data.get("name") or email.split("@")[0].capitalize()
        oauth_id = user_data.get("sub", "")
        avatar_url = user_data.get("picture", "")

        return {
            "email": email,
            "name": name,
            "oauth_id": oauth_id,
            "avatar_url": avatar_url,
            "provider": "google"
        }, None

    elif provider == "microsoft":
        token_url = MS_TOKEN_URL_TEMPLATE.format(tenant=tenant)
        token_resp = requests.post(
            token_url,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code"
            },
            timeout=10
        )
        token_data = token_resp.json()
        if "error" in token_data or "access_token" not in token_data:
            return None, token_data.get("error_description") or token_data.get("error") or "Failed to exchange token with Microsoft."

        access_token = token_data["access_token"]
        user_resp = requests.get(
            MS_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10
        )
        user_data = user_resp.json()
        email = (user_data.get("mail") or user_data.get("userPrincipalName") or "").lower().strip()
        name = user_data.get("displayName") or email.split("@")[0].capitalize()
        oauth_id = user_data.get("id", "")

        return {
            "email": email,
            "name": name,
            "oauth_id": oauth_id,
            "avatar_url": "",
            "provider": "microsoft"
        }, None

    return None, f"Unsupported provider: {provider}"

def generate_otp_code():
    """Generates a secure 6-digit one-time passcode."""
    return f"{secrets.randbelow(900000) + 100000}"

def get_otp_expiry(minutes=15):
    """Calculates OTP expiration timestamp in UTC."""
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)
