import unittest
import tempfile
import os
import shutil
from decimal import Decimal
from utils.data_loader import OlistDataLoader
from agents.order_seller_agent import OrderSellerAgent

class TestOrderSellerAgent(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        
        # Tạo mock olist_orders_dataset.csv
        orders_csv = os.path.join(self.test_dir, "olist_orders_dataset.csv")
        with open(orders_csv, "w", encoding="utf-8") as f:
            f.write('"order_id","customer_id","order_status","order_purchase_timestamp","order_approved_at","order_delivered_carrier_date","order_delivered_customer_date","order_estimated_delivery_date"\n')
            f.write('order_ontime,cust_1,delivered,2018-01-01,2018-01-01,2018-01-02 10:00:00,2018-01-03 10:00:00,2018-01-05 10:00:00\n')
            f.write('order_late_seller,cust_2,delivered,2018-01-01,2018-01-01,2018-01-05 14:00:00,2018-01-07 10:00:00,2018-01-06 10:00:00\n')
            f.write('order_no_items,cust_3,delivered,2018-01-01,2018-01-01,2018-01-02 10:00:00,2018-01-03 10:00:00,2018-01-05 10:00:00\n')
            f.write('order_missing_seller,cust_4,delivered,2018-01-01,2018-01-01,2018-01-02 10:00:00,2018-01-03 10:00:00,2018-01-05 10:00:00\n')
            f.write('order_null_dates,cust_5,invoiced,2018-01-01,2018-01-01,,,\n')

        # Tạo mock olist_order_items_dataset.csv
        items_csv = os.path.join(self.test_dir, "olist_order_items_dataset.csv")
        with open(items_csv, "w", encoding="utf-8") as f:
            f.write('"order_id","order_item_id","product_id","seller_id","shipping_limit_date","price","freight_value"\n')
            # order_ontime: carrier 2018-01-02 < limit 2018-01-03
            f.write('order_ontime,1,prod_1,seller_1,2018-01-03 10:00:00,100.00,15.00\n')
            # order_late_seller: carrier 2018-01-05 > limit 2018-01-04
            f.write('order_late_seller,1,prod_2,seller_2,2018-01-04 10:00:00,50.00,10.00\n')
            f.write('order_late_seller,2,prod_3,seller_2,2018-01-04 10:00:00,25.50,5.50\n')
            # order_missing_seller
            f.write('order_missing_seller,1,prod_1,seller_nonexistent,2018-01-03 10:00:00,10.00,2.00\n')
            # order_null_dates
            f.write('order_null_dates,1,prod_1,seller_1,,10.00,2.00\n')

        # Tạo mock olist_sellers_dataset.csv
        sellers_csv = os.path.join(self.test_dir, "olist_sellers_dataset.csv")
        with open(sellers_csv, "w", encoding="utf-8") as f:
            f.write('"seller_id","seller_zip_code_prefix","seller_city","seller_state"\n')
            f.write('seller_1,12345,Sao Paulo,SP\n')
            f.write('seller_2,67890,Rio de Janeiro,RJ\n')

        self.loader = OlistDataLoader(data_dir=self.test_dir)
        self.agent = OrderSellerAgent(data_loader=self.loader)

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

    def test_standard_ontime_order(self):
        task = self._make_task("order_ontime")
        res = self.agent.process_task(task)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["agent_name"], "order_seller")
        facts = res["facts"]
        self.assertTrue(facts["order_found"])
        self.assertEqual(facts["order"]["order_status"], "delivered")
        self.assertEqual(len(facts["items"]), 1)
        self.assertFalse(facts["items"][0]["handoff_after_limit"])
        self.assertEqual(facts["item_total_brl"], 100.00)
        self.assertEqual(facts["freight_total_brl"], 15.00)
        self.assertEqual(facts["violating_seller_ids"], [])
        self.assertEqual(facts["missing_seller_ids"], [])

        self.assertEqual(res["entity_candidates"]["order_ids"], ["order_ontime"])
        self.assertEqual(res["entity_candidates"]["item_ids"], ["order_ontime:1"])
        self.assertEqual(res["entity_candidates"]["seller_ids"], ["seller_1"])
        self.assertIn("order:order_ontime", res["evidence_candidates"])
        self.assertIn("item:order_ontime:1", res["evidence_candidates"])
        self.assertIn("seller:seller_1", res["evidence_candidates"])

    def test_late_seller_handoff(self):
        task = self._make_task("order_late_seller")
        res = self.agent.process_task(task)
        self.assertEqual(res["status"], "success")
        facts = res["facts"]
        self.assertEqual(len(facts["items"]), 2)
        self.assertTrue(facts["items"][0]["handoff_after_limit"])
        self.assertTrue(facts["items"][1]["handoff_after_limit"])
        self.assertEqual(facts["item_total_brl"], 75.50)
        self.assertEqual(facts["freight_total_brl"], 15.50)
        self.assertEqual(facts["violating_seller_ids"], ["seller_2"])

    def test_order_no_items(self):
        task = self._make_task("order_no_items")
        res = self.agent.process_task(task)
        self.assertEqual(res["status"], "success")
        facts = res["facts"]
        self.assertTrue(facts["order_found"])
        self.assertEqual(facts["items"], [])
        self.assertEqual(facts["item_total_brl"], 0.00)
        self.assertEqual(facts["freight_total_brl"], 0.00)
        self.assertEqual(res["entity_candidates"]["item_ids"], [])
        self.assertEqual(res["entity_candidates"]["seller_ids"], [])

    def test_order_not_found(self):
        task = self._make_task("non_existent_order")
        res = self.agent.process_task(task)
        self.assertEqual(res["status"], "not_found")
        self.assertGreater(len(res["errors"]), 0)
        self.assertEqual(res["errors"][0]["code"], "ORDER_NOT_FOUND")

    def test_missing_seller(self):
        task = self._make_task("order_missing_seller")
        res = self.agent.process_task(task)
        self.assertEqual(res["status"], "data_error")
        self.assertGreater(len(res["errors"]), 0)

    def test_null_dates(self):
        task = self._make_task("order_null_dates")
        res = self.agent.process_task(task)
        self.assertEqual(res["status"], "success")
        facts = res["facts"]
        self.assertIsNone(facts["order"]["order_delivered_carrier_date"])
        self.assertIsNone(facts["items"][0]["handoff_after_limit"])

if __name__ == "__main__":
    unittest.main()
