"""Waveform peaks of a WAV file (stdlib ``wave`` only). The UI simulator (``ui/mock/api-mock.js``) copies these rules
exactly, and a parity test keeps them equal.

Rules: ``n`` buckets over the L frames (bucket i spans frames ``i*L//n`` to ``(i+1)*L//n``); the value of a sample is the
largest absolute value among its channels, over full scale ``2**(8*width-1)``; a peak is ``max/scale`` rounded half-up to 3
decimals, capped at 1.0; an empty bucket (L < n) is 0."""
import array
import sys
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


def _decoder(width):
    """``(decode, to_abs)`` for little-endian PCM of ``width`` bytes: ``decode(data)`` is a sequence of samples and
    ``to_abs(slice)`` the largest absolute value in a slice, from one ``max`` and one ``min`` (C speed, no Python loop)."""
    if width == 1:  # unsigned, centred on 128
        return lambda data: bytes(data), lambda seq: max(max(seq) - 128, 128 - min(seq))
    if width == 3:  # no 24-bit array type: put each sample in the top 3 bytes of a 32-bit one (value << 8)
        def decode(data):
            out = bytearray(len(data) // 3 * 4)
            out[1::4], out[2::4], out[3::4] = data[0::3], data[1::3], data[2::3]
            return _signed(out, 4)
        return decode, lambda seq: max(max(seq), -min(seq)) >> 8
    return (lambda data: _signed(data, width)), lambda seq: max(max(seq), -min(seq))


def _signed(data, width):
    arr = array.array({2: "h", 4: "i" if array.array("i").itemsize == 4 else "l"}[width])
    arr.frombytes(bytes(data))
    if sys.byteorder == "big":  # WAV samples are little-endian
        arr.byteswap()
    return arr


def peaks(path, n=DEFAULT_N):
    """``{"peaks": [float, ...] (n values), "audioMs": int}`` of the WAV at ``path``."""
    _check_n(n)
    try:
        with wave.open(str(path), "rb") as w:
            width, chans, rate, total = w.getsampwidth(), w.getnchannels(), w.getframerate(), w.getnframes()
            if not 1 <= width <= 4 or chans < 1 or rate < 1:
                raise PeaksError(f"{path}: unsupported WAV format")
            decode, to_abs = _decoder(width)
            edges = [i * total // n for i in range(n + 1)]  # bucket i spans frames edges[i] .. edges[i+1]
            maxes = [0] * n
            pos = 0  # index of the next frame to read
            bucket = 0
            while pos < total:
                data = w.readframes(min(_CHUNK_FRAMES, total - pos))
                got = len(data) // (width * chans)
                if got == 0:
                    break  # truncated file: stop at what is there
                vals = decode(data[:got * width * chans])
                end = pos + got
                while bucket < n and edges[bucket] < end:
                    lo, hi = max(edges[bucket], pos), min(edges[bucket + 1], end)
                    if hi > lo:  # the max over all channels of all frames is the max over all samples
                        m = to_abs(vals[(lo - pos) * chans:(hi - pos) * chans])
                        if m > maxes[bucket]:
                            maxes[bucket] = m
                    if edges[bucket + 1] > end:
                        break  # the bucket goes on in the next chunk
                    bucket += 1
                pos = end
    except (wave.Error, EOFError) as e:
        raise PeaksError(f"{path}: cannot read the WAV ({e})") from e
    except OSError as e:
        raise PeaksError(f"{path}: cannot read the file ({e})") from e
    scale = 2 ** (8 * width - 1)
    # round-half-up in integers (Python's round() is half-even and JS's Math.round() is half-up: they would disagree
    # on exact ties such as 2048/32768); the simulator does the same integer arithmetic
    return {"peaks": [min(1.0, ((2000 * m + scale) // (2 * scale)) / 1000) for m in maxes], "audioMs": total * 1000 // rate}
