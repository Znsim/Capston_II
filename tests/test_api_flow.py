import unittest

import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.model.db_model import Conversation, ConversationStatus, DeviceInfo
from tests.asgi_client import ASGITestClient


class FakeEstimator:
    classes_ = np.arange(32)
    n_features_in_ = 63

    def predict(self, features):
        return np.asarray([1])

    def predict_proba(self, features):
        probabilities = np.zeros((1, 32), dtype=float)
        probabilities[0, 1] = 0.99
        return probabilities


class FakeEncoder:
    classes_ = np.asarray(["none", "ㄱ"] + [f"label-{index}" for index in range(2, 32)])

    def inverse_transform(self, values):
        return np.asarray([self.classes_[int(value)] for value in values])


class ApiFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(cls.engine)
        cls.session = sessionmaker(bind=cls.engine)()
        cls.session.add_all(
            [
                DeviceInfo(device_id="TEST_01", station_name="서울역", location="1번 출구"),
                DeviceInfo(device_id="TEST_02", station_name="부산역", location="안내소"),
            ]
        )
        cls.session.commit()

        def override_db():
            yield cls.session

        app.dependency_overrides[get_db] = override_db
        app.state.model = type(
            "FakeBundle",
            (),
            {"estimator": FakeEstimator(), "label_encoder": FakeEncoder()},
        )()
        cls.client = ASGITestClient(app)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        cls.session.close()
        cls.engine.dispose()

    def setUp(self):
        self.client.cookies.clear()

    def test_complete_multi_kiosk_api_flow(self):
        status, inference, _ = self.client.post(
            "/api/inference",
            {"device_id": "TEST_01", "keypoints": [0.0] * 63},
        )
        self.assertEqual(status, 200)
        self.assertEqual(inference["recognized_word"], "ㄱ")

        status, first, _ = self.client.post(
            "/api/conversations",
            {"device_id": "TEST_01", "question_text": "첫 번째 질문"},
        )
        self.assertEqual(status, 201)
        status, second, _ = self.client.post(
            "/api/conversations",
            {"device_id": "TEST_02", "question_text": "두 번째 질문"},
        )
        self.assertEqual(status, 201)
        self.assertNotEqual(first["conversation_id"], second["conversation_id"])

        status, _, _ = self.client.get("/api/staff/list")
        self.assertEqual(status, 401)
        status, login, _ = self.client.post(
            "/api/auth/login", {"password": settings.ADMIN_PASSWORD}
        )
        self.assertEqual(status, 200)
        self.assertTrue(login["authenticated"])

        status, waiting, _ = self.client.get(
            "/api/staff/list", query={"page": 1, "limit": 100}
        )
        self.assertEqual(status, 200)
        self.assertEqual(waiting["total"], 2)
        by_id = {item["conversation_id"]: item for item in waiting["items"]}
        self.assertEqual(by_id[first["conversation_id"]]["station_name"], "서울역")
        self.assertEqual(by_id[second["conversation_id"]]["device_id"], "TEST_02")

        status, reply, _ = self.client.post(
            "/api/staff/reply",
            {"conversation_id": first["conversation_id"], "reply": "첫 번째 답변"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(reply["conversation_id"], first["conversation_id"])

        status, poll, _ = self.client.get(
            f"/api/conversations/{first['conversation_id']}",
            query={"device_id": "TEST_01"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(poll["status"], "COMPLETED")
        self.assertEqual(poll["staff_reply"], "첫 번째 답변")

        wrong_status, _, _ = self.client.get(
            f"/api/conversations/{first['conversation_id']}",
            query={"device_id": "TEST_02"},
        )
        self.assertEqual(wrong_status, 404)

        duplicate_status, _, _ = self.client.post(
            "/api/staff/reply",
            {"conversation_id": first["conversation_id"], "reply": "중복 답변"},
        )
        self.assertEqual(duplicate_status, 400)

        status, waiting, _ = self.client.get(
            "/api/staff/list", query={"page": 1, "limit": 100}
        )
        self.assertEqual(status, 200)
        self.assertEqual(waiting["total"], 1)
        self.assertEqual(waiting["items"][0]["conversation_id"], second["conversation_id"])

        rows = self.session.query(Conversation).all()
        self.assertEqual(len(rows), 2)
        first_row = self.session.get(Conversation, first["conversation_id"])
        self.assertEqual(first_row.status, ConversationStatus.COMPLETED)

    def test_admin_can_create_update_and_list_devices(self):
        anonymous_status, _, _ = self.client.get("/api/devices")
        self.assertEqual(anonymous_status, 401)

        login_status, _, _ = self.client.post(
            "/api/auth/login", {"password": settings.ADMIN_PASSWORD}
        )
        self.assertEqual(login_status, 200)

        create_status, created, _ = self.client.post(
            "/api/devices",
            {
                "device_id": "DAEJEON_03",
                "station_name": "대전역",
                "location": "3번 창구",
            },
        )
        self.assertEqual(create_status, 201)
        self.assertEqual(created["device_id"], "DAEJEON_03")

        duplicate_status, _, _ = self.client.post(
            "/api/devices",
            {
                "device_id": "DAEJEON_03",
                "station_name": "대전역",
                "location": "다른 위치",
            },
        )
        self.assertEqual(duplicate_status, 409)

        invalid_status, _, _ = self.client.post(
            "/api/devices",
            {
                "device_id": "INVALID_04",
                "station_name": "   ",
                "location": "4번 창구",
            },
        )
        self.assertEqual(invalid_status, 422)

        update_status, updated, _ = self.client.put(
            "/api/devices/DAEJEON_03",
            {"station_name": "대전역", "location": "안내소"},
        )
        self.assertEqual(update_status, 200)
        self.assertEqual(updated["location"], "안내소")

        list_status, devices, _ = self.client.get("/api/devices")
        self.assertEqual(list_status, 200)
        self.assertIn("DAEJEON_03", {item["device_id"] for item in devices})


if __name__ == "__main__":
    unittest.main()
