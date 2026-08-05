import unittest
import copy
from agents.verifier_agent import VerifierAgent

class TestVerifierAgent(unittest.TestCase):
    def setUp(self):
        self.agent = VerifierAgent()
        self.valid_payload = {
            "draft_result": {
                "case_id": "EC_001",
                "order_id": "order_test_1",
                "status": "action_required",
                "primary_issue": "canceled_order_paid",
                "policy_decision": {
                    "primary_issue": "canceled_order_paid",
                    "matched_rule_priority": 1,
                    "recommended_refund_brl": 100.00,
                    "currency": "BRL",
                    "responsible_parties": [{"party_type": "platform", "party_id": "OLIST_PLATFORM"}]
                },
                "evidence": {
                    "entity_candidates": {
                        "order_ids": ["order_test_1"],
                        "seller_ids": [],
                        "item_ids": [],
                        "payment_ids": ["order_test_1:1"]
                    },
                    "evidence_candidates": ["order:order_test_1", "payment:order_test_1:1", "policy:ORDER_CANCELED_AFTER_PAYMENT"]
                }
            },
            "evidence_bundle": {
                "contract_version": "1.0",
                "run_id": "run_1",
                "correlation_id": "corr_1",
                "case_id": "EC_001",
                "order_id": "order_test_1",
                "payment_facts": {"payment_total_brl": 100.00},
                "item_seller_facts": {"item_total_brl": 80.00, "freight_total_brl": 20.00}
            },
            "policy_decision": {
                "primary_issue": "canceled_order_paid",
                "matched_rule_priority": 1,
                "recommended_refund_brl": 100.00,
                "currency": "BRL"
            }
        }
        self.base_task = {
            "contract_version": "1.0",
            "run_id": "run_1",
            "correlation_id": "corr_1",
            "case_id": "EC_001",
            "order_id": "order_test_1",
            "policy_version": "EC_POLICY_V1",
            "payload": self.valid_payload
        }

    def test_all_axes_pass(self):
        res = self.agent.process_task(self.base_task)
        self.assertEqual(res["status"], "success")
        facts = res["facts"]
        self.assertEqual(facts["verdict"], "PASS")
        self.assertEqual(len(facts["passed_checks"]), 8)
        self.assertEqual(facts["failed_checks"], [])

    def test_identity_mismatch(self):
        task = copy.deepcopy(self.base_task)
        task["payload"]["draft_result"]["order_id"] = "different_order"
        res = self.agent.process_task(task)
        self.assertEqual(res["facts"]["verdict"], "FAIL")
        self.assertIn("identity", res["facts"]["failed_checks"])

    def test_entity_limit_exceeded(self):
        task = copy.deepcopy(self.base_task)
        task["payload"]["draft_result"]["evidence"]["entity_candidates"]["order_ids"] = [
            "o1", "o2", "o3", "o4", "o5", "o6" # 6 IDs, max is 5
        ]
        res = self.agent.process_task(task)
        self.assertEqual(res["facts"]["verdict"], "FAIL")
        self.assertIn("entities", res["facts"]["failed_checks"])

    def test_evidence_limit_exceeded(self):
        task = copy.deepcopy(self.base_task)
        task["payload"]["draft_result"]["evidence"]["evidence_candidates"] = [
            f"item:{i}" for i in range(11) # 11 IDs, max is 10
        ]
        res = self.agent.process_task(task)
        self.assertEqual(res["facts"]["verdict"], "FAIL")
        self.assertIn("evidence", res["facts"]["failed_checks"])

    def test_financials_invalid_refund(self):
        task = copy.deepcopy(self.base_task)
        # Refund 500 while total payment is only 100
        task["payload"]["draft_result"]["policy_decision"]["recommended_refund_brl"] = 500.00
        res = self.agent.process_task(task)
        self.assertEqual(res["facts"]["verdict"], "FAIL")
        self.assertIn("financials", res["facts"]["failed_checks"])

    def test_limits_responsible_parties_exceeded(self):
        task = copy.deepcopy(self.base_task)
        task["payload"]["draft_result"]["policy_decision"]["responsible_parties"] = [
            {"party_type": "seller", "party_id": f"s_{i}"} for i in range(4) # 4 parties, max is 3
        ]
        res = self.agent.process_task(task)
        self.assertEqual(res["facts"]["verdict"], "FAIL")
        self.assertIn("limits", res["facts"]["failed_checks"])

if __name__ == "__main__":
    unittest.main()
