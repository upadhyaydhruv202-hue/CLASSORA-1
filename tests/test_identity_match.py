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
    def test_linear_svm_and_l2_gate(self):
        """Source: SVC linear + L2 <= 0.6 against the predicted student's embedding."""
        try:
            from sklearn.svm import SVC
        except Exception:
            self.skipTest("sklearn is not installed")
        rng = np.random.default_rng(0)
        a = rng.normal(size=128)
        a = a / np.linalg.norm(a)
        b = rng.normal(size=128)
        b = b / np.linalg.norm(b)
        clf = SVC(kernel="linear", probability=True, class_weight="balanced")
        clf.fit([a, b], [1, 2])
        predicted = int(clf.predict([a])[0])
        self.assertEqual(predicted, 1)
        train = {1: a, 2: b}
        score = float(np.linalg.norm(train[predicted] - a))
        self.assertLessEqual(score, 0.6)
        far = float(np.linalg.norm(a - b))
        self.assertGreater(far, 0.6)


if __name__ == "__main__":
    unittest.main()
