"""
Alert Dispatcher Service
========================
Generates location-specific safety alerts in Nepali (text + synthesized voice)
and dispatches them via the configured mode.

MODES
-----
  mock  — Renders alerts locally; writes audio to /tmp. No real notifications sent.
  live  — Sends actual SMS/push notifications and uses AWS Polly for voice.
          REQUIRES explicit team sign-off before enabling.

Data mode labels are embedded in every alert payload.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

AlertMode = Literal["mock", "live"]
ALERT_MODE: AlertMode = os.getenv("ALERT_MODE", "mock")  # type: ignore[assignment]

# Nepali alert templates (simplified — expand with professional translations)
ALERT_TEMPLATES = {
    "HIGH": {
        "ne": (
            "⚠️ अत्यन्त उच्च बाढी जोखिम। तत्काल उच्च स्थानमा जानुहोस्। "
            "आफ्नो परिवार र पशुहरू लिएर सुरक्षित स्थानमा जानुहोस्।"
        ),
        "en": (
            "EXTREME FLOOD RISK. Evacuate to higher ground immediately. "
            "Take family and livestock to safe ground."
        ),
    },
    "MEDIUM": {
        "ne": (
            "⚠️ मध्यम बाढी जोखिम। सतर्क रहनुहोस् र स्थानीय अधिकारीहरूको निर्देशन पालना गर्नुहोस्।"
        ),
        "en": (
            "MODERATE FLOOD RISK. Stay alert and follow local authority guidance."
        ),
    },
    "LOW": {
        "ne": "ℹ️ कम बाढी जोखिम। नदी नजिक नजानुहोस्।",
        "en": "LOW FLOOD RISK. Avoid proximity to rivers.",
    },
}


@dataclass
class AlertPayload:
    """Represents a single alert for one zone."""
    zone_id: str
    risk_level: str
    text_ne: str
    text_en: str
    audio_path: str | None  # local path (mock) or S3 URI (live)
    data_mode: str
    alert_mode: str
    timestamp_utc: str


class AlertDispatcher:
    """Generates and (mock) dispatches flood alerts.

    Args:
        mode: "mock" for safe demo use; "live" requires team sign-off.
        voice_language: BCP-47 language tag for voice synthesis.
    """

    def __init__(
        self,
        mode: AlertMode = ALERT_MODE,
        voice_language: str = "ne-NP",
    ) -> None:
        if mode == "live":
            logger.warning(
                "ALERT DISPATCHER: live mode enabled. "
                "Ensure team sign-off has been obtained before proceeding."
            )
        self.mode = mode
        self.voice_language = voice_language

    def generate_alert(
        self,
        zone_id: str,
        risk_level: str,
        *,
        data_mode: str = "HISTORICAL",
        timestamp_utc: str = "unknown",
    ) -> AlertPayload:
        """Generate a text alert for a risk zone.

        Args:
            zone_id: Identifier for the geographic zone.
            risk_level: HIGH | MEDIUM | LOW.
            data_mode: HISTORICAL | SIMULATED | LIVE.
            timestamp_utc: ISO-8601 UTC timestamp.

        Returns:
            AlertPayload with text in Nepali and English.
        """
        template = ALERT_TEMPLATES.get(risk_level, ALERT_TEMPLATES["LOW"])
        text_ne = f"[{data_mode}] {template['ne']}"
        text_en = f"[{data_mode}] {template['en']}"

        audio_path = self._synthesise_voice(zone_id, text_ne, data_mode)

        return AlertPayload(
            zone_id=zone_id,
            risk_level=risk_level,
            text_ne=text_ne,
            text_en=text_en,
            audio_path=audio_path,
            data_mode=data_mode,
            alert_mode=self.mode,
            timestamp_utc=timestamp_utc,
        )

    def _synthesise_voice(
        self, zone_id: str, text: str, data_mode: str
    ) -> str | None:
        """Generate voice audio for the alert.

        In mock mode: writes a placeholder file (no actual synthesis).
        In live mode: calls AWS Polly and returns an S3 URI.
        """
        if self.mode == "mock":
            out = Path("/tmp") / f"alert_{zone_id}_{data_mode}.mp3"
            # In real implementation, call a TTS library or pre-record samples.
            out.write_text(
                f"[MOCK AUDIO PLACEHOLDER — {data_mode}] {text}", encoding="utf-8"
            )
            logger.info("Mock audio written to %s", out)
            return str(out)

        # live mode — AWS Polly
        import boto3  # noqa: PLC0415
        polly = boto3.client("polly")
        response = polly.synthesize_speech(
            Text=text,
            OutputFormat="mp3",
            VoiceId=os.getenv("AWS_POLLY_VOICE_ID", "Kajal"),
            LanguageCode=self.voice_language,
        )
        s3_key = f"alerts/audio/{zone_id}_{data_mode}.mp3"
        bucket = os.environ["S3_DATA_BUCKET"]
        import boto3 as _boto3  # noqa: PLC0415
        _boto3.client("s3").put_object(
            Bucket=bucket,
            Key=s3_key,
            Body=response["AudioStream"].read(),
            ContentType="audio/mpeg",
        )
        return f"s3://{bucket}/{s3_key}"

    def dispatch(self, payload: AlertPayload) -> dict:
        """Dispatch (or mock-dispatch) an alert.

        Args:
            payload: AlertPayload to send.

        Returns:
            Dispatch result metadata.
        """
        if self.mode == "mock":
            logger.info(
                "[MOCK DISPATCH] zone=%s level=%s data_mode=%s",
                payload.zone_id,
                payload.risk_level,
                payload.data_mode,
            )
            return {
                "status": "mock_dispatched",
                "zone_id": payload.zone_id,
                "risk_level": payload.risk_level,
                "data_mode": payload.data_mode,
                "alert_mode": "mock",
                "note": "No real notification sent. Demo mode only.",
            }

        # live dispatch logic (SNS, SMS, push) — implement before enabling live mode
        raise NotImplementedError(
            "Live dispatch not yet implemented. "
            "Obtain team sign-off and implement SNS/push integration."
        )
