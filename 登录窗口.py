import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QHBoxLayout, QPushButton, QVBoxLayout, QSizePolicy, QSpacerItem, QLineEdit
from PyQt5.QtCore import Qt, QRect
from PyQt5.QtGui import QMouseEvent


class RoundedWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        central_widget.setStyleSheet("""
            QWidget {
                background-color: #2E3440;
                border-radius: 15px;
                
            }
        """)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(5)

        spacer = QSpacerItem(20, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        button_layout.addItem(spacer)

        minimize_button = QPushButton("─")
        minimize_button.setFixedSize(30, 30)
        minimize_button.setStyleSheet("""
            QPushButton {
                background-color: #4C566A;
                color: white;
                border-radius: 15px;
                font-size: 16px;
                border: none;
            }
            QPushButton:hover {
                background-color: #5E81AC;
            }
        """)
        minimize_button.clicked.connect(self.showMinimized)
        button_layout.addWidget(minimize_button)

        close_button = QPushButton("×")
        close_button.setFixedSize(30, 30)
        close_button.setStyleSheet("""
            QPushButton {
                background-color: #BF616A;
                color: white;
                border-radius: 15px;
                font-size: 16px;
                border: none;
            }
            QPushButton:hover {
                background-color: #D08770;
            }
        """)
        close_button.clicked.connect(self.close)
        button_layout.addWidget(close_button)

        main_layout.addLayout(button_layout)

        spacer_bottom = QWidget()
        spacer_bottom.setStyleSheet("background-color: transparent; border: none;")  # 透明背景
        spacer_bottom.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        main_layout.addWidget(spacer_bottom)

        self.resize(400, 100)

        self.center()

        self.drag_pos = None
        self.drag_edge = None
        self.resize_margin = 10

        textbox_layout = QHBoxLayout()
        self.textbox = QLineEdit(self)
        self.textbox.setPlaceholderText('请输入你的用户名')
        self.textbox.setFixedSize(500, 50)
        self.textbox.setStyleSheet("""
            QLineEdit {
                background-color: #2E3440;
                color: white;
                border-radius: 15px;
                border: 1px solid black;
            }
        """)
        self.textbox.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        textbox_layout.addWidget(self.textbox)
        main_layout.addLayout(textbox_layout)
        submit_layout = QHBoxLayout()
        submit_button = QPushButton('确定')
        submit_button.setFixedSize(100, 30)
        submit_button.setStyleSheet("""
            QPushButton{
                background-color: #5E81AC;
                color: white;
                border-radius: 15px;
                border: 1px solid black;
                font-size: 16px;
            }
            QPushButton:hover {
                background-color: #81A1C1;
            }
        """)
        submit_button.clicked.connect(self.submit_)
        submit_layout.addWidget(submit_button)
        main_layout.addLayout(submit_layout)

    def submit_(self):
        user_name = self.textbox.text()
        write_name = open('账号记录.txt', 'w', encoding='utf-8')
        write_name.write(str(user_name))
        write_name.close()
        write_name = open('聊天记录.txt', 'w', encoding='utf-8')
        write_name.write('')
        write_name.close()
        self.close()

    def center(self):
        screen = QApplication.primaryScreen().geometry()
        size = self.geometry()
        x = (screen.width() - size.width()) // 2
        y = (screen.height() - size.height()) // 2
        self.move(x, y)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.drag_pos = event.globalPos()

            self.drag_edge = self.get_edge(event.pos())

    def mouseMoveEvent(self, event: QMouseEvent):
        if event.buttons() == Qt.LeftButton:
            if self.drag_edge:
                return
            else:
                self.move(self.pos() + event.globalPos() - self.drag_pos)
                self.drag_pos = event.globalPos()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.drag_pos = None
            self.drag_edge = None

    def get_edge(self, pos):
        rect = self.rect()
        if pos.x() <= self.resize_margin:
            if pos.y() <= self.resize_margin:
                return "top-left"
            elif pos.y() >= rect.height() - self.resize_margin:
                return "bottom-left"
            else:
                return "left"
        elif pos.x() >= rect.width() - self.resize_margin:
            if pos.y() <= self.resize_margin:
                return "top-right"
            elif pos.y() >= rect.height() - self.resize_margin:
                return "bottom-right"
            else:
                return "right"
        elif pos.y() <= self.resize_margin:
            return "top"
        elif pos.y() >= rect.height() - self.resize_margin:
            return "bottom"
        return None


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = RoundedWindow()
    window.show()
    sys.exit(app.exec_())