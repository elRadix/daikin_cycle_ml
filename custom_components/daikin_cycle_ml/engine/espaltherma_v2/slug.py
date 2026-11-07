"""ESPAltherma v2 (beta) slug helpers.

Replicates src/homeassistant.cpp::makeJsonKey() from the ESPAltherma
beta branch (PR #260, 2026 Q4):

    std::string makeJsonKey(const char *input) {
        std::string out;
        for (const char *p = input; *p; ++p) {
            unsigned char c = static_cast<unsigned char>(*p);
            if (std::isalnum(c))       out.push_back(std::tolower(c));
            else if (c == ' ')         out.push_back('_');
            // all other chars (. - ( ) : / _) are DROPPED
        }
        return out;
    }

Real examples (from @fransh47's EPRA12EAV3, 2026-11-06):
    "Operation Mode"                        -> operation_mode
    "I/U operation mode"                    -> iu_operation_mode
    "3way valve(On:DHW_Off:Space)"          -> 3way_valveondhwoffspace
    "Outdoor air temp.(R1T)"                -> outdoor_air_tempr1t
    "Inlet water temp.(R4T)"                -> inlet_water_tempr4t
    "Flow sensor (l/min)"                   -> flow_sensor_lmin
    "Leaving water temp. after BUH (R2T)"   -> leaving_water_temp_after_buh_r2t

Quirks documented in tests (R684):
    - `_` in input is dropped (not alnum, not space)
    - `.` `(` `)` `:` `/` `-` are dropped
    - Non-ASCII is dropped (C++ std::isalnum on unsigned char is ASCII)
    - Only spaces become `_`
"""
from __future__ import annotations

DEFAULT_PREFIX = "sensor.espaltherma_"


def _is_ascii_alnum(ch: str) -> bool:
    """ASCII-only alnum, mirroring C++ std::isalnum on unsigned char."""
    return ("0" <= ch <= "9") or ("a" <= ch <= "z") or ("A" <= ch <= "Z")


def make_json_key(label: str) -> str:
    """Mirror ESPAltherma's C++ makeJsonKey exactly."""
    out: list[str] = []
    for ch in label:
        if _is_ascii_alnum(ch):
            out.append(ch.lower())
        elif ch == " ":
            out.append("_")
    return "".join(out)


def entity_id_for(label: str, prefix: str = DEFAULT_PREFIX) -> str:
    """Full v2 entity_id for a canonical label, using makeJsonKey."""
    return f"{prefix}{make_json_key(label)}"
