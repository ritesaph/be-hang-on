WINDOW_SECONDS = 12
SAMPLE_RATE_HZ = 16000
BYTES_PER_SAMPLE = 2
CHANNELS = 1


class AudioSessionBuffer:
    def __init__(
        self,
        window_seconds: int = WINDOW_SECONDS,
        sample_rate: int = SAMPLE_RATE_HZ,
        bytes_per_sample: int = BYTES_PER_SAMPLE,
        channels: int = CHANNELS,
    ) -> None:
        self.sample_rate = sample_rate
        self.bytes_per_sample = bytes_per_sample
        self.channels = channels
        self._window_size_bytes = sample_rate * bytes_per_sample * channels * window_seconds
        self._buffer = bytearray()

    def add_chunk(self, chunk: bytes) -> None:
        self._buffer.extend(chunk)

    def has_full_window(self) -> bool:
        return len(self._buffer) >= self._window_size_bytes

    def pop_window(self) -> bytes:
        window = bytes(self._buffer[: self._window_size_bytes])
        del self._buffer[: self._window_size_bytes]
        return window

    def flush_remainder(self) -> bytes | None:
        if not self._buffer:
            return None
        remainder = bytes(self._buffer)
        self._buffer.clear()
        return remainder
