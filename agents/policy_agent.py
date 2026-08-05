from typing import Dict, Any, List, Optional
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from utils.llm_client import LLMClient

MODEL_NAME = "gemini-flash-lite-latest"
PARAMETER_SIZE = "<= 10B (Flash-Lite Lightweight Agent Model)"

class PolicyAgent:
    """
    Policy Agent: Thi hành bảng quyết định chính sách EC_POLICY_V1 với 6 quy tắc
    được phân cấp ưu tiên từ 1 đến 6. Có giải trình bằng chứng và không dùng AI suy đoán thay cho luật xác định.
    """
    def __init__(self, llm_client: Optional[Any] = None):
        self.llm = llm_client if llm_client is not None else LLMClient(default_model=MODEL_NAME)
        self.model_name = MODEL_NAME
        self.parameter_size = PARAMETER_SIZE

    def _quantize_brl(self, val: Any) -> Decimal:
        try:
            if isinstance(val, Decimal):
                d = val
            else:
                d = Decimal(str(val))
            return d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except (InvalidOperation, ValueError, TypeError):
            return Decimal("0.00")

    def _create_base_result(self, task: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "contract_version": task.get("contract_version", "1.0"),
            "run_id": task.get("run_id", ""),
            "correlation_id": task.get("correlation_id", ""),
            "case_id": task.get("case_id", ""),
            "order_id": task.get("order_id", ""),
            "agent_name": "policy",
            "model_metadata": {
                "agent": "policy",
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

    def _make_error(self, code: str, path: str, message: str, source: str = "EC_POLICY_V1") -> Dict[str, Any]:
        return {
            "code": code,
            "path": path,
            "message": message,
            "source": source,
            "retryable": False,
            "retry_target": "coordinator"
        }

    def process_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        result = self._create_base_result(task)

        if task.get("contract_version") != "1.0":
            result["status"] = "invalid_input"
            result["errors"].append(self._make_error("INVALID_CONTRACT_VERSION", "contract_version", "Chỉ hỗ trợ version 1.0"))
            return result

        payload = task.get("payload", {})
        policy_version = payload.get("policy_version", task.get("policy_version"))
        if policy_version != "EC_POLICY_V1":
            result["status"] = "invalid_input"
            result["errors"].append(self._make_error("UNSUPPORTED_POLICY_VERSION", "payload.policy_version", "Chỉ hỗ trợ EC_POLICY_V1"))
            return result

        bundle = payload.get("evidence_bundle", {})
        order_facts = bundle.get("order_facts", {})
        item_seller_facts = bundle.get("item_seller_facts", {})
        payment_facts = bundle.get("payment_facts", {})
        delivery_facts = bundle.get("delivery_facts", {})

        order_info = order_facts.get("order", {})
        order_status = order_info.get("order_status", "")
        
        payment_total = self._quantize_brl(payment_facts.get("payment_total_brl", 0.0))
        freight_total = self._quantize_brl(item_seller_facts.get("freight_total_brl", 0.0))
        payment_count = int(payment_facts.get("payment_count", 0))
        diff_brl = self._quantize_brl(payment_facts.get("difference_brl", 0.0))
        is_reconciled = bool(payment_facts.get("is_reconciled", diff_brl <= Decimal("0.10")))

        delivered_after = bool(delivery_facts.get("delivered_after_estimate", False))
        delivery_within = bool(delivery_facts.get("delivery_within_estimate", False))
        attribution = delivery_facts.get("attribution_candidate", "")
        responsible_seller_candidates = delivery_facts.get("responsible_seller_candidates", [])

        excluded = []
        matched_priority = None
        primary_issue = ""
        case_status = ""
        root_causes = []
        responsible_parties = []
        recommended_refund = Decimal("0.00")
        actions = []
        confidence_explanation = ""
        policy_evidence_code = ""

        # Rule 1: Canceled order + paid > 0
        if order_status == "canceled" and payment_total > Decimal("0.00"):
            matched_priority = 1
            primary_issue = "canceled_order_paid"
            case_status = "action_required"
            root_causes = ["ORDER_CANCELED_AFTER_PAYMENT"]
            responsible_parties = [{"party_type": "platform", "party_id": "OLIST_PLATFORM"}]
            recommended_refund = payment_total
            actions = ["issue_full_refund"]
            confidence_explanation = "Đơn hàng canceled đã thu tiền thanh toán"
            policy_evidence_code = "ORDER_CANCELED_AFTER_PAYMENT"
        else:
            reason = "ORDER_STATUS_NOT_CANCELED" if order_status != "canceled" else "PAYMENT_TOTAL_NOT_GREATER_THAN_ZERO"
            excluded.append({"priority": 1, "reason_code": reason})

        # Rule 2: Unavailable order + paid > 0
        if matched_priority is None:
            if order_status == "unavailable" and payment_total > Decimal("0.00"):
                matched_priority = 2
                primary_issue = "unavailable_order_paid"
                case_status = "action_required"
                root_causes = ["ORDER_UNAVAILABLE_AFTER_PAYMENT"]
                responsible_parties = [{"party_type": "platform", "party_id": "OLIST_PLATFORM"}]
                recommended_refund = payment_total
                actions = ["issue_full_refund"]
                confidence_explanation = "Đơn hàng unavailable đã thu tiền thanh toán"
                policy_evidence_code = "ORDER_UNAVAILABLE_AFTER_PAYMENT"
            else:
                reason = "ORDER_STATUS_NOT_UNAVAILABLE" if order_status != "unavailable" else "PAYMENT_TOTAL_NOT_GREATER_THAN_ZERO"
                excluded.append({"priority": 2, "reason_code": reason})

        # Rule 3: Late delivery seller
        if matched_priority is None:
            if delivered_after and attribution == "seller":
                matched_priority = 3
                primary_issue = "late_delivery_seller"
                case_status = "action_required"
                root_causes = ["SELLER_HANDOFF_AFTER_LIMIT"]
                responsible_parties = [{"party_type": "seller", "party_id": str(s)} for s in responsible_seller_candidates[:3]]
                if not responsible_parties:
                    responsible_parties = [{"party_type": "seller", "party_id": "SELLER_UNKNOWN"}]
                recommended_refund = freight_total
                actions = ["refund_freight"]
                confidence_explanation = "Giao hàng sau dự kiến do seller giao bưu cục muộn"
                policy_evidence_code = "SELLER_HANDOFF_AFTER_LIMIT"
            else:
                reason = "DELIVERED_CUSTOMER_DATE_NOT_AFTER_ESTIMATE" if not delivered_after else "NO_SELLER_HANDOFF_AFTER_LIMIT"
                excluded.append({"priority": 3, "reason_code": reason})

        # Rule 4: Late delivery logistics
        if matched_priority is None:
            if delivered_after and attribution == "logistics_provider":
                matched_priority = 4
                primary_issue = "late_delivery_logistics"
                case_status = "action_required"
                root_causes = ["CARRIER_DELIVERED_AFTER_ESTIMATE"]
                responsible_parties = [{"party_type": "logistics_provider", "party_id": "LOGISTICS_PROVIDER"}]
                recommended_refund = freight_total
                actions = ["refund_freight"]
                confidence_explanation = "Giao hàng sau dự kiến do đơn vị vận chuyển chậm"
                policy_evidence_code = "CARRIER_DELIVERED_AFTER_ESTIMATE"
            else:
                reason = "DELIVERED_CUSTOMER_DATE_NOT_AFTER_ESTIMATE" if not delivered_after else "LOGISTICS_ATTRIBUTION_CRITERIA_NOT_MET"
                excluded.append({"priority": 4, "reason_code": reason})

        # Rule 5: Valid split payment
        if matched_priority is None:
            if payment_count >= 2 and is_reconciled:
                matched_priority = 5
                primary_issue = "valid_split_payment"
                case_status = "no_action"
                root_causes = ["MULTIPLE_PAYMENTS_RECONCILED"]
                responsible_parties = []
                recommended_refund = Decimal("0.00")
                actions = ["explain_valid_split_payment"]
                confidence_explanation = "Thanh toán chia nhỏ hợp lệ đã đối sánh thành công"
                policy_evidence_code = "MULTIPLE_PAYMENTS_RECONCILED"
            else:
                reason = "PAYMENT_COUNT_LESS_THAN_TWO" if payment_count < 2 else "PAYMENT_NOT_RECONCILED"
                excluded.append({"priority": 5, "reason_code": reason})

        # Rule 6: Unsupported late claim
        if matched_priority is None:
            if delivery_within and is_reconciled:
                matched_priority = 6
                primary_issue = "unsupported_late_claim"
                case_status = "no_action"
                root_causes = ["DELIVERY_WITHIN_ESTIMATE"]
                responsible_parties = []
                recommended_refund = Decimal("0.00")
                actions = ["reject_late_refund"]
                confidence_explanation = "Đơn hàng giao đúng hạn và thanh toán khớp, không có cơ sở hoàn tiền"
                policy_evidence_code = "DELIVERY_WITHIN_ESTIMATE"
            else:
                reason = "DELIVERY_NOT_WITHIN_ESTIMATE" if not delivery_within else "PAYMENT_NOT_RECONCILED"
                excluded.append({"priority": 6, "reason_code": reason})

        # Unclassified Case
        if matched_priority is None:
            result["status"] = "data_error"
            result["errors"].append(self._make_error("UNCLASSIFIED_CASE", "evidence_bundle", "Không có quy tắc chính sách nào phù hợp với bằng chứng"))
            return result

        # Chế biến Evidence candidates cho decision
        cand_evs = bundle.get("evidence_candidates", [])
        selected_evs = []
        for ev in cand_evs:
            if ev not in selected_evs:
                selected_evs.append(ev)

        pol_ev = f"policy:{policy_evidence_code}"
        if pol_ev not in selected_evs:
            selected_evs.append(pol_ev)

        selected_evs = selected_evs[:10]

        result["facts"] = {
            "confidence_score": 1.0,
            "confidence_explanation": confidence_explanation,
            "matched_rule_priority": matched_priority,
            "primary_issue": primary_issue,
            "case_status": case_status,
            "root_causes": root_causes,
            "responsible_parties": responsible_parties[:3],
            "recommended_refund_brl": float(recommended_refund),
            "currency": "BRL",
            "resolution_actions": actions,
            "excluded_higher_priority_rules": excluded,
            "selected_evidence_ids": selected_evs
        }

        # Kế thừa entities & evs cho level agent result
        result["entity_candidates"] = bundle.get("entity_candidates", {})
        result["evidence_candidates"] = selected_evs
        return result
