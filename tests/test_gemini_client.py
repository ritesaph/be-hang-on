import io
import wave

import pytest
from google.genai.errors import APIError

from app.gemini.client import GeminiAnalysisError, _wrap_pcm_as_wav, analyze_window
from app.gemini.schemas import SuspicionAnalysis


def _make_api_error(code: int) -> APIError:
    return APIError(code=code, response_json={"error": {"message": "boom"}})


async def _no_sleep(*args, **kwargs) -> None:
    return None


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


def test_wrap_pcm_as_wav_produces_valid_wav_header():
    pcm = b"\x00\x01" * 100

    wav_bytes = _wrap_pcm_as_wav(pcm, sample_rate=16000, channels=1, bytes_per_sample=2)

    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        assert wf.getframerate() == 16000
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.readframes(wf.getnframes()) == pcm


@pytest.mark.asyncio
async def test_analyze_window_parses_structured_response(monkeypatch):
    canned = SuspicionAnalysis(
        is_suspicious=True, confidence=0.9, reason="menyebut OTP", updated_context="ctx"
    )

    async def fake_generate_content(model, contents, config):
        return _FakeResponse(canned.model_dump_json())

    monkeypatch.setattr(
        "app.gemini.client._client.aio.models.generate_content", fake_generate_content
    )

    result = await analyze_window(
        pcm_audio=b"\x00\x00" * 100,
        rolling_context="",
        sample_rate=16000,
        channels=1,
        bytes_per_sample=2,
    )

    assert result == canned


@pytest.mark.asyncio
async def test_analyze_window_retries_on_retryable_error(monkeypatch):
    calls = {"count": 0}
    canned = SuspicionAnalysis(
        is_suspicious=False, confidence=0.1, reason="normal", updated_context="ctx"
    )

    async def fake_generate_content(model, contents, config):
        calls["count"] += 1
        if calls["count"] < 3:
            raise _make_api_error(429)
        return _FakeResponse(canned.model_dump_json())

    monkeypatch.setattr(
        "app.gemini.client._client.aio.models.generate_content", fake_generate_content
    )
    monkeypatch.setattr("app.gemini.client.asyncio.sleep", _no_sleep)

    result = await analyze_window(
        pcm_audio=b"\x00\x00" * 100,
        rolling_context="",
        sample_rate=16000,
        channels=1,
        bytes_per_sample=2,
    )

    assert calls["count"] == 3
    assert result == canned


@pytest.mark.asyncio
async def test_analyze_window_raises_after_exhausting_retries(monkeypatch):
    calls = {"count": 0}

    async def fake_generate_content(model, contents, config):
        calls["count"] += 1
        raise _make_api_error(503)

    monkeypatch.setattr(
        "app.gemini.client._client.aio.models.generate_content", fake_generate_content
    )
    monkeypatch.setattr("app.gemini.client.asyncio.sleep", _no_sleep)

    with pytest.raises(GeminiAnalysisError):
        await analyze_window(
            pcm_audio=b"\x00\x00" * 100,
            rolling_context="",
            sample_rate=16000,
            channels=1,
            bytes_per_sample=2,
        )

    assert calls["count"] == 3


@pytest.mark.asyncio
async def test_analyze_window_does_not_retry_non_retryable_error(monkeypatch):
    calls = {"count": 0}

    async def fake_generate_content(model, contents, config):
        calls["count"] += 1
        raise _make_api_error(404)

    monkeypatch.setattr(
        "app.gemini.client._client.aio.models.generate_content", fake_generate_content
    )

    with pytest.raises(GeminiAnalysisError):
        await analyze_window(
            pcm_audio=b"\x00\x00" * 100,
            rolling_context="",
            sample_rate=16000,
            channels=1,
            bytes_per_sample=2,
        )

    assert calls["count"] == 1
