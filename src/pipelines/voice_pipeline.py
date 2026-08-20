"""Voice identity — same Resemblyzer pipeline as the original Streamlit app."""
import io
import json
import threading

import numpy as np
import librosa
from resemblyzer import VoiceEncoder, preprocess_wav

_voice_encoder = None
_voice_lock = threading.Lock()
_voice_loading = False
_voice_error = None
VOICE_SIZE = 256
MATCH_THRESHOLD = 0.65


class VoiceWarmingError(RuntimeError):
    """Encoder is still loading Torch weights. Caller should retry shortly."""


def as_voice_vector(value):
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            return None
    try:
        arr = np.asarray(value, dtype=np.float64).reshape(-1)
    except Exception:
        return None
    if arr.size < 64:
        return None
    return arr


def _load_encoder_blocking():
    global _voice_encoder, _voice_loading, _voice_error
    try:
        encoder = VoiceEncoder()
        with _voice_lock:
            _voice_encoder = encoder
            _voice_error = None
    except Exception as exc:
        with _voice_lock:
            _voice_error = str(exc) or "Voice encoder failed to load."
            _voice_encoder = None
    finally:
        with _voice_lock:
            _voice_loading = False


def warmup_voice_encoder():
    """Start Torch/Resemblyzer load in the background. Safe to call many times."""
    global _voice_loading
    with _voice_lock:
        if _voice_encoder is not None or _voice_loading:
            return
        _voice_loading = True
        _voice_error = None
    threading.Thread(target=_load_encoder_blocking, name="classora-voice-warmup", daemon=True).start()


def voice_encoder_ready():
    with _voice_lock:
        return _voice_encoder is not None


def load_voice_encoder(wait=False):
    global _voice_encoder
    with _voice_lock:
        if _voice_encoder is not None:
            return _voice_encoder
        if _voice_error and not _voice_loading:
            raise RuntimeError(_voice_error)
    warmup_voice_encoder()
    if not wait:
        raise VoiceWarmingError("Voice model is still loading. Wait about 15 seconds and try again.")
    for _ in range(120):
        threading.Event().wait(0.5)
        with _voice_lock:
            if _voice_encoder is not None:
                return _voice_encoder
            if _voice_error and not _voice_loading:
                raise RuntimeError(_voice_error)
    raise VoiceWarmingError("Voice model is still loading. Try again in a moment.")


def _cosine(a, b):
    a = np.asarray(a, dtype=np.float64).reshape(-1)
    b = np.asarray(b, dtype=np.float64).reshape(-1)
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na < 1e-8 or nb < 1e-8:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def get_voice_embedding(audio_bytes):
    if not audio_bytes:
        return None
    encoder = load_voice_encoder(wait=True)
    audio, _sr = librosa.load(io.BytesIO(audio_bytes), sr=16000, mono=True)
    if audio is None or len(audio) < 16000 * 0.4:
        return None
    wav = preprocess_wav(audio)
    embedding = encoder.embed_utterance(wav)
    return np.asarray(embedding, dtype=np.float64).reshape(-1).tolist()


def identify_speaker(new_embedding, candidates_dict, threshold=MATCH_THRESHOLD):
    probe = as_voice_vector(new_embedding)
    if probe is None or not candidates_dict:
        return None, 0.0

    best_sid = None
    best_score = -1.0
    for sid, stored_embedding in candidates_dict.items():
        stored = as_voice_vector(stored_embedding)
        if stored is None:
            continue
        similarity = _cosine(probe, stored)
        if similarity > best_score:
            best_score = similarity
            best_sid = sid

    if best_sid is not None and best_score >= threshold:
        return best_sid, best_score
    return None, best_score


def process_bulk_audio(audio_bytes, candidates_dict, threshold=MATCH_THRESHOLD):
    if not audio_bytes:
        return {}
    encoder = load_voice_encoder(wait=False)
    audio, sr = librosa.load(io.BytesIO(audio_bytes), sr=16000, mono=True)
    if audio is None or len(audio) < sr * 0.4:
        return {}

    identified_results = {}

    def _match(chunk):
        wav = preprocess_wav(chunk)
        embedding = encoder.embed_utterance(wav)
        sid, score = identify_speaker(embedding, candidates_dict, threshold)
        if sid is not None:
            prev = identified_results.get(sid, -1.0)
            if score > prev:
                identified_results[sid] = score

    # Short takes (a few seconds) — one pass, like Streamlit enroll/match.
    if len(audio) < sr * 8:
        _match(audio)
        return identified_results

    segments = librosa.effects.split(audio, top_db=30)
    if segments is None or len(segments) == 0:
        segments = np.array([[0, len(audio)]])

    min_len = int(sr * 0.5)
    for start, end in segments:
        if (end - start) < min_len:
            continue
        _match(audio[start:end])

    if not identified_results:
        _match(audio)

    return identified_results
