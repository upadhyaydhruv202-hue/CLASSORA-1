"""Identity matching helpers (no live camera)."""
import unittest

import numpy as np


class VoiceIdentifyTests(unittest.TestCase):
    def test_same_embedding_matches(self):
        try:
            from src.pipelines.voice_pipeline import identify_speaker
        except Exception:
            self.skipTest("voice dependencies are not installed")
        vec = np.ones(256, dtype=np.float64)
        vec = vec / np.linalg.norm(vec)
        sid, score = identify_speaker(vec, {12: vec}, 0.65)
        self.assertEqual(sid, 12)
        self.assertGreaterEqual(score, 0.99)

    def test_empty_candidates(self):
        try:
            from src.pipelines.voice_pipeline import identify_speaker
        except Exception:
            self.skipTest("voice dependencies are not installed")
        sid, score = identify_speaker(np.ones(256), {}, 0.65)
        self.assertIsNone(sid)
        self.assertEqual(score, 0.0)


class FaceVectorTests(unittest.TestCase):
    def test_parses_json_and_rejects_bad_size(self):
        try:
            from src.pipelines.face_pipeline import as_face_vector
        except Exception:
            self.skipTest("dlib is not installed")
        raw = [0.0] * 128
        vec = as_face_vector(raw)
        self.assertEqual(vec.size, 128)
        self.assertIsNone(as_face_vector([0.0, 1.0]))
        self.assertIsNone(as_face_vector(None))


if __name__ == "__main__":
    unittest.main()
