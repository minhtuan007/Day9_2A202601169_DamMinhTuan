import unittest
from decimal import Decimal
from agents.policy_agent import PolicyAgent

class TestPolicyAgent(unittest.TestCase):
    def setUp(self):
        self.agent = PolicyAgent()

    def _make_task(self, order_status: str, payment_total: float, delivered_after: bool, attribution: str, payment_count: int, diff: float, delivery_within: bool = False, seller_ids: list = None) -> dict:
        bundle = {
            "contract_version": "1.0",
            "run_id": "run_1",
            "correlation_id": "corr_1",
            "case_id": "EC_001",
            "order_id": "order_test",
            "policy_version": "EC_POLICY_V1",
            "source_status": {"order_seller": "success", "payment": "success", "delivery": "success"},
            "order_facts": {"order_found": True, "order": {"order_status": order_status}},
            "item_seller_facts": {"item_total_brl": 100.0, "freight_total_brl": 20.0},
            "payment_facts": {"payment_total_brl": payment_total, "payment_count": payment_count, "difference_brl": diff, "is_reconciled": (diff <= 0.10)},
            "delivery_facts": {"delivered_after_estimate": delivered_after, "delivery_within_estimate": delivery_within, "attribution_candidate": attribution, "responsible_seller_candidates": seller_ids or []},
            "entity_candidates": {"order_ids": ["order_test"], "seller_ids": seller_ids or [], "item_ids": ["order_test:1"], "payment_ids": ["order_test:1"]},
            "evidence_candidates": ["order:order_test", "item:order_test:1", "payment:order_test:1"] + ([f"seller:{s}" for s in (seller_ids or [])])
        }
        return {
            "contract_version": "1.0",
            "run_id": "run_1",
            "correlation_id": "corr_1",
            "case_id": "EC_001",
            "order_id": "order_test",
            "policy_version": "EC_POLICY_V1",
            "payload": {"evidence_bundle": bundle, "policy_version": "EC_POLICY_V1"}
        }

    def test_rule_1_canceled_paid(self):
        task = self._make_task("canceled", 120.0, False, "not_applicable", 1, 0.0)
        res = self.agent.process_task(task)
        self.assertEqual(res["status"], "success")
        decision = res["facts"]
        self.assertEqual(decision["matched_rule_priority"], 1)
        self.assertEqual(decision["primary_issue"], "canceled_order_paid")
        self.assertEqual(decision["recommended_refund_brl"], 120.0)
        self.assertEqual(decision["resolution_actions"], ["issue_full_refund"])
        self.assertEqual(decision["responsible_parties"][0]["party_type"], "platform")
        self.assertEqual(decision["excluded_higher_priority_rules"], [])

    def test_rule_2_unavailable_paid(self):
        task = self._make_task("unavailable", 120.0, False, "not_applicable", 1, 0.0)
        res = self.agent.process_task(task)
        self.assertEqual(res["status"], "success")
        decision = res["facts"]
        self.assertEqual(decision["matched_rule_priority"], 2)
        self.assertEqual(decision["primary_issue"], "unavailable_order_paid")
        self.assertEqual(len(decision["excluded_higher_priority_rules"]), 1)

    def test_rule_3_late_delivery_seller(self):
        task = self._make_task("delivered", 120.0, True, "seller", 1, 0.0, False, ["seller_abc"])
        res = self.agent.process_task(task)
        self.assertEqual(res["status"], "success")
        decision = res["facts"]
        self.assertEqual(decision["matched_rule_priority"], 3)
        self.assertEqual(decision["primary_issue"], "late_delivery_seller")
        self.assertEqual(decision["recommended_refund_brl"], 20.0) # Freight total
        self.assertEqual(decision["responsible_parties"][0]["party_type"], "seller")
        self.assertEqual(decision["responsible_parties"][0]["party_id"], "seller_abc")
        self.assertEqual(len(decision["excluded_higher_priority_rules"]), 2)

    def test_rule_4_late_delivery_logistics(self):
        task = self._make_task("delivered", 120.0, True, "logistics_provider", 1, 0.0)
        res = self.agent.process_task(task)
        self.assertEqual(res["status"], "success")
        decision = res["facts"]
        self.assertEqual(decision["matched_rule_priority"], 4)
        self.assertEqual(decision["primary_issue"], "late_delivery_logistics")
        self.assertEqual(decision["responsible_parties"][0]["party_type"], "logistics_provider")
        self.assertEqual(decision["recommended_refund_brl"], 20.0)

    def test_rule_5_valid_split_payment(self):
        task = self._make_task("delivered", 120.0, False, "none", 2, 0.0, False)
        res = self.agent.process_task(task)
        self.assertEqual(res["status"], "success")
        decision = res["facts"]
        self.assertEqual(decision["matched_rule_priority"], 5)
        self.assertEqual(decision["primary_issue"], "valid_split_payment")
        self.assertEqual(decision["recommended_refund_brl"], 0.0)
        self.assertEqual(decision["case_status"], "no_action")
        self.assertEqual(decision["resolution_actions"], ["explain_valid_split_payment"])

    def test_rule_6_unsupported_late_claim(self):
        task = self._make_task("delivered", 120.0, False, "none", 1, 0.0, True)
        res = self.agent.process_task(task)
        self.assertEqual(res["status"], "success")
        decision = res["facts"]
        self.assertEqual(decision["matched_rule_priority"], 6)
        self.assertEqual(decision["primary_issue"], "unsupported_late_claim")
        self.assertEqual(decision["recommended_refund_brl"], 0.0)

    def test_unclassified_case(self):
        # Không match rule nào
        task = self._make_task("invoiced", 0.0, False, "unknown", 1, 5.0, False)
        res = self.agent.process_task(task)
        self.assertIn(res["status"], ["data_error", "invalid_input"])
        self.assertEqual(res["errors"][0]["code"], "UNCLASSIFIED_CASE")

if __name__ == "__main__":
    unittest.main()
