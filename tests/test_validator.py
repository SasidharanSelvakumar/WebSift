import pytest
from backend.url_validator import validate_and_sanitize_url, SSRFProtectionError, is_ip_blocked
import ipaddress


def test_valid_public_urls():
    url, ip = validate_and_sanitize_url("https://example.com")
    assert url.startswith("https://example.com")
    assert ip != ""

    url, ip = validate_and_sanitize_url("http://example.com/blog/article?id=123")
    assert "article" in url


def test_url_scheme_validation():
    with pytest.raises(ValueError, match="Only 'http' and 'https'"):
        validate_and_sanitize_url("ftp://example.com/file.txt")

    with pytest.raises(ValueError, match="Only 'http' and 'https'"):
        validate_and_sanitize_url("file:///etc/passwd")

    with pytest.raises(ValueError, match="Only 'http' and 'https'"):
        validate_and_sanitize_url("gopher://example.com")


def test_localhost_and_blocked_hostnames():
    with pytest.raises(SSRFProtectionError):
        validate_and_sanitize_url("http://localhost:8000/secret")

    with pytest.raises(SSRFProtectionError):
        validate_and_sanitize_url("http://metadata.google.internal/computeMetadata/v1/")

    with pytest.raises(SSRFProtectionError):
        validate_and_sanitize_url("http://instance-data/latest/meta-data/")


def test_ip_direct_ssrf_blocks():
    # Loopback
    with pytest.raises(SSRFProtectionError):
        validate_and_sanitize_url("http://127.0.0.1:8080")

    with pytest.raises(SSRFProtectionError):
        validate_and_sanitize_url("http://127.10.20.30")

    # Cloud metadata
    with pytest.raises(SSRFProtectionError):
        validate_and_sanitize_url("http://169.254.169.254/latest/meta-data/")

    # RFC 1918 Private
    with pytest.raises(SSRFProtectionError):
        validate_and_sanitize_url("http://10.0.0.1")

    with pytest.raises(SSRFProtectionError):
        validate_and_sanitize_url("http://192.168.1.100")

    with pytest.raises(SSRFProtectionError):
        validate_and_sanitize_url("http://172.16.0.5")

    # IPv6 loopback
    with pytest.raises(SSRFProtectionError):
        validate_and_sanitize_url("http://[::1]")


def test_ip_blocked_helper():
    assert is_ip_blocked(ipaddress.ip_address("127.0.0.1"))[0] is True
    assert is_ip_blocked(ipaddress.ip_address("10.50.1.2"))[0] is True
    assert is_ip_blocked(ipaddress.ip_address("192.168.0.1"))[0] is True
    assert is_ip_blocked(ipaddress.ip_address("169.254.169.254"))[0] is True
    assert is_ip_blocked(ipaddress.ip_address("8.8.8.8"))[0] is False
    assert is_ip_blocked(ipaddress.ip_address("1.1.1.1"))[0] is False
