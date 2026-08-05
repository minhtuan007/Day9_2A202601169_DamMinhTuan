import os
from typing import Dict, Any, List, Optional
from utils.data_loader import OlistDataLoader
from utils.llm_client import LLMClient

MODEL_NAME = "gemini-flash-lite-latest"
PARAMETER_SIZE = "<= 10B (Flash-Lite Lightweight Agent Model)"

class DeliveryAgent:
    """
    Delivery Agent: Điều tra tiến trình vận chuyển, so sánh thời gian giao hàng thực tế
    với dự kiến và xác định bên có trách nhiệm khi xảy ra giao trễ hạn (Seller hay Logistics).
    Tích hợp LLM hỗ trợ tổng hợp báo cáo vận chuyển.
    """
    def __init__(self, data_loader: Optional[OlistDataLoader] = None, llm_client: Optional[Any] = None):
        self.data_loader = data_loader if data_loader is not None else OlistDataLoader()
        self.llm = llm_client if llm_client is not None else LLMClient(default_model=MODEL_NAME)
        self.model_name = MODEL_NAME
        self.parameter_size = PARAMETER_SIZE

    def _create_base_result(self, task: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "contract_version": task.get("contract_version", "1.0"),
            "run_id": task.get("run_id", ""),
            "correlation_id": task.get("correlation_id", ""),
            "case_id": task.get("case_id", ""),
            "order_id": task.get("order_id", ""),
            "agent_name": "delivery",
            "model_metadata": {
                "agent": "delivery",
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
            result["errors"].append(self._make_error("ORDER_NOT_FOUND", "customer_request.claimed_order_id", f"Không tìm thấy order {order_id}", "olist_orders_dataset.csv"))
            return result

        order_status = self._clean_val(order_row.get("order_status")) or ""
        customer_date = self._clean_val(order_row.get("order_delivered_customer_date"))
        estimate_date = self._clean_val(order_row.get("order_estimated_delivery_date"))
        carrier_date = self._clean_val(order_row.get("order_delivered_carrier_date"))

        delivery_timestamp_available = bool(customer_date and estimate_date)
        delivered_after_estimate = bool(delivery_timestamp_available and customer_date > estimate_date) # type: ignore
        delivery_within_estimate = bool(delivery_timestamp_available and customer_date <= estimate_date) # type: ignore

        # 3. Tra cứu Items và So sánh hạn Handoff
        item_rows = self.data_loader.get_order_items(order_id)
        try:
            sorted_items = sorted(item_rows, key=lambda x: int(x.get("order_item_id", 0)))
        except ValueError:
            sorted_items = item_rows

        seller_handoffs = []
        late_seller_ids = []
        all_items_have_timestamps = (len(sorted_items) > 0)

        for row in sorted_items:
            try:
                order_item_id_int = int(row.get("order_item_id", 0))
            except ValueError:
                order_item_id_int = 0

            seller_id = self._clean_val(row.get("seller_id")) or ""
            limit_date = self._clean_val(row.get("shipping_limit_date"))
            
            handoff_after = None
            if carrier_date and limit_date:
                handoff_after = (carrier_date > limit_date)
                if handoff_after and seller_id and seller_id not in late_seller_ids:
                    late_seller_ids.append(seller_id)
            else:
                all_items_have_timestamps = False

            seller_handoffs.append({
                "order_item_id": order_item_id_int,
                "seller_id": seller_id,
                "shipping_limit_date": limit_date or "",
                "carrier_date": carrier_date or "",
                "handoff_after_limit": handoff_after
            })

        # 4. Quyết định Attribution Candidate
        attribution_candidate = "unknown"
        responsible_seller_candidates = []
        root_cause_candidates = []

        if order_status in ("canceled", "unavailable") and not delivery_timestamp_available:
            attribution_candidate = "not_applicable"
        elif not delivery_timestamp_available:
            attribution_candidate = "unknown"
            result["warnings"].append("Thiếu timestamp giao hàng thực tế hoặc dự kiến để đánh giá delivery")
        elif delivered_after_estimate:
            if len(late_seller_ids) > 0:
                attribution_candidate = "seller"
                responsible_seller_candidates = late_seller_ids
                root_cause_candidates = ["SELLER_HANDOFF_AFTER_LIMIT"]
            elif len(sorted_items) > 0 and all_items_have_timestamps and len(late_seller_ids) == 0:
                attribution_candidate = "logistics_provider"
                root_cause_candidates = ["CARRIER_DELIVERED_AFTER_ESTIMATE"]
            else:
                attribution_candidate = "unknown"
                result["warnings"].append("Giao trễ hạn nhưng thiếu thông tin limit/carrier date của item để phân chia trách nhiệm")
        elif delivery_within_estimate:
            attribution_candidate = "none"
            root_cause_candidates = ["DELIVERY_WITHIN_ESTIMATE"]

        result["facts"] = {
            "delivery_timestamp_available": delivery_timestamp_available,
            "delivered_after_estimate": delivered_after_estimate,
            "delivery_within_estimate": delivery_within_estimate,
            "seller_handoffs": seller_handoffs,
            "attribution_candidate": attribution_candidate,
            "responsible_seller_candidates": responsible_seller_candidates,
            "root_cause_candidates": root_cause_candidates
        }

        # 5. Đóng gói Entity và Evidence Candidates
        result["entity_candidates"] = {
            "order_ids": [order_id],
            "seller_ids": responsible_seller_candidates[:5]
        }

        evidence_list = [f"order:{order_id}"]
        for s_id in responsible_seller_candidates:
            ev = f"seller:{s_id}"
            if ev not in evidence_list:
                evidence_list.append(ev)
        for cause in root_cause_candidates:
            ev = f"policy:{cause}"
            if ev not in evidence_list:
                evidence_list.append(ev)

        result["evidence_candidates"] = evidence_list[:10]
        return result
