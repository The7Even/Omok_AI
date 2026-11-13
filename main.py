import os
os.environ["NUMBA_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"

import sys
from PyQt6.QtWidgets import QApplication
from engine.search import warmup_engine
from ui.main_window import MainWindow


def main():
    warmup_engine()
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()