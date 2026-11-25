"""对话助手页面不向业务人员展示内部字段名或枚举值。"""

import unittest
from pathlib import Path


class AssistantUiTextTests(unittest.TestCase):
    def test_internal_field_names_and_enums_are_mapped_before_display(self):
        script = (Path(__file__).resolve().parents[1] / "app" / "static" / "js" / "assistant_chat.js").read_text(encoding="utf-8")
        self.assertIn("fieldLabels[name] || '相关信息'", script)
        self.assertIn("formatValue(name, data.field_suggestions[name])", script)
        self.assertIn("shutdown: {YES: '已停机'", script)


if __name__ == "__main__":
    unittest.main()
