"""下载已登记的公开参考数据；原始文件只保存在 Git 忽略目录。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


SOURCES = {
    "uci-ai4i-2020": {
        "url": "https://archive.ics.uci.edu/static/public/601/ai4i+2020+predictive+maintenance+dataset.zip",
        "filename": "ai4i_2020_predictive_maintenance.zip",
        "license": "CC BY 4.0",
    },
}


def download(source_id: str) -> dict[str, str | int]:
    source = SOURCES[source_id]
    output_dir = ROOT / "数据资料" / "公开参考数据" / "原始数据"
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / source["filename"]
    with urlopen(source["url"], timeout=60) as response:
        content = response.read()
    output.write_bytes(content)
    return {
        "source_id": source_id,
        "filename": output.name,
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "license": source["license"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="下载经许可登记的公开参考数据。")
    parser.add_argument("--source", choices=sorted(SOURCES), required=True)
    args = parser.parse_args()
    print(json.dumps(download(args.source), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
