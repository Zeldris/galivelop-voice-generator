"""Waveform peaks of a WAV file (stdlib ``wave`` only). The UI simulator (``ui/mock/api-mock.js``) copies these rules
exactly, and a parity test keeps them equal.

Rules: ``n`` buckets over the L frames (bucket i spans frames ``i*L//n`` to ``(i+1)*L//n``); the value of a sample is the
largest absolute value among its channels, over full scale ``2**(8*width-1)``; a peak is ``max/scale`` rounded half-up to 3
decimals, capped at 1.0; an empty bucket (L < n) is 0."""
import wave

DEFAULT_N = 400
MIN_N = 16
MAX_N = 2000
_CHUNK_FRAMES = 65536


class PeaksError(ValueError):
    """The file is not a PCM WAV that ``wave`` can read (floating-point WAVs included)."""


def _check_n(n):
    if isinstance(n, bool) or not isinstance(n, int) or not MIN_N <= n <= MAX_N:
        raise ValueError(f"n must be an integer between {MIN_N} and {MAX_N}, got {n!r}")


def _samples(data, width):
    """Absolute value of every sample in a block of little-endian PCM bytes."""
    if width == 1:
        return [abs(b - 128) for b in data]
    return [abs(int.from_bytes(data[i:i + width], "little", signed=True)) for i in range(0, len(data), width)]


def peaks(path, n=DEFAULT_N):
    """``{"peaks": [float, ...] (n values), "audioMs": int}`` of the WAV at ``path``."""
    _check_n(n)
    try:
        with wave.open(str(path), "rb") as w:
            width, chans, rate, total = w.getsampwidth(), w.getnchannels(), w.getframerate(), w.getnframes()
            if not 1 <= width <= 4 or chans < 1 or rate < 1:
                raise PeaksError(f"{path}: unsupported WAV format")
            maxes = [0] * n
            pos = 0  # index of the next frame to read
            bucket = 0
            while pos < total:
                data = w.readframes(min(_CHUNK_FRAMES, total - pos))
                got = len(data) // (width * chans)
                if got == 0:
                    break  # truncated file: stop at what is there
                vals = _samples(data[:got * width * chans], width)
                for f in range(got):
                    frame = pos + f
                    while frame >= (bucket + 1) * total // n:
                        bucket += 1
                    m = max(vals[f * chans:(f + 1) * chans])
                    if m > maxes[bucket]:
                        maxes[bucket] = m
                pos += got
    except (wave.Error, EOFError) as e:
        raise PeaksError(f"{path}: cannot read the WAV ({e})") from e
    except OSError as e:
        raise PeaksError(f"{path}: cannot read the file ({e})") from e
    scale = 2 ** (8 * width - 1)
    # round-half-up in integers (Python's round() is half-even and JS's Math.round() is half-up: they would disagree
    # on exact ties such as 2048/32768); the simulator does the same integer arithmetic
    return {"peaks": [min(1.0, ((2000 * m + scale) // (2 * scale)) / 1000) for m in maxes], "audioMs": total * 1000 // rate}
