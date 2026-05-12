import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import settings
from database.face_db import get_face_db
from recognition.arcface_recognizer import get_recognizer


def enroll_face(name: str, image_dir: str) -> None:
    """批量录入人脸图片到数据库。

    Args:
        name: 人名
        image_dir: 图片目录路径
    """
    image_dir_path = Path(image_dir)
    if not image_dir_path.exists():
        print(f"错误：目录不存在 {image_dir_path}")
        return

    image_extensions = {".jpg", ".jpeg", ".png", ".bmp"}
    image_files = [
        f for f in image_dir_path.iterdir()
        if f.suffix.lower() in image_extensions
    ]

    if not image_files:
        print(f"错误：目录中没有找到图片文件 {image_dir_path}")
        return

    print(f"找到 {len(image_files)} 张图片，开始处理...")

    recognizer = get_recognizer()
    db = get_face_db()

    embeddings: list[np.ndarray] = []
    success_count = 0
    fail_count = 0

    for img_path in image_files:
        img = cv2.imread(str(img_path))
        if img is None:
            print(f"  跳过：无法读取 {img_path.name}")
            fail_count += 1
            continue

        embedding = recognizer.extract_embedding(img)
        if embedding is None:
            print(f"  跳过：未检测到人脸 {img_path.name}")
            fail_count += 1
            continue

        embeddings.append(embedding)
        success_count += 1
        print(f"  成功：{img_path.name}")

    if not embeddings:
        print("错误：没有成功提取到任何人脸特征")
        return

    mean_embedding = np.mean(embeddings, axis=0)
    norm = np.linalg.norm(mean_embedding)
    if norm > 0:
        mean_embedding = mean_embedding / norm

    try:
        db.add_face(name, mean_embedding)
    except Exception as e:
        print(f"错误：保存失败 - {e}")
        return

    print(f"\n录入完成：{name}")
    print(f"  成功：{success_count} 张")
    print(f"  失败：{fail_count} 张")
    print(f"  特征向量已保存到数据库")


def main() -> None:
    parser = argparse.ArgumentParser(description="人脸录入脚本")
    parser.add_argument("--name", required=True, help="人名")
    parser.add_argument("--dir", required=True, help="图片目录路径")
    args = parser.parse_args()

    enroll_face(args.name, args.dir)


if __name__ == "__main__":
    main()
