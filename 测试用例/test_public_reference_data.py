"""公开参考数据下载脚本的边界与元数据校验。"""

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "运行脚本" / "download_public_reference_data.py"
spec = importlib.util.spec_from_file_location("download_public_reference_data", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PublicReferenceDataTests(unittest.TestCase):
    def test_only_allowlisted_source_is_downloadable(self):
        self.assertEqual(set(module.SOURCES), {"uci-ai4i-2020"})

    def test_allowlisted_source_has_official_url_and_clear_license(self):
        source = module.SOURCES["uci-ai4i-2020"]
        self.assertTrue(source["url"].startswith("https://archive.ics.uci.edu/"))
        self.assertEqual(source["license"], "CC BY 4.0")
