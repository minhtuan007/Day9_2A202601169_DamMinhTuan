# Todo Checklist: Full Multi-Agent A2A System Implementation

## Phase 1: Expand DataLoader & Order-Seller Agent
- [x] Mở rộng `OlistDataLoader` trong `utils/data_loader.py` (thêm hàm tra cứu `get_order`, `get_seller`, `get_product` với O(1) cache).
  - [x] Viết bổ sung test case trong `tests/test_data_loader.py` và chạy PASS.
- [x] Viết failing unit tests (RED phase) cho `OrderSellerAgent` trong `tests/test_order_seller_agent.py`.
- [x] Triển khai logic `OrderSellerAgent` trong `agents/order_seller_agent.py` (GREEN phase).
  - Acceptance criteria:
    - [x] Tìm đúng order, xác nhận seller, trả về timestamp.
    - [x] Tính `item_total_brl` và `freight_total_brl` chuẩn xác bằng `Decimal`.
    - [x] Phát hiện seller giao trễ cho bưu cục (`carrier_date > shipping_limit_date`).
  - Verification: `python -m unittest tests/test_order_seller_agent.py -v`

## Phase 2: Delivery Agent
- [x] Viết failing unit tests (RED phase) cho `DeliveryAgent` trong `tests/test_delivery_agent.py`.
- [x] Triển khai logic `DeliveryAgent` trong `agents/delivery_agent.py` (GREEN phase).
  - Acceptance criteria:
    - [x] So sánh ngày giao khách thực tế (`actual > estimate`).
    - [x] Phái quyết `attribution_candidate`: `seller` (nếu có item giao bưu cục muộn), `logistics_provider` (nếu mọi item giao bưu cục đúng hạn), `none` (nếu giao đúng hạn khách), `not_applicable` hoặc `unknown`.
  - Verification: `python -m unittest tests/test_delivery_agent.py -v`

## Phase 3: Policy Agent
- [x] Viết failing unit tests (RED phase) cho `PolicyAgent` trong `tests/test_policy_agent.py`.
- [x] Triển khai logic `PolicyAgent` trong `agents/policy_agent.py` (GREEN phase).
  - Acceptance criteria:
    - [x] Nhận `EvidenceBundle`, áp dụng tuần tự 6 quy tắc thuộc `EC_POLICY_V1` từ ưu tiên 1 đến 6.
    - [x] Xuất ra quyết định chứa `primary_issue`, `recommended_refund_brl`, `resolution_actions`, và lý do loại các rule ưu tiên cao hơn `excluded_higher_priority_rules`.
    - [x] Trả confidence `1.0` khi đủ critical facts, báo lỗi `UNCLASSIFIED_CASE` nếu không khớp rule nào.
  - Verification: `python -m unittest tests/test_policy_agent.py -v`

## Phase 4: Verifier Agent
- [x] Viết failing unit tests (RED phase) cho `VerifierAgent` trong `tests/test_verifier_agent.py`.
- [x] Triển khai logic `VerifierAgent` trong `agents/verifier_agent.py` (GREEN phase).
  - Acceptance criteria:
    - [x] Kiểm định 8 trục: `schema`, `identity`, `entities`, `evidence`, `financials`, `policy`, `limits`, `determinism`.
    - [x] Đảm bảo giới hạn đầu ra: tối đa 5 entity IDs mỗi loại, 10 evidence IDs, loại trùng và có thứ tự ổn định.
    - [x] Trả ra phán quyết `verdict`: `"PASS"` hoặc `"FAIL"`.
  - Verification: `python -m unittest tests/test_verifier_agent.py -v`

## Phase 5: Coordinator Agent
- [x] Viết failing unit tests (RED phase) cho `CoordinatorAgent` trong `tests/test_coordinator.py`.
- [x] Triển khai logic `CoordinatorAgent` trong `agents/coordinator.py` (GREEN phase).
  - Acceptance criteria:
    - [x] Quản lý state machine: `RECEIVED -> VALIDATED -> DISPATCHED -> COLLECTED -> POLICY_DECIDED -> DRAFTED -> VERIFYING -> VERIFIED -> WRITTEN`.
    - [x] Điều phối gửi `AgentTask` cho 3 domain agents, tập hợp `EvidenceBundle`.
    - [x] Bẫy lỗi đối chiếu tài chính chéo, gửi Policy Agent và Verifier Agent, chỉ cho phép ghi output khi Verifier trả `PASS`.
  - Verification: `python -m unittest tests/test_coordinator.py -v`

## Phase 6: Batch Pipeline Integration & Execution (`main.py`)
- [x] Triển khai logic orchestrator trong `main.py` để duyệt 50 file từ `input/EC_001.json` đến `input/EC_050.json`.
- [x] Thực thi ghi nhận audit nhật ký hệ thống vào `logging/trace.jsonl` (chuẩn JSONL) và khai báo cấu hình AI vào `logging/metadata.json`.
- [x] Thi hành toàn bộ chặng chạy thử và kiểm chứng:
  - Verification 1 (Unit Test Suite): `python -m unittest discover -s tests -v` (100% PASS)
  - Verification 2 (Batch Run): `python main.py` (Hoàn thành tạo 50 file trong `output/` thành công).
