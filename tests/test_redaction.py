from shadow.memory import Redactor, redact


def test_empty_text_passthrough():
    text, matched = redact("")
    assert text == ""
    assert matched == []


def test_plain_text_unchanged():
    original = "This is a normal sentence with no secrets."
    text, matched = redact(original)
    assert text == original
    assert matched == []


def test_openai_key_redacted():
    text, matched = redact("here is my key sk-abcdefghij1234567890abcdefghij")
    assert "[REDACTED]" in text
    assert "openai_key" in matched
    assert "sk-" not in text


def test_github_pat_redacted():
    text, matched = redact("token: ghp_" + "a" * 36)
    assert "[REDACTED]" in text
    assert "github_pat" in matched


def test_aws_key_redacted():
    text, matched = redact("AKIAIOSFODNN7EXAMPLE")
    assert "[REDACTED]" in text
    assert "aws_key" in matched


def test_slack_token_redacted():
    text, matched = redact("xoxb-1234567890-abcdefghij")
    assert "[REDACTED]" in text
    assert "slack_token" in matched


def test_pem_private_key_redacted():
    pem = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEpAIBAAKCAQEA...\n"
        "-----END RSA PRIVATE KEY-----"
    )
    text, matched = redact(pem)
    assert "[REDACTED]" in text
    assert "pem_private" in matched


def test_jwt_redacted():
    jwt = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiIxMjM0NTY3ODkwIn0."
        "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    )
    text, matched = redact(jwt)
    assert "[REDACTED]" in text
    assert "jwt" in matched


def test_hex_token_redacted():
    text, matched = redact("a" * 64)
    assert "[REDACTED]" in text
    assert "hex_token" in matched


def test_credit_card_redacted():
    # Visa test number (Luhn-valid)
    text, matched = redact("card 4111 1111 1111 1111")
    assert "[REDACTED]" in text
    assert "card_candidate" in matched


def test_fake_credit_card_number_kept():
    # Not Luhn-valid, so should stay
    text, matched = redact("order 1234 5678 9012 3456")
    assert "[REDACTED]" not in text
    assert "card_candidate" not in matched


def test_email_kept_by_default():
    text, matched = redact("contact me at alice@example.com")
    assert "alice@example.com" in text
    assert "email" not in matched


def test_email_redacted_when_enabled():
    r = Redactor(redact_emails=True)
    text, matched = r.redact("contact me at alice@example.com")
    assert "[REDACTED]" in text
    assert "email" in matched


def test_disabled_redactor_passthrough():
    r = Redactor(enabled=False)
    text, matched = r.redact("sk-abcdefghij1234567890abcdefghij")
    assert "sk-" in text
    assert matched == []


def test_multiple_secrets_in_one_text():
    text = "key1 sk-abcdefghij1234567890abcdefghij " "and key2 ghp_" + "b" * 36
    redacted, matched = redact(text)
    assert redacted.count("[REDACTED]") == 2
    assert "openai_key" in matched
    assert "github_pat" in matched


def test_custom_placeholder():
    r = Redactor(placeholder="<SECRET>")
    text, _ = r.redact("sk-abcdefghij1234567890abcdefghij")
    assert "<SECRET>" in text
    assert "[REDACTED]" not in text


def test_normal_short_hex_not_redacted():
    # Less than 32 chars — should not match
    text, matched = redact("id: deadbeef")
    assert "hex_token" not in matched


def test_luhn_validation_positive():
    from shadow.memory.redaction import _luhn_valid

    assert _luhn_valid("4111111111111111") is True
    assert _luhn_valid("5500000000000004") is True


def test_luhn_validation_negative():
    from shadow.memory.redaction import _luhn_valid

    assert _luhn_valid("4111111111111112") is False
    assert _luhn_valid("1234567890123456") is False
