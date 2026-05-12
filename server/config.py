from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """服务器配置，支持 .env 文件覆盖。"""

    # 服务器
    server_host: str = "0.0.0.0"
    server_port: int = 8000

    # YOLO 人脸检测
    yolo_model_path: str = str(Path(__file__).parent.parent / "models" / "yolov8n-face.pt")
    yolo_confidence_threshold: float = 0.5

    # ArcFace 人脸识别
    arcface_model_name: str = "buffalo_l"
    face_match_threshold: float = 0.4

    # 人脸数据库
    face_db_dir: str = str(Path(__file__).parent.parent / "face_db")
    face_db_sqlite: str = str(Path(__file__).parent.parent / "face_db" / "faces.db")

    # 模型缓存目录
    model_dir: str = str(Path(__file__).parent.parent / "models")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
