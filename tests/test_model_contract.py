import unittest
from pathlib import Path

import numpy as np
from pydantic import ValidationError

from app.ai.inference import InferenceError, _to_feature_array, load_model
from app.schema.schema_ import SignRequest


class ModelContractTests(unittest.TestCase):
    def test_feature_array_requires_exactly_63_values(self):
        self.assertEqual(_to_feature_array([0.0] * 63).shape, (1, 63))
        with self.assertRaises(InferenceError):
            _to_feature_array([0.0] * 62)

    def test_request_rejects_non_finite_coordinates(self):
        with self.assertRaises(ValidationError):
            SignRequest(device_id="TEST_01", keypoints=[0.0] * 62 + [float("nan")])

    @unittest.skipUnless(
        Path("app/ai/models/gesture_model.pkl").exists()
        and Path("app/ai/models/label_encoder.pkl").exists(),
        "deployed model artifacts are not present",
    )
    def test_deployed_model_and_encoder_mapping(self):
        bundle = load_model()
        self.assertEqual(int(bundle.estimator.n_features_in_), 63)
        model_classes = np.asarray(bundle.estimator.classes_)
        encoder_classes = np.asarray(bundle.label_encoder.classes_)
        self.assertEqual(len(model_classes), 32)
        self.assertEqual(len(model_classes), len(encoder_classes))
        decoded = bundle.label_encoder.inverse_transform(model_classes)
        np.testing.assert_array_equal(decoded, encoder_classes)


if __name__ == "__main__":
    unittest.main()
