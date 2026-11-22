"""显式构建本地课程虚构候选快照；不训练模型，不读取冻结测试集。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app
from app.models import TrainingCandidateReview
from app.services.training_dataset import build_versioned_snapshot


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "本地运行数据" / "训练候选" / "版本化正式训练集"


app = create_app()
with app.app_context():
    reviews = TrainingCandidateReview.query.filter_by(decision="ACCEPTED").order_by(TrainingCandidateReview.id).all()
    manifest, location = build_versioned_snapshot(reviews, OUTPUT)
    if location:
        print(f"已构建本地候选快照：{location}，共 {manifest['sample_count']} 条；未训练模型。")
    else:
        print("没有满足课程虚构与案例家族要求的已接受候选，未写入快照。")
