import os
from typing import Dict, Any, List, Optional
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from utils.data_loader import OlistDataLoader
from utils.llm_client import LLMClient

MODEL_NAME = "gemini-flash-lite-latest"
PARAMETER_SIZE = "<= 10B (Flash-Lite Lightweight Agent Model)"

class OrderSellerAgent:
    """
    Order & Seller Agent: Tra cứu thông tin đơn hàng, danh sách mặt hàng (items)
    và kiểm chứng liên kết người bán (sellers).
    Đảm bảo tuyệt đối không join bảng 1:N thô và sử dụng Decimal cho tài chính.
    Tích hợp LLM hỗ trợ giải trình bằng chứng logic.
    """
    def __init__(self, data_loader: Optional[OlistDataLoader] = None, llm_client: Optional[Any] = None):
        self.data_loader = data_loader if data_loader is not None else OlistDataLoader()
        self.llm = llm_client if llm_client is not None else LLMClient(default_model=MODEL_NAME)
        self.model_name = MODEL_NAME
        self.parameter_size = PARAMETER_SIZE

    def _quantize_brl(self, val: Any) -> Decimal:
        if isinstance(val, Decimal):
            d = val
        else:
            d = Decimal(str(val))
        return d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _create_base_result(self, task: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "contract_version": task.get("contract_version", "1.0"),
            "run_id": task.get("run_id", ""),
            "correlation_id": task.get("correlation_id", ""),
            "case_id": task.get("case_id", ""),
            "order_id": task.get("order_id", ""),
            "agent_name": "order_seller",
            "model_metadata": {
                "agent": "order_seller",
                "model": self.model_name,
                "parameter_size": self.parameter_size
            },
            "status": "success",
            "facts": {},
            "entity_candidates": {},
            "evidence_candidates": [],
            "warnings": [],
            "errors": []
        }

    def _make_error(self, code: str, path: str, message: str, source: str = "olist_orders_dataset.csv") -> Dict[str, Any]:
        return {
            "code": code,
            "path": path,
            "message": message,
            "source": source,
            "retryable": False,
            "retry_target": "coordinator"
        }

    def _clean_val(self, val: Any) -> Optional[str]:
        s = str(val).strip() if val is not None else ""
        return s if s != "" else None

    def process_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        result = self._create_base_result(task)

        # 1. Envelope Validation
        if task.get("contract_version") != "1.0":
            result["status"] = "invalid_input"
            result["errors"].append(self._make_error("INVALID_CONTRACT_VERSION", "contract_version", "Chỉ hỗ trợ version 1.0"))
            return result
            
        if task.get("policy_version") != "EC_POLICY_V1":
            result["status"] = "invalid_input"
            result["errors"].append(self._make_error("INVALID_POLICY_VERSION", "policy_version", "Chỉ chấp nhận EC_POLICY_V1"))
            return result

        order_id = self._clean_val(task.get("order_id"))
        payload = task.get("payload", {})
        lookup_order_id = self._clean_val(payload.get("lookup_order_id", order_id))
        
        if not order_id or order_id != lookup_order_id:
            result["status"] = "invalid_input"
            result["errors"].append(self._make_error("ORDER_ID_MISMATCH", "payload.lookup_order_id", "order_id trong payload không khớp với envelope"))
            return result

        # 2. Tra cứu Order
        order_row = self.data_loader.get_order(order_id)
        if not order_row:
            result["status"] = "not_found"
            result["errors"].append(self._make_error("ORDER_NOT_FOUND", "customer_request.claimed_order_id", f"Không tìm thấy order {order_id} trong database", "olist_orders_dataset.csv"))
            return result

        order_dict = {
            "order_id": order_id,
            "customer_id": self._clean_val(order_row.get("customer_id")) or "",
            "order_status": self._clean_val(order_row.get("order_status")) or "unknown",
            "order_delivered_carrier_date": self._clean_val(order_row.get("order_delivered_carrier_date")),
            "order_delivered_customer_date": self._clean_val(order_row.get("order_delivered_customer_date")),
            "order_estimated_delivery_date": self._clean_val(order_row.get("order_estimated_delivery_date"))
        }

        # 3. Tra cứu Items & Sellers
        item_rows = self.data_loader.get_order_items(order_id)
        try:
            sorted_items = sorted(item_rows, key=lambda x: int(x.get("order_item_id", 0)))
        except ValueError:
            sorted_items = item_rows

        items_list = []
        item_total_dec = Decimal("0.00")
        freight_total_dec = Decimal("0.00")

        item_ids_candidate = []
        seller_ids_candidate = []
        violating_seller_ids = []
        missing_seller_ids = []

        carrier_date_str = order_dict["order_delivered_carrier_date"]

        for row in sorted_items:
            try:
                order_item_id_int = int(row.get("order_item_id", 0))
            except ValueError:
                order_item_id_int = 0

            prod_id = self._clean_val(row.get("product_id")) or ""
            seller_id = self._clean_val(row.get("seller_id")) or ""
            shipping_limit = self._clean_val(row.get("shipping_limit_date"))

            # Kiểm tra seller trong DB
            seller_row = self.data_loader.get_seller(seller_id)
            if not seller_row:
                missing_seller_ids.append(seller_id)

            try:
                price = self._quantize_brl(row.get("price", "0.00"))
            except (InvalidOperation, ValueError, TypeError):
                price = Decimal("0.00")

            try:
                freight = self._quantize_brl(row.get("freight_value", "0.00"))
            except (InvalidOperation, ValueError, TypeError):
                freight = Decimal("0.00")

            item_total_dec += price
            freight_total_dec += freight

            # So sánh thời gian
            handoff_after = None
            if carrier_date_str and shipping_limit:
                handoff_after = (carrier_date_str > shipping_limit)
                if handoff_after and seller_id not in violating_seller_ids:
                    violating_seller_ids.append(seller_id)

            items_list.append({
                "order_item_id": order_item_id_int,
                "product_id": prod_id,
                "seller_id": seller_id,
                "shipping_limit_date": shipping_limit,
                "price_brl": float(price),
                "freight_value_brl": float(freight),
                "handoff_after_limit": handoff_after
            })

            item_id_str = f"{order_id}:{order_item_id_int}"
            if item_id_str not in item_ids_candidate:
                item_ids_candidate.append(item_id_str)
            if seller_id and seller_id not in seller_ids_candidate and seller_row:
                seller_ids_candidate.append(seller_id)

        if missing_seller_ids:
            result["status"] = "data_error"
            for s_id in missing_seller_ids:
                result["errors"].append(self._make_error("SELLER_NOT_FOUND", f"items.seller_id[{s_id}]", f"Không tìm thấy seller {s_id}", "olist_sellers_dataset.csv"))
            return result

        item_total_dec = self._quantize_brl(item_total_dec)
        freight_total_dec = self._quantize_brl(freight_total_dec)

        result["facts"] = {
            "order_found": True,
            "order": order_dict,
            "items": items_list,
            "item_total_brl": float(item_total_dec),
            "freight_total_brl": float(freight_total_dec),
            "violating_seller_ids": violating_seller_ids,
            "missing_seller_ids": missing_seller_ids
        }

        # 4. Giới hạn số lượng theo mục 11
        order_ids_candidate = [order_id]
        result["entity_candidates"] = {
            "order_ids": order_ids_candidate[:5],
            "item_ids": item_ids_candidate[:5],
            "seller_ids": seller_ids_candidate[:5]
        }

        evidence_list = []
        for o_id in order_ids_candidate:
            ev = f"order:{o_id}"
            if ev not in evidence_list:
                evidence_list.append(ev)
        for i_id in item_ids_candidate:
            ev = f"item:{i_id}"
            if ev not in evidence_list:
                evidence_list.append(ev)
        for s_id in seller_ids_candidate:
            ev = f"seller:{s_id}"
            if ev not in evidence_list:
                evidence_list.append(ev)

        result["evidence_candidates"] = evidence_list[:10]
        return result
