import unittest
import tempfile
import os
import shutil
import json
from utils.data_loader import OlistDataLoader
from agents.order_seller_agent import OrderSellerAgent
from agents.payment_agent import PaymentAgent
from agents.delivery_agent import DeliveryAgent
from agents.policy_agent import PolicyAgent
from agents.verifier_agent import VerifierAgent
from agents.coordinator import Coordinator

class TestCoordinator(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.output_dir = os.path.join(self.test_dir, "output")
        os.makedirs(self.output_dir, exist_ok=True)

        # Tạo mock dataset CSVs
        with open(os.path.join(self.test_dir, "olist_orders_dataset.csv"), "w", encoding="utf-8") as f:
            f.write('"order_id","customer_id","order_status","order_purchase_timestamp","order_approved_at","order_delivered_carrier_date","order_delivered_customer_date","order_estimated_delivery_date"\n')
            f.write('order_ontime,cust_1,delivered,2018-01-01,2018-01-01,2018-01-02 10:00:00,2018-01-03 10:00:00,2018-01-05 10:00:00\n')

        with open(os.path.join(self.test_dir, "olist_order_payments_dataset.csv"), "w", encoding="utf-8") as f:
            f.write('"order_id","payment_sequential","payment_type","payment_installments","payment_value"\n')
            f.write('order_ontime,1,credit_card,1,115.00\n')

        with open(os.path.join(self.test_dir, "olist_order_items_dataset.csv"), "w", encoding="utf-8") as f:
            f.write('"order_id","order_item_id","product_id","seller_id","shipping_limit_date","price","freight_value"\n')
            f.write('order_ontime,1,prod_1,seller_1,2018-01-03 10:00:00,100.00,15.00\n')

        with open(os.path.join(self.test_dir, "olist_sellers_dataset.csv"), "w", encoding="utf-8") as f:
            f.write('"seller_id","seller_zip_code_prefix","seller_city","seller_state"\n')
            f.write('seller_1,12345,Sao Paulo,SP\n')

        self.loader = OlistDataLoader(data_dir=self.test_dir)
        self.coordinator = Coordinator(data_loader=self.loader)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_successful_end_to_end_flow(self):
        case_data = {
            "contract_version": "1.0",
            "case_id": "EC_TEST_001",
            "order_id": "order_ontime",
            "policy_version": "EC_POLICY_V1",
            "requested_at": "2018-10-18T00:00:00-03:00",
            "customer_request": {
                "claimed_order_id": "order_ontime",
                "request_type": "late_delivery",
                "customer_narrative": "Order was on time though"
            }
        }

        result = self.coordinator.process_case(case_data, output_dir=self.output_dir, run_id="run_test_1")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["current_state"], "WRITTEN")
        self.assertTrue(os.path.exists(os.path.join(self.output_dir, "EC_TEST_001.json")))

        with open(os.path.join(self.output_dir, "EC_TEST_001.json"), "r", encoding="utf-8") as f:
            saved_json = json.load(f)
        self.assertEqual(saved_json["case_id"], "EC_TEST_001")
        self.assertEqual(saved_json["status"], "no_action")
        self.assertEqual(saved_json["primary_issue"], "unsupported_late_claim")
        self.assertIn("trace_logs", result)
        states = [log["state_to"] for log in result["trace_logs"]]
        self.assertIn("VALIDATED", states)
        self.assertIn("COLLECTED", states)
        self.assertIn("POLICY_DECIDED", states)
        self.assertIn("VERIFIED", states)
        self.assertIn("WRITTEN", states)

    def test_not_found_order_stops_pipeline(self):
        case_data = {
            "contract_version": "1.0",
            "case_id": "EC_TEST_404",
            "order_id": "non_existent_id",
            "policy_version": "EC_POLICY_V1",
            "requested_at": "2018-10-18T00:00:00-03:00",
            "customer_request": {"claimed_order_id": "non_existent_id", "request_type": "late_delivery"}
        }
        result = self.coordinator.process_case(case_data, output_dir=self.output_dir, run_id="run_test_2")
        self.assertEqual(result["current_state"], "FAILED")
        self.assertFalse(os.path.exists(os.path.join(self.output_dir, "EC_TEST_404.json")))
        self.assertEqual(result["error"]["code"], "ORDER_NOT_FOUND")

    def test_verifier_failure_no_write(self):
        # Tạo mock Verifier luôn trả về FAIL để kiểm chứng chốt chặn an toàn
        class MockFailingVerifier:
            def process_task(self, task):
                return {"status": "success", "facts": {"verdict": "FAIL", "failed_checks": ["financials"], "passed_checks": []}, "errors": [{"code": "FINANCIAL_MISMATCH", "message": "Simulated failure"}]}

        coord_failing = Coordinator(data_loader=self.loader, verifier_agent=MockFailingVerifier())
        case_data = {
            "contract_version": "1.0",
            "case_id": "EC_TEST_FAIL",
            "order_id": "order_ontime",
            "policy_version": "EC_POLICY_V1",
            "requested_at": "2018-10-18T00:00:00-03:00",
            "customer_request": {"claimed_order_id": "order_ontime", "request_type": "late_delivery"}
        }
        result = coord_failing.process_case(case_data, output_dir=self.output_dir, run_id="run_test_3")
        self.assertEqual(result["current_state"], "FAILED")
        self.assertFalse(os.path.exists(os.path.join(self.output_dir, "EC_TEST_FAIL.json")))
        self.assertEqual(result["error"]["code"], "FINANCIAL_MISMATCH")

if __name__ == "__main__":
    unittest.main()
