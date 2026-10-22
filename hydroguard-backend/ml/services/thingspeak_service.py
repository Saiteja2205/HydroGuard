"""ThingSpeak ingestion for HydroGuard.

Fetches the most recent observations from a ThingSpeak channel and shapes them
into the (window, 5) contract the forecasting models require.

ThingSpeak returns one JSON object per feed with ``field1``..``field5`` plus a
``created_at`` string. A field is absent or empty when the device did not log
that measurement for the interval, which is the normal case for a cold start or
a sensor hiccup. Those gaps are handled explicitly and *reported*, never hidden:

* A gap inside the available range is filled **causally** -- each missing value
  takes the most recent earlier observed value for that field. Nothing from the
  future is used, so a gap cannot leak information forward into the window.
* If the channel has returned fewer feeds than the model window, the missing
  leading rows are padded by repeating the first available reading for each
  field. This is a deliberate cold-start convenience and is counted in
  ``padded_rows`` so a caller can see how much of the window is synthetic.

Both counts are returned with the data rather than being silently absorbed, so
the API can disclose how much of a forecast window was measured versus carried
forward. Nothing here fabricates a measurement: an out-of-range value is
treated as missing (and therefore filled from an earlier real reading), exactly
as ``ml.data.validator`` already does for training data.

Configuration comes from the environment:

* ``HYDROGUARD_THINGSPEAK_CHANNEL_ID``  - required to fetch (digits only)
* ``HYDROGUARD_THINGSPEAK_READ_API_KEY`` - optional; needed for private channels
* ``HYDROGUARD_THINGSPEAK_BASE_URL``     - defaults to the public API host
* ``HYDROGUARD_THINGSPEAK_RESULTS``      - feed count to request, default 30
* ``HYDROGUARD_THINGSPEAK_TIMEOUT_SECONDS`` - per-request budget, default 10
* ``HYDROGUARD_THINGSPEAK_RGB_FIELD_MAP`` - optional JSON mapping field names to
  "red"/"green"/"blue"/"clear" for raw RGB sensor counts (fields 6-9 by default)
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence

import httpx

from ml.data.validator import PARAMETERS, VALID_RANGES

# ThingSpeak assigns fields to a channel in order. The HydroGuard channel logs
# the four modelled water-quality parameters on fields 1-4, and RGB colour
# sensor readings on fields 5-7. Field 8 is a status flag (0=normal, 1=abnormal).
# Field 5 is Red, field 6 is Green, field 7 is Blue. Field 8 is a status flag.
# Field 9 (clear) does not exist on this hardware.
# Kept as an explicit table so a channel that logs a different order is a
# one-line configuration change rather than a rewrite.
DEFAULT_FIELD_MAP: dict[str, str] = {
    "field1": PARAMETERS[0],  # pH
    "field2": PARAMETERS[1],  # TDS
    "field3": PARAMETERS[2],  # turbidity
    "field4": PARAMETERS[3],  # temperature
    # field5 is Red (RGB), not a modelled parameter
}

# Optional RGB field mapping for channels that log raw sensor counts.
# These are NOT fed into the ML models; they are passed through for
# visualization only. Values are 0-100 relative intensity percentages.
DEFAULT_RGB_FIELD_MAP: dict[str, str] = {
    "field5": "red",
    "field6": "green",
    "field7": "blue",
    # field8 is status (0=normal, 1=abnormal), not a colour channel
    # field9 (clear) does not exist on this hardware
}

DEFAULT_BASE_URL = "https://api.thingspeak.com"
DEFAULT_RESULTS = 30
DEFAULT_TIMEOUT_SECONDS = 10.0

# ThingSpeak's own feed timestamps look like "2026-10-14 03:44:14 UTC".
_THINGSPEAK_TIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S %Z",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S%z",
)


class ThingSpeakError(RuntimeError):
    """Base class for ThingSpeak ingestion failures."""


class ThingSpeakNotConfigured(ThingSpeakError):
    """No channel id is configured, so no fetch can be attempted."""


class ThingSpeakInvalidChannel(ThingSpeakError):
    """The configured channel id is not a valid ThingSpeak identifier."""


class ThingSpeakUnavailable(ThingSpeakError):
    """The channel could not be read (network failure, timeout, or bad payload)."""


@dataclass(frozen=True)
class ThingSpeakConfig:
    """Resolved ThingSpeak settings. Values are read once per fetch."""

    channel_id: str
    read_api_key: str = ""
    base_url: str = DEFAULT_BASE_URL
    results: int = DEFAULT_RESULTS
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    field_map: Mapping[str, str] = field(default_factory=lambda: dict(DEFAULT_FIELD_MAP))
    rgb_field_map: Mapping[str, str] = field(default_factory=lambda: dict(DEFAULT_RGB_FIELD_MAP))

    @property
    def configured(self) -> bool:
        return bool(self.channel_id)


@dataclass(frozen=True)
class ThingSpeakWindow:
    """A ready-to-forecast window plus the honesty metadata about its gaps.

    ``values`` is ordered oldest-first and always exactly ``window_size`` rows
    of FOUR floats (pH, TDS, turbidity, temperature), which is the shape the
    models require for the core water-quality parameters. ``source`` records
    where the rows came from, while ``forward_filled`` / ``padded_rows`` /
    ``unobserved_parameters`` say how much of the window was carried forward
    rather than measured, so a caller can tell observed data from fill.

    The optical_colour_index is NOT directly measured by the hardware; it is a
    derived quantity that would need to be computed from RGB values. Since no
    validated formula exists, it is NOT fabricated here. The 4 core parameters
    are provided for forecasting; the optical_colour_index is available
    separately via ``has_optical_colour_index`` and ``optical_colour_index``.

    Raw RGB sensor counts (if present in the channel) are carried separately
    in ``rgb_values`` and are NOT included in ``values`` (the ML feature array).
    """

    values: tuple[tuple[float, ...], ...]
    timestamps: tuple[datetime | None, ...]
    latest_timestamp: datetime | None
    forward_filled: int
    padded_rows: int
    observed_rows: int
    source: str = "THINGSPEAK"
    channel_id: str = ""
    missing_by_parameter: Mapping[str, int] = field(default_factory=dict)
    unobserved_parameters: tuple[str, ...] = ()
    leading_filled: int = 0
    # Raw RGB sensor counts per row: tuple of (red, green, blue, clear) or None
    rgb_values: tuple[tuple[int | None, int | None, int | None, int | None], ...] = ()
    latest_entry_id: Optional[int] = None
    latest_status_flag: Optional[int] = None


    @property
    def window_size(self) -> int:
        return len(self.values)

    @property
    def has_optical_colour_index(self) -> bool:
        """Whether optical_colour_index is available (always False for ThingSpeak)."""
        return False

    @property
    def optical_colour_index(self) -> Optional[float]:
        """Optical colour index value (always None for ThingSpeak - no validated formula)."""
        return None


def load_config_from_env(environ: Mapping[str, str] | None = None) -> ThingSpeakConfig:
    """Build a config from the environment without raising on a cold start.

    A missing channel id yields ``configured == False`` so the caller can
    answer "not configured" truthfully instead of crashing on import. A channel
    id that is present but malformed is rejected immediately, because accepting
    it would let a bad value reach the request URL.
    """
    env = os.environ if environ is None else environ

    channel_id = (env.get("HYDROGUARD_THINGSPEAK_CHANNEL_ID") or "").strip()
    read_api_key = (env.get("HYDROGUARD_THINGSPEAK_READ_API_KEY") or "").strip()
    base_url = (env.get("HYDROGUARD_THINGSPEAK_BASE_URL") or DEFAULT_BASE_URL).strip().rstrip("/")

    raw_results = (env.get("HYDROGUARD_THINGSPEAK_RESULTS") or "").strip()
    try:
        results = int(raw_results) if raw_results else DEFAULT_RESULTS
    except ValueError:
        results = DEFAULT_RESULTS

    raw_timeout = (env.get("HYDROGUARD_THINGSPEAK_TIMEOUT_SECONDS") or "").strip()
    try:
        timeout_seconds = float(raw_timeout) if raw_timeout else DEFAULT_TIMEOUT_SECONDS
    except ValueError:
        timeout_seconds = DEFAULT_TIMEOUT_SECONDS

    # Optional RGB field map override (JSON string mapping field names to
    # "red"/"green"/"blue"/"clear"). If not provided, uses DEFAULT_RGB_FIELD_MAP.
    rgb_field_map = dict(DEFAULT_RGB_FIELD_MAP)
    raw_rgb_map = (env.get("HYDROGUARD_THINGSPEAK_RGB_FIELD_MAP") or "").strip()
    if raw_rgb_map:
        try:
            import json
            parsed = json.loads(raw_rgb_map)
            if isinstance(parsed, dict):
                rgb_field_map = {str(k): str(v) for k, v in parsed.items()}
        except (json.JSONDecodeError, TypeError):
            # Invalid JSON falls back to default mapping
            pass

    return ThingSpeakConfig(
        channel_id=channel_id,
        read_api_key=read_api_key,
        base_url=base_url or DEFAULT_BASE_URL,
        results=max(results, DEFAULT_RESULTS),
        timeout_seconds=timeout_seconds if timeout_seconds > 0 else DEFAULT_TIMEOUT_SECONDS,
        rgb_field_map=rgb_field_map,
    )


def build_feed_url(config: ThingSpeakConfig) -> str:
    """Build the feeds URL, validating the channel id first.

    The channel id is interpolated into a URL path, so it is restricted to
    digits. ThingSpeak channel ids are numeric, and rejecting anything else
    prevents a crafted value from redirecting the request to another path or
    host on the ThingSpeak API.
    """
    if not config.configured:
        raise ThingSpeakNotConfigured(
            "HYDROGUARD_THINGSPEAK_CHANNEL_ID is not set, so no ThingSpeak channel can be read."
        )
    if not config.channel_id.isdigit():
        raise ThingSpeakInvalidChannel(
            "The configured ThingSpeak channel id must contain digits only."
        )

    url = f"{config.base_url}/channels/{config.channel_id}/feeds.json"
    query = f"results={max(1, config.results)}"
    if config.read_api_key:
        # Never logged: the key is a credential and must not reach log output.
        query = f"{query}&api_key={config.read_api_key}"
    return f"{url}?{query}"


def _parse_timestamp(raw: Any) -> datetime | None:
    """Parse a ThingSpeak ``created_at`` into timezone-aware UTC, or None.

    A feed with an unreadable timestamp is not discarded -- its values are
    still usable for the window -- but it cannot be presented as the
    observation time, so it reports None instead of a fabricated instant.
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    for fmt in _THINGSPEAK_TIME_FORMATS:
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    # Last resort: let fromisoformat try, but only if it yields an aware value.
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _coerce_value(raw: Any, parameter: str) -> float | None:
    """Convert a ThingSpeak field to a float, or None if unusable.

    An empty/absent field is missing. A non-numeric value is missing. An
    out-of-range value is missing too: passing a physically impossible reading
    to the models would be worse than carrying forward an earlier real one, and
    this mirrors the validator's treatment of training data.
    """
    if raw is None:
        return None
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        try:
            value = float(text)
        except ValueError:
            return None
    elif isinstance(raw, (int, float)):
        value = float(raw)
    else:
        return None

    if value != value:  # NaN
        return None

    # Distinguish physical aqueous observations from open-circuit / 0V ADC sensor dropouts
    if parameter == 'pH' and value <= 0.05:
        # Sensor dropout: 0V analog ADC reading / disconnected pH probe
        return None
    if parameter in ('temperature', 'temp') and value <= 0.5:
        # Sensor dropout: 0V analog ADC reading / disconnected temp probe
        return None

    bounds = VALID_RANGES.get(parameter)
    if bounds is not None:
        lower, upper = bounds
        if value < lower or value > upper:
            return None
    return value


