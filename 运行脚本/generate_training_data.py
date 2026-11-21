"""生成可复现的虚构分类数据；仅供课程训练和评测，不代表真实企业工单。"""

import csv
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "数据资料" / "训练数据" / "模拟训练工单.csv"

TEMPLATES = {
    "THERMAL_COOLING": ["控制柜温度报警，风扇声音异常", "设备连续运行后温度升高，外壳发烫", "主轴附近温度持续升高，冷却效果变差", "冷却液流量明显变小，屏幕提示冷却相关报警", "加工过程中温控报警反复出现", "控制柜屏幕出现温度提示，同时听到冷却风扇转速异常", "温控报警出现前设备仍能操作，冷却液循环明显变弱"],
    "MECHANICAL": ["传动侧运行时持续有异响，伴随明显振动", "主轴转动时声音异常，设备振动比平时大", "机构动作不顺畅，偶尔出现卡滞", "输送带运行时跑偏，并听到摩擦声", "设备启动后传动部位有间歇性敲击声", "传动机构有摩擦声和振动，但屏幕上的传感数据仍连续更新", "设备运行有卡滞感，未出现通信中断或数据丢失提示"],
    "ELECTRICAL_CONTROL": ["通电后控制面板没有显示，设备无法启动", "设备运行中控制屏突然黑屏，按键没有反应", "控制器提示故障，启动指令无法执行", "设备上电后显示异常，无法进入正常操作界面", "操作面板反复重启，设备不能正常开始工作", "控制柜供电正常但触摸屏无显示，设备无法进入操作界面"],
    "SENSOR_COMMUNICATION": ["传感器读数跳动，屏幕显示数据异常", "设备提示通信中断，采集数据无法更新", "控制器间歇提示无法接收传感信号", "运行中采集数据丢失，报警信息不完整", "通信报警反复出现，设备状态无法正常读取", "屏幕数据不更新并提示通信中断，未观察到设备发热或风扇异常", "冷却风扇运行正常，控制器仍提示采集信号丢失"],
}
PROVENANCE = {
    "THERMAL_COOLING": ("公开资料改写", "SIEMENS-808D-SERVICE-2017", "SINUMERIK 808D", "700018|700019", "冷却/温控异常仅作为客服分诊线索；停机或风险未知时必须转人工。"),
    "ELECTRICAL_CONTROL": ("公开资料改写", "SCHNEIDER-ATV320-SCF4", "Altivar 320", "SCF4", "功率或电缆短路风险不作远程诊断，必须人工确认。"),
    "MECHANICAL": ("课程模拟", "COURSE-MECHANICAL-001", "通用传动设备", "", "仅记录客户可观察到的异响、振动或卡滞，不推断部件损坏。"),
    "SENSOR_COMMUNICATION": ("课程模拟", "COURSE-COMM-001", "通用控制系统", "", "通信和传感现象需结合设备型号、报警信息人工核对。"),
}
SUFFIXES = ["，请协助确认处理方向。", "，暂未确认是否需要停机。", "，报警代码暂未记录。", "，客户无法判断是否存在安全风险。", "，需要进一步核对设备型号。"]
SPLITS = [("train", 36), ("validation", 12), ("test", 12)]


def main():
    randomizer = random.Random(20261120)
    rows = []
    for category, templates in TEMPLATES.items():
        source_type, source_id, equipment_scope, alarm_code, review_note = PROVENANCE[category]
        for split, count in SPLITS:
            # 每个集合使用独立表达模板，避免同一句式跨训练、验证、测试集合泄漏。
            # 按模板序号分桶：三组都有多种业务表达，且不共用同一句式。
            usable = {"train": templates[0::3], "validation": templates[1::3], "test": templates[2::3]}[split]
            for index in range(count):
                template = usable[index % len(usable)]
                rows.append({
                    "sample_id": f"SIM-{category[:3]}-{split[:1].upper()}-{index + 1:03d}",
                    "split": split,
                    "category": category,
                    "description": template + randomizer.choice(SUFFIXES),
                    "source_type": source_type,
                    "source_id": source_id,
                    "equipment_scope": equipment_scope,
                    "alarm_code": alarm_code,
                    "shutdown": "UNKNOWN",
                    "safety_risk": "UNKNOWN",
                    "human_review_required": "true",
                    "review_note": review_note,
                })
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["sample_id", "split", "category", "description", "source_type", "source_id", "equipment_scope", "alarm_code", "shutdown", "safety_risk", "human_review_required", "review_note"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"已生成 {len(rows)} 条虚构样本：{OUTPUT}")


if __name__ == "__main__":
    main()
