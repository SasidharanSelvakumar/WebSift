import ipaddress
import socket
from urllib.parse import urlparse, urlunparse
from typing import List, Tuple

from backend.config import BLOCKED_CIDR_NETWORKS, BLOCKED_HOSTNAMES

# Pre-parse networks for high-speed checking
_PARSED_BLOCKED_NETWORKS = [ipaddress.ip_network(cidr) for cidr in BLOCKED_CIDR_NETWORKS]


class SSRFProtectionError(ValueError):
    """Raised when a URL attempts to target private, loopback, or metadata addresses."""
    pass


def is_ip_blocked(ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address) -> Tuple[bool, str]:
    """
    Check if an IPv4 or IPv6 address is restricted under SSRF rules.
    Returns (is_blocked, reason).
    """
    if ip_obj.is_loopback:
        return True, f"Loopback address ({ip_obj}) is restricted."
    if ip_obj.is_private:
        return True, f"Private network address ({ip_obj}) is restricted."
    if ip_obj.is_link_local:
        return True, f"Link-local address ({ip_obj}) is restricted."
    if ip_obj.is_multicast:
        return True, f"Multicast address ({ip_obj}) is restricted."
    if ip_obj.is_reserved:
        return True, f"Reserved address ({ip_obj}) is restricted."
    if ip_obj.is_unspecified:
        return True, f"Unspecified address ({ip_obj}) is restricted."

    # IPv4-mapped IPv6 check (e.g. ::ffff:127.0.0.1)
    if isinstance(ip_obj, ipaddress.IPv6Address) and ip_obj.ipv4_mapped:
        mapped_v4 = ip_obj.ipv4_mapped
        return is_ip_blocked(mapped_v4)

    # Check against explicit CIDR blacklist
    for net in _PARSED_BLOCKED_NETWORKS:
        if ip_obj in net:
            return True, f"Address ({ip_obj}) belongs to restricted CIDR block {net}."

    return False, ""


def validate_and_sanitize_url(url_str: str) -> Tuple[str, str]:
    """
    Validates that a URL is safe to scrape:
    - Must be HTTP or HTTPS
    - Hostname must be valid
    - Resolves DNS and ensures destination IP is not private/loopback/cloud metadata
    Returns (sanitized_url, resolved_primary_ip).
    Raises SSRFProtectionError or ValueError.
    """
    if not url_str or not isinstance(url_str, str):
        raise ValueError("URL must be a non-empty string.")

    cleaned_url = url_str.strip()
    if not cleaned_url.startswith(("http://", "https://")):
        # Auto-prefix http if missing scheme or provide clear error
        if "://" not in cleaned_url:
            cleaned_url = "https://" + cleaned_url
        else:
            raise ValueError("Only 'http' and 'https' protocols are permitted.")

    try:
        parsed = urlparse(cleaned_url)
    except Exception as e:
        raise ValueError(f"Invalid URL structure: {str(e)}")

    if parsed.scheme.lower() not in ("http", "https"):
        raise ValueError(f"Unsupported URL scheme '{parsed.scheme}'. Only 'http' and 'https' are allowed.")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL does not contain a valid hostname.")

    hostname_lower = hostname.lower().strip()

    # Reject cloud metadata hostnames and localhost
    if hostname_lower in BLOCKED_HOSTNAMES:
        raise SSRFProtectionError(f"Access to '{hostname}' is blocked for security reasons.")

    # Reject internal domain suffixes
    blocked_suffixes = (
        ".localhost",
        ".local",
        ".internal",
        ".localdomain",
        ".arpa",
        ".onion",
        ".corp",
        ".lan",
    )
    if any(hostname_lower.endswith(sfx) for sfx in blocked_suffixes):
        raise SSRFProtectionError(f"Access to internal domain '{hostname}' is restricted.")

    # Check if hostname is an IP literal
    try:
        ip_obj = ipaddress.ip_address(hostname_lower)
        blocked, reason = is_ip_blocked(ip_obj)
        if blocked:
            raise SSRFProtectionError(f"Direct IP access forbidden: {reason}")
        primary_ip = str(ip_obj)
    except ValueError:
        # Hostname is a domain name: resolve DNS
        try:
            # socket.getaddrinfo returns list of (family, type, proto, canonname, sockaddr)
            addr_info = socket.getaddrinfo(hostname_lower, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        except socket.gaierror as e:
            raise ValueError(f"Could not resolve domain '{hostname}': {str(e)}")

        if not addr_info:
            raise ValueError(f"DNS lookup returned no records for '{hostname}'.")

        resolved_ips: List[str] = []
        for info in addr_info:
            sockaddr = info[4]
            ip_str = sockaddr[0]
            resolved_ips.append(ip_str)
            try:
                ip_obj = ipaddress.ip_address(ip_str)
                blocked, reason = is_ip_blocked(ip_obj)
                if blocked:
                    raise SSRFProtectionError(
                        f"Target domain '{hostname}' resolved to restricted IP ({ip_str}): {reason}"
                    )
            except ValueError:
                raise SSRFProtectionError(f"Invalid IP address resolved for '{hostname}': {ip_str}")

        primary_ip = resolved_ips[0]

    # Reconstruct sanitized URL (strip any credentials for security)
    port_str = f":{parsed.port}" if parsed.port and parsed.port not in (80, 443) else ""
    netloc = f"{hostname_lower}{port_str}"
    sanitized_url = urlunparse((
        parsed.scheme.lower(),
        netloc,
        parsed.path or "/",
        parsed.params,
        parsed.query,
        ""  # strip fragments
    ))

    return sanitized_url, primary_ip