def parse_feeds(
    feeds: Sequence[Mapping[str, Any]],
    config: ThingSpeakConfig,
) -> ThingSpeakWindow:
    """Turn raw ThingSpeak feeds into a validated, gap-filled model window.

    The result is always exactly ``config.results`` rows even when the channel
    returned nothing at all, so the caller never has to special-case a short
    response. When there are genuinely no observations the window is filled
    from the configured midpoints and ``observed_rows`` is 0, which lets the
    API refuse to present such a window as sensor data.

    ML parameters (pH, TDS, turbidity, temperature) are extracted from fields 1-4
    per the field_map and gap-filled for the model. The optical_colour_index is
    NOT directly measured by the hardware; it is a derived quantity that would
    need to be computed from RGB values. Since no validated formula exists,
    it is NOT fabricated here. The 4 core parameters are extracted from fields
    1-4 and gap-filled for the model. Raw RGB sensor readings (if present on
    fields 5-7 per rgb_field_map) are extracted separately and NOT gap-filled
    or fed into the ML models.
    """
    window_size = max(1, config.results)
    field_map = config.field_map
    rgb_field_map = config.rgb_field_map

    # Verified against the live ThingSpeak API: the feeds endpoint returns
    # entries in ASCENDING chronological order (oldest first, newest last),
    # e.g. 12:08:16, 12:20:18, ... 12:56:15. Reversing here would feed the
    # models a backwards window, so the order is preserved as-is.
    ordered = list(feeds)

    timestamps: list[datetime | None] = []
    # columns[param][row_index] -> value or None
    # Only the 4 core parameters that are directly measured by the hardware
    ML_PARAMETERS = ("pH", "TDS", "turbidity", "temperature")
    columns: dict[str, list[float | None]] = {param: [] for param in ML_PARAMETERS}
    # rgb_columns[colour][row_index] -> value or None
    rgb_columns: dict[str, list[int | None]] = {col: [] for col in ("red", "green", "blue", "clear")}

    for feed in ordered:
        timestamps.append(_parse_timestamp(feed.get("created_at")))
        for field_name, parameter in field_map.items():
            if parameter not in columns:
                continue
            columns[parameter].append(_coerce_value(feed.get(field_name), parameter))
        for field_name, colour in rgb_field_map.items():
            if colour not in rgb_columns:
                continue
            raw = feed.get(field_name)
            if raw is None:
                rgb_columns[colour].append(None)
            elif isinstance(raw, str):
                text = raw.strip()
                if not text:
                    rgb_columns[colour].append(None)
                else:
                    try:
                        rgb_columns[colour].append(int(float(text)))
                    except ValueError:
                        rgb_columns[colour].append(None)
            elif isinstance(raw, (int, float)):
                rgb_columns[colour].append(int(raw))
            else:
                rgb_columns[colour].append(None)

    observed_rows = len(ordered)
    missing_by_parameter = {
        param: sum(1 for value in values if value is None)
        for param, values in columns.items()
    }

    forward_filled = 0  # cells carrying an earlier observed value (causal)
    leading_filled = 0  # head cells repeating the first observed value
    unobserved_parameters: list[str] = []  # fields the channel never reported

    for parameter, values in columns.items():
        # Causal forward fill: walk oldest-to-newest carrying the last observed
        # value for this field. Nothing from a later row is used to fill an
        # earlier one, so the fill cannot leak the future into the window.
        last_seen: float | None = None
        for index, value in enumerate(values):
            if value is None:
                if last_seen is not None:
                    values[index] = last_seen
                    forward_filled += 1
            else:
                last_seen = value

        # Leading gaps: the field is absent at the head of the window, so there
        # is no earlier reading to carry forward and a later one would leak the
        # future. Repeat this field's first observed value instead -- the
        # cold-start rule. Counted apart from the causal fills above.
        first_available = next((v for v in values if v is not None), None)
        if first_available is None:
            # The channel never reported this field in the whole response, so
            # there is nothing to repeat. Fill with the documented range
            # midpoint (never a fabricated measurement) and remember which
            # fields are affected so the caller can refuse to present them as
            # observed sensor data.
            bounds = VALID_RANGES.get(parameter)
            midpoint = (bounds[0] + bounds[1]) / 2.0 if bounds else 0.0
            for index in range(len(values)):
                values[index] = midpoint
            unobserved_parameters.append(parameter)
            continue
        for index, value in enumerate(values):
            if value is None:
                values[index] = first_available
                leading_filled += 1

    padded_rows = 0
    if observed_rows < window_size:
        padded_rows = window_size - observed_rows
        # Leading padding for a short channel history. Each field repeats its
        # first available reading, per the cold-start contract. The fill loop
        # above removed every None from columns that had at least one row; a
        # channel that returned NO feeds at all still has empty columns, so
        # those are padded with the documented range midpoint instead.
        for parameter, values in columns.items():
            if values:
                values[:0] = [values[0]] * padded_rows
            else:
                bounds = VALID_RANGES.get(parameter)
                midpoint = (bounds[0] + bounds[1]) / 2.0 if bounds else 0.0
                values[:0] = [midpoint] * padded_rows
        timestamps[:0] = [None] * padded_rows

    # Trim to exactly the window size (the channel may return more than asked).
    for parameter in columns:
        columns[parameter] = columns[parameter][-window_size:]
    timestamps = timestamps[-window_size:]

    # Build the 4-parameter ML feature array (no optical_colour_index)
    ML_PARAMETERS = ("pH", "TDS", "turbidity", "temperature")
    values = tuple(
        tuple(float(columns[param][row]) for param in ("pH", "TDS", "turbidity", "temperature"))
        for row in range(window_size)
    )

    # Build RGB values tuple (no gap-filling for raw sensor counts)
    rgb_values = tuple(
        tuple(
            rgb_columns[col][row] if row < len(rgb_columns[col]) else None
            for col in ("red", "green", "blue", "clear")
        )
        for row in range(window_size)
    )

    latest_timestamp = next((ts for ts in reversed(timestamps) if ts is not None), None)

    latest_entry_id = None
    latest_status_flag = None
    if ordered:
        newest_feed = ordered[-1]
        try:
            latest_entry_id = int(newest_feed.get("entry_id"))
        except (ValueError, TypeError):
            latest_entry_id = None
        raw_status = newest_feed.get("field8")
        if raw_status is not None:
            try:
                latest_status_flag = int(float(str(raw_status).strip()))
            except (ValueError, TypeError):
                latest_status_flag = None

    return ThingSpeakWindow(
        values=values,
        timestamps=tuple(timestamps),
        latest_timestamp=latest_timestamp,
        forward_filled=forward_filled,
        padded_rows=padded_rows,
        observed_rows=min(observed_rows, window_size),
        source="THINGSPEAK",
        channel_id=config.channel_id,
        missing_by_parameter=missing_by_parameter,
        unobserved_parameters=tuple(unobserved_parameters),
        leading_filled=leading_filled,
        rgb_values=rgb_values,
        latest_entry_id=latest_entry_id,
        latest_status_flag=latest_status_flag,
    )


