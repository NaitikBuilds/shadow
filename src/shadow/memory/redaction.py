"""Redaction of secrets before embedding or storage.

Every observation passes through `redact()` before it is written to the
database or embedded. API keys, tokens, credit card numbers, and PEM
keys are replaced with a placeholder so the vector store never contains
secrets.

Design: pure function, no state, no I/O. Easy to test and easy to call
from anywhere.
"""

import re

# Regex patterns for known secret formats.
_SECRET_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}\b")),
    ("github_pat", re.compile(r"\bghp_[A-Za-z0-9]{30,}\b")),
    ("aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b")),
    (
        "pem_private",
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
            re.DOTALL,
        ),
    ),
    # JWT: three base64url chunks separated by dots, first chunk starts with eyJ
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\b")),
    # Long hex strings (32+ chars, standalone)
    ("hex_token", re.compile(r"\b[a-fA-F0-9]{32,}\b")),
    # Credit card candidates (13-19 digits with optional spaces/dashes)
    ("card_candidate", re.compile(r"\b(?:\d[ -]?){12,18}\d\b")),
]

_EMAIL = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")


class Redactor:
    """Applies secret-redaction patterns to text."""

    def __init__(
        self,
        enabled: bool = True,
        redact_emails: bool = False,
        placeholder: str = "[REDACTED]",
    ):
        self.enabled = enabled
        self.redact_emails = redact_emails
        self.placeholder = placeholder

    def redact(self, text: str) -> tuple[str, list[str]]:
        """Return (redacted_text, [matched_type, ...])."""
        if not self.enabled or not text:
            return text, []

        redacted = text
        matched: list[str] = []

        for name, pattern in _SECRET_PATTERNS:

            def _replace(match, _name=name):
                if _name == "card_candidate" and not _luhn_valid(match.group(0)):
                    return match.group(0)  # not a real card, leave alone
                matched.append(_name)
                return self.placeholder

            redacted = pattern.sub(_replace, redacted)

        if self.redact_emails:

            def _email_replace(match):
                matched.append("email")
                return self.placeholder

            redacted = _EMAIL.sub(_email_replace, redacted)

        return redacted, matched


def redact(
    text: str,
    enabled: bool = True,
    redact_emails: bool = False,
    placeholder: str = "[REDACTED]",
) -> tuple[str, list[str]]:
    """Convenience wrapper. Returns (redacted_text, matched_types)."""
    return Redactor(
        enabled=enabled,
        redact_emails=redact_emails,
        placeholder=placeholder,
    ).redact(text)


def _luhn_valid(candidate: str) -> bool:
    """Validate a candidate credit card number with the Luhn checksum."""
    digits = [int(c) for c in candidate if c.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False
    checksum = 0
    reverse = digits[::-1]
    for i, d in enumerate(reverse):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0
