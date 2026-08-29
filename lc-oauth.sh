#!/bin/bash
#
# lc-oauth.sh - LimaCharlie OAuth Authentication
#
# Usage: ./lc-oauth.sh [OPTIONS]
#   -o, --oid OID       Organization ID (optional)
#   -p, --provider      OAuth provider: google (default) or microsoft
#   -n, --no-browser    Don't auto-open browser
#   -h, --help          Show help
#
# Outputs the LimaCharlie JWT to stdout on success.
# All status messages go to stderr.
#

set -euo pipefail

# ============================================================================
# Configuration
# ============================================================================

FIREBASE_API_KEY="${LC_FIREBASE_API_KEY:-AIzaSyB5VyO6qS-XlnVD3zOIuEVNBD5JFn22_1w}"
PREFERRED_PORTS=(8085 8086 8087 8088 8089)
CALLBACK_TIMEOUT=300

# Default options
OID=""
PROVIDER="google.com"
NO_BROWSER=false

# Cleanup tracking
CLEANUP_FILES=()

# ============================================================================
# Utility Functions
# ============================================================================

log() {
    echo "$@" >&2
}

die() {
    log "Error: $1"
    exit 1
}

# Cleanup handler
cleanup() {
    for f in "${CLEANUP_FILES[@]}"; do
        rm -f "$f" 2>/dev/null || true
    done
}
trap cleanup EXIT

# JSON value extraction (works without jq)
# Usage: json_get "$json_string" "key"
json_get() {
    local json="$1"
    local key="$2"
    # Try to extract string value, handling escaped quotes and unicode
    local result
    result=$(printf '%s' "$json" | grep -oE "\"$key\"[[:space:]]*:[[:space:]]*\"([^\"\\\\]|\\\\.)*\"" | head -1 | sed 's/.*:[[:space:]]*"//;s/"$//' | sed 's/\\u0026/\&/g;s/\\"/"/g')
    if [ -n "$result" ]; then
        printf '%s' "$result"
        return
    fi
    # Fallback to simpler extraction for non-escaped values
    printf '%s' "$json" | grep -o "\"$key\":\"[^\"]*\"" | head -1 | cut -d'"' -f4 | sed 's/\\u0026/\&/g'
}

# JSON string escaping for safe payload construction
json_escape() {
    local s="$1"
    s="${s//\\/\\\\}"    # Escape backslashes first
    s="${s//\"/\\\"}"    # Escape double quotes
    s="${s//$'\n'/\\n}"  # Escape newlines
    s="${s//$'\r'/\\r}"  # Escape carriage returns
    s="${s//$'\t'/\\t}"  # Escape tabs
    printf '%s' "$s"
}

# Check if a command exists
has_cmd() {
    command -v "$1" >/dev/null 2>&1
}

# Cross-platform timeout wrapper
run_with_timeout() {
    local timeout_seconds="$1"
    shift

    if has_cmd timeout; then
        timeout "$timeout_seconds" "$@"
    elif has_cmd gtimeout; then
        # GNU coreutils on macOS via Homebrew
        gtimeout "$timeout_seconds" "$@"
    else
        # Fallback using perl (available on macOS)
        perl -e "alarm $timeout_seconds; exec @ARGV" -- "$@"
    fi
}

# ============================================================================
# Browser Opening - Cross-platform
# ============================================================================

open_browser() {
    local url="$1"

    if [ "$NO_BROWSER" = true ]; then
        return 1
    fi

    # Try various browser openers in order of preference
    if has_cmd xdg-open; then
        xdg-open "$url" 2>/dev/null &
        return 0
    elif has_cmd open; then
        # macOS
        open "$url" 2>/dev/null &
        return 0
    elif has_cmd gnome-open; then
        gnome-open "$url" 2>/dev/null &
        return 0
    elif has_cmd kde-open; then
        kde-open "$url" 2>/dev/null &
        return 0
    elif has_cmd wslview; then
        # WSL
        wslview "$url" 2>/dev/null &
        return 0
    elif [ -n "${BROWSER:-}" ] && has_cmd "$BROWSER"; then
        "$BROWSER" "$url" 2>/dev/null &
        return 0
    fi

    return 1
}

# ============================================================================
# Netcat Callback Server - Cross-platform
# ============================================================================