def parse_history_readings(
    feeds: Sequence[Mapping[str, Any]],
    config: ThingSpeakConfig,
) -> list[dict[str, Any]]:
    """Convert raw ThingSpeak feeds into chronological historical reading dicts."""
    readings: list[dict[str, Any]] = []
    field_map = config.field_map
    rgb_field_map = config.rgb_field_map

    for feed in feeds:
        ts = _parse_timestamp(feed.get("created_at"))
        iso_ts = ts.strftime("%Y-%m-%dT%H:%M:%SZ") if ts is not None else None
        if not iso_ts:
            continue
        try:
            entry_id = int(feed.get("entry_id"))
        except (ValueError, TypeError):
            entry_id = None

        row: dict[str, Any] = {
            "timestamp": iso_ts,
            "entry_id": entry_id,
            "source": "THINGSPEAK",
        }

        # Modelled parameters (pH, TDS, turbidity, temperature)
        for field_name, parameter in field_map.items():
            val = _coerce_value(feed.get(field_name), parameter)
            param_key = parameter.lower()
            row[param_key] = val
            if parameter == "pH":
                row["pH"] = val
            elif parameter == "TDS":
                row["TDS"] = val

        # RGB channels
        for field_name, colour in rgb_field_map.items():
            raw_rgb = feed.get(field_name)
            if raw_rgb is not None:
                try:
                    row[colour] = int(float(str(raw_rgb).strip()))
                except (ValueError, TypeError):
                    row[colour] = None
            else:
                row[colour] = None

        # Field 8 status flag
        raw_status = feed.get("field8")
        if raw_status is not None:
            try:
                row["status_flag"] = int(float(str(raw_status).strip()))
            except (ValueError, TypeError):
                row["status_flag"] = None
        else:
            row["status_flag"] = None

        readings.append(row)

    # Sort ascending chronologically
    readings.sort(key=lambda r: r.get("timestamp") or "")
    return readings



