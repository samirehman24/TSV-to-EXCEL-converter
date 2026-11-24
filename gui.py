
from pathlib import Path

from PyQt5.QtCore import Qt, QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (
    QWidget,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QFileDialog,
    QMessageBox,
    QTabWidget,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QAbstractItemView
)

from validator import validate_tsv
from converter import convert_tsv_to_excel


# Drag and drop component

class DropArea(QLabel):

    file_dropped = pyqtSignal(str)

    def __init__(self):
        super().__init__()

        self.setObjectName("dropArea")
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(130)

        self.default_text = (
            "Drag & Drop your TSV or TXT file here\n\n"
            "Supported formats: .tsv and .txt"
        )

        self.setText(self.default_text)

    def dragEnterEvent(self, event):

        if event.mimeData().hasUrls():

            event.acceptProposedAction()

            self.setStyleSheet("""
                background-color: #dcfce7;
                border: 2px dashed #217346;
                border-radius: 10px;
                color: #217346;
                font-size: 17px;
            """)

            self.setText("Drop your file here!")

        else:
            event.ignore()

    def dragMoveEvent(self, event):

        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):

        self.setStyleSheet("")
        self.setText(self.default_text)
        event.accept()

    def dropEvent(self, event):

        self.setStyleSheet("")
        self.setText(self.default_text)

        urls = event.mimeData().urls()

        if len(urls) != 1:

            QMessageBox.warning(
                self,
                "Invalid Selection",
                "Please drop only one file at a time."
            )
            return

        if not urls[0].isLocalFile():
            event.ignore()
            return

        file_path = urls[0].toLocalFile()
        path = Path(file_path)

        if not path.is_file():

            QMessageBox.warning(
                self,
                "Invalid File",
                "Please drop a valid file."
            )
            return

        if path.suffix.lower() not in (".txt", ".tsv"):

            QMessageBox.warning(
                self,
                "Unsupported File",
                "Only TXT and TSV files are supported."
            )
            return

        self.file_dropped.emit(file_path)
        event.acceptProposedAction()



