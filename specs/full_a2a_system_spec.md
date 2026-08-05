# Spec: Full Multi-Agent A2A System Implementation (Olist E-commerce)

## 1. Objective
Xây dựng trọn bộ các agent nghiệp vụ còn lại (`Order & Seller Agent`, `Delivery Agent`, `Policy Agent`, `Verifier Agent`, `Coordinator Agent` và batch orchestration `main.py`) cho hệ thống điều tra tự động các ca khiếu nại thương mại điện tử Olist. Toàn bộ các agent phải tương tác nhịp nhàng với nhau và ăn khớp hoàn hảo với `Payment Agent` đã hoàn thiện, tuân thủ nghiêm ngặt mô hình giao tiếp bằng hợp đồng Agent-to-Agent (A2A), đạt độ chính xác tuyệt đối (Financial & Policy Determinism) và vượt qua kiểm duyệt để giải quyết thành công 50 ca `EC_001.json` đến `EC_050.json`.

## 2. Tech Stack & Runtime Environment
- **Ngôn ngữ:** Python 3.11
- **Quản lý tài chính:** Sử dụng đối tượng `decimal.Decimal` với cờ `ROUND_HALF_UP` cho tiền tệ BRL.
- **Thư viện chuẩn:** `json`, `csv`, `pathlib`, `unittest`, `dataclasses`, `typing`, `datetime` (Không dùng pandas hay thư viện bên thứ 3 để đảm bảo tính nhẹ và kiểm soát memory/type chính xác).
- **Mô hình AI & Metadata:** Khai báo cụ thể trong source code và log tại `logging/metadata.json` theo ràng buộc dung lượng model $\le 10\text{B}$ tham số.

## 3. Commands
- **Chạy toàn bộ Test Suite:** `python -m unittest discover -s tests -v`
- **Chạy riêng biệt từng Unit Test:**
  - Data Loader & Payment: `python -m unittest tests/test_data_loader.py tests/test_payment_agent.py -v`
  - Order & Seller: `python -m unittest tests/test_order_seller_agent.py -v`
  - Delivery Agent: `python -m unittest tests/test_delivery_agent.py -v`
  - Policy Agent: `python -m unittest tests/test_policy_agent.py -v`
  - Verifier Agent: `python -m unittest tests/test_verifier_agent.py -v`
  - Coordinator & Batch Pipeline: `python -m unittest tests/test_coordinator.py -v`
- **Chạy thực thi Batch Processing:** `python main.py`

## 4. Project Structure & Scope
```text
project/
├── data/                 # Database CSV chỉ đọc (Olist datasets)
├── input/                # 50 file JSON khiếu nại (EC_001 -> EC_050)
├── output/               # Kết quả JSON cuối cùng (chỉ xuất sau khi Verifier PASS)
├── logging/              # Nhật ký kiểm toán trace.jsonl & metadata.json
├── agents/               
│   ├── coordinator.py        # [NEW/IMPLEMENT] Nhạc trưởng điều phối & state machine
│   ├── order_seller_agent.py # [NEW/IMPLEMENT] Tra cứu orders, items, sellers, products
│   ├── payment_agent.py      # [DONE] Đối soát thanh toán & tiền hàng
│   ├── delivery_agent.py     # [NEW/IMPLEMENT] Kiểm tra giao trễ & quy trách nhiệm logistics/seller
│   ├── policy_agent.py       # [NEW/IMPLEMENT] Áp dụng 6 quy tắc EC_POLICY_V1
│   └── verifier_agent.py     # [NEW/IMPLEMENT] Kiểm tra chéo 8 trục trước khi xuất output
├── utils/
│   └── data_loader.py        # [MODIFY] Bổ sung hàm đọc orders, sellers, products với O(1) cache
├── specs/
│   ├── payment_agent_spec.md
│   └── full_a2a_system_spec.md
├── tasks/
│   ├── plan.md
│   └── todo.md
├── tests/                # Bộ test TDD phủ toàn bộ các agent
└── main.py               # [NEW/IMPLEMENT] Entry point cho batch process 50 cases
```

## 5. Agent Contracts & Logic Details

### 5.1. Mở rộng OlistDataLoader (`utils/data_loader.py`)
- Bổ sung hàm tải và in-memory cache: `get_order(order_id)`, `get_seller(seller_id)`, `get_product(product_id)`.
- Tuyệt đối giữ nguyên chế độ **read-only**, không ghi/sửa dữ liệu và giữ trọn kiểu `str` cho ID.

### 5.2. Order & Seller Agent (`agents/order_seller_agent.py`)
- **Nghiệp vụ:** Tìm kiếm thông tin đơn hàng từ `olist_orders_dataset.csv`, tra cứu danh sách items và xác nhận sự tồn tại của seller từ `olist_sellers_dataset.csv`.
- **Facts trả về:** `order_found`, object `order` (chứa `order_status` và 3 timestamps), danh sách `items`, `item_total_brl`, `freight_total_brl`, `violating_seller_ids`, `missing_seller_ids`.
- **Candidates:** `order_ids`, `item_ids` (`<order_id>:<order_item_id>`), `seller_ids`. Evidence candidate: `order:...`, `item:...`, `seller:...`.

