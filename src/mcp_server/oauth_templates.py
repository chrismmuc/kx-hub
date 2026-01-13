"""
HTML templates for OAuth 2.1 authorization and consent UI.

Provides simple, functional HTML pages for user authentication and consent.
"""


import html


def _render_oauth_hidden_inputs(oauth_params: dict) -> str:
    if not oauth_params:
        return ""

    fields = [
        "client_id",
        "redirect_uri",
        "response_type",
        "state",
        "scope",
        "code_challenge",
        "code_challenge_method",
    ]
    hidden_inputs = []
    for field in fields:
        value = oauth_params.get(field)
        if value is None:
            continue
        # HTML-escape values to prevent injection
        escaped_value = html.escape(str(value), quote=True)
        hidden_inputs.append(f'<input type="hidden" name="{field}" value="{escaped_value}">')

    return "\n            ".join(hidden_inputs)


def get_login_page(client_name: str, scope: str, oauth_params: dict, action_url: str, error: str = None) -> str:
    """
    Generate login page HTML.

    Args:
        client_name: Name of the OAuth client
        scope: Requested scope
        error: Error message to display (optional)

    Returns:
        HTML page
    """
    error_html = f'<div class="error">{error}</div>' if error else ""
    hidden_inputs_html = _render_oauth_hidden_inputs(oauth_params)

    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>kx-hub Authorization</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            padding: 20px;
        }}
        .container {{
            background: white;
            border-radius: 12px;
            box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
            padding: 40px;
            max-width: 400px;
            width: 100%;
        }}
        h1 {{
            color: #333;
            font-size: 24px;
            margin: 0 0 10px 0;
            text-align: center;
        }}
        .subtitle {{
            color: #666;
            font-size: 14px;
            text-align: center;
            margin-bottom: 30px;
        }}
        .client-info {{
            background: #f7f7f7;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 25px;
        }}
        .client-info strong {{
            display: block;
            color: #333;
            margin-bottom: 5px;
        }}
        .client-info span {{
            color: #667eea;
            font-weight: 600;
        }}
        .scope {{
            color: #666;
            font-size: 13px;
            margin-top: 10px;
        }}
        .form-group {{
            margin-bottom: 20px;
        }}
        label {{
            display: block;
            color: #333;
            font-weight: 500;
            margin-bottom: 8px;
            font-size: 14px;
        }}
        input[type="password"] {{
            width: 100%;
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 14px;
            box-sizing: border-box;
            transition: border-color 0.3s;
        }}
        input[type="password"]:focus {{
            outline: none;
            border-color: #667eea;
        }}
        button {{
            width: 100%;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 14px;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        button:hover {{
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
        }}
        button:active {{
            transform: translateY(0);
        }}
        .error {{
            background: #fee;
            border-left: 4px solid #c33;
            color: #c33;
            padding: 12px;
            border-radius: 4px;
            margin-bottom: 20px;
            font-size: 14px;
        }}
        .info {{
            color: #666;
            font-size: 12px;
            text-align: center;
            margin-top: 20px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🔐 kx-hub Authorization</h1>
        <p class="subtitle">Sign in to authorize access</p>

        {error_html}

        <div class="client-info">
            <strong>Application:</strong>
            <span>{client_name}</span>
            <div class="scope">
                <strong>Requesting access to:</strong> {scope or "your kx-hub knowledge base"}
            </div>
        </div>

        <form method="POST" action="{action_url}">
            {hidden_inputs_html}
            <div class="form-group">
                <label for="password">Password</label>
                <input type="password" id="password" name="password" required autofocus>
            </div>

            <button type="submit">Authorize</button>
        </form>

        <p class="info">
            This authorization flow is protected by kx-hub.<br>
            Your credentials are never shared with third-party applications.
        </p>
    </div>
</body>
</html>
    """


def get_consent_page(client_name: str, scope: str, user_email: str, oauth_params: dict, action_url: str) -> str:
    """
    Generate consent page HTML (shown after successful login).

    Args:
        client_name: Name of the OAuth client
        scope: Requested scope
        user_email: Authenticated user email

    Returns:
        HTML page
    """
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Authorize {client_name}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            padding: 20px;
        }}
        .container {{
            background: white;
            border-radius: 12px;
            box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
            padding: 40px;
            max-width: 450px;
            width: 100%;
        }}
        h1 {{
            color: #333;
            font-size: 24px;
            margin: 0 0 10px 0;
        }}
        .user-info {{
            background: #f0f4ff;
            border-radius: 8px;
            padding: 12px;
            margin-bottom: 25px;
            font-size: 14px;
            color: #666;
        }}
        .permissions {{
            background: #f7f7f7;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 25px;
        }}
        .permissions h2 {{
            margin: 0 0 15px 0;
            font-size: 16px;
            color: #333;
        }}
        .permissions ul {{
            list-style: none;
            padding: 0;
            margin: 0;
        }}
        .permissions li {{
            padding: 10px 0 10px 30px;
            position: relative;
            color: #555;
            font-size: 14px;
        }}
        .permissions li:before {{
            content: "✓";
            position: absolute;
            left: 0;
            color: #667eea;
            font-weight: bold;
            font-size: 18px;
        }}
        .button-group {{
            display: flex;
            gap: 12px;
        }}
        button {{
            flex: 1;
            padding: 14px;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            border: none;
        }}
        .btn-authorize {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }}
        .btn-authorize:hover {{
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
        }}
        .btn-cancel {{
            background: #f0f0f0;
            color: #666;
        }}
        .btn-cancel:hover {{
            background: #e0e0e0;
        }}
        .info {{
            color: #666;
            font-size: 12px;
            text-align: center;
            margin-top: 20px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Authorize {client_name}</h1>

        <div class="user-info">
            Signed in as: <strong>{user_email}</strong>
        </div>

        <div class="permissions">
            <h2>{client_name} is requesting permission to:</h2>
            <ul>
                <li>Access your kx-hub knowledge base</li>
                <li>Search and retrieve your highlights and notes</li>
                <li>View knowledge cards and cluster information</li>
                <li>Get reading recommendations based on your content</li>
            </ul>
        </div>

        <form id="consent-form" method="POST" action="{action_url}">
            <input type="hidden" name="consent" value="approve">
            {_render_oauth_hidden_inputs(oauth_params)}
            <div class="button-group">
                <button type="button" class="btn-cancel" onclick="window.location.href='?error=access_denied'">
                    Cancel
                </button>
                <button type="submit" class="btn-authorize" onclick="submitForm(event)">
                    Authorize
                </button>
            </div>
        </form>
        <script>
            function submitForm(e) {{
                e.preventDefault();
                var form = document.getElementById('consent-form');
                console.log('Submitting form to:', form.action);
                form.submit();
            }}
        </script>

        <p class="info">
            You can revoke this access at any time from your kx-hub settings.
        </p>
    </div>
</body>
</html>
    """


def get_error_page(error: str, error_description: str) -> str:
    """
    Generate error page HTML.

    Args:
        error: Error code
        error_description: Human-readable error description

    Returns:
        HTML page
    """
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Authorization Error</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            padding: 20px;
        }}
        .container {{
            background: white;
            border-radius: 12px;
            box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
            padding: 40px;
            max-width: 400px;
            width: 100%;
            text-align: center;
        }}
        .error-icon {{
            font-size: 64px;
            margin-bottom: 20px;
        }}
        h1 {{
            color: #c33;
            font-size: 24px;
            margin: 0 0 15px 0;
        }}
        p {{
            color: #666;
            font-size: 14px;
            line-height: 1.6;
        }}
        .error-code {{
            background: #f7f7f7;
            border-radius: 6px;
            padding: 10px;
            margin-top: 20px;
            font-family: monospace;
            font-size: 12px;
            color: #999;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="error-icon">⚠️</div>
        <h1>Authorization Failed</h1>
        <p>{error_description}</p>
        <div class="error-code">Error code: {error}</div>
    </div>
</body>
</html>
    """


def get_success_page(redirect_url: str, client_name: str) -> str:
    """
    Generate authorization success page with auto-redirect.

    Args:
        redirect_url: Full callback URL with code and state
        client_name: Name of the OAuth client

    Returns:
        HTML page
    """
    # Escape URL for HTML attributes and JavaScript
    escaped_url = html.escape(redirect_url, quote=True)
    escaped_client = html.escape(client_name)
    # For JavaScript, we need to escape backslashes and quotes
    js_url = redirect_url.replace("\\", "\\\\").replace('"', '\\"').replace("'", "\\'")

    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="refresh" content="3;url={escaped_url}">
    <title>Authorization Successful</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            padding: 20px;
        }}
        .container {{
            background: white;
            border-radius: 12px;
            box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
            padding: 40px;
            max-width: 450px;
            width: 100%;
            text-align: center;
        }}
        .success-icon {{
            font-size: 64px;
            margin-bottom: 20px;
            animation: bounce 1s ease infinite;
        }}
        @keyframes bounce {{
            0%, 100% {{ transform: translateY(0); }}
            50% {{ transform: translateY(-10px); }}
        }}
        h1 {{
            color: #333;
            font-size: 24px;
            margin: 0 0 15px 0;
        }}
        p {{
            color: #666;
            font-size: 14px;
            line-height: 1.6;
            margin-bottom: 20px;
        }}
        .redirect-info {{
            background: #f0f4ff;
            border-radius: 8px;
            padding: 12px;
            font-size: 13px;
            color: #666;
            margin-top: 20px;
        }}
        .manual-link {{
            display: inline-block;
            margin-top: 15px;
            padding: 12px 24px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            text-decoration: none;
            border-radius: 8px;
            font-weight: 600;
            transition: transform 0.2s;
        }}
        .manual-link:hover {{
            transform: translateY(-2px);
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="success-icon">✅</div>
        <h1>Authorization Successful!</h1>
        <p>
            You have successfully authorized <strong>{escaped_client}</strong> to access your kx-hub knowledge base.
        </p>
        <p>
            You will be redirected back to {escaped_client} in 3 seconds...
        </p>

        <div class="redirect-info">
            If you are not redirected automatically, click the button below:
        </div>

        <a href="{escaped_url}" class="manual-link">
            Return to {escaped_client}
        </a>
    </div>

    <script>
        // Auto-redirect after 3 seconds
        setTimeout(function() {{
            window.location.href = "{js_url}";
        }}, 3000);
    </script>
</body>
</html>
    """
