from typing import Dict, Any, List, Optional
from decimal import Decimal, InvalidOperation
from utils.llm_client import LLMClient

MODEL_NAME = "gemini-flash-lite-latest"
PARAMETER_SIZE = "<= 10B (Flash-Lite Lightweight Agent Model)"

class VerifierAgent:
    """
    Verifier Agent: Thẩm định toàn vẹn kết quả đầu ra theo 8 trục tự động.
    Đóng vai trò chốt chặn trước khi Coordinator xuất file, không sửa lỗi mà chỉ ghi nhận phán quyết PASS/FAIL.
    Tích hợp LLM hỗ trợ tạo tóm tắt nhật ký thẩm định (không thay cho kiểm định xác định).
    """
    def __init__(self, llm_client: Optional[Any] = None):
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
            "agent_name": "verifier",
            "model_metadata": {
                "agent": "verifier",
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

    def _make_error(self, code: str, path: str, message: str, source: str = "verifier") -> Dict[str, Any]:
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
        draft = payload.get("draft_result", {})
        bundle = payload.get("evidence_bundle", {})
        decision = payload.get("policy_decision", {})

        passed_checks = []
        failed_checks = []

        # 1. Schema Check
        required_draft_keys = ["case_id", "order_id", "status"]
        schema_ok = all(k in draft for k in required_draft_keys)
        if schema_ok:
            passed_checks.append("schema")
        else:
            failed_checks.append("schema")
            result["errors"].append(self._make_error("SCHEMA_VALIDATION_FAILED", "draft_result", "Draft result thiếu trường bắt buộc"))

        # 2. Identity Check
        t_order_id = str(task.get("order_id", "")).strip()
        d_order_id = str(draft.get("order_id", "")).strip()
        b_order_id = str(bundle.get("order_id", "")).strip()
        t_case_id = str(task.get("case_id", "")).strip()
        d_case_id = str(draft.get("case_id", "")).strip()

        identity_ok = (t_order_id == d_order_id == b_order_id) and (t_case_id == d_case_id) and (d_order_id != "")
        if identity_ok:
            passed_checks.append("identity")
        else:
            failed_checks.append("identity")
            result["errors"].append(self._make_error("IDENTITY_MISMATCH", "draft_result.order_id", f"Mất đồng bộ định danh order/case: {t_order_id} vs {d_order_id} vs {b_order_id}"))

        # 3. Entities Check
        entities = draft.get("evidence", {}).get("entity_candidates", {})
        o_ids = entities.get("order_ids", [])
        s_ids = entities.get("seller_ids", [])
        i_ids = entities.get("item_ids", [])
        p_ids = entities.get("payment_ids", [])
        
        entities_ok = all(len(lst) <= 5 for lst in (o_ids, s_ids, i_ids, p_ids)) and len(set(o_ids)) == len(o_ids)
        if entities_ok:
            passed_checks.append("entities")
        else:
            failed_checks.append("entities")
            result["errors"].append(self._make_error("ENTITY_LIMIT_EXCEEDED", "draft_result.evidence.entity_candidates", "Vượt giới hạn 5 IDs mỗi loại hoặc có ID trùng lặp"))

        # 4. Evidence Check
        evs = draft.get("evidence", {}).get("evidence_candidates", [])
        evs_ok = (len(evs) <= 10) and (len(set(evs)) == len(evs))
        if evs_ok:
            passed_checks.append("evidence")
        else:
            failed_checks.append("evidence")
            result["errors"].append(self._make_error("EVIDENCE_LIMIT_EXCEEDED", "draft_result.evidence.evidence_candidates", f"Vượt giới hạn 10 evidence IDs hoặc bị trùng: {len(evs)}"))

        # 5. Financials Check
        pol_decision = draft.get("policy_decision", decision)
        refund_val = pol_decision.get("recommended_refund_brl", 0.0)
        currency = pol_decision.get("currency", "BRL")
        try:
            refund_dec = Decimal(str(refund_val))
        except (InvalidOperation, ValueError, TypeError):
            refund_dec = Decimal("-1.00")

        pay_facts = bundle.get("payment_facts", {})
        item_facts = bundle.get("item_seller_facts", {})
        pay_total = Decimal(str(pay_facts.get("payment_total_brl", 0.0)))
        item_total = Decimal(str(item_facts.get("item_total_brl", 0.0)))
        freight_total = Decimal(str(item_facts.get("freight_total_brl", 0.0)))
        max_possible = max(pay_total, item_total + freight_total)

        financials_ok = (refund_dec >= Decimal("0.00")) and (refund_dec <= max_possible) and (currency == "BRL")
        if financials_ok:
            passed_checks.append("financials")
        else:
            failed_checks.append("financials")
            result["errors"].append(self._make_error("FINANCIAL_MISMATCH", "policy_decision.recommended_refund_brl", f"Số tiền hoàn ({refund_val}) vượt ngưỡng tối đa hợp lệ ({max_possible}) hoặc sai currency"))

        # 6. Policy Check
        valid_issues = [
            "canceled_order_paid", "unavailable_order_paid", "late_delivery_seller",
            "late_delivery_logistics", "valid_split_payment", "unsupported_late_claim"
        ]
        issue = pol_decision.get("primary_issue", "")
        prio = pol_decision.get("matched_rule_priority", 0)
        policy_ok = (issue in valid_issues) and (1 <= int(prio) <= 6)
        if policy_ok:
            passed_checks.append("policy")
        else:
            failed_checks.append("policy")
            result["errors"].append(self._make_error("INVALID_POLICY_RULE", "policy_decision.primary_issue", f"Primary issue hoặc priority không hợp lệ: {issue} ({prio})"))

        # 7. Limits Check
        parties = pol_decision.get("responsible_parties", [])
        actions = pol_decision.get("resolution_actions", [])
        limits_ok = (len(parties) <= 3) and (len(actions) <= 5)
        if limits_ok:
            passed_checks.append("limits")
        else:
            failed_checks.append("limits")
            result["errors"].append(self._make_error("LIMIT_VALIDATION_FAILED", "policy_decision.responsible_parties", "Vượt giới hạn kích thước responsible_parties (<=3) hoặc resolution_actions (<=5)"))

        # 8. Determinism Check
        # Đảm bảo không có sai số dấu phẩy động dạng .0000000000000001
        refund_str = str(refund_val)
        determinism_ok = len(refund_str.split(".")[-1]) <= 2 if "." in refund_str else True
        if determinism_ok:
            passed_checks.append("determinism")
        else:
            failed_checks.append("determinism")
            result["errors"].append(self._make_error("NON_DETERMINISTIC_FLOAT", "policy_decision.recommended_refund_brl", f"Số tiền bị sai số floating point vô hạn: {refund_str}"))

        verdict = "PASS" if len(failed_checks) == 0 else "FAIL"

        result["facts"] = {
            "verdict": verdict,
            "passed_checks": passed_checks,
            "failed_checks": failed_checks
        }
        
        result["entity_candidates"] = entities
        result["evidence_candidates"] = evs
        return result
