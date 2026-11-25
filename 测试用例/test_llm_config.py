"""大模型配置默认值应给推理型模型保留足够的可见回复额度。"""

import unittest

from app.config import Config


class LlmConfigTests(unittest.TestCase):
    def test_default_output_budget_is_sufficient_for_visible_reply(self):
        self.assertGreaterEqual(Config.LLM_MAX_OUTPUT_TOKENS, 1200)


if __name__ == "__main__":
    unittest.main()
