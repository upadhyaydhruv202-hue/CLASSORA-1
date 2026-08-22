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

    def test_dot_product_threshold(self):
        """Source identify_speaker uses np.dot, not cosine."""
        try:
            from src.pipelines.voice_pipeline import identify_speaker
        except Exception:
            self.skipTest("voice dependencies are not installed")
        probe = np.array([1.0, 0.0], dtype=np.float64)
        other = np.array([0.0, 1.0], dtype=np.float64)
        sid, score = identify_speaker(probe, {1: other}, 0.65)
        self.assertIsNone(sid)
        self.assertLess(score, 0.65)

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


class FaceSvmTests(unittest.TestCase):
    def test_nearest_neighbor_rejects_unknown_when_only_one_enrolled(self):
        """A lone enrolled face must not claim every new person (login → register)."""
        try:
            from src.pipelines.face_pipeline import LOGIN_THRESHOLD, nearest_face_match
        except Exception:
            self.skipTest("face pipeline is not importable")
        rng = np.random.default_rng(1)
        enrolled = rng.normal(size=128)
        enrolled = enrolled / np.linalg.norm(enrolled)
        stranger = rng.normal(size=128)
        stranger = stranger / np.linalg.norm(stranger)
        sid, dist = nearest_face_match(stranger, [enrolled], [7])
        self.assertEqual(sid, 7)
        self.assertGreater(dist, LOGIN_THRESHOLD)

    def test_nearest_neighbor_accepts_same_face(self):
        try:
            from src.pipelines.face_pipeline import LOGIN_THRESHOLD, nearest_face_match
        except Exception:
            self.skipTest("face pipeline is not importable")
        rng = np.random.default_rng(2)
        enrolled = rng.normal(size=128)
        enrolled = enrolled / np.linalg.norm(enrolled)
        probe = enrolled + rng.normal(size=128) * 0.01
        sid, dist = nearest_face_match(probe, [enrolled], [7])
        self.assertEqual(sid, 7)
        self.assertLessEqual(dist, LOGIN_THRESHOLD)


if __name__ == "__main__":
    unittest.main()