def fetch_feeds(
    config: ThingSpeakConfig,
    client: httpx.Client | None = None,
    max_retries: int = 3,
    retry_delay_seconds: float = 0.5,
) -> list[Mapping[str, Any]]:
    """Fetch the channel's recent feeds and return the raw feed mappings.

    Supports bounded retries with exponential backoff on transient network
    or timeout failures. ``client`` may be injected so tests can exercise
    the parsing and error paths without touching the network.
    """
    url = build_feed_url(config)

    owns_client = client is None
    last_error: Exception | None = None
    response: httpx.Response | None = None

    for attempt in range(1, max_retries + 1):
        http_client = client if client is not None else httpx.Client(timeout=config.timeout_seconds)
        try:
            response = http_client.get(url)
            # Deterministic status codes: return immediately without retrying
            if response.status_code in (200, 401, 403, 404):
                break
            # Server errors (5xx): retry with backoff if attempts remain
            if attempt < max_retries:
                time.sleep(retry_delay_seconds * (2 ** (attempt - 1)))
                continue
        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            last_error = exc
            if attempt < max_retries:
                time.sleep(retry_delay_seconds * (2 ** (attempt - 1)))
                continue
        finally:
            if owns_client:
                http_client.close()

    if response is None:
        if isinstance(last_error, httpx.TimeoutException):
            raise ThingSpeakUnavailable(
                f"The ThingSpeak channel request exceeded {config.timeout_seconds:g}s."
            ) from last_error
        raise ThingSpeakUnavailable("The ThingSpeak channel could not be reached.") from last_error

    if response.status_code == 404:
        raise ThingSpeakUnavailable("The configured ThingSpeak channel was not found.")
    if response.status_code in (401, 403):
        raise ThingSpeakUnavailable(
            "ThingSpeak rejected the request; a private channel needs a read API key."
        )
    if response.status_code != 200:
        raise ThingSpeakUnavailable(
            f"ThingSpeak returned HTTP {response.status_code} for the channel feed."
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise ThingSpeakUnavailable("ThingSpeak returned a non-JSON response.") from exc

    feeds = payload.get("feeds") if isinstance(payload, Mapping) else None
    if not isinstance(feeds, list):
        raise ThingSpeakUnavailable("The ThingSpeak response did not contain a feed list.")
    return [feed for feed in feeds if isinstance(feed, Mapping)]


def fetch_window(
    config: ThingSpeakConfig | None = None,
    client: httpx.Client | None = None,
) -> ThingSpeakWindow:
    """Fetch the channel and return a validated window ready for inference."""
    resolved = config or load_config_from_env()
    return parse_feeds(fetch_feeds(resolved, client=client), resolved)


def create_thingspeak_fetcher(
    environ: Mapping[str, str] | None = None,
    client_factory: Callable[[], httpx.Client] | None = None,
) -> Callable[[], ThingSpeakWindow]:
    """Build a zero-argument fetcher bound to one environment snapshot.

    Capturing the environment at construction keeps the configuration
    resolution out of the request path, so a malformed value surfaces at
    startup rather than on the first mobile call.
    """
    config = load_config_from_env(environ)

    def _fetch() -> ThingSpeakWindow:
        if not config.configured:
            raise ThingSpeakNotConfigured(
                "HYDROGUARD_THINGSPEAK_CHANNEL_ID is not set, so no ThingSpeak channel can be read."
            )
        client = client_factory() if client_factory else None
        return fetch_window(config, client=client)

    return _fetch