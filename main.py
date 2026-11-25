
import sys
import ctypes
from pathlib import Path

from PyQt5.QtWidgets import QApplication, QPushButton
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon, QPixmap

from gui import MainWindow
from styles import APP_STYLE


def main():

    # Windows taskbar application identity
    if sys.platform == "win32":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "TSVtoExcel.Converter.Version1"
        )

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLE)
    app.setApplicationName("TSV to Excel Converter")

    # Load the logo using its absolute path
    base_path = Path(__file__).resolve().parent
    logo_path = base_path / "app_logo.png"

    pixmap = QPixmap(str(logo_path))

    print("Logo path:", logo_path, flush=True)
    print("File exists:", logo_path.exists(), flush=True)
    print("Image loaded:", not pixmap.isNull(), flush=True)

    icon = QIcon(pixmap)
    app.setWindowIcon(icon)

    window = MainWindow()
    window.setWindowIcon(icon)
        # Pointing hand cursor for buttons
    for button in window.findChildren(QPushButton):
        button.setCursor(Qt.PointingHandCursor)

    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
