import csv
import os
from typing import List, Dict, Any, Optional
from pathlib import Path

class OlistDataLoader:
    """
    Lớp tải và truy xuất dữ liệu từ các file CSV của Olist.
    Đảm bảo 100% chỉ đọc, không chỉnh sửa hay can thiệp dữ liệu gốc,
    giữ nguyên mọi định danh và giá trị dưới dạng string (chuỗi).
    """
    def __init__(self, data_dir: str | Path = "data"):
        self.data_dir = str(data_dir)
        self._payments_cache: Optional[Dict[str, List[Dict[str, str]]]] = None
        self._items_cache: Optional[Dict[str, List[Dict[str, str]]]] = None
        self._orders_cache: Optional[Dict[str, Dict[str, str]]] = None
        self._sellers_cache: Optional[Dict[str, Dict[str, str]]] = None
        self._products_cache: Optional[Dict[str, Dict[str, str]]] = None

    def _load_payments_if_needed(self) -> None:
        if self._payments_cache is not None:
            return
        self._payments_cache = {}
        file_path = os.path.join(self.data_dir, "olist_order_payments_dataset.csv")
        if not os.path.exists(file_path):
            return
        with open(file_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                order_id = str(row.get("order_id", "")).strip()
                if order_id not in self._payments_cache:
                    self._payments_cache[order_id] = []
                self._payments_cache[order_id].append(dict(row))

    def _load_items_if_needed(self) -> None:
        if self._items_cache is not None:
            return
        self._items_cache = {}
        file_path = os.path.join(self.data_dir, "olist_order_items_dataset.csv")
        if not os.path.exists(file_path):
            return
        with open(file_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                order_id = str(row.get("order_id", "")).strip()
                if order_id not in self._items_cache:
                    self._items_cache[order_id] = []
                self._items_cache[order_id].append(dict(row))

    def _load_orders_if_needed(self) -> None:
        if self._orders_cache is not None:
            return
        self._orders_cache = {}
        file_path = os.path.join(self.data_dir, "olist_orders_dataset.csv")
        if not os.path.exists(file_path):
            return
        with open(file_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                order_id = str(row.get("order_id", "")).strip()
                if order_id in self._orders_cache:
                    raise ValueError(f"DUPLICATE_PRIMARY_KEY: Trùng khóa chính order_id {order_id} trong olist_orders_dataset.csv")
                self._orders_cache[order_id] = dict(row)

    def _load_sellers_if_needed(self) -> None:
        if self._sellers_cache is not None:
            return
        self._sellers_cache = {}
        file_path = os.path.join(self.data_dir, "olist_sellers_dataset.csv")
        if not os.path.exists(file_path):
            return
        with open(file_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                seller_id = str(row.get("seller_id", "")).strip()
                if seller_id in self._sellers_cache:
                    raise ValueError(f"DUPLICATE_PRIMARY_KEY: Trùng khóa chính seller_id {seller_id} trong olist_sellers_dataset.csv")
                self._sellers_cache[seller_id] = dict(row)

    def _load_products_if_needed(self) -> None:
        if self._products_cache is not None:
            return
        self._products_cache = {}
        file_path = os.path.join(self.data_dir, "olist_products_dataset.csv")
        if not os.path.exists(file_path):
            return
        with open(file_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                product_id = str(row.get("product_id", "")).strip()
                if product_id in self._products_cache:
                    raise ValueError(f"DUPLICATE_PRIMARY_KEY: Trùng khóa chính product_id {product_id} trong olist_products_dataset.csv")
                self._products_cache[product_id] = dict(row)

    def get_order_payments(self, order_id: str) -> List[Dict[str, str]]:
        self._load_payments_if_needed()
        if not self._payments_cache:
            return []
        return [dict(row) for row in self._payments_cache.get(str(order_id).strip(), [])]

    def get_order_items(self, order_id: str) -> List[Dict[str, str]]:
        self._load_items_if_needed()
        if not self._items_cache:
            return []
        return [dict(row) for row in self._items_cache.get(str(order_id).strip(), [])]

    def get_order(self, order_id: str) -> Optional[Dict[str, str]]:
        self._load_orders_if_needed()
        if not self._orders_cache:
            return None
        row = self._orders_cache.get(str(order_id).strip())
        return dict(row) if row else None

    def get_seller(self, seller_id: str) -> Optional[Dict[str, str]]:
        self._load_sellers_if_needed()
        if not self._sellers_cache:
            return None
        row = self._sellers_cache.get(str(seller_id).strip())
        return dict(row) if row else None

    def get_product(self, product_id: str) -> Optional[Dict[str, str]]:
        self._load_products_if_needed()
        if not self._products_cache:
            return None
        row = self._products_cache.get(str(product_id).strip())
        return dict(row) if row else None
