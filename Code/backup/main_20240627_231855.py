import ctypes
import sys
import subprocess
import json
import os
import csv
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QApplication, QInputDialog, QWidget, QVBoxLayout, QPushButton, QTextEdit, 
                             QMessageBox, QGroupBox, QFormLayout, QLineEdit, QHBoxLayout, 
                             QScrollArea, QDialog, QDialogButtonBox, QCheckBox, QFileDialog,
                             QComboBox, QLabel, QProgressBar, QMenuBar, QAction, QMainWindow, QFrame)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QIcon, QFont
from PyQt5.QtWebEngineWidgets import QWebEngineView

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)

class PasswordRetriever(QThread):
    password_retrieved = pyqtSignal(str, str, str)
    progress_updated = pyqtSignal(int)

    def __init__(self, profiles):
        super().__init__()
        self.profiles = profiles

    def run(self):
        for i, profile in enumerate(self.profiles):
            try:
                result = subprocess.check_output(f'netsh wlan show profile "{profile}" key=clear', shell=True, text=True, stderr=subprocess.DEVNULL)
                password_line = [line for line in result.split('\n') if 'Key Content' in line]
                if password_line:
                    password = password_line[0].split(':')[1].strip()
                else:
                    password = ''
                self.password_retrieved.emit(profile, password, '')
            except subprocess.CalledProcessError as e:
                self.password_retrieved.emit(profile, '', str(e))
            self.progress_updated.emit(int((i + 1) / len(self.profiles) * 100))

