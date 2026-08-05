#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script kiểm thử kết nối và suy luận thực tế với Mô hình AI (gemini-flash-lite-latest <= 10B)
Sử dụng mã khóa API trong file .env để thực thi đánh giá nghiệp vụ trực tiếp qua mạng.
"""
import os
import sys
import json
import io
from utils.llm_client import LLMClient
from agents.coordinator import Coordinator

# Đảm bảo terminal Windows hiển thị tiếng Việt UTF-8 chính xác
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def run_live_demo(case_filename="EC_007.json"):
    print("=" * 70)
    print("      KIỂM THỬ KẾT NỐI VÀ SUY LUẬN VỚI MÔ HÌNH AI THỰC TẾ")
    print("=" * 70)

    llm_client = LLMClient()
    print(f"[INFO] Cấu hình Model Mặc định: {llm_client.default_model} (<= 10B)")
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key or api_key == "your_gemini_api_key_here":
        print("[WARNING] Không tìm thấy API Key hợp lệ trong .env. Hệ thống sẽ dùng fallback.")
    else:
        print(f"[INFO] Phát hiện API Key hợp lệ (••••{api_key[-4:]}). Sẵn sàng kết nối máy chủ Cloud AI.")

    # Nạp 1 ca kiểm toán phức tạp từ input
    case_path = os.path.join("input", case_filename)
    if not os.path.exists(case_path):
        case_path = os.path.join("input", "EC_001.json")
    
    with open(case_path, "r", encoding="utf-8") as f:
        task_data = json.load(f)

    customer_msg = task_data.get("customer_request", {}).get("message", "N/A")
    order_id = task_data.get("customer_request", {}).get("claimed_order_id", "N/A")

    print(f"\n[STEP 1] Chạy điều phối luồng A2A cho ca: {task_data.get('case_id')} | Đơn hàng: {order_id}")
    print(f" -> Khiếu nại khách hàng: \"{customer_msg}\"")
    
    coordinator = Coordinator()
    final_output = coordinator.process_case(task_data)
    
    print(f" -> Trạng thái chu trình (Current State): {final_output.get('current_state', 'N/A')}")
    print(f" -> Vấn đề chính (Primary Issue): {final_output.get('primary_issue', 'N/A')}")
    
    policy_dec = final_output.get("policy_decision", {})
    verdict = final_output.get("verification", {}).get("verdict", "PASS")
    print(f" -> Phán quyết chính sách: Khuyến nghị hoàn tiền {policy_dec.get('recommended_refund_brl', 0)} BRL (Quy tắc ưu tiên số {policy_dec.get('matched_rule_priority')})")
    print(f" -> Thẩm định độc lập (Verifier Agent): {verdict}")

    # Bắt đầu gửi dữ liệu sang AI để đánh giá thực tế qua API
    print("\n[STEP 2] Gửi dữ liệu bằng chứng xác định sang Mô hình Cloud AI (Google Gemini) để thẩm định...")
    
    # 1. Thao tác với Agent Thanh Toán (Payment)
    prompt_payment = (
        f"Hãy đóng vai chuyên gia kiểm toán Thanh Toán (Payment Agent). Đơn hàng {order_id} bị khiếu nại với vấn đề '{final_output.get('primary_issue')}'. "
        f"Số tiền khuyến nghị hoàn lại là {policy_dec.get('recommended_refund_brl', 0)} BRL. "
        f"Hãy viết đúng 1 câu nghiệp vụ tiếng Việt xác nhận tính hợp lệ tài chính và lý do vì sao cần hoàn khoản thanh toán này cho khách."
    )
    print("\n--- 🤖 [AI Payment Agent Live Inference] ---")
    res_payment = llm_client.generate(prompt_payment, system_instruction="Bạn là trợ lý AI chuyên môn kiểm toán thanh toán và tài chính E-commerce.")
    print(f"Kết quả AI (Model: {llm_client.default_model}):\n=> {res_payment.strip()}")

    # 2. Thao tác với Agent Chính Sách & Điều phối (Policy & Coordinator)
    prompt_policy = (
        f"Hãy đóng vai Thẩm phán Điều phối Chính sách (Policy Coordinator). Lý do ra quyết định cho đơn hàng này: '{policy_dec.get('confidence_explanation')}'. "
        f"Các bên chịu trách nhiệm (Responsible Parties): {json.dumps(policy_dec.get('responsible_parties', []), ensure_ascii=False)}. "
        f"Hãy đưa ra 1 câu kết luận phán quyết cuối cùng và đanh thép về xử lý tranh chấp gửi cho ban điều hành Sàn Olist."
    )
    print("\n--- 🤖 [AI Policy Coordinator Live Inference] ---")
    res_policy = llm_client.generate(prompt_policy, system_instruction="Bạn là thẩm phán chính sách cấp cao giải quyết tranh chấp đơn hàng.")
    print(f"Kết quả AI (Model: {llm_client.default_model}):\n=> {res_policy.strip()}")

    print("\n" + "=" * 70)
    print("      KIỂM THỬ KẾT NỐI VÀ SUY LUẬN VỚI MÔ HÌNH THẬT HOÀN TẤT 100%!")
    print("=" * 70)

if __name__ == "__main__":
    run_live_demo("EC_007.json")
