# WebSift - Backend Configuration and Security Constants
from typing import Set

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 WebSift/1.0"

# Timeouts in seconds
REQUEST_TIMEOUT_SECONDS = 15.0
PLAYWRIGHT_TIMEOUT_MS = 20000

# Max download size: 10 Megabytes
MAX_CONTENT_LENGTH = 10 * 1024 * 1024

# SSRF Blocked IPv4 and IPv6 CIDR networks
BLOCKED_CIDR_NETWORKS = [
    # IPv4 Private & Loopback & Special
    "0.0.0.0/8",          # "This" network
    "10.0.0.0/8",         # RFC 1918 Private
    "100.64.0.0/10",      # Carrier-grade NAT
    "127.0.0.0/8",        # Loopback
    "169.254.0.0/16",     # Link-local / Cloud metadata (AWS, GCP, Azure, etc.)
    "172.16.0.0/12",      # RFC 1918 Private
    "192.0.0.0/24",       # IETF Protocol Assignments
    "192.0.2.0/24",       # TEST-NET-1
    "192.88.99.0/24",     # 6to4 Relay Anycast
    "192.168.0.0/16",     # RFC 1918 Private
    "198.18.0.0/15",      # Benchmarking
    "198.51.100.0/24",    # TEST-NET-2
    "203.0.113.0/24",     # TEST-NET-3
    "224.0.0.0/4",        # Multicast
    "240.0.0.0/4",        # Reserved
    "255.255.255.255/32", # Broadcast
    # IPv6 Loopback & Special
    "::/128",             # Unspecified
    "::1/128",            # Loopback
    "::ffff:0:0/96",      # IPv4-mapped IPv6
    "64:ff9b::/96",       # IPv4/IPv6 translation
    "100::/64",           # Discard-only
    "2001::/23",          # IETF Protocol
    "2001:db8::/32",      # Documentation
    "2002::/16",          # 6to4
    "fc00::/7",           # Unique Local Address (private)
    "fe80::/10",          # Link-local
    "ff00::/8",           # Multicast
]

# Cloud metadata hostname blacklists
BLOCKED_HOSTNAMES: Set[str] = {
    "localhost",
    "localhost.localdomain",
    "instance-data",
    "metadata.google.internal",
    "metadata.internal",
    "metadata",
}

# Formula injection trigger characters for spreadsheet safety
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
