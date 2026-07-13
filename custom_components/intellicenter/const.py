"""Constants for the Pentair IntelliCenter integration."""

from __future__ import annotations

from typing import Literal

# Integration domain
DOMAIN = "intellicenter"

# Units of measurement (not available in Home Assistant constants)
CONST_RPM = "rpm"  # revolutions per minute
CONST_GPM = "gpm"  # gallons per minute

CALIB_ATTR = "CALIB"  # not yet in pyintellicenter
CHLOR_ATTR = "CHLOR"  # not yet in pyintellicenter
DNTSTP_ATTR = "DNTSTP"  # not yet in pyintellicenter
MANHT_ATTR = "MANHT"  # not yet in pyintellicenter
PORT_ATTR = "PORT"  # not yet in pyintellicenter
PRIMFLO_ATTR = "PRIMFLO"  # not yet in pyintellicenter
PRIMTIM_ATTR = "PRIMTIM"  # not yet in pyintellicenter
PROBE_ATTR = "PROBE"  # not yet in pyintellicenter
SINGLE_ATTR = "SINGLE"  # not yet in pyintellicenter

# Configuration option keys
CONF_KEEPALIVE_INTERVAL = "keepalive_interval"
CONF_RECONNECT_DELAY = "reconnect_delay"
CONF_TRANSPORT = "transport"

# Transport type values
TRANSPORT_TCP = "tcp"
TRANSPORT_WEBSOCKET = "websocket"
TransportType = Literal["tcp", "websocket"]

# Default values for configuration options
DEFAULT_KEEPALIVE_INTERVAL = 90  # seconds
DEFAULT_RECONNECT_DELAY = 30  # seconds
DEFAULT_TRANSPORT = "tcp"  # type: TransportType

# Minimum/maximum values for configuration options
MIN_KEEPALIVE_INTERVAL = 30
MAX_KEEPALIVE_INTERVAL = 300
MIN_RECONNECT_DELAY = 10
MAX_RECONNECT_DELAY = 120
