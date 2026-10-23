"""ThingSpeak continuous background alert monitor for HydroGuard.

Periodically fetches recent feeds from the configured ThingSpeak channel,
identifies genuinely new readings via entry IDs and timestamps, evaluates valid
water-quality readings against active thresholds, creates alerts for violations,
and resolves alerts when readings return to normal.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
import math
import os
from typing import Any, Callable, Mapping, Optional, Sequence
import uuid

import httpx
from sqlalchemy.orm import Session

from app.db.database import get_db_context
from app.db.repositories import (
    NodeRepository,
    RawTelemetryRepository,
    SensorReadingRepository,
    ThingSpeakMonitorRepository,
)
from ml.data.sensor_validation import (
    classify_observation,
    validate_parameter,
)
from app.services.alert_service import AlertService
from app.services.push_notification_service import PushNotificationService
import ml.services.thingspeak_service as thingspeak_service
from ml.services.thingspeak_service import (
    ThingSpeakConfig,
    ThingSpeakError,
    ThingSpeakInvalidChannel,
    ThingSpeakNotConfigured,
    ThingSpeakUnavailable,
    _coerce_value,
    _parse_timestamp,
    fetch_feeds,
    load_config_from_env,
)

logger = logging.getLogger("hydroguard.thingspeak_monitor")

DEFAULT_POLL_INTERVAL_SECONDS = 30.0
MIN_POLL_INTERVAL_SECONDS = 0.1
MAX_BACKOFF_SECONDS = 120.0


def _parse_entry_id(raw: Any) -> Optional[int]:
    """Parse an entry_id safely to int or None."""
    if raw is None:
        return None
    try:
        return int(raw)
    except (ValueError, TypeError):
        return None


def _feed_sort_key(feed: Mapping[str, Any]) -> tuple[datetime, int]:
    """Sort feeds chronologically oldest first by timestamp, then entry ID."""
    ts = _parse_timestamp(feed.get("created_at")) or datetime.min.replace(tzinfo=timezone.utc)
    entry_id = _parse_entry_id(feed.get("entry_id")) or 0
    return (ts, entry_id)


def _is_new_feed(
    feed: Mapping[str, Any],
    last_entry_id: Optional[int],
    last_feed_timestamp: Optional[datetime],
) -> bool:
    """Determine whether a feed is newer than the saved checkpoint.

    Entry ID is the primary discriminator when present. Feed timestamps are used
    as a fallback when entry IDs are absent.
    """
    feed_entry_id = _parse_entry_id(feed.get("entry_id"))
    feed_ts = _parse_timestamp(feed.get("created_at"))

    # Primary discriminator: entry_id
    if last_entry_id is not None and feed_entry_id is not None:
        return feed_entry_id > last_entry_id

    # Fallback discriminator: timestamp
    if last_feed_timestamp is not None and feed_ts is not None:
        if last_feed_timestamp.tzinfo is None:
            last_feed_timestamp = last_feed_timestamp.replace(tzinfo=timezone.utc)
        if feed_ts.tzinfo is None:
            feed_ts = feed_ts.replace(tzinfo=timezone.utc)
        return feed_ts > last_feed_timestamp

    # If checkpoint has neither entry_id nor timestamp, this is the first poll
    if last_entry_id is None and last_feed_timestamp is None:
        return True

    return False


def _resolve_poll_interval(environ: Optional[Mapping[str, str]] = None) -> float:
    """Validate and resolve the polling interval from environment."""
    env = os.environ if environ is None else environ
    raw = env.get("HYDROGUARD_THINGSPEAK_ALERT_POLL_SECONDS")
    if not raw or not raw.strip():
        return DEFAULT_POLL_INTERVAL_SECONDS

    try:
        val = float(raw.strip())
        if not math.isfinite(val) or val <= 0:
            logger.warning(
                "Invalid HYDROGUARD_THINGSPEAK_ALERT_POLL_SECONDS=%r (must be a positive number); using default %.1fs.",
                raw,
                DEFAULT_POLL_INTERVAL_SECONDS,
            )
            return DEFAULT_POLL_INTERVAL_SECONDS
        if val < MIN_POLL_INTERVAL_SECONDS:
            logger.warning(
                "HYDROGUARD_THINGSPEAK_ALERT_POLL_SECONDS=%.2f is below minimum %.2fs; clamping to %.2fs.",
                val,
                MIN_POLL_INTERVAL_SECONDS,
                MIN_POLL_INTERVAL_SECONDS,
            )
            return MIN_POLL_INTERVAL_SECONDS
        return val
    except ValueError:
        logger.warning(
            "Could not parse HYDROGUARD_THINGSPEAK_ALERT_POLL_SECONDS=%r as float; using default %.1fs.",
            raw,
            DEFAULT_POLL_INTERVAL_SECONDS,
        )
        return DEFAULT_POLL_INTERVAL_SECONDS


class ThingSpeakAlertMonitor:
    """Background service that periodically polls ThingSpeak for alert monitoring."""

    def __init__(
        self,
        poll_interval: Optional[float] = None,
        config: Optional[ThingSpeakConfig] = None,
        fetch_feeds_fn: Optional[Callable[..., list[Mapping[str, Any]]]] = None,
        http_client: Optional[httpx.Client] = None,
        max_backoff_seconds: float = MAX_BACKOFF_SECONDS,
    ):
        self._poll_interval = poll_interval
        self._config = config
        self._fetch_feeds_fn = fetch_feeds_fn
        self._http_client = http_client
        self._max_backoff_seconds = max_backoff_seconds

        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._is_running = False
        self._worker_id = f"worker-{uuid.uuid4().hex[:12]}"
        self._lock = asyncio.Lock()

    @property
    def is_running(self) -> bool:
        return self._is_running and self._task is not None and not self._task.done()

    @property
    def poll_interval(self) -> float:
        if self._poll_interval is not None:
            return self._poll_interval
        return _resolve_poll_interval()

    async def start(self) -> bool:
        """Start the background monitoring task.

        Returns:
            True if started, False if disabled or already running.
        """
        async with self._lock:
            if self.is_running:
                logger.debug("ThingSpeak alert monitor is already running.")
                return True

            # Check explicit opt-out
            if os.getenv("HYDROGUARD_DISABLE_THINGSPEAK_ALERT_MONITOR", "").strip().lower() in ("true", "1"):
                logger.info("ThingSpeak alert monitor is disabled by HYDROGUARD_DISABLE_THINGSPEAK_ALERT_MONITOR.")
                return False

            config = self._config or load_config_from_env()
            if not config.configured:
                logger.warning(
                    "ThingSpeak alert monitor disabled: HYDROGUARD_THINGSPEAK_CHANNEL_ID is not configured."
                )
                return False

            if not config.channel_id.isdigit():
                logger.warning(
                    "ThingSpeak alert monitor disabled: HYDROGUARD_THINGSPEAK_CHANNEL_ID must contain digits only."
                )
                return False

            self._stop_event.clear()
            self._is_running = True
            interval = self.poll_interval

            logger.info(
                "ThingSpeak alert monitor starting for channel '%s' (poll interval: %.1fs, worker: %s).",
                config.channel_id,
                interval,
                self._worker_id,
            )

            self._task = asyncio.create_task(self._run_loop(), name="thingspeak-alert-monitor")
            return True

    async def stop(self, timeout: float = 5.0) -> None:
        """Stop the background monitoring task cleanly."""
        async with self._lock:
            if not self._is_running and (self._task is None or self._task.done()):
                return

            logger.info("Stopping ThingSpeak alert monitor...")
            self._stop_event.set()
            self._is_running = False

            if self._task and not self._task.done():
                self._task.cancel()
                try:
                    await asyncio.wait_for(self._task, timeout=timeout)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
                except Exception as exc:
                    logger.error("Exception awaiting monitor task shutdown: %s", exc)

            self._task = None
            logger.info("ThingSpeak alert monitor stopped.")

    async def _run_loop(self) -> None:
        """Main polling loop with bounded backoff and cancellation handling."""
        consecutive_failures = 0

        while not self._stop_event.is_set():
            try:
                await self.poll_once()
                consecutive_failures = 0
            except asyncio.CancelledError:
                break
            except Exception as exc:
                consecutive_failures += 1
                backoff = min(
                    self._max_backoff_seconds,
                    self.poll_interval * (2 ** min(consecutive_failures - 1, 5)),
                )
                # Strip potential credentials or query strings from logged error
                err_msg = str(exc)
                if "api_key=" in err_msg:
                    err_msg = err_msg.split("api_key=")[0] + "[REDACTED]"
                logger.warning(
                    "ThingSpeak alert monitor poll failed (attempt %d): %s. Retrying in %.1fs.",
                    consecutive_failures,
                    err_msg,
                    backoff,
                )
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=backoff)
                    break
                except asyncio.TimeoutError:
                    continue

            # Sleep between successful polling cycles
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.poll_interval)
                break
            except asyncio.TimeoutError:
                pass

    async def poll_once(self) -> int:
        """Execute one complete polling iteration.

        Returns:
            Number of new feeds processed during this iteration.
        """
        config = self._config or load_config_from_env()
        if not config.configured or not config.channel_id.isdigit():
            return 0

        fetcher = self._fetch_feeds_fn or fetch_feeds

        # Non-blocking synchronous HTTP call in worker thread
        raw_feeds = await asyncio.to_thread(fetcher, config, client=self._http_client)
        if not raw_feeds:
            return 0

        # Execute database operations
        return await asyncio.to_thread(self._process_feeds_in_db, config, raw_feeds)

    def _process_feeds_in_db(
        self,
        config: ThingSpeakConfig,
        raw_feeds: Sequence[Mapping[str, Any]],
    ) -> int:
        """Process feeds synchronously inside a managed database session."""
        channel_id = config.channel_id
        thingspeak_node_id = f"thingspeak-{channel_id}"
        processed_count = 0

        with get_db_context() as db:
            # Ensure the node exists in nodes table for alert association
            NodeRepository.get_or_create(
                db, thingspeak_node_id, f"ThingSpeak Channel {channel_id}", "ThingSpeak"
            )

            # Coordinate via durable lease to avoid concurrent processing across instances/workers
            lease_acquired = ThingSpeakMonitorRepository.acquire_lease(
                db, channel_id, owner_id=self._worker_id, lease_seconds=60
            )
            if not lease_acquired:
                logger.debug(
                    "Channel %s is currently leased by another monitor worker; skipping poll.",
                    channel_id,
                )
                return 0

            try:
                checkpoint = ThingSpeakMonitorRepository.get_checkpoint(db, channel_id)
                last_entry_id = checkpoint.last_entry_id if checkpoint else None
                last_feed_timestamp = checkpoint.last_feed_timestamp if checkpoint else None

                # Sort feeds chronologically ascending (oldest first)
                sorted_feeds = sorted(raw_feeds, key=_feed_sort_key)

                # Filter genuinely new feeds
                new_feeds = [
                    feed
                    for feed in sorted_feeds
                    if _is_new_feed(feed, last_entry_id, last_feed_timestamp)
                ]

                if not new_feeds:
                    return 0

                logger.debug(
                    "Processing %d new feed(s) for channel %s in chronological order.",
                    len(new_feeds),
                    channel_id,
                )

                for feed in new_feeds:
                    feed_entry_id = _parse_entry_id(feed.get("entry_id"))
                    feed_ts = _parse_timestamp(feed.get("created_at"))

                    # Extract raw string values faithfully as received from ThingSpeak feed
                    param_to_field = {param.lower(): field for field, param in config.field_map.items()}
                    rgb_to_field = {colour.lower(): field for field, colour in config.rgb_field_map.items()}

                    def _extract_raw_str(fld: Optional[str]) -> Optional[str]:
                        if fld is not None and fld in feed and feed[fld] is not None:
                            return str(feed[fld]).strip()
                        return None

                    raw_ph_str = _extract_raw_str(param_to_field.get("ph"))
                    raw_tds_str = _extract_raw_str(param_to_field.get("tds"))
                    raw_turb_str = _extract_raw_str(param_to_field.get("turbidity"))
                    raw_temp_str = _extract_raw_str(param_to_field.get("temperature"))

                    raw_red_str = _extract_raw_str(rgb_to_field.get("red"))
                    raw_green_str = _extract_raw_str(rgb_to_field.get("green"))
                    raw_blue_str = _extract_raw_str(rgb_to_field.get("blue"))

                    # Run parameter-specific validation
                    val_ph = validate_parameter("pH", raw_ph_str)
                    val_tds = validate_parameter("TDS", raw_tds_str)
                    val_turb = validate_parameter("turbidity", raw_turb_str)
                    val_temp = validate_parameter("temperature", raw_temp_str)

                    param_results = {
                        "ph": val_ph,
                        "tds": val_tds,
                        "turbidity": val_turb,
                        "temperature": val_temp,
                    }
                    validation_results_dict = {k: v.to_dict() for k, v in param_results.items()}
                    overall_status, rejection_reason, is_normalizable = classify_observation(param_results)

                    # 1. Durably record raw telemetry observation first
                    try:
                        raw_obs, _ = RawTelemetryRepository.create_or_get(
                            db=db,
                            channel_id=channel_id,
                            entry_id=feed_entry_id,
                            source_timestamp=feed_ts,
                            source="THINGSPEAK",
                            raw_payload=dict(feed),
                            raw_ph=raw_ph_str,
                            raw_tds=raw_tds_str,
                            raw_turbidity=raw_turb_str,
                            raw_temperature=raw_temp_str,
                            raw_red=raw_red_str,
                            raw_green=raw_green_str,
                            raw_blue=raw_blue_str,
                            overall_status=overall_status,
                            validation_results=validation_results_dict,
                            validation_version="2.0.0",
                            rejection_reason=rejection_reason,
                            is_persisted_normalized=False,
                            processing_status="INGESTED",
                        )
                    except Exception as raw_exc:
                        logger.error(
                            "Failed to persist raw observation for channel %s (entry_id=%s): %s",
                            channel_id,
                            feed_entry_id,
                            raw_exc,
                        )
                        # Halt batch processing so checkpoint does not advance past unrecorded observation
                        break

                    # 2. Persist normalized SensorReading only when validation rules permit it
                    normalized_success = True
                    if is_normalizable and feed_ts is not None:
                        existing_reading = SensorReadingRepository.get_by_node_and_timestamp(
                            db, thingspeak_node_id, feed_ts
                        )
                        if not existing_reading:
                            try:
                                def _parse_rgb(val: Optional[str]) -> Optional[int]:
                                    if val is None:
                                        return None
                                    try:
                                        return int(float(val))
                                    except (ValueError, TypeError):
                                        return None

                                new_reading = SensorReadingRepository.create(
                                    db=db,
                                    node_id=thingspeak_node_id,
                                    timestamp=feed_ts,
                                    ph=float(val_ph.coerced_value),
                                    tds=float(val_tds.coerced_value),
                                    turbidity=float(val_turb.coerced_value),
                                    temperature=(
                                        float(val_temp.coerced_value)
                                        if val_temp.is_valid_for_model and val_temp.coerced_value is not None
                                        else None
                                    ),
                                    red=_parse_rgb(raw_red_str),
                                    green=_parse_rgb(raw_green_str),
                                    blue=_parse_rgb(raw_blue_str),
                                    source="THINGSPEAK",
                                )
                                raw_obs.is_persisted_normalized = True
                                raw_obs.normalized_reading_id = new_reading.id
                                raw_obs.processing_status = "PROCESSED_NORMALIZED"
                                db.commit()
                                logger.info(
                                    "Persisted ThingSpeak reading for %s (entry_id=%s, ts=%s).",
                                    thingspeak_node_id,
                                    feed_entry_id,
                                    feed_ts,
                                )
                            except Exception as persist_exc:
                                logger.warning(
                                    "Failed to persist reading for %s: %s",
                                    thingspeak_node_id,
                                    persist_exc,
                                )
                                raw_obs.processing_status = "NORMALIZATION_FAILED"
                                raw_obs.error_message = str(persist_exc)
                                db.commit()
                                normalized_success = False
                        else:
                            raw_obs.is_persisted_normalized = True
                            raw_obs.normalized_reading_id = existing_reading.id
                            raw_obs.processing_status = "PROCESSED_NORMALIZED"
                            db.commit()
                    else:
                        # Ineligible for normalized persistence (e.g. dropout, out-of-bounds, missing required field)
                        raw_obs.is_persisted_normalized = False
                        raw_obs.processing_status = "SKIPPED_INELIGIBLE"
                        db.commit()

                    # If eligible normalized write failed unexpectedly, halt so retry can occur without skipping
                    if not normalized_success:
                        logger.warning(
                            "Halting batch at entry_id=%s due to normalized persistence failure; checkpoint will not advance.",
                            feed_entry_id,
                        )
                        break

                    # 3. Alert evaluation & auto-resolution (only with values valid for alerts)
                    alerts: list[Alert] = []
                    reading_for_alerts: dict[str, Any] = {"timestamp": feed_ts}
                    if val_ph.is_valid_for_alerts and val_ph.coerced_value is not None:
                        reading_for_alerts["ph"] = val_ph.coerced_value
                    if val_tds.is_valid_for_alerts and val_tds.coerced_value is not None:
                        reading_for_alerts["tds"] = val_tds.coerced_value
                    if val_turb.is_valid_for_alerts and val_turb.coerced_value is not None:
                        reading_for_alerts["turbidity"] = val_turb.coerced_value
                    if val_temp.is_valid_for_alerts and val_temp.coerced_value is not None:
                        reading_for_alerts["temperature"] = val_temp.coerced_value

                    has_alert_parameters = any(
                        k in reading_for_alerts for k in ("ph", "tds", "turbidity", "temperature")
                    )
                    if has_alert_parameters:
                        alerts = AlertService.evaluate_reading_for_alerts(
                            db, thingspeak_node_id, reading_for_alerts
                        )
                        if alerts:
                            logger.info(
                                "Created %d alert(s) for node %s from ThingSpeak feed (entry_id=%s).",
                                len(alerts),
                                thingspeak_node_id,
                                feed_entry_id,
                            )

                        resolved = AlertService.check_and_resolve_alerts(
                            db, thingspeak_node_id, reading_for_alerts
                        )
                        if resolved > 0:
                            logger.info(
                                "Auto-resolved %d alert(s) for node %s from ThingSpeak feed (entry_id=%s).",
                                resolved,
                                thingspeak_node_id,
                                feed_entry_id,
                            )

                    # 4. Advance checkpoint to this feed
                    last_entry_id = feed_entry_id if feed_entry_id is not None else last_entry_id
                    last_feed_timestamp = feed_ts if feed_ts is not None else last_feed_timestamp

                    ThingSpeakMonitorRepository.update_checkpoint(
                        db=db,
                        channel_id=channel_id,
                        last_entry_id=last_entry_id,
                        last_feed_timestamp=last_feed_timestamp,
                    )
                    db.commit()
                    processed_count += 1

                    # 5. Dispatch push notifications for newly committed alerts
                    if alerts:
                        for new_alert in alerts:
                            try:
                                PushNotificationService.notify_alert_created(db, new_alert)
                            except Exception as push_err:
                                logger.warning(
                                    "Failed to dispatch push notification for alert %s: %s",
                                    getattr(new_alert, "id", None),
                                    push_err,
                                )

            finally:
                # Release lease
                try:
                    ThingSpeakMonitorRepository.release_lease(db, channel_id, owner_id=self._worker_id)
                except Exception as exc:
                    logger.debug("Error releasing monitor lease: %s", exc)

        return processed_count


# Global singleton instance
_global_monitor: Optional[ThingSpeakAlertMonitor] = None


def get_alert_monitor() -> ThingSpeakAlertMonitor:
    """Get or create the global ThingSpeakAlertMonitor instance."""
    global _global_monitor
    if _global_monitor is None:
        _global_monitor = ThingSpeakAlertMonitor()
    return _global_monitor
