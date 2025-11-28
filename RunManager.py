# AutoPYVideos Manager 启动脚本
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "manager"))

from App import Main

if __name__ == "__main__":
    Main()
