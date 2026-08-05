import os
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from utils.data_loader import OlistDataLoader
from agents.order_seller_agent import OrderSellerAgent
from agents.payment_agent import PaymentAgent
from agents.delivery_agent import DeliveryAgent
from agents.policy_agent import PolicyAgent
from agents.verifier_agent import VerifierAgent
from utils.llm_client import LLMClient

MODEL_NAME = "gemini-flash-lite-latest"
PARAMETER_SIZE = "<= 10B (Flash-Lite Lightweight Agent Model)"

class Coordinator:
    """
    Coordinator Agent: Điều phối toàn bộ vòng đời của một ca kiểm toán (case).
    Quản lý State Machine tường minh, tổng hợp chứng cứ từ 3 Domain Agents,
    chuyển cho Policy Agent ra quyết định và Verifier Agent kiểm định trước khi xuất file an toàn.
    Tích hợp LLM điều phối báo cáo tổng hợp.
    """
    def __init__(
        self,
        data_loader: Optional[OlistDataLoader] = None,
        order_seller_agent: Optional[Any] = None,
        payment_agent: Optional[Any] = None,
        delivery_agent: Optional[Any] = None,
        policy_agent: Optional[Any] = None,
        verifier_agent: Optional[Any] = None,
        llm_client: Optional[Any] = None
    ):
        self.data_loader = data_loader if data_loader is not None else OlistDataLoader()
        self.llm = llm_client if llm_client is not None else LLMClient(default_model=MODEL_NAME)
        self.model_name = MODEL_NAME
        self.parameter_size = PARAMETER_SIZE
        self.os_agent = order_seller_agent if order_seller_agent is not None else OrderSellerAgent(data_loader=self.data_loader, llm_client=self.llm)
        self.pay_agent = payment_agent if payment_agent is not None else PaymentAgent(data_loader=self.data_loader, llm_client=self.llm)
        self.deliv_agent = delivery_agent if delivery_agent is not None else DeliveryAgent(data_loader=self.data_loader, llm_client=self.llm)
        self.policy_agent = policy_agent if policy_agent is not None else PolicyAgent(llm_client=self.llm)
        self.verifier_agent = verifier_agent if verifier_agent is not None else VerifierAgent(llm_client=self.llm)

    def _log_trace(self, trace_list: List[Dict[str, Any]], run_id: str, correlation_id: str, case_id: str, from_state: str, to_state: str, details: Dict[str, Any] = None) -> None:
        trace_list.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": run_id,
            "correlation_id": correlation_id,
            "case_id": case_id,
            "state_from": from_state,
            "state_to": to_state,
            "event_type": "STATE_TRANSITION" if to_state != "FAILED" else "ERROR",
            "details": details or {}
        })

    def process_case(self, case_data: Dict[str, Any], output_dir: str = "output", run_id: str = "") -> Dict[str, Any]:
        trace_logs = []
        current_state = "RECEIVED"
        
        case_id = str(case_data.get("case_id", "")).strip()
        order_id = str(case_data.get("order_id") or case_data.get("customer_request", {}).get("claimed_order_id", "")).strip()
        contract_version = str(case_data.get("contract_version", "1.0")).strip()
        policy_version = str(case_data.get("policy_version", "EC_POLICY_V1")).strip()
        
        if not run_id:
            run_id = case_data.get("run_id") or f"run_{uuid.uuid4().hex[:8]}"
        correlation_id = case_data.get("correlation_id") or f"corr_{case_id}_{uuid.uuid4().hex[:6]}"

        self._log_trace(trace_logs, run_id, correlation_id, case_id, "NONE", "RECEIVED")

        # 1. VALIDATED
        if not case_id or not order_id or contract_version != "1.0":
            err = {"code": "INVALID_CASE_SCHEMA", "message": "Thiếu case_id, order_id hoặc sai contract_version"}
            self._log_trace(trace_logs, run_id, correlation_id, case_id, current_state, "FAILED", {"error": err})
            return {"current_state": "FAILED", "status": "invalid_input", "error": err, "trace_logs": trace_logs}
        
        current_state = "VALIDATED"
        self._log_trace(trace_logs, run_id, correlation_id, case_id, "RECEIVED", "VALIDATED")

        # 2. DISPATCHED & COLLECTED (Domain Agents)
        current_state = "DISPATCHED"
        self._log_trace(trace_logs, run_id, correlation_id, case_id, "VALIDATED", "DISPATCHED")

        domain_task = {
            "contract_version": contract_version,
            "run_id": run_id,
            "correlation_id": correlation_id,
            "case_id": case_id,
            "order_id": order_id,
            "policy_version": policy_version,
            "payload": {"lookup_order_id": order_id}
        }

        os_res = self.os_agent.process_task(domain_task)
        pay_res = self.pay_agent.process_task(domain_task)
        deliv_res = self.deliv_agent.process_task(domain_task)

        for res, ag_name in [(os_res, "order_seller"), (pay_res, "payment"), (deliv_res, "delivery")]:
            if res.get("status") != "success":
                err = res.get("errors", [{"code": "DOMAIN_AGENT_ERROR", "message": f"Agent {ag_name} failed"}])[0]
                self._log_trace(trace_logs, run_id, correlation_id, case_id, current_state, "FAILED", {"agent": ag_name, "error": err})
                return {"current_state": "FAILED", "status": res.get("status", "error"), "error": err, "errors": res.get("errors", []), "trace_logs": trace_logs}

        current_state = "COLLECTED"
        self._log_trace(trace_logs, run_id, correlation_id, case_id, "DISPATCHED", "COLLECTED")

        # Gộp Entity & Evidence Candidates trong Evidence Bundle
        order_ids = []
        seller_ids = []
        item_ids = []
        payment_ids = []
        evidence_ids = []

        for res in (os_res, pay_res, deliv_res):
            ent = res.get("entity_candidates", {})
            for oid in ent.get("order_ids", []):
                if oid not in order_ids:
                    order_ids.append(oid)
            for sid in ent.get("seller_ids", []):
                if sid not in seller_ids:
                    seller_ids.append(sid)
            for iid in ent.get("item_ids", []):
                if iid not in item_ids:
                    item_ids.append(iid)
            for pid in ent.get("payment_ids", []):
                if pid not in payment_ids:
                    payment_ids.append(pid)
            for evid in res.get("evidence_candidates", []):
                if evid not in evidence_ids:
                    evidence_ids.append(evid)

        evidence_bundle = {
            "contract_version": contract_version,
            "run_id": run_id,
            "correlation_id": correlation_id,
            "case_id": case_id,
            "order_id": order_id,
            "policy_version": policy_version,
            "source_status": {
                "order_seller": os_res.get("status", "error"),
                "payment": pay_res.get("status", "error"),
                "delivery": deliv_res.get("status", "error")
            },
            "order_facts": {"order_found": os_res["facts"].get("order_found", False), "order": os_res["facts"].get("order", {})},
            "item_seller_facts": {
                "items": os_res["facts"].get("items", []),
                "item_total_brl": os_res["facts"].get("item_total_brl", 0.0),
                "freight_total_brl": os_res["facts"].get("freight_total_brl", 0.0),
                "violating_seller_ids": os_res["facts"].get("violating_seller_ids", [])
            },
            "payment_facts": pay_res.get("facts", {}),
            "delivery_facts": deliv_res.get("facts", {}),
            "entity_candidates": {
                "order_ids": order_ids[:5],
                "seller_ids": seller_ids[:5],
                "item_ids": item_ids[:5],
                "payment_ids": payment_ids[:5]
            },
            "evidence_candidates": evidence_ids[:10]
        }

        # 3. POLICY_DECIDED
        policy_task = {
            "contract_version": contract_version,
            "run_id": run_id,
            "correlation_id": correlation_id,
            "case_id": case_id,
            "order_id": order_id,
            "policy_version": policy_version,
            "payload": {"evidence_bundle": evidence_bundle, "policy_version": policy_version}
        }
        pol_res = self.policy_agent.process_task(policy_task)
        if pol_res.get("status") != "success":
            err = pol_res.get("errors", [{"code": "POLICY_DECISION_FAILED", "message": "Policy agent failed"}])[0]
            self._log_trace(trace_logs, run_id, correlation_id, case_id, current_state, "FAILED", {"agent": "policy", "error": err})
            return {"current_state": "FAILED", "status": pol_res.get("status", "error"), "error": err, "errors": pol_res.get("errors", []), "trace_logs": trace_logs}

        policy_decision = pol_res.get("facts", {})
        current_state = "POLICY_DECIDED"
        self._log_trace(trace_logs, run_id, correlation_id, case_id, "COLLECTED", "POLICY_DECIDED")

        # 4. DRAFTED
        draft_result = {
            "contract_version": contract_version,
            "run_id": run_id,
            "correlation_id": correlation_id,
            "case_id": case_id,
            "order_id": order_id,
            "status": policy_decision.get("case_status", "action_required"),
            "primary_issue": policy_decision.get("primary_issue", ""),
            "policy_decision": policy_decision,
            "evidence": {
                "entity_candidates": evidence_bundle["entity_candidates"],
                "evidence_candidates": policy_decision.get("selected_evidence_ids", evidence_bundle["evidence_candidates"])
            },
            "warnings": os_res.get("warnings", []) + pay_res.get("warnings", []) + deliv_res.get("warnings", []) + pol_res.get("warnings", []),
            "errors": []
        }
        current_state = "DRAFTED"
        self._log_trace(trace_logs, run_id, correlation_id, case_id, "POLICY_DECIDED", "DRAFTED")

        # 5. VERIFYING & VERIFIED
        current_state = "VERIFYING"
        self._log_trace(trace_logs, run_id, correlation_id, case_id, "DRAFTED", "VERIFYING")

        verifier_task = {
            "contract_version": contract_version,
            "run_id": run_id,
            "correlation_id": correlation_id,
            "case_id": case_id,
            "order_id": order_id,
            "policy_version": policy_version,
            "payload": {
                "draft_result": draft_result,
                "evidence_bundle": evidence_bundle,
                "policy_decision": policy_decision
            }
        }
        verif_res = self.verifier_agent.process_task(verifier_task)
        verdict = verif_res.get("facts", {}).get("verdict", "FAIL")

        if verif_res.get("status") != "success" or verdict != "PASS":
            err = verif_res.get("errors", [{"code": "VERIFICATION_FAILED", "message": "Verifier verdict failed"}])[0]
            if not verif_res.get("errors") and verdict != "PASS":
                err = {"code": "VERIFICATION_FAILED", "message": f"Checks failed: {verif_res.get('facts', {}).get('failed_checks', [])}"}
            self._log_trace(trace_logs, run_id, correlation_id, case_id, current_state, "FAILED", {"agent": "verifier", "error": err})
            return {"current_state": "FAILED", "status": "verification_error", "error": err, "errors": verif_res.get("errors", [err]), "trace_logs": trace_logs}

        draft_result["verification"] = verif_res.get("facts", {})
        current_state = "VERIFIED"
        self._log_trace(trace_logs, run_id, correlation_id, case_id, "VERIFYING", "VERIFIED")

        # 6. WRITTEN (Atomic File Write)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            final_file = os.path.join(output_dir, f"{case_id}.json")
            temp_file = os.path.join(output_dir, f"{case_id}.tmp.{uuid.uuid4().hex}")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(draft_result, f, indent=2, ensure_ascii=False)
            os.replace(temp_file, final_file)

        current_state = "WRITTEN"
        self._log_trace(trace_logs, run_id, correlation_id, case_id, "VERIFIED", "WRITTEN")

        draft_result["current_state"] = current_state
        draft_result["status"] = "success"
        draft_result["trace_logs"] = trace_logs
        return draft_result