# Detect netcat variant and set appropriate flags
detect_netcat() {
    if has_cmd nc; then
        # Check for macOS/BSD netcat first
        if [[ "${OSTYPE:-}" == darwin* ]]; then
            echo "bsd"
        elif nc -h 2>&1 | grep -q 'GNU netcat'; then
            echo "gnu"
        elif nc -h 2>&1 | grep -q '\-q.*quit'; then
            echo "openbsd"
        elif nc -h 2>&1 | grep -q 'ncat'; then
            echo "nmap"
        else
            # Default to trying openbsd-style
            echo "openbsd"
        fi
    elif has_cmd ncat; then
        echo "nmap"
    elif has_cmd netcat; then
        echo "netcat"
    else
        echo "none"
    fi
}

# Find a free port from the preferred list
find_free_port() {
    for port in "${PREFERRED_PORTS[@]}"; do
        # Use nc -z for portable port check
        if ! nc -z localhost "$port" 2>/dev/null; then
            echo "$port"
            return 0
        fi
    done
    die "All OAuth callback ports (8085-8089) are in use"
}

# Start callback server and wait for OAuth redirect
# Returns the query string from the callback
wait_for_callback() {
    local port="$1"
    local nc_variant
    nc_variant=$(detect_netcat)

    # Build HTTP response body and headers
    local body='<html><head><title>LimaCharlie</title></head><body style="font-family:sans-serif;text-align:center;padding:50px;"><h1>Authentication Successful</h1><p>You can close this window and return to your terminal.</p></body></html>'
    local response
    response=$(printf 'HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: %d\r\nConnection: close\r\n\r\n%s' "${#body}" "$body")

    local tmpfile
    tmpfile=$(mktemp)
    CLEANUP_FILES+=("$tmpfile")

    # Create a temporary script for the netcat command to avoid echo -e issues
    local nc_script
    nc_script=$(mktemp)
    CLEANUP_FILES+=("$nc_script")

    case "$nc_variant" in
        bsd)
            # macOS BSD netcat - no -p flag, no -q flag
            cat > "$nc_script" <<NCSCRIPT
#!/bin/bash
printf '%s' '$response' | nc -l $port
NCSCRIPT
            ;;
        openbsd)
            # OpenBSD netcat (most common on Debian/Ubuntu)
            # Try with -q first, fall back without
            cat > "$nc_script" <<NCSCRIPT
#!/bin/bash
printf '%s' '$response' | nc -l -p $port -q 1 2>/dev/null || printf '%s' '$response' | nc -l $port
NCSCRIPT
            ;;
        gnu)
            # GNU netcat
            cat > "$nc_script" <<NCSCRIPT
#!/bin/bash
printf '%s' '$response' | nc -l -p $port -c
NCSCRIPT
            ;;
        nmap)
            # Nmap's ncat
            cat > "$nc_script" <<NCSCRIPT
#!/bin/bash
printf '%s' '$response' | ncat -l $port --recv-only
NCSCRIPT
            ;;
        netcat)
            # Generic netcat
            cat > "$nc_script" <<NCSCRIPT
#!/bin/bash
printf '%s' '$response' | netcat -l -p $port
NCSCRIPT
            ;;
        none)
            die "No netcat found. Please install netcat-openbsd, ncat, or netcat."
            ;;
    esac

    chmod +x "$nc_script"

    if ! run_with_timeout "$CALLBACK_TIMEOUT" "$nc_script" > "$tmpfile" 2>/dev/null; then
        # Check if we got any data despite timeout
        if [ ! -s "$tmpfile" ]; then
            die "Callback server failed or timed out"
        fi
    fi

    local request
    request=$(cat "$tmpfile")

    # Extract query string from: GET /callback?code=...&state=... HTTP/1.1
    local callback_path
    callback_path=$(echo "$request" | head -1 | awk '{print $2}')

    if [ -z "$callback_path" ] || [[ "$callback_path" != /callback* ]]; then
        die "Invalid callback received"
    fi

    # Return the query string
    echo "${callback_path#*\?}"
}

# ============================================================================
# MFA Handling
# ============================================================================

