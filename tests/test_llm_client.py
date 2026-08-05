import unittest
import os
from unittest.mock import patch
from utils.llm_client import LLMClient

class TestLLMClient(unittest.TestCase):
    def setUp(self):
        self.client = LLMClient()

    def test_default_model_name_and_params(self):
        self.assertEqual(self.client.default_model, "gemini-flash-lite-latest")
        self.assertEqual(self.client.max_parameters, "10B")

    def test_fallback_when_no_api_key(self):
        # Đảm bảo không có key trong môi trường để kiểm thử offline/fallback an toàn
        with patch.dict(os.environ, {}, clear=True):
            response = self.client.generate(
                prompt="Tóm tắt tình trạng đối soát: Khớp hoàn toàn.",
                system_instruction="Bạn là chuyên gia kiểm toán."
            )
            self.assertTrue("Khớp hoàn toàn" in response or "Đánh giá nghiệp vụ" in response)
            self.assertIsInstance(response, str)

    @patch("urllib.request.urlopen")
    def test_gemini_api_invocation(self, mock_urlopen):
        # Giả lập gọi Google Gemini API thành công qua giao thức REST urllib
        mock_response = unittest.mock.MagicMock()
        mock_response.read.return_value = b'{"candidates": [{"content": {"parts": [{"text": "Phan tich tu Gemini: Giao hang dung han."}]}}]}'
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test_fake_gemini_key"}, clear=True):
            client = LLMClient()
            res = client.generate("Kiểm tra đơn hàng", model="gemini-flash-lite-latest")
            self.assertIn("Phan tich tu Gemini", res)

    @patch("urllib.request.urlopen")
    def test_openai_compatible_invocation(self, mock_urlopen):
        mock_response = unittest.mock.MagicMock()
        mock_response.read.return_value = b'{"choices": [{"message": {"content": "Phan tich tu OpenRouter: Hoan tien freight."}}]}'
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test_openai_key", "OPENAI_BASE_URL": "https://api.mock.in/v1"}, clear=True):
            client = LLMClient()
            res = client.generate("Kiểm tra bồi thường", model="gemini-flash-lite-latest")
            self.assertIn("Phan tich tu OpenRouter", res)

if __name__ == "__main__":
    unittest.main()
