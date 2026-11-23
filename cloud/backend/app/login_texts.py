"""The texts of ZITADEL's login that MedMusketeer overrides (English), on top of ZITADEL's defaults.

Set by the zitadel-bootstrap job on the instance and on every organisation, and by the API on each
organisation it creates: ZITADEL v4.20 does not pass the instance's texts on to an organisation, and
the login asks for an organisation's texts on its pages for that organisation's users (the code page
of an invite among them). Keys as in the login's locales/en.json (zitadel-login v4.20).
"""

# Accounts start with an invite code the administrator hands over (D12), but the login's code page
# asked for "the Code provided in the verification email", so people pressed "Resend code", which
# replaces the administrator's code by one e-mailed to them and makes the first stop working
# ("Code is invalid").
LOGIN_TEXTS = {
    "loginname": {"labels": {"loginname": "Login Name"}},
    "verify": {
        "verify": {
            "description": "Enter the invite code your administrator gave you.",
            "noCodeReceived": "Lost the code? Ask your administrator for a new one.",
            "resendCode": "E-mail me a new code (the old one stops working)",
        },
        "errors": {
            "couldNotVerifyInvite": "This invite code is not valid. A code stops working when a new one is sent: "
                                    "ask your administrator for a new code.",
        },
    },
    "password": {
        "errors": {
            "couldNotCreateSessionForUser": "Sign-in failed. Check your password and try again, or use Reset Password.",
            "failedToAuthenticateNoLimit": "Wrong password. Try again, or use Reset Password.",
            "failedToAuthenticate": "Wrong password ({failedAttempts} of {maxPasswordAttempts} attempts used).{lockoutMessage}",
        },
    },
}
LOGIN_TEXTS_LOCALE = "en"
TRANSLATIONS = "/v2/settings/hosted_login_translation"

