"""Voice identity — original Resemblyzer pipeline.

Source: https://github.com/shradha-khapra/ai-attendance-project-app
  src/pipelines/voice_pipeline.py

Streamlit (@st.cache_resource / st.error) is replaced by a process-wide
VoiceEncoder singleton so this file can run under FastAPI. Preprocess,
embed_utterance, np.dot matching, 0.65 threshold, and librosa split
(top_db=30, min 0.5s) are unchanged.
"""
from resemblyzer import VoiceEncoder, preprocess_wav
import numpy as np
import io
import json
import threading
import librosa


_voice_encoder = None
_voice_lock = threading.Lock()
_voice_loading = False
_voice_error = None
VOICE_SIZE = 256
MATCH_THRESHOLD = 0.65


class VoiceWarmingError(RuntimeError):
    """Encoder is still loading Torch weights. Caller should retry shortly."""


def as_voice_vector(value):
    """Parse a stored embedding (list or JSON string) for DB/API integration."""
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
    """Same role as @st.cache_resource: load VoiceEncoder once per process."""
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


def load_voice_encoder(wait=True):
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


def get_voice_embedding(audio_bytes):
    try:
        encoder = load_voice_encoder()

        audio, sr = librosa.load(io.BytesIO(audio_bytes), sr=16000)
        wav = preprocess_wav(audio)
        embedding = encoder.embed_utterance(wav)
        return embedding.tolist()
    except Exception:
        return None


def identify_speaker(new_embedding, candidates_dict, threshold=0.65):
    if new_embedding is None or not candidates_dict:
        return None, 0.0

    best_sid = None
    best_score = -1.0

    probe = as_voice_vector(new_embedding)
    if probe is None:
        probe = np.asarray(new_embedding, dtype=np.float64).reshape(-1)

    for sid, stored_embedding in candidates_dict.items():
        if stored_embedding is not None and (
            not hasattr(stored_embedding, "__len__") or len(stored_embedding) > 0
        ):
            stored = as_voice_vector(stored_embedding)
            if stored is None:
                stored = np.asarray(stored_embedding, dtype=np.float64).reshape(-1)
            similarity = np.dot(probe, stored)
            if similarity > best_score:
                best_score = similarity
                best_sid = sid

    if best_score >= threshold:
        return best_sid, best_score

    return None, best_score


def process_bulk_audio(audio_bytes, candidates_dict, threshold=0.65):
    try:
        encoder = load_voice_encoder()

        audio, sr = librosa.load(io.BytesIO(audio_bytes), sr=16000)
        segments = librosa.effects.split(audio, top_db=30)

        identified_results = {}

        for start, end in segments:

            if (end - start) < sr * 0.5:
                continue
            segment_audio = audio[start:end]
            wav = preprocess_wav(segment_audio)
            embedding = encoder.embed_utterance(wav)

            sid, score = identify_speaker(embedding, candidates_dict, threshold)

            if sid:
                if sid not in identified_results or score > identified_results[sid]:
                    identified_results[sid] = score

        return identified_results
    except Exception:
        return {}
