"""Voice adapter boundary for Faster-Whisper/Silero/Kokoro or Pipecat.

The actual model dependencies are optional. Keep audio transport out of the
core so text requests and hardware-free tests remain available.
"""

from collections.abc import Callable


def transcribe_and_think(audio: bytes, transcribe: Callable[[bytes], str], think: Callable[[str], dict]) -> dict:
    text = transcribe(audio).strip()
    if not text:
        return {"status": "ignored", "reason": "no speech detected"}
    return {"status": "ok", "transcript": text, "thought": think(text)}
