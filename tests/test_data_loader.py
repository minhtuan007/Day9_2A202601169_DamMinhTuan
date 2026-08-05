import unittest
import tempfile
import os
import shutil
from pathlib import Path
from utils.data_loader import OlistDataLoader

class TestOlistDataLoader(unittest.TestCase):
    def setUp(self):
        # Tạo thư mục tạm và file CSV mẫu để kiểm chứng tính năng độc lập, nhanh gọn
        self.test_dir = tempfile.mkdtemp()
        
        # File mẫu olist_order_payments_dataset.csv
        self.payments_csv = os.path.join(self.test_dir, "olist_order_payments_dataset.csv")
        with open(self.payments_csv, "w", encoding="utf-8") as f:
            f.write('"order_id","payment_sequential","payment_type","payment_installments","payment_value"\n')
            f.write('order_1,1,credit_card,1,100.00\n')
            f.write('order_2,1,credit_card,2,50.00\n')
            f.write('order_2,2,voucher,1,15.10\n')
            f.write('"order_3",1,credit_card,1,10.00\n')
            
        # File mẫu olist_order_items_dataset.csv
        self.items_csv = os.path.join(self.test_dir, "olist_order_items_dataset.csv")
        with open(self.items_csv, "w", encoding="utf-8") as f:
            f.write('"order_id","order_item_id","product_id","seller_id","shipping_limit_date","price","freight_value"\n')
            f.write('order_1,1,prod_1,seller_1,2018-01-01 12:00:00,85.00,15.00\n')
            f.write('order_2,1,prod_2,seller_2,2018-01-02 12:00:00,35.00,10.00\n')
            f.write('order_2,2,prod_3,seller_2,2018-01-02 12:00:00,15.00,5.10\n')

        # File mẫu olist_orders_dataset.csv
        self.orders_csv = os.path.join(self.test_dir, "olist_orders_dataset.csv")
        with open(self.orders_csv, "w", encoding="utf-8") as f:
            f.write('"order_id","customer_id","order_status","order_purchase_timestamp","order_approved_at","order_delivered_carrier_date","order_delivered_customer_date","order_estimated_delivery_date"\n')
            f.write('order_1,cust_1,delivered,2018-01-01,2018-01-01,2018-01-02,2018-01-03,2018-01-05\n')
            f.write('order_2,cust_2,delivered,2018-01-02,2018-01-02,2018-01-03,2018-01-06,2018-01-05\n')

        # File mẫu olist_sellers_dataset.csv
        self.sellers_csv = os.path.join(self.test_dir, "olist_sellers_dataset.csv")
        with open(self.sellers_csv, "w", encoding="utf-8") as f:
            f.write('"seller_id","seller_zip_code_prefix","seller_city","seller_state"\n')
            f.write('seller_1,12345,Sao Paulo,SP\n')
            f.write('seller_2,67890,Rio de Janeiro,RJ\n')

        # File mẫu olist_products_dataset.csv
        self.products_csv = os.path.join(self.test_dir, "olist_products_dataset.csv")
        with open(self.products_csv, "w", encoding="utf-8") as f:
            f.write('"product_id","product_category_name","product_name_lenght","product_description_lenght","product_photos_qty","product_weight_g","product_length_cm","product_height_cm","product_width_cm"\n')
            f.write('prod_1,beleza_saude,50,500,2,200,20,10,15\n')
            f.write('prod_2,relogios_presentes,40,400,1,100,15,5,10\n')
            f.write('prod_3,informatica_acessorios,30,300,3,150,18,8,12\n')

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_get_order_payments(self):
        loader = OlistDataLoader(data_dir=self.test_dir)
        payments_order_2 = loader.get_order_payments("order_2")
        self.assertEqual(len(payments_order_2), 2)
        
        # Đảm bảo toàn bộ giá trị là string (chuỗi), không bị tự ý ép kiểu sang int/float
        self.assertIsInstance(payments_order_2[0]["payment_sequential"], str)
        self.assertIsInstance(payments_order_2[0]["payment_value"], str)
        self.assertEqual(payments_order_2[0]["payment_type"], "credit_card")
        self.assertEqual(payments_order_2[1]["payment_type"], "voucher")

    def test_get_order_items(self):
        loader = OlistDataLoader(data_dir=self.test_dir)
        items_order_2 = loader.get_order_items("order_2")
        self.assertEqual(len(items_order_2), 2)
        self.assertEqual(items_order_2[0]["seller_id"], "seller_2")
        self.assertIsInstance(items_order_2[0]["price"], str)

    def test_no_cartesian_product_and_empty_order(self):
        loader = OlistDataLoader(data_dir=self.test_dir)
        # Order không tồn tại
        self.assertEqual(loader.get_order_payments("non_existent_order"), [])
        self.assertEqual(loader.get_order_items("non_existent_order"), [])
        
        # Đảm bảo 2 hàm trả ra list riêng rành mạch, không bị join thô vào nhau
        payments = loader.get_order_payments("order_2")
        items = loader.get_order_items("order_2")
        self.assertEqual(len(payments), 2)
        self.assertEqual(len(items), 2)
        # Kiểm tra không có trường của items lọt vào trong dict payment
        self.assertNotIn("seller_id", payments[0])

    def test_integration_with_real_data(self):
        # Kiểm tra nhanh integration với thư mục data/ gốc nếu có
        real_data_dir = os.path.join(Path(__file__).parent.parent, "data")
        if os.path.exists(os.path.join(real_data_dir, "olist_order_payments_dataset.csv")):
            loader = OlistDataLoader(data_dir=real_data_dir)
            payments = loader.get_order_payments("b81ef226f3fe1789b1e8b2acac839d17")
            self.assertGreaterEqual(len(payments), 1)
            self.assertEqual(payments[0]["payment_value"], "99.33")

    def test_get_order(self):
        loader = OlistDataLoader(data_dir=self.test_dir)
        order = loader.get_order("order_1")
        self.assertIsNotNone(order)
        self.assertEqual(order["customer_id"], "cust_1")
        self.assertEqual(order["order_status"], "delivered")
        self.assertIsNone(loader.get_order("non_existent_id"))

    def test_get_seller(self):
        loader = OlistDataLoader(data_dir=self.test_dir)
        seller = loader.get_seller("seller_1")
        self.assertIsNotNone(seller)
        self.assertEqual(seller["seller_city"], "Sao Paulo")
        self.assertIsNone(loader.get_seller("non_existent_seller"))

    def test_get_product(self):
        loader = OlistDataLoader(data_dir=self.test_dir)
        product = loader.get_product("prod_1")
        self.assertIsNotNone(product)
        self.assertEqual(product["product_category_name"], "beleza_saude")
        self.assertIsNone(loader.get_product("non_existent_product"))

    def test_duplicate_primary_key_raises(self):
        # Tạo thêm 1 order trùng ID để kiểm tra cảnh báo lỗi DUPLICATE_PRIMARY_KEY
        dup_dir = tempfile.mkdtemp()
        try:
            with open(os.path.join(dup_dir, "olist_orders_dataset.csv"), "w", encoding="utf-8") as f:
                f.write('"order_id","customer_id"\n')
                f.write('order_1,cust_1\n')
                f.write('order_1,cust_2_duplicate\n')
            loader = OlistDataLoader(data_dir=dup_dir)
            with self.assertRaises(ValueError) as ctx:
                loader.get_order("order_1")
            self.assertIn("DUPLICATE_PRIMARY_KEY", str(ctx.exception))
        finally:
            shutil.rmtree(dup_dir)

if __name__ == "__main__":
    unittest.main()
