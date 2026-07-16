from app.calls.audio_buffer import AudioSessionBuffer


def _buffer(window_seconds: int = 1, sample_rate: int = 100) -> AudioSessionBuffer:
    return AudioSessionBuffer(
        window_seconds=window_seconds, sample_rate=sample_rate, bytes_per_sample=2, channels=1
    )


def test_no_full_window_when_empty():
    buf = _buffer()
    assert buf.has_full_window() is False


def test_full_window_below_threshold():
    buf = _buffer(window_seconds=1, sample_rate=100)
    buf.add_chunk(b"\x00" * 100)
    assert buf.has_full_window() is False


def test_full_window_at_threshold():
    buf = _buffer(window_seconds=1, sample_rate=100)
    buf.add_chunk(b"\x00" * 200)
    assert buf.has_full_window() is True


def test_pop_window_returns_exact_size_and_drains_buffer():
    buf = _buffer(window_seconds=1, sample_rate=100)
    buf.add_chunk(b"\x01" * 200)

    window = buf.pop_window()

    assert len(window) == 200
    assert buf.has_full_window() is False


def test_pop_window_keeps_overflow_for_next_window():
    buf = _buffer(window_seconds=1, sample_rate=100)
    buf.add_chunk(b"\x01" * 250)

    first = buf.pop_window()
    assert len(first) == 200
    assert buf.has_full_window() is False

    buf.add_chunk(b"\x02" * 150)
    assert buf.has_full_window() is True
    second = buf.pop_window()
    assert len(second) == 200


def test_chunks_can_arrive_in_small_pieces():
    buf = _buffer(window_seconds=1, sample_rate=100)
    for _ in range(200):
        buf.add_chunk(b"\x00")

    assert buf.has_full_window() is True


def test_flush_remainder_returns_none_when_empty():
    buf = _buffer()
    assert buf.flush_remainder() is None


def test_flush_remainder_returns_partial_data_and_clears():
    buf = _buffer(window_seconds=1, sample_rate=100)
    buf.add_chunk(b"\x03" * 50)

    remainder = buf.flush_remainder()

    assert remainder == b"\x03" * 50
    assert buf.flush_remainder() is None