# Main application window
class MainWindow(QWidget):

    def __init__(self):
        super().__init__()

        self.input_file = None
        self.output_file = None

        self.init_ui()

    def init_ui(self):

        self.setWindowTitle(
            "TSV to Excel Converter - V1.0"
        )

        self.resize(1150, 800)
        self.setMinimumSize(800, 650)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 20, 25, 20)
        layout.setSpacing(12)

        # Application heading
        heading = QLabel("TSV to Excel Converter")
        heading.setObjectName("heading")
        heading.setAlignment(Qt.AlignCenter)

        subtitle = QLabel(
            "Accurate | Reliable | Easy to use"
        )
        subtitle.setObjectName("subtitle")
        subtitle.setAlignment(Qt.AlignCenter)

        layout.addWidget(heading)
        layout.addWidget(subtitle)

        # Input tabs
        self.tabs = QTabWidget()

        # TAB 1: Import file
        file_tab = QWidget()
        file_layout = QVBoxLayout(file_tab)

        self.drop_area = DropArea()
        self.drop_area.file_dropped.connect(
            self.select_file
        )

        self.browse_button = QPushButton("Browse File")
        self.browse_button.clicked.connect(
            self.browse_file
        )

        self.file_label = QLabel("No file selected")
        self.file_label.setTextFormat(Qt.PlainText)
        self.file_label.setWordWrap(True)

        file_layout.addWidget(self.drop_area)
        file_layout.addWidget(self.browse_button)
        file_layout.addWidget(self.file_label)

        # TAB 2: Paste TSV data
        paste_tab = QWidget()
        paste_layout = QVBoxLayout(paste_tab)

        self.text_input = QPlainTextEdit()

        self.text_input.setPlaceholderText(
            "Paste your tab-separated data here...\n\n"
            "Name\tCity\tZipCode\n"
            "ABC Electric\tLinden\t07036"
        )

        self.text_input.setTabChangesFocus(False)
        self.text_input.setLineWrapMode(
            QPlainTextEdit.NoWrap
        )

        paste_layout.addWidget(self.text_input)

        self.clear_button = QPushButton("Clear Text")
        self.clear_button.clicked.connect(
            self.text_input.clear
        )

        paste_layout.addWidget(self.clear_button)

        self.tabs.addTab(file_tab, "Import File")
        self.tabs.addTab(paste_tab, "Paste TSV Data")

        self.tabs.setMaximumHeight(280)

        layout.addWidget(self.tabs)

        # Action buttons
        button_layout = QHBoxLayout()

        self.preview_button = QPushButton(
            "Validate & Preview"
        )

        self.preview_button.clicked.connect(
            self.preview_data
        )

        self.convert_button = QPushButton(
            "Convert to Excel"
        )

        self.convert_button.clicked.connect(
            self.convert_data
        )

        button_layout.addWidget(self.preview_button)
        button_layout.addWidget(self.convert_button)

        layout.addLayout(button_layout)

        # Preview table
        preview_heading = QLabel("Data Preview")
        preview_heading.setStyleSheet(
            "font-size: 17px; font-weight: bold;"
        )

        layout.addWidget(preview_heading)

        self.table = QTableWidget()

        self.table.setAlternatingRowColors(True)

        self.table.setEditTriggers(
            QAbstractItemView.NoEditTriggers
        )

        self.table.setSelectionBehavior(
            QAbstractItemView.SelectRows
        )

        self.table.setWordWrap(False)

        layout.addWidget(self.table, 1)

        # Validation and conversion status
        self.status_label = QLabel(
            "Import a file or paste TSV data to begin."
        )

        self.status_label.setObjectName("status")
        self.status_label.setTextFormat(Qt.PlainText)
        self.status_label.setWordWrap(True)

        layout.addWidget(self.status_label)

        # Output folder button
        self.open_folder_button = QPushButton(
            "Open Output Folder"
        )

        self.open_folder_button.setEnabled(False)

        self.open_folder_button.clicked.connect(
            self.open_folder
        )

        layout.addWidget(self.open_folder_button)

        # Clear old previews when the input changes
        self.tabs.currentChanged.connect(
            self.clear_preview
        )

        self.text_input.textChanged.connect(
            self.clear_preview
        )

    # Select file using file browser
    def browse_file(self):

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select TSV File",
            "",
            "TSV Files (*.tsv *.txt)"
        )

        if file_path:
            self.select_file(file_path)

    # Handle selected or dropped file
    def select_file(self, file_path):

        path = Path(file_path)

        if (
            not path.is_file()
            or path.suffix.lower() not in (".txt", ".tsv")
        ):

            QMessageBox.warning(
                self,
                "Invalid File",
                "Please select a valid TXT or TSV file."
            )
            return

        self.input_file = path

        self.tabs.setCurrentIndex(0)
        self.clear_preview()

        self.file_label.setText(
            f"Selected file: {path.name}"
        )

        self.file_label.setToolTip(str(path))

        self.status_label.setText(
            "File loaded. Click Validate & Preview."
        )

    # Reset preview
    def clear_preview(self):

        self.table.clear()
        self.table.setRowCount(0)
        self.table.setColumnCount(0)

        self.status_label.setText(
            "Input changed. Validate before conversion."
        )

    # Read current input
    def get_input_data(self):

        if self.tabs.currentIndex() == 0:

            if self.input_file is None:
                raise ValueError(
                    "Please select a TSV or TXT file."
                )

            with open(
                self.input_file,
                "r",
                encoding="utf-8-sig",
                newline=""
            ) as file:
                return file.read()

        else:

            text = self.text_input.toPlainText()

            if not text.strip():
                raise ValueError(
                    "Please paste your TSV data."
                )

            return text

    # Validate current data
    def validate_data(self, text):

        result = validate_tsv(text=text)

        if not result["valid"]:

            errors = result["errors"]

            message = "\n".join(errors[:15])

            if len(errors) > 15:
                message += (
                    f"\n... and {len(errors) - 15} more errors."
                )

            raise ValueError(message)

        return result

    # Display validation and preview
    def preview_data(self):

        try:

            text = self.get_input_data()
            result = self.validate_data(text)

            self.populate_table(result)

        except Exception as error:

            self.clear_preview()
            self.show_error(str(error))

    # Populate table
    def populate_table(self, result):

        headers = result["headers"]
        rows = result["rows"]

        # Display only the first 100 records
        preview_rows = rows[:100]

        # Limit the preview to 100 columns
        preview_headers = headers[:100]

        self.table.clear()

        self.table.setColumnCount(
            len(preview_headers)
        )

        self.table.setRowCount(len(preview_rows))

        self.table.setHorizontalHeaderLabels(
            preview_headers
        )

        for row_index, row in enumerate(preview_rows):

            for column_index, value in enumerate(row[:100]):

                item = QTableWidgetItem(value)

                self.table.setItem(
                    row_index,
                    column_index,
                    item
                )

        self.table.resizeColumnsToContents()

        # Prevent extremely wide columns
        for column in range(len(preview_headers)):

            width = self.table.columnWidth(column)

            self.table.setColumnWidth(
                column,
                min(max(width, 100), 350)
            )

        status = (
            f"Validation passed | "
            f"Records: {len(rows)} | "
            f"Columns: {len(headers)} | "
            f"Preview: {len(preview_rows)} rows, "
            f"{len(preview_headers)} columns"
        )

        if result["warnings"]:

            status += (
                f"\nWarnings: {len(result['warnings'])} | "
                + "; ".join(result["warnings"][:3])
            )

        self.status_label.setText(status)

    # Convert TSV to Excel
    def convert_data(self):

        try:

            text = self.get_input_data()

            # Always validate again before converting
            validation = self.validate_data(text)

            self.populate_table(validation)

            # Default output filename
            if self.tabs.currentIndex() == 0:

                default_path = str(
                    self.input_file.with_suffix(".xlsx")
                )

            else:

                default_path = str(
                    Path.home() / "converted_data.xlsx"
                )

            output_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save Excel File",
                default_path,
                "Excel Workbook (*.xlsx)",
                options=QFileDialog.DontConfirmOverwrite
            )

            if not output_path:
                return

            output_path = Path(output_path)

            if output_path.suffix.lower() != ".xlsx":

                output_path = output_path.with_suffix(
                    ".xlsx"
                )

            # Confirm overwriting
            if output_path.exists():

                reply = QMessageBox.question(
                    self,
                    "File Already Exists",
                    f"{output_path.name} already exists.\n"
                    "Do you want to overwrite it?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )

                if reply != QMessageBox.Yes:
                    return

            # Call our existing conversion engine
            result = convert_tsv_to_excel(
                text=text,
                output_path=output_path
            )

            self.output_file = Path(
                result["output_file"]
            )

            self.open_folder_button.setEnabled(True)

            self.status_label.setText(
                f"Conversion successful!\n"
                f"Records: {result['records']} | "
                f"Columns: {result['columns']}\n"
                f"Saved to: {self.output_file}"
            )

            self.show_success(result)

        except PermissionError:

            self.show_error(
                "Unable to save the Excel file.\n"
                "Close the file if it is open in Excel "
                "or choose a writable folder."
            )

        except Exception as error:

            self.show_error(str(error))

    # Success popup
    def show_success(self, result):

        message = QMessageBox(self)

        message.setIcon(QMessageBox.Information)

        message.setWindowTitle(
            "Conversion Successful"
        )

        message.setTextFormat(Qt.PlainText)

        message.setText(
            "Your Excel file has been created successfully!"
        )

        message.setInformativeText(
            f"Records: {result['records']}\n"
            f"Columns: {result['columns']}\n\n"
            f"Location:\n{result['output_file']}"
        )

        folder_button = message.addButton(
            "Open Folder",
            QMessageBox.ActionRole
        )

        message.addButton(QMessageBox.Ok)

        message.exec_()

        if message.clickedButton() == folder_button:
            self.open_folder()

    # Open output location
    def open_folder(self):

        if self.output_file:

            folder = self.output_file.parent

            success = QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(folder))
            )

            if not success:

                self.show_error(
                    f"Unable to open folder:\n{folder}"
                )

    # Error popup
    def show_error(self, message):

        self.status_label.setText(
            f"Error: {message}"
        )

        popup = QMessageBox(self)
        popup.setIcon(QMessageBox.Critical)
        popup.setWindowTitle("Application Error")
        popup.setTextFormat(Qt.PlainText)
        popup.setText(message)
        popup.exec_()