handle_mfa() {
    local mfa_pending_credential="$1"
    local mfa_info="$2"

    log ""
    log "============================================================"
    log "Multi-Factor Authentication Required"
    log "============================================================"
    log ""
    log "Your account has 2FA enabled. Please complete verification."
    log ""

    # Extract first MFA factor info
    local mfa_enrollment_id
    local factor_type

    mfa_enrollment_id=$(echo "$mfa_info" | grep -o '"mfaEnrollmentId":"[^"]*"' | head -1 | cut -d'"' -f4)

    if echo "$mfa_info" | grep -q '"totpInfo"'; then
        factor_type="totp"
        log "Factor: Authenticator app (TOTP)"
    elif echo "$mfa_info" | grep -q '"phoneInfo"'; then
        factor_type="phone"
        local phone
        phone=$(echo "$mfa_info" | grep -o '"phoneInfo":"[^"]*"' | head -1 | cut -d'"' -f4)
        log "Factor: SMS to $phone"
    else
        die "Unknown MFA factor type"
    fi

    log ""

    # Prompt for code (up to 3 attempts)
    local code=""
    local attempts=0
    while [ $attempts -lt 3 ]; do
        read -r -p "Enter 6-digit verification code: " code </dev/tty

        if [ -z "$code" ]; then
            log "Error: Code cannot be empty"
            ((attempts++))
            continue
        fi

        if ! [[ "$code" =~ ^[0-9]{6}$ ]]; then
            log "Error: Code must be exactly 6 digits"
            ((attempts++))
            continue
        fi

        break
    done

    if [ $attempts -ge 3 ]; then
        die "Maximum MFA attempts exceeded"
    fi

    log "Verifying code..."

    # Escape values for JSON
    local escaped_credential escaped_enrollment_id
    escaped_credential=$(json_escape "$mfa_pending_credential")
    escaped_enrollment_id=$(json_escape "$mfa_enrollment_id")

    # Build MFA finalize payload
    local mfa_payload
    if [ "$factor_type" = "totp" ]; then
        mfa_payload=$(cat <<EOF
{
    "mfaPendingCredential": "$escaped_credential",
    "mfaEnrollmentId": "$escaped_enrollment_id",
    "totpVerificationInfo": {
        "verificationCode": "$code"
    }
}
EOF
)
    else
        mfa_payload=$(cat <<EOF
{
    "mfaPendingCredential": "$escaped_credential",
    "mfaEnrollmentId": "$escaped_enrollment_id",
    "phoneVerificationInfo": {
        "code": "$code"
    }
}
EOF
)
    fi

    local mfa_response
    mfa_response=$(curl -s -X POST \
        "https://identitytoolkit.googleapis.com/v2/accounts/mfaSignIn:finalize?key=$FIREBASE_API_KEY" \
        -H "Content-Type: application/json" \
        --data-binary @- <<< "$mfa_payload")

    # Check for error
    if echo "$mfa_response" | grep -q '"error"'; then
        local error_msg
        error_msg=$(echo "$mfa_response" | grep -o '"message":"[^"]*"' | cut -d'"' -f4)
        die "MFA verification failed: $error_msg"
    fi

    # Return the ID token
    json_get "$mfa_response" "idToken"
}

# ============================================================================
# Main OAuth Flow
# ============================================================================