class NetworkPassTool(QMainWindow):
    def __init__(self):
        super().__init__()
        self.profiles = []
        self.passwords = {}
        self.compact_mode = False
        self.initUI()

    def initUI(self):
        self.setWindowTitle('TSTP:Network Password Tool')
        self.setGeometry(100, 100, 710, 300)
        self.setMinimumWidth(710)
        self.setMaximumWidth(710)
        self.setWindowIcon(QIcon(resource_path("app_icon.ico")))

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        self.layout = QVBoxLayout()
        self.central_widget.setLayout(self.layout)

        self.create_menu()
        self.create_search_bar()
        self.create_scroll_area()
        self.create_bottom_buttons()
        self.create_status_bar()

    def create_menu(self):
        self.menu_bar = self.menuBar()

        file_menu = self.menu_bar.addMenu('File')
        
        refresh_action = QAction('Refresh Profiles', self)
        refresh_action.triggered.connect(self.refresh_profiles)
        file_menu.addAction(refresh_action)

        export_action = QAction('Export Passwords', self)
        export_action.triggered.connect(self.export_passwords)
        file_menu.addAction(export_action)
        
        exit_action = QAction('Exit', self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        view_menu = self.menu_bar.addMenu('View')
        
        compact_mode_action = QAction('Compact Mode', self)
        compact_mode_action.triggered.connect(self.toggle_compact_mode)
        view_menu.addAction(compact_mode_action)

        help_menu = self.menu_bar.addMenu('Help')
        tutorial_action = QAction('Show Tutorial', self)
        tutorial_action.triggered.connect(self.open_np_tutorial)
        help_menu.addAction(tutorial_action)
        
    def open_np_tutorial(self):
        tutorial_window = TutorialWindow(self)
        tutorial_window.exec_() 

    def create_search_bar(self):
        search_layout = QHBoxLayout()
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText('Search networks...')
        self.search_bar.textChanged.connect(self.filter_networks)
        search_layout.addWidget(self.search_bar)
        self.layout.addLayout(search_layout)

    def create_scroll_area(self):
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.network_container = QWidget()
        self.network_layout = QVBoxLayout()
        self.network_container.setLayout(self.network_layout)
        self.scroll_area.setWidget(self.network_container)
        self.layout.addWidget(self.scroll_area)

    def create_bottom_buttons(self):
        self.button_layout_bottom = QHBoxLayout()
        
        self.refresh_button = QPushButton('Refresh Profiles')
        self.refresh_button.clicked.connect(self.refresh_profiles)
        self.button_layout_bottom.addWidget(self.refresh_button)

        self.toggle_all_button = QPushButton('Toggle All')
        self.toggle_all_button.clicked.connect(self.toggle_all_groupboxes)
        self.button_layout_bottom.addWidget(self.toggle_all_button)

        self.save_button = QPushButton('Export Passwords')
        self.save_button.clicked.connect(self.export_passwords)
        self.button_layout_bottom.addWidget(self.save_button)

        self.show_all_button = QPushButton('Show All Passwords')
        self.show_all_button.clicked.connect(self.toggle_all_passwords)
        self.button_layout_bottom.addWidget(self.show_all_button)

        self.compact_mode_button = QPushButton('Compact Mode')
        self.compact_mode_button.clicked.connect(self.toggle_compact_mode)
        self.button_layout_bottom.addWidget(self.compact_mode_button)

        self.layout.addLayout(self.button_layout_bottom)

    def create_status_bar(self):
        self.status_bar = QLabel('Ready')
        self.layout.addWidget(self.status_bar)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.layout.addWidget(self.progress_bar)

    def load_profiles(self):
        self.profiles = []
        self.passwords = {}
        try:
            result = subprocess.check_output('netsh wlan show profile', shell=True, text=True)
            self.profiles = [line.split(':')[1].strip() for line in result.split('\n') if 'All User Profile' in line]
            self.status_bar.setText(f'Found {len(self.profiles)} networks')
            self.retrieve_passwords()
        except subprocess.CalledProcessError as e:
            QMessageBox.critical(self, 'Error', f'Failed to retrieve network profiles.\n{str(e)}')

    def retrieve_passwords(self):
        self.progress_bar.setVisible(True)
        self.password_retriever = PasswordRetriever(self.profiles)
        self.password_retriever.password_retrieved.connect(self.on_password_retrieved)
        self.password_retriever.progress_updated.connect(self.progress_bar.setValue)
        self.password_retriever.finished.connect(self.on_password_retrieval_finished)
        self.password_retriever.start()

    def on_password_retrieved(self, profile, password, error):
        self.passwords[profile] = password
        if error:
            print(f"Error retrieving password for {profile}: {error}")

    def on_password_retrieval_finished(self):
        self.progress_bar.setVisible(False)
        self.populate_network_list()

    def populate_network_list(self):
        for i in reversed(range(self.network_layout.count())): 
            self.network_layout.itemAt(i).widget().setParent(None)

        for profile in self.profiles:
            self.create_profile_groupbox(profile)

    def create_profile_groupbox(self, profile_name):
        frame = QFrame()
        frame.setFrameShape(QFrame.Box)
        frame.setLayout(QHBoxLayout())

        checkbox = QCheckBox(profile_name)
        checkbox.setChecked(True)
        checkbox.setStyleSheet("text-align: left;")  # Ensure text is aligned to the left
        checkbox.stateChanged.connect(lambda state, fr=frame: self.toggle_groupbox(fr, state))
        frame.layout().addWidget(checkbox)

        password_field = QLineEdit()
        password_field.setEchoMode(QLineEdit.Password)
        password_field.setReadOnly(True)
        password_field.setFixedWidth(300)
        password_field.setText(self.passwords.get(profile_name, ''))
        frame.layout().addWidget(password_field)

        show_password_button = QPushButton('Show')
        show_password_button.setFixedSize(75, 30)
        show_password_button.clicked.connect(lambda: self.toggle_password_visibility(password_field, show_password_button))
        frame.layout().addWidget(show_password_button)

        copy_password_button = QPushButton('Copy')
        copy_password_button.setFixedSize(75, 30)
        copy_password_button.clicked.connect(lambda: self.copy_to_clipboard(password_field.text()))
        frame.layout().addWidget(copy_password_button)

        self.network_layout.addWidget(frame)

    def toggle_groupbox(self, frame, state):
        for i in range(1, frame.layout().count()):
            item = frame.layout().itemAt(i)
            if item and item.widget():
                item.widget().setVisible(state == Qt.Checked)
        frame.setFixedHeight(40 if state == Qt.Unchecked else frame.sizeHint().height())

    def toggle_all_groupboxes(self):
        all_checked = all(self.network_layout.itemAt(i).widget().findChild(QCheckBox).isChecked() 
                          for i in range(self.network_layout.count()))
        new_state = not all_checked
        for i in range(self.network_layout.count()):
            frame = self.network_layout.itemAt(i).widget()
            checkbox = frame.findChild(QCheckBox)
            checkbox.setChecked(new_state)

    def toggle_password_visibility(self, password_field, button):
        if password_field.echoMode() == QLineEdit.Password:
            password_field.setEchoMode(QLineEdit.Normal)
            button.setText('Hide')
        else:
            password_field.setEchoMode(QLineEdit.Password)
            button.setText('Show')

    def toggle_all_passwords(self):
        show_all = self.show_all_button.text() == 'Show All Passwords'
        for i in range(self.network_layout.count()):
            frame = self.network_layout.itemAt(i).widget()
            password_field = frame.findChild(QLineEdit)
            show_button = frame.findChildren(QPushButton)[0]
            password_field.setEchoMode(QLineEdit.Normal if show_all else QLineEdit.Password)
            show_button.setText('Hide' if show_all else 'Show')
        self.show_all_button.setText('Hide All Passwords' if show_all else 'Show All Passwords')

    def copy_to_clipboard(self, text):
        clipboard = QApplication.instance().clipboard()
        clipboard.setText(text)
        self.status_bar.setText('Password copied to clipboard')

    def export_passwords(self):
        export_format, ok = QInputDialog.getItem(self, "Select Export Format", 
                                                 "Choose the export format:", 
                                                 ["Text File", "CSV File", "JSON File"], 0, False)
        if ok and export_format:
            file_filter = "Text files (*.txt)" if export_format == "Text File" else \
                          "CSV files (*.csv)" if export_format == "CSV File" else \
                          "JSON files (*.json)"
            file_name, _ = QFileDialog.getSaveFileName(self, "Save File", "", file_filter)
            if file_name:
                try:
                    if export_format == "Text File":
                        self.export_to_text(file_name)
                    elif export_format == "CSV File":
                        self.export_to_csv(file_name)
                    else:
                        self.export_to_json(file_name)
                    self.status_bar.setText(f'Passwords exported to {file_name}')
                except Exception as e:
                    QMessageBox.critical(self, 'Error', f'Failed to export passwords.\n{str(e)}')

    def export_to_text(self, file_name):
        with open(file_name, 'w') as file:
            for profile, password in self.passwords.items():
                file.write(f'Network: {profile}\nPassword: {password}\n\n')

    def export_to_csv(self, file_name):
        with open(file_name, 'w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['Network', 'Password'])
            for profile, password in self.passwords.items():
                writer.writerow([profile, password])

    def export_to_json(self, file_name):
        with open(file_name, 'w') as file:
            json.dump(self.passwords, file, indent=4)

    def filter_networks(self):
        search_text = self.search_bar.text().lower()
        for i in range(self.network_layout.count()):
            frame = self.network_layout.itemAt(i).widget()
            frame.setVisible(search_text in frame.findChild(QCheckBox).text().lower())

    def refresh_profiles(self):
        self.load_profiles()

    def toggle_compact_mode(self):
        if not self.compact_mode:
            self.compact_mode_button.setText('Full Mode')
            self.setMinimumWidth(400)
            self.setMaximumWidth(400)
            self.setGeometry(100, 100, 350, 150)
            self.search_bar.hide()
            self.scroll_area.hide()
            self.toggle_all_button.hide()
            self.show_all_button.hide()
            for i in range(self.network_layout.count()):
                self.network_layout.itemAt(i).widget().hide()
            self.compact_layout = QVBoxLayout()
            self.compact_dropdown = QComboBox()
            self.compact_dropdown.addItems(self.profiles)
            self.compact_dropdown.currentIndexChanged.connect(self.show_compact_profile)
            self.compact_layout.addWidget(self.compact_dropdown)
            self.compact_profile_container = QVBoxLayout()
            self.compact_layout.addLayout(self.compact_profile_container)
            self.layout.insertLayout(3, self.compact_layout)
            self.compact_mode = True
        else:
            self.compact_mode_button.setText('Compact Mode')
            self.setMinimumWidth(710)
            self.setMaximumWidth(710)
            self.setGeometry(100, 100, 710, 300)
            self.search_bar.show()
            self.scroll_area.show()
            self.toggle_all_button.show()
            self.show_all_button.show()
            for i in range(self.network_layout.count()):
                self.network_layout.itemAt(i).widget().show()
            self.clear_layout(self.compact_profile_container)
            self.layout.removeItem(self.compact_layout)
            self.compact_dropdown.deleteLater()
            self.compact_profile_container.deleteLater()
            self.compact_layout.deleteLater()
            self.compact_mode = False

    def show_compact_profile(self, index):
        profile_name = self.compact_dropdown.itemText(index)
        self.clear_layout(self.compact_profile_container)
        self.create_profile_groupbox_compact(profile_name)

    def create_profile_groupbox_compact(self, profile_name):
        groupbox = QGroupBox(profile_name)
        layout = QFormLayout()

        password_layout = QHBoxLayout()
        password_field = QLineEdit()
        password_field.setEchoMode(QLineEdit.Password)
        password_field.setReadOnly(True)
        password_field.setText(self.passwords.get(profile_name, ''))
        password_layout.addWidget(password_field)

        show_password_button = QPushButton('Show')
        show_password_button.setFixedSize(75, 30)
        show_password_button.clicked.connect(lambda: self.toggle_password_visibility(password_field, show_password_button))
        password_layout.addWidget(show_password_button)

        copy_password_button = QPushButton('Copy')
        copy_password_button.setFixedSize(75, 30)
        copy_password_button.clicked.connect(lambda: self.copy_to_clipboard(password_field.text()))
        password_layout.addWidget(copy_password_button)

        layout.addRow('Password:', password_layout)
        groupbox.setLayout(layout)
        self.compact_profile_container.addWidget(groupbox)

    def clear_layout(self, layout):
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def show_tutorial(self):
        tutorial = QDialog(self)
        tutorial.setWindowTitle('Advanced Network Password Viewer Tutorial')
        tutorial.setFixedSize(660,400)
        tutorial_layout = QVBoxLayout()

        tutorial_text = QTextEdit()
        tutorial_text.setReadOnly(True)
        tutorial_text.setFont(QFont('Arial', 10))
        tutorial_text.setHtml("""
        <h2>Welcome to the Advanced Network Password Viewer!</h2>
        <p>This application helps you manage and view Wi-Fi network passwords on your system. Here's how to use it:</p>
        <ol>
            <li><b>View Networks:</b> All saved Wi-Fi networks are displayed in the main window.</li>
            <li><b>Show/Hide Details:</b> Click the checkbox next to each network to show or hide its details.</li>
            <li><b>View Passwords:</b> Click the 'Show' button next to a password field to reveal the password.</li>
            <li><b>Copy Passwords:</b> Use the 'Copy' button to copy a password to your clipboard.</li>
            <li><b>Search Networks:</b> Use the search bar at the top to filter networks by name.</li>
            <li><b>Refresh Networks:</b> Click 'Refresh Profiles' to update the list of networks.</li>
            <li><b>Show All Passwords:</b> Use this button to reveal all passwords at once.</li>
            <li><b>Export Passwords:</b> Click 'Export Passwords' to save all passwords in various formats.</li>
            <li><b>Toggle All:</b> Use this to show/hide details for all networks at once.</li>
            <li><b>Compact Mode:</b> Switch between full and compact views for easier navigation.</li>
        </ol>
        <p><b>Note:</b> This tool requires administrative privileges to access network passwords.</p>
        """)
        tutorial_layout.addWidget(tutorial_text)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        buttons.accepted.connect(tutorial.accept)
        tutorial_layout.addWidget(buttons)

        tutorial.setLayout(tutorial_layout)
        tutorial.setMinimumSize(500, 400)
        tutorial.exec_()
        
    def check_admin_privileges(self):
        try:
            is_admin = os.getuid() == 0
        except AttributeError:
            is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        if not is_admin:
            self.prompt_restart_as_admin()

    def prompt_restart_as_admin(self):
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Warning)
        msg_box.setText("This program is not running with administrative privileges.")
        msg_box.setInformativeText("Would you like to restart the program as an administrator?")
        msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg_box.setDefaultButton(QMessageBox.Yes)
        reply = msg_box.exec()

        if reply == QMessageBox.Yes:
            self.restart_as_admin()

    def restart_as_admin(self):
        if sys.platform == 'win32':
            script = os.path.abspath(sys.argv[0])
            params = ' '.join([script] + sys.argv[1:])
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
        else:
            # For other OSes, additional implementation is required
            print("This feature is not implemented for non-Windows platforms.")
        sys.exit()
        
class TutorialWindow(QDialog):
    def __init__(self, parent=None):
        super(TutorialWindow, self).__init__(parent)
        self.setWindowTitle("Interactive Tutorial")
        self.setGeometry(100, 100, 850, 600)
        self.setWindowModality(Qt.ApplicationModal)

        self.layout = QVBoxLayout()

        self.webView = QWebEngineView()
        self.layout.addWidget(self.webView)

        self.navigation_layout = QHBoxLayout()
        self.home_button = QPushButton("Home")
        self.home_button.clicked.connect(self.go_to_home_page)
        self.navigation_layout.addWidget(self.home_button)

        self.back_button = QPushButton("Previous")
        self.back_button.clicked.connect(self.go_to_previous_page)
        self.navigation_layout.addWidget(self.back_button)

        self.next_button = QPushButton("Next")
        self.next_button.clicked.connect(self.go_to_next_page)
        self.navigation_layout.addWidget(self.next_button)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.navigation_layout.addWidget(self.progress_bar)

        self.start_button = QPushButton("Start Using App")
        self.start_button.clicked.connect(self.close)
        self.navigation_layout.addWidget(self.start_button)

        self.layout.addLayout(self.navigation_layout)
        self.setLayout(self.layout)

        self.current_page_index = 0
        self.tutorial_pages = [
            self.create_welcome_page(),
            self.create_admin_privileges_page(),
            self.create_interface_overview_page(),
            self.create_view_networks_page(),
            self.create_refresh_profiles_page(),
            self.create_export_passwords_page(),
            self.create_about_us_page()
        ]

        self.load_tutorial_page(self.current_page_index)

    def create_welcome_page(self):
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body { font-family: Arial, sans-serif; }
                h1 { color: #333; }
                p { font-size: 14px; line-height: 1.6; }
            </style>
        </head>
        <body>
            <h1>Welcome to the Interactive Tutorial</h1>
            <p>In this tutorial, you will learn how to use the key features of the Network Password Tool.</p>
            <p>Let's get started!</p>
        </body>
        </html>
        """

    def create_interface_overview_page(self):
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body { font-family: Arial, sans-serif; }
                h1 { color: #333; }
                p { font-size: 14px; line-height: 1.6; }
                ul { list-style-type: disc; margin-left: 20px; }
            </style>
        </head>
        <body>
            <h1>Interface Overview</h1>
            <p>The main interface of the Network Password Tool consists of several key components:</p>
            <ul>
                <li><b>Menu Bar:</b> Contains options for refreshing profiles, exporting passwords, and accessing the tutorial.</li>
                <li><b>Search Bar:</b> Allows you to filter networks by name.</li>
                <li><b>Network List:</b> Displays all saved Wi-Fi networks.</li>
                <li><b>Bottom Buttons:</b> Buttons for refreshing profiles, exporting passwords, and toggling views.</li>
                <li><b>Status Bar:</b> Displays status messages and progress information.</li>
            </ul>
        </body>
        </html>
        """

    def create_view_networks_page(self):
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body { font-family: Arial, sans-serif; }
                h1 { color: #333; }
                p { font-size: 14px; line-height: 1.6; }
                ol { list-style-type: decimal; margin-left: 20px; }
            </style>
        </head>
        <body>
            <h1>Viewing Networks</h1>
            <p>To view the saved Wi-Fi networks and their passwords:</p>
            <ol>
                <li>Run the application. The main window will display all saved Wi-Fi networks.</li>
                <li>Click the checkbox next to a network to show or hide its details.</li>
                <li>Click the 'Show' button next to the password field to reveal the password.</li>
                <li>Use the 'Copy' button to copy the password to your clipboard.</li>
            </ol>
        </body>
        </html>
        """

    def create_refresh_profiles_page(self):
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body { font-family: Arial, sans-serif; }
                h1 { color: #333; }
                p { font-size: 14px; line-height: 1.6; }
            </style>
        </head>
        <body>
            <h1>Refreshing Profiles</h1>
            <p>To refresh the list of network profiles:</p>
            <ol>
                <li>Click the 'Refresh Profiles' button in the menu or at the bottom of the main window.</li>
                <li>The application will retrieve the latest list of saved Wi-Fi networks.</li>
                <li>New networks will be added to the list, and any removed networks will be updated accordingly.</li>
            </ol>
        </body>
        </html>
        """

    def create_export_passwords_page(self):
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body { font-family: Arial, sans-serif; }
                h1 { color: #333; }
                p { font-size: 14px; line-height: 1.6; }
                ul { list-style-type: disc; margin-left: 20px; }
            </style>
        </head>
        <body>
            <h1>Exporting Passwords</h1>
            <p>To export the network passwords:</p>
            <ol>
                <li>Click the 'Export Passwords' button in the menu or at the bottom of the main window.</li>
                <li>Select the desired export format (Text File, CSV File, JSON File) and click 'OK'.</li>
                <li>Choose the location to save the file and enter a file name.</li>
                <li>Click 'Save' to export the passwords to the selected file format.</li>
            </ol>
        </body>
        </html>
        """

    def create_admin_privileges_page(self):
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body { font-family: Arial, sans-serif; }
                h1 { color: #333; }
                p { font-size: 14px; line-height: 1.6; }
            </style>
        </head>
        <body>
            <h1>Admin Privileges</h1>
            <p>This tool requires administrative privileges to access network passwords. If the program is not running with admin privileges:</p>
            <ol>
                <li>The application will prompt you to restart with administrative privileges.</li>
                <li>Click 'Yes' to restart the application as an administrator.</li>
                <li>If running on Windows, the application will automatically restart with the necessary privileges.</li>
            </ol>
        </body>
        </html>
        """

    def create_about_us_page(self):
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body { font-family: Arial, sans-serif; }
                h1 { color: #333; }
                p { font-size: 14px; line-height: 1.6; }
            </style>
        </head>
        <body>
            <h1>About Us</h1>
            <p><b>Custom Solutions at The Heart of Innovation: Your Challenge, Our Mission</b></p>
            <p>At The Solutions To Problems, LLC (TSTP), we are not just about developing software; we are about creating solutions. Our foundation is built on the belief that the best innovations arise from addressing real, tangible problems. This philosophy has led us to develop a range of products that are as diverse as they are functional, each born from a need, a frustration, or a gap in existing technological offerings. Our mission is simple yet profound: to eliminate productivity issues across all aspects of computer usage, transforming challenges into opportunities for efficiency and ease.</p>
            <p><b>The Essence of Our Innovation: Driven by User Needs</b></p>
            <p>Every TSTP product stems from a direct need or problem articulated by users like you. Our development process is a testament to our commitment to listening, understanding, and acting on the challenges you face, ensuring that our solutions not only meet but exceed expectations.</p>
            <p><b>Your Input: The Catalyst for Our Next Solution</b></p>
            <p>This approach to solving specific, real-world problems exemplifies how we operate. But what about the challenges you face daily? Whether it is a task that could be faster, a process that could be smoother, or a problem you think no one has tackled yet, we want to hear from you.</p>
            <p>Your experiences, struggles, and needs are the seeds from which our next solutions will grow. By sharing your challenges with us, you are not just finding a solution for yourself; you are contributing to a future where technology makes all our lives easier.</p>
            <p><b>Get Involved</b></p>
            <p>Reach out to us at Support@TSTP.xyz with your ideas, challenges, or feedback on our existing tools. Explore our product range at <a href="https://www.tstp.xyz">TSTP.xyz</a> and let us know how we can tailor our technologies to better serve your needs.</p>
            <p>At The Solutions To Problems, LLC, your challenges are our inspiration. Together, let us redefine the boundaries of what technology can achieve, creating custom solutions that bring peace, efficiency, and innovation to every computing session.</p>
            <p>Connect with us on:</p>
            <ul>
                <li><a href="https://www.linkedin.com/company/thesolutions-toproblems/">LinkedIn</a></li>
                <li><a href="https://www.facebook.com/profile.php?id=61557162643039">Facebook</a></li>
                <li><a href="https://twitter.com/TSTP_LLC">Twitter</a></li>
                <li><a href="https://www.youtube.com/@yourpststudios/">YouTube</a></li>
                <li><a href="https://github.com/TSTP-Enterprises">GitHub</a></li>
            </ul>
        </body>
        </html>
        """

    def load_tutorial_page(self, index):
        self.webView.setHtml(self.tutorial_pages[index])
        self.progress_bar.setValue(int((index + 1) / len(self.tutorial_pages) * 100))
    
    def go_to_next_page(self):
        if self.current_page_index < len(self.tutorial_pages) - 1:
            self.current_page_index += 1
            self.load_tutorial_page(self.current_page_index)

    def go_to_previous_page(self):
        if self.current_page_index > 0:
            self.current_page_index -= 1
            self.load_tutorial_page(self.current_page_index)

    def go_to_home_page(self):
        self.current_page_index = 0
        self.load_tutorial_page(self.current_page_index)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = NetworkPassTool()
    ex.show()
    ex.load_profiles()
    sys.exit(app.exec_())
