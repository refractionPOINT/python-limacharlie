"""
Firebase Multi-Factor Authentication (MFA) support for CLI OAuth.

This module handles MFA verification when users have enrolled second factors
in Firebase (TOTP authenticator apps or SMS). After completing OAuth sign-in,
if MFA is required, this module prompts the user for their verification code
and obtains an ID token with the firebase.sign_in_second_factor claim.
"""

import requests
import time
from typing import Dict, List, Optional

from .constants import FIREBASE_API_KEY


class FirebaseMFAError(Exception):
    """Firebase MFA authentication errors."""
    pass


class MFAHandler:
    """Handles Firebase MFA verification for OAuth users."""

    # Firebase Auth API v2 endpoints for MFA
    _BASE_V2 = "https://identitytoolkit.googleapis.com/v2"
    _MFA_FINALIZE = f"{_BASE_V2}/accounts/mfaSignIn:finalize"

    @staticmethod
    def display_mfa_factors(mfa_info: List[Dict]) -> Dict:
        """
        Display enrolled MFA factors to the user and return the selected one.

        Args:
            mfa_info: List of MFA factor info from Firebase

        Returns:
            Dictionary with selected MFA factor details

        Raises:
            FirebaseMFAError: If no valid factors found
        """
        if not mfa_info:
            raise FirebaseMFAError("No MFA factors found")

        print("\n" + "="*60)
        print("Multi-Factor Authentication Required")
        print("="*60)
        print("\nYour account has 2FA enabled. Please complete verification.\n")
        print("Enrolled authentication factor(s):")

        for i, factor in enumerate(mfa_info, 1):
            mfa_enrollment_id = factor.get('mfaEnrollmentId', 'unknown')
            display_name = factor.get('displayName', 'Unnamed factor')

            # Determine factor type
            if 'phoneInfo' in factor:
                phone = factor['phoneInfo']
                factor_type = f"SMS to {phone}"
            elif 'totpInfo' in factor:
                factor_type = "Authenticator app (TOTP)"
            else:
                factor_type = "Unknown factor type"

            print(f"  {i}. {display_name} ({factor_type})")

        # For simplicity, use first factor if only one exists
        # In the future, could prompt user to select
        selected_factor = mfa_info[0]
        print()

        return selected_factor

    @staticmethod
    def prompt_verification_code(factor: Dict, max_attempts: int = 3) -> str:
        """
        Prompt user for MFA verification code.

        Args:
            factor: The MFA factor being used
            max_attempts: Maximum number of input attempts

        Returns:
            The verification code entered by user

        Raises:
            FirebaseMFAError: If user exceeds max attempts or cancels
        """
        factor_name = factor.get('displayName', 'your authenticator')

        if 'phoneInfo' in factor:
            prompt = f"Enter the 6-digit code sent via SMS: "
        else:
            prompt = f"Enter the 6-digit code from {factor_name}: "

        for attempt in range(max_attempts):
            try:
                code = input(prompt).strip()

                # Validate code format
                if not code:
                    print("Error: Code cannot be empty. Please try again.")
                    continue

                if not code.isdigit():
                    print("Error: Code must contain only digits. Please try again.")
                    continue

                if len(code) != 6:
                    print(f"Error: Code must be exactly 6 digits (you entered {len(code)}). Please try again.")
                    continue

                return code

            except KeyboardInterrupt:
                print("\n\nMFA verification cancelled by user.")
                raise FirebaseMFAError("MFA verification cancelled by user")
            except EOFError:
                raise FirebaseMFAError("MFA verification cancelled (EOF)")

        raise FirebaseMFAError(f"Maximum attempts ({max_attempts}) exceeded")

    @staticmethod
    def finalize_mfa_sign_in(mfa_pending_credential: str,
                            mfa_factor: Dict,
                            verification_code: str) -> Dict[str, str]:
        """
        Complete MFA verification and get ID token with MFA claim.

        Args:
            mfa_pending_credential: The pending credential from signInWithIdp
            mfa_factor: The MFA factor being verified
            verification_code: The 6-digit verification code

        Returns:
            Dictionary with tokens including MFA claim:
            {
                'id_token': 'firebase-id-token-with-mfa-claim',
                'refresh_token': 'refresh-token',
                'expires_at': unix_timestamp,
                'mfa_verified': True
            }

        Raises:
            FirebaseMFAError: If MFA verification fails
        """
        url = f"{MFAHandler._MFA_FINALIZE}?key={FIREBASE_API_KEY}"

        mfa_enrollment_id = mfa_factor.get('mfaEnrollmentId')
        if not mfa_enrollment_id:
            raise FirebaseMFAError("Invalid MFA factor: missing mfaEnrollmentId")

        # Build the request payload based on factor type
        payload = {
            "mfaPendingCredential": mfa_pending_credential,
            "mfaEnrollmentId": mfa_enrollment_id,
        }

        # Add verification info based on factor type
        if 'phoneInfo' in mfa_factor:
            # SMS verification
            payload["phoneVerificationInfo"] = {
                "code": verification_code
            }
        else:
            # TOTP verification (authenticator app)
            payload["totpVerificationInfo"] = {
                "verificationCode": verification_code
            }

        try:
            print("\nVerifying code...")
            response = requests.post(url, json=payload, timeout=15)

            if response.status_code != 200:
                error_data = response.json()
                error_msg = error_data.get('error', {}).get('message', 'Unknown error')

                # Parse common error messages
                if 'INVALID_MFA_PENDING_CREDENTIAL' in error_msg:
                    raise FirebaseMFAError("MFA session expired. Please try logging in again.")
                elif 'INVALID_CODE' in error_msg or 'CODE_EXPIRED' in error_msg:
                    raise FirebaseMFAError("Invalid or expired verification code.")
                elif 'TOO_MANY_ATTEMPTS' in error_msg:
                    raise FirebaseMFAError("Too many failed attempts. Please try logging in again.")
                else:
                    raise FirebaseMFAError(f"MFA verification failed: {error_msg}")

            data = response.json()

            # Calculate expiry timestamp
            expires_in = int(data.get('expiresIn', '3600'))
            expires_at = int(time.time()) + expires_in

            print("Verification successful!")

            return {
                'id_token': data['idToken'],
                'refresh_token': data['refreshToken'],
                'expires_at': expires_at,
                'mfa_verified': True
            }

        except requests.exceptions.Timeout:
            raise FirebaseMFAError("MFA verification request timed out. Please try again.")
        except requests.exceptions.RequestException as e:
            raise FirebaseMFAError(f"Network error during MFA verification: {str(e)}")

    @classmethod
    def handle_mfa_flow(cls, mfa_pending_credential: str,
                       mfa_info: List[Dict]) -> Dict[str, str]:
        """
        Complete MFA flow: display factors, prompt for code, verify.

        Args:
            mfa_pending_credential: The pending credential from signInWithIdp
            mfa_info: List of enrolled MFA factors

        Returns:
            Dictionary with MFA-verified tokens

        Raises:
            FirebaseMFAError: If MFA flow fails
        """
        # Display factors and select one
        selected_factor = cls.display_mfa_factors(mfa_info)

        # Prompt for verification code
        verification_code = cls.prompt_verification_code(selected_factor)

        # Finalize MFA and get token with claim
        return cls.finalize_mfa_sign_in(
            mfa_pending_credential,
            selected_factor,
            verification_code
        )
