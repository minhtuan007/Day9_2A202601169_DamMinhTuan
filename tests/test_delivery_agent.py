import unittest
import tempfile
import os
import shutil
from utils.data_loader import OlistDataLoader
from agents.delivery_agent import DeliveryAgent

class TestDeliveryAgent(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        
        # Tạo mock olist_orders_dataset.csv
        orders_csv = os.path.join(self.test_dir, "olist_orders_dataset.csv")
        with open(orders_csv, "w", encoding="utf-8") as f:
            f.write('"order_id","customer_id","order_status","order_purchase_timestamp","order_approved_at","order_delivered_carrier_date","order_delivered_customer_date","order_estimated_delivery_date"\n')
            # Giao trễ do seller (actual 07 > estimate 05, carrier 04 > limit 03)
            f.write('order_late_seller,cust_1,delivered,2018-01-01,2018-01-01,2018-01-04 10:00:00,2018-01-07 10:00:00,2018-01-05 10:00:00\n')
            # Giao trễ do logistics (actual 07 > estimate 05, carrier 02 < limit 03)
            f.write('order_late_logistics,cust_2,delivered,2018-01-01,2018-01-01,2018-01-02 10:00:00,2018-01-07 10:00:00,2018-01-05 10:00:00\n')
            # Giao đúng hạn (actual 04 <= estimate 05)
            f.write('order_ontime,cust_3,delivered,2018-01-01,2018-01-01,2018-01-02 10:00:00,2018-01-04 10:00:00,2018-01-05 10:00:00\n')
            # Canceled & Unavailable (thiếu delivery date) -> not_applicable
            f.write('order_canceled,cust_4,canceled,2018-01-01,2018-01-01,,,\n')
            f.write('order_unavailable,cust_5,unavailable,2018-01-01,2018-01-01,,,\n')
            # Thiếu delivery date trên đơn delivered -> unknown
            f.write('order_unknown,cust_6,invoiced,2018-01-01,2018-01-01,,,\n')

        # Tạo mock olist_order_items_dataset.csv
        items_csv = os.path.join(self.test_dir, "olist_order_items_dataset.csv")
        with open(items_csv, "w", encoding="utf-8") as f:
            f.write('"order_id","order_item_id","product_id","seller_id","shipping_limit_date","price","freight_value"\n')
            f.write('order_late_seller,1,prod_1,seller_1,2018-01-03 10:00:00,100.00,15.00\n')
            f.write('order_late_logistics,1,prod_2,seller_2,2018-01-03 10:00:00,50.00,10.00\n')
            f.write('order_ontime,1,prod_3,seller_3,2018-01-03 10:00:00,30.00,5.00\n')
            f.write('order_canceled,1,prod_4,seller_4,2018-01-03 10:00:00,40.00,5.00\n')
            f.write('order_unavailable,1,prod_5,seller_5,2018-01-03 10:00:00,50.00,5.00\n')
            f.write('order_unknown,1,prod_6,seller_6,2018-01-03 10:00:00,60.00,5.00\n')

        self.loader = OlistDataLoader(data_dir=self.test_dir)
        self.agent = DeliveryAgent(data_loader=self.loader)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def _make_task(self, order_id: str) -> dict:
        return {
            "contract_version": "1.0",
            "run_id": "test_run",
            "correlation_id": "corr_1",
            "case_id": "EC_001",
            "order_id": order_id,
            "policy_version": "EC_POLICY_V1",
            "requested_at": "2018-10-18T00:00:00-03:00",
            "payload": {"lookup_order_id": order_id}
        }

    def test_late_delivery_seller_attribution(self):
        task = self._make_task("order_late_seller")
        res = self.agent.process_task(task)
        self.assertEqual(res["status"], "success")
        facts = res["facts"]
        self.assertTrue(facts["delivery_timestamp_available"])
        self.assertTrue(facts["delivered_after_estimate"])
        self.assertFalse(facts["delivery_within_estimate"])
        self.assertEqual(facts["attribution_candidate"], "seller")
        self.assertEqual(facts["responsible_seller_candidates"], ["seller_1"])
        self.assertEqual(facts["root_cause_candidates"], ["SELLER_HANDOFF_AFTER_LIMIT"])

    def test_late_delivery_logistics_attribution(self):
        task = self._make_task("order_late_logistics")
        res = self.agent.process_task(task)
        self.assertEqual(res["status"], "success")
        facts = res["facts"]
        self.assertEqual(facts["attribution_candidate"], "logistics_provider")
        self.assertEqual(facts["responsible_seller_candidates"], [])
        self.assertEqual(facts["root_cause_candidates"], ["CARRIER_DELIVERED_AFTER_ESTIMATE"])

    def test_ontime_delivery(self):
        task = self._make_task("order_ontime")
        res = self.agent.process_task(task)
        self.assertEqual(res["status"], "success")
        facts = res["facts"]
        self.assertTrue(facts["delivery_within_estimate"])
        self.assertEqual(facts["attribution_candidate"], "none")
        self.assertEqual(facts["root_cause_candidates"], ["DELIVERY_WITHIN_ESTIMATE"])

    def test_canceled_or_unavailable_not_applicable(self):
        for o_id in ("order_canceled", "order_unavailable"):
            task = self._make_task(o_id)
            res = self.agent.process_task(task)
            self.assertEqual(res["status"], "success")
            self.assertEqual(res["facts"]["attribution_candidate"], "not_applicable")

    def test_unknown_delivery_dates(self):
        task = self._make_task("order_unknown")
        res = self.agent.process_task(task)
        self.assertEqual(res["status"], "success")
        facts = res["facts"]
        self.assertFalse(facts["delivery_timestamp_available"])
        self.assertEqual(facts["attribution_candidate"], "unknown")
        self.assertGreater(len(res["warnings"]), 0)

if __name__ == "__main__":
    unittest.main()
