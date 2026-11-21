"""校验本地脱敏工单导入文件；不上传、不输出工单原文。"""

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.algorithms.deidentification import find_sensitive_patterns

REQUIRED_FIELDS = {
    "source_ticket_token", "asset_token", "equipment_type", "description_deidentified",
    "operating_state", "shutdown", "safety_risk", "alarm_code_status",
    "data_classification", "processing_status",
}


def validate_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    findings = []
    for index, row in enumerate(rows, start=2):
        token = row.get("source_ticket_token", "") or f"ROW-{index}"
        missing = sorted(field for field in REQUIRED_FIELDS if not (row.get(field) or "").strip())
        if missing:
            findings.append({"source_ticket_token": token, "issue": "MISSING_REQUIRED_FIELDS", "details": ",".join(missing)})
        for field in ("description_deidentified", "submitter_note_deidentified"):
            patterns = find_sensitive_patterns(row.get(field, ""))
            if patterns:
                findings.append({"source_ticket_token": token, "issue": "POSSIBLE_SENSITIVE_DATA", "details": f"{field}:{','.join(patterns)}"})
        if row.get("data_classification") not in {"DEIDENTIFIED_INTERNAL", "DEIDENTIFIED_RESTRICTED"}:
            findings.append({"source_ticket_token": token, "issue": "INVALID_CLASSIFICATION", "details": "必须使用脱敏数据分级"})
        if row.get("processing_status") != "PENDING_DUAL_ANNOTATION":
            findings.append({"source_ticket_token": token, "issue": "INVALID_INITIAL_STATUS", "details": "导入初始状态必须为 PENDING_DUAL_ANNOTATION"})
    return findings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="本地脱敏工单 CSV 路径")
    parser.add_argument("--report", required=True, help="不含工单原文的校验报告 JSON 路径")
    args = parser.parse_args()
    with Path(args.input).open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    findings = validate_rows(rows)
    report = {"row_count": len(rows), "finding_count": len(findings), "findings": findings}
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"脱敏校验完成：{len(rows)} 条，发现 {len(findings)} 项。")
    if findings:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