### 5.3. Delivery Agent (`agents/delivery_agent.py`)
- **Nghiệp vụ:** So sánh chuỗi timestamp `order_delivered_customer_date` với `order_estimated_delivery_date` (đúng hạn hay trễ hạn). So sánh ngày giao cho bên vận chuyển (`carrier_date`) với hạn bưu cục (`shipping_limit_date`) của từng item.
- **Phân định trách nhiệm (`attribution_candidate`):**
  - Trễ + có item bàn giao cho carrier trễ hơn limit -> `seller`.
  - Trễ + mọi item bàn giao đúng limit -> `logistics_provider`.
  - Đúng hạn -> `none`.
  - Hủy/Không khả dụng và thiếu ngày delivery -> `not_applicable`.
  - Đơn delivered nhưng thiếu timestamp -> `unknown` (+ warning).

### 5.4. Policy Agent (`agents/policy_agent.py`)
- **Nghiệp vụ:** Đọc `EvidenceBundle` từ Coordinator, duyệt 6 quy tắc của `EC_POLICY_V1` từ trên xuống dưới (ưu tiên 1 -> 6). Rule đầu tiên khớp sẽ khóa quyết định:
  1. `order_status=canceled` & payment total > 0 $\to$ issue: `canceled_order_paid`, refund: payment total, party: `platform/OLIST_PLATFORM`, action: `issue_full_refund`.
  2. `order_status=unavailable` & payment total > 0 $\to$ issue: `unavailable_order_paid`, refund: payment total, party: `platform/OLIST_PLATFORM`, action: `issue_full_refund`.
  3. Giao trễ do seller (`attribution=seller`) $\to$ issue: `late_delivery_seller`, refund: freight total, party: `seller/<id>`, action: `refund_freight`.
  4. Giao trễ do logistics (`attribution=logistics_provider`) $\to$ issue: `late_delivery_logistics`, refund: freight total, party: `logistics_provider/LOGISTICS_PROVIDER`, action: `refund_freight`.
  5. Payment row count $\ge 2$ & difference $\le 0.10$ $\to$ issue: `valid_split_payment`, refund: 0.00, status: `no_action`, action: `explain_valid_split_payment`.
  6. Giao đúng hạn & payment reconciled $\to$ issue: `unsupported_late_claim`, refund: 0.00, status: `no_action`, action: `reject_late_refund`.
- **Confidence:** Luôn trả `1.0` nếu đầy đủ critical facts cho rule. Trả rõ `excluded_higher_priority_rules`.

### 5.5. Verifier Agent (`agents/verifier_agent.py`)
- **Nghiệp vụ:** Thẩm định 8 trục kiểm tra (`schema`, `identity`, `entities`, `evidence`, `financials`, `policy`, `limits`, `determinism`).
- **Ràng buộc giới hạn:** Tối đa 5 entity mỗi tập (`order_ids`, `item_ids`, `seller_ids`, `payment_ids`), tối đa 10 `evidence_ids`, 3 causes, 3 parties, 5 actions. Mảng phải loại trùng và duy trì thứ tự ổn định.
- **Phái quyết:** Trả `verdict: "PASS"` hoặc `"FAIL"` cùng dict `checks` và `recomputed_values`.

### 5.6. Coordinator Agent & Main Batch Runner
- **Coordinator:** Quản lý State Machine (`RECEIVED -> VALIDATED -> DISPATCHED -> COLLECTED -> POLICY_DECIDED -> DRAFTED -> VERIFYING -> VERIFIED -> WRITTEN`). Thực hiện fan-out `AgentTask`, gom nhặt `EvidenceBundle`, gửi Policy, tạo draft, thử nghiệm với Verifier. Chỉ khi PASS mới thực hiện ghi file JSON vào `output/<case_id>.json`.
- **Main (`main.py`):** Duyệt trúng 50 file `input/EC_001.json` đến `EC_050.json`. Ghi nhật ký thực tế theo chuẩn JSONL vào `logging/trace.jsonl` và khai báo cấu hình mô hình AI vào `logging/metadata.json`.

## 6. Boundaries & Guardrails
- **ALWAYS DO:** Dùng `Decimal` cho tài chính; bẫy lỗi và trả `ErrorDetail` chuẩn; chạy test PASS trước mỗi lần đóng gói slice; giới hạn đầu ra đúng mục 11 của tài liệu kiến trúc.
- **ASK FIRST:** Thay đổi schema của `AgentTask` / `AgentResult` hoặc chỉnh sửa bất kỳ test case nào đã được khóa của `Payment Agent`.
- **NEVER DO:** 
  - KHÔNG ghi vào `output/` khi Verifier chưa đánh dấu `PASS`.
  - KHÔNG thay đổi, ghi đè hoặc tạo thêm file trong thư mục `data/` và `input/`.
  - KHÔNG dùng `float()` khi cộng dồn tiền BRL.
  - KHÔNG join trực tiếp các bảng 1:N thô vào nhau.
  - KHÔNG đưa log trace hay internal explanations vào file JSON output nộp bài.

## 7. Success Criteria
- Toàn bộ 12 test cases của Payment Agent hiện tại tiếp tục PASS 100%.
- Các bộ Unit Test mới cho `Order & Seller`, `Delivery`, `Policy`, `Verifier`, `Coordinator` đều đạt 100% PASS.
- Khi thi hành lệnh `python main.py`, hệ thống tự động xử lý thành công 50 case, xuất ra đúng 50 file hợp lệ từ `output/EC_001.json` đến `output/EC_050.json`, kèm theo file log hoàn chỉnh tại `logging/trace.jsonl` và `logging/metadata.json`.

## 8. Open Questions / Clarifications
- *Không có. Tài liệu kiến trúc `architecture.md` đã cung cấp đặc tả JSON Schema và danh sách Policy vô cùng tường minh.*
