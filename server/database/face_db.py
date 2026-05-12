import sqlite3
from datetime import datetime
from pathlib import Path

import numpy as np

from config import settings


class FaceDB:
    """人脸数据库，使用 SQLite 存储人员信息，numpy 存储特征向量。"""

    def __init__(self) -> None:
        """初始化数据库连接并创建表。"""
        self.db_path = settings.face_db_sqlite
        self.db_dir = Path(settings.face_db_dir)
        self.db_dir.mkdir(parents=True, exist_ok=True)

        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_table()

    def _create_table(self) -> None:
        """创建人脸信息表。"""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS faces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                embedding_file TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        self.conn.commit()

    def add_face(self, name: str, embedding: np.ndarray) -> None:
        """添加人脸到数据库。

        Args:
            name: 人名
            embedding: 特征向量

        Raises:
            sqlite3.IntegrityError: 如果人名已存在
        """
        embedding_file = f"{name}.npy"
        np.save(self.db_dir / embedding_file, embedding)

        self.conn.execute(
            "INSERT INTO faces (name, embedding_file, created_at) VALUES (?, ?, ?)",
            (name, embedding_file, datetime.now().isoformat()),
        )
        self.conn.commit()

    def remove_face(self, name: str) -> bool:
        """从数据库中删除人脸。

        Args:
            name: 人名

        Returns:
            是否成功删除
        """
        cursor = self.conn.execute(
            "SELECT embedding_file FROM faces WHERE name = ?", (name,),
        )
        row = cursor.fetchone()
        if row is None:
            return False

        embedding_path = self.db_dir / row["embedding_file"]
        if embedding_path.exists():
            embedding_path.unlink()

        self.conn.execute("DELETE FROM faces WHERE name = ?", (name,))
        self.conn.commit()
        return True

    def list_faces(self) -> list[dict]:
        """列出所有已录入的人脸。

        Returns:
            人脸信息列表
        """
        cursor = self.conn.execute(
            "SELECT id, name, embedding_file, created_at FROM faces ORDER BY id",
        )
        return [dict(row) for row in cursor.fetchall()]

    def load_all_embeddings(self) -> tuple[np.ndarray, list[str]]:
        """加载所有特征向量到内存。

        Returns:
            (特征向量矩阵, 人名列表)
        """
        faces = self.list_faces()
        if not faces:
            return np.empty((0, 512), dtype=np.float32), []

        embeddings = []
        names = []
        for face in faces:
            embedding_path = self.db_dir / face["embedding_file"]
            if embedding_path.exists():
                embeddings.append(np.load(embedding_path))
                names.append(face["name"])

        if not embeddings:
            return np.empty((0, 512), dtype=np.float32), []

        return np.stack(embeddings), names

    def close(self) -> None:
        """关闭数据库连接。"""
        self.conn.close()


_db: FaceDB | None = None


def get_face_db() -> FaceDB:
    """获取全局人脸数据库单例。"""
    global _db
    if _db is None:
        _db = FaceDB()
    return _db