do_oauth() {
    # Find free port
    local port
    port=$(find_free_port)
    local redirect_uri="http://localhost:$port/callback"

    log "Starting OAuth flow..."
    log "Callback server on port $port"

    # Step 1: Get auth URI from Firebase
    log "Requesting auth URL from Firebase..."

    # Escape provider for JSON (though it should be safe)
    local escaped_provider
    escaped_provider=$(json_escape "$PROVIDER")

    local auth_payload
    auth_payload=$(cat <<EOF
{
    "providerId": "$escaped_provider",
    "continueUri": "$redirect_uri",
    "authFlowType": "CODE_FLOW",
    "oauthScope": "openid email profile"
}
EOF
)

    local auth_response
    auth_response=$(curl -s -X POST \
        "https://identitytoolkit.googleapis.com/v1/accounts:createAuthUri?key=$FIREBASE_API_KEY" \
        -H "Content-Type: application/json" \
        --data-binary @- <<< "$auth_payload")

    local session_id auth_uri
    session_id=$(json_get "$auth_response" "sessionId")
    auth_uri=$(json_get "$auth_response" "authUri")

    if [ -z "$session_id" ] || [ -z "$auth_uri" ]; then
        die "Failed to get auth URI from Firebase"
    fi

    # Step 2: Open browser or show URL
    log ""
    if open_browser "$auth_uri"; then
        log "Browser opened. Please complete authentication."
    else
        log "Please visit this URL to authenticate:"
        log ""
        log "$auth_uri"
        log ""
    fi

    log "Waiting for callback (timeout: ${CALLBACK_TIMEOUT}s)..."

    # Step 3: Wait for callback
    local query_string
    query_string=$(wait_for_callback "$port")

    if [ -z "$query_string" ]; then
        die "No callback data received"
    fi

    # Check for OAuth error in callback
    if echo "$query_string" | grep -q "error="; then
        local error
        error=$(echo "$query_string" | grep -o 'error=[^&]*' | cut -d= -f2)
        die "OAuth error: $error"
    fi

    log "Callback received, exchanging token..."

    # Step 4: Exchange with Firebase signInWithIdp
    # Escape session_id for JSON
    local escaped_session_id
    escaped_session_id=$(json_escape "$session_id")

    local token_payload
    token_payload=$(cat <<EOF
{
    "requestUri": "$redirect_uri",
    "postBody": "$query_string",
    "sessionId": "$escaped_session_id",
    "returnSecureToken": true,
    "returnIdpCredential": true
}
EOF
)

    local token_response
    token_response=$(curl -s -X POST \
        "https://identitytoolkit.googleapis.com/v1/accounts:signInWithIdp?key=$FIREBASE_API_KEY" \
        -H "Content-Type: application/json" \
        --data-binary @- <<< "$token_payload")

    # Check for MFA requirement
    local mfa_pending
    mfa_pending=$(json_get "$token_response" "mfaPendingCredential")

    local firebase_id_token
    if [ -n "$mfa_pending" ]; then
        # MFA required
        local mfa_info
        mfa_info=$(echo "$token_response" | grep -o '"mfaInfo":\[[^]]*\]')
        firebase_id_token=$(handle_mfa "$mfa_pending" "$mfa_info")
    else
        firebase_id_token=$(json_get "$token_response" "idToken")
    fi

    if [ -z "$firebase_id_token" ]; then
        die "Failed to get Firebase token"
    fi

    log "Firebase authentication successful"

    # Step 5: Exchange Firebase token for LimaCharlie JWT
    log "Exchanging for LimaCharlie JWT..."

    local lc_payload="fb_auth=$firebase_id_token"
    if [ -n "$OID" ]; then
        lc_payload="$lc_payload&oid=$OID"
    fi

    local lc_response
    lc_response=$(curl -s -X POST "https://jwt.limacharlie.io" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        --data-binary @- <<< "$lc_payload")

    local lc_jwt
    lc_jwt=$(json_get "$lc_response" "jwt")

    if [ -z "$lc_jwt" ]; then
        local error_msg
        error_msg=$(json_get "$lc_response" "error")
        if [ -n "$error_msg" ]; then
            die "LimaCharlie JWT error: $error_msg"
        fi
        die "Failed to get LimaCharlie JWT"
    fi

    log ""
    log "Authentication successful!"

    # Output JWT to stdout
    echo "$lc_jwt"
}

# ============================================================================
# Argument Parsing
# ============================================================================

show_help() {
    cat >&2 <<EOF
Usage: $0 [OPTIONS]

LimaCharlie OAuth Authentication - outputs JWT to stdout

Options:
  -o, --oid OID        Organization ID (optional, for org-scoped JWT)
  -p, --provider NAME  OAuth provider: google (default) or microsoft
  -n, --no-browser     Don't auto-open browser, just print URL
  -h, --help           Show this help message

Examples:
  $0                           # Authenticate with Google
  $0 -p microsoft              # Authenticate with Microsoft
  $0 -o abc123-def456          # Get JWT for specific org
  $0 -n                        # Manual browser mode

Output:
  On success, prints only the JWT to stdout.
  All status messages go to stderr.

  Example usage with curl:
    JWT=\$($0)
    curl -H "Authorization: bearer \$JWT" https://api.limacharlie.io/v1/...

Requirements:
  - curl
  - netcat (nc, ncat, or netcat)
  - timeout (coreutils) or gtimeout (on macOS via Homebrew) or perl
EOF
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -o|--oid)
                [ -n "${2:-}" ] || die "Option $1 requires an argument"
                OID="$2"
                shift 2
                ;;
            -p|--provider)
                [ -n "${2:-}" ] || die "Option $1 requires an argument"
                case "$2" in
                    google)
                        PROVIDER="google.com"
                        ;;
                    microsoft)
                        PROVIDER="microsoft.com"
                        ;;
                    *)
                        die "Unknown provider: $2. Use 'google' or 'microsoft'."
                        ;;
                esac
                shift 2
                ;;
            -n|--no-browser)
                NO_BROWSER=true
                shift
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            *)
                die "Unknown option: $1. Use -h for help."
                ;;
        esac
    done
}

# ============================================================================
# Main
# ============================================================================

main() {
    parse_args "$@"

    # Check dependencies
    has_cmd curl || die "curl is required but not found"
    [ "$(detect_netcat)" != "none" ] || die "netcat (nc/ncat) is required but not found"

    # Check for timeout capability
    if ! has_cmd timeout && ! has_cmd gtimeout && ! has_cmd perl; then
        die "timeout, gtimeout, or perl is required but not found"
    fi

    do_oauth
}

main "$@"
