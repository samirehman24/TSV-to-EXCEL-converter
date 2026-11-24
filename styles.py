
APP_STYLE = """
QWidget {
    background-color: #f1f5f9;
    color: #1e293b;
    font-family: Segoe UI;
    font-size: 13px;
}

QPushButton {
    background-color: #217346;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 12px 20px;
    font-weight: bold;
}

QPushButton:hover {
    background-color: #185c37;
}

QPushButton:disabled {
    background-color: #cbd5e1;
    color: #64748b;
}

QPlainTextEdit, QTableWidget {
    background-color: white;
    border: 1px solid #cbd5e1;
    border-radius: 5px;
    selection-background-color: #bbf7d0;
    selection-color: #14532d;
}

QHeaderView::section {
    background-color: #217346;
    color: white;
    padding: 8px;
    border: 1px solid #185c37;
    font-weight: bold;
}

QTabWidget::pane {
    border: 1px solid #cbd5e1;
    background-color: white;
}

QTabBar::tab {
    background-color: #e2e8f0;
    padding: 12px 25px;
}

QTabBar::tab:selected {
    background-color: #217346;
    color: white;
}

QLabel#heading {
    font-size: 28px;
    font-weight: bold;
    color: #217346;
}

QLabel#subtitle {
    color: #64748b;
    font-size: 13px;
}

QLabel#dropArea {
    border: 2px dashed #94a3b8;
    border-radius: 10px;
    background-color: #ffffff;
    color: #475569;
    font-size: 17px;
    padding: 20px;
}

QLabel#status {
    background-color: white;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    padding: 12px;
}
"""
