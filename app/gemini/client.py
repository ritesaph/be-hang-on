import asyncio
import io
import wave

from google import genai
from google.genai import types
from google.genai.errors import APIError

from app.config import settings
from app.gemini.prompts import build_system_instruction
from app.gemini.schemas import SuspicionAnalysis

MODEL_NAME = "gemini-3.1-flash-lite"
MAX_RETRIES = 2
RETRYABLE_CODES = {429, 500, 502, 503, 504}

_client = genai.Client(api_key=settings.gemini_api_key)


class GeminiAnalysisError(Exception):
    pass


def _wrap_pcm_as_wav(
    pcm_bytes: bytes, sample_rate: int, channels: int, bytes_per_sample: int
) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(bytes_per_sample)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_bytes)
    return buffer.getvalue()


async def analyze_window(
    pcm_audio: bytes,
    rolling_context: str,
    sample_rate: int,
    channels: int,
    bytes_per_sample: int,
) -> SuspicionAnalysis:
    wav_bytes = _wrap_pcm_as_wav(pcm_audio, sample_rate, channels, bytes_per_sample)

    contents = [
        types.Part.from_bytes(data=wav_bytes, mime_type="audio/wav"),
        f"Ringkasan konteks sebelumnya: {rolling_context or '(belum ada)'}",
    ]
    config = types.GenerateContentConfig(
        system_instruction=build_system_instruction(),
        response_mime_type="application/json",
        response_schema=SuspicionAnalysis,
    )

    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = await _client.aio.models.generate_content(
                model=MODEL_NAME, contents=contents, config=config
            )
            return SuspicionAnalysis.model_validate_json(response.text)
        except APIError as exc:
            last_error = exc
            if exc.code not in RETRYABLE_CODES or attempt == MAX_RETRIES:
                break
            await asyncio.sleep(2**attempt)

    raise GeminiAnalysisError(str(last_error)) from last_error
