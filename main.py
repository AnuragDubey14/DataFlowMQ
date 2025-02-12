import sys
import json
import threading
# sys.coinit_flags = 2
from PyQt5.QtWidgets import QApplication, QMainWindow, QPushButton, QMessageBox,QWidget 
from PyQt5 import QtGui as qtg 
import PyQt5.QtCore as qtc
from PyQt5.QtCore import  Qt
import warnings
warnings.simplefilter("ignore", UserWarning)
import PyQt5.QtWidgets as qtw 
import logging
import os
import glob
import ctypes
import logging
import random
from cryptography.fernet import Fernet 
from PyQt5.QtWidgets import QPlainTextEdit
from PyQt5.QtCore import QMetaObject, Qt, Q_ARG, pyqtSlot
from PyQt5.QtGui import QTextOption
from client import SimpleMQTTClient
from datetime import datetime
import time
import queue




def is_admin():
    """Check if program is run by admin or not"""
    return ctypes.windll.shell32.IsUserAnAdmin() != 0

# Function to relaunch the script as administrator if it's not already running as admin
def run_as_admin():
    """restart the program to run as admin."""
    if sys.argv[0] != __file__:  # If the script is not already running as admin
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, __file__, None, 1)
        sys.exit()

def resource_path(relative_path):
    """ Get the absolute path to a resource, works for dev and PyInstaller. """
    try:
        base_path = sys._MEIPASS  # PyInstaller creates a temp folder and stores path in _MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")  # Use the script directory for non-PyInstaller environments

    return os.path.join(base_path, relative_path)

class LoggerConfig:
    """Initialize a new log file to log each action into a log file
    Argument: Log file path"""
    def __init__(self, log_file_path='./Internal_files/DataSync.log'):
        # Set up logging configuration before deleting old log files
        logging.basicConfig(
            filename=resource_path(log_file_path),  # Log file name
            filemode='w',            # Write mode to create a new file
            format='%(asctime)s - %(levelname)s - %(message)s',  # Format of log messages
            level=logging.DEBUG       # Log level
        )

        # Create a logger instance
        self.logger = logging.getLogger(__name__)

        # Delete unused log files after logging is configured
        self.delete_unused_log_files(log_file_path)

    def get_logger(self):
        """Return logger object to use in entire application"""
        return self.logger
    
    def is_file_in_use(self, filepath):
        """Check if log file in use by another process or not!"""
        try:
            # Attempt to open file exclusively
            fd = os.open(filepath, os.O_RDWR | os.O_EXCL)
            os.close(fd)  # Close immediately if successful
            return False  # File is not in use
        except (OSError, PermissionError):
            return True  # File is in use

    def delete_unused_log_files(self, active_log_file, directory='./Internal_files/'):
        """Delete all previous logs file that is not currently in use."""
        # Use glob to find all .log files in the specified directory
        log_files = glob.glob(os.path.join(directory, '*.log'))
        
        for log_file in log_files:
            # Skip the active log file to avoid conflicts
            if log_file == active_log_file:
                continue

            if not self.is_file_in_use(log_file):
                try:
                    os.remove(log_file)
                    self.logger.debug(f"{log_file} has been deleted.")
                except FileNotFoundError:
                    self.logger.warning(f"{log_file} does not exist.")
                except PermissionError:
                    self.logger.warning(f"{log_file} is in use and cannot be deleted.")
            else:
                self.logger.info(f"{log_file} is currently in use and was not deleted.")


class QTextEditLogger(logging.Handler):
    def __init__(self, parent, widget):
        super().__init__()
        self.parent = parent
        self.widget = widget
        self.widget.setObjectName("Application Logger")
        self.widget.setReadOnly(True)  # Make the log window read-only
        self.widget.setWordWrapMode(QTextOption.WrapAnywhere)  # Wrap long lines

    def emit(self, record):
        """Override the emit method to write log messages to the QTextEdit widget."""
        try:
            if self.widget is not None and self.widget:
                msg = self.format(record)
                # print(f"Logging message: {msg}")
                QMetaObject.invokeMethod(self.widget, "appendPlainText", Qt.QueuedConnection, Q_ARG(str, msg))
            else:
                print("Widget is deleted or not valid!")
        except RuntimeError as e:
            print(f"Error while emitting log: {e}")

    def format(self, record):
        """Define the log message format."""
        log_fmt = "%(asctime)s - %(levelname)s - %(message)s"
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)



class MainWindow(QMainWindow):
    """Intialize the app 
    Argument: Screen_width,screen_height."""

    logMessageSignal = qtc.pyqtSignal(str)
    start_queue_timers_signal=qtc.pyqtSignal(int)

    def __init__(self,screen_width,screen_height):
        super().__init__()
        self.screen_width = screen_width
        self.screen_height = screen_height 
        self.setWindowTitle("DataSync")
        self.export_key = 'KLZGj33iKwBAiuMHCld_oxjt3G6gUA_lxIq7kt8his8='
        # self.setGeometry(800, 800, self.screen_width, self.screen_height)
        self.setWindowIcon(qtg.QIcon(resource_path('./internal_files/logo.png')))
        # self.setWindowFlags(qtc.Qt.Window | qtc.Qt.WindowCloseButtonHint | qtc.Qt.WindowMinimizeButtonHint)
        process_id=str(os.getpid())
        config=self.read_file(resource_path("./Internal_files/config.tu"))
        config=self.decrypt_data(config)
        self.config=json.loads(config)
        self.first_connect=False
        self.cl0=None
        self.cl1=None
        self.cl2=None
        self.broker1_timer=None
        self.broker2_timer=None
        self.store_data_queue1=queue.Queue()     
        self.store_data_queue2=queue.Queue()     
        self.selected_serial_number=""
        self.logMessageSignal.connect(self.logMessage)
        self.start_queue_timers_signal.connect(self.start_queue_timers)
        logger_config = LoggerConfig(resource_path(f'./Internal_files/DataSync{process_id}.log'))
        self.logger = logger_config.get_logger()
        # Use the logger
        self.logger.info("Application started")
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        # Main vertical layout
        self.main_layout = qtw.QVBoxLayout(central_widget)

        # Vertical splitter to divide into three parts
        splitter = qtw.QSplitter(Qt.Vertical)

        # Top part: Label
        self.toplabel = qtw.QLabel("TekUncorked | DataSync")
        self.toplabel.setFont(qtg.QFont("Sans-serif", int(self.screen_height*0.015), qtg.QFont.Bold))
        self.toplabel.setAlignment(qtc.Qt.AlignCenter)
        self.toplabel.setStyleSheet("color: #2596be;")
        splitter.addWidget(self.toplabel)

        # Middle part: Stacked widget
        self.stacked_widget = qtw.QStackedWidget(self)
        # self.stacked_widget.setMinimumHeight(int(self.screen_height * 0.6))
        splitter.addWidget(self.stacked_widget)

        # Bottom part: Log window
        self.logTextBox = qtw.QPlainTextEdit(self)
        self.application_logger, self.logTextBox = self.setup_text_logger()
        splitter.addWidget(self.logTextBox.widget)

        # Set sizes for each section
        splitter.setSizes([int(self.screen_height * 0.10), int(self.screen_height * 0.75), int(self.screen_height * 0.15)])
        splitter.setStretchFactor(1, 1)  # Make the middle part resizable

        # Add the splitter to the main layout
        self.main_layout.addWidget(splitter)

        self.create_menu_bar()  # Create menu bar
        self.application_logger.info("Application started successfully!")
        self.create_widgets()

        self.set_current_page(self.first_window_widget)

    def create_menu_bar(self):
        "Create Menubar/Navigation here"

        self.menubar = qtw.QMenuBar()
        self.menubar.setFixedHeight(int(self.screen_height*0.06))
        self.menubar.setContentsMargins(0,0,100,100)

        self.disconnect_action=qtw.QAction("Disconnect", self)
        self.disconnect_action.triggered.connect(self.disconnect_client) 
        self.disconnect_action.setFont(qtg.QFont("Arial", 20, qtg.QFont.Bold))  
        self.menubar.addAction(self.disconnect_action) 
        self.disconnect_action.setVisible(True)

        self.save_action=qtw.QAction("Save", self)
        self.save_action.triggered.connect(self.download_log_thread_func) 
        self.save_action.setFont(qtg.QFont("Arial", 20, qtg.QFont.Bold))  
        self.menubar.addAction(self.save_action) 
        self.save_action.setVisible(True)

        self.help_action=qtw.QAction("Help", self)
        self.help_action.triggered.connect(self.help)
        self.help_action.setFont(qtg.QFont("Arial", 20, qtg.QFont.Bold))  
        self.menubar.addAction(self.help_action)
        self.help_action.setVisible(True)

        self.about_action=qtw.QAction("About", self)
        self.about_action.triggered.connect(self.showAbout) 
        self.about_action.setFont(qtg.QFont("Arial", 20, qtg.QFont.Bold))  
        self.menubar.addAction(self.about_action) 
        self.about_action.setVisible(True)

        # Add separator
        self.menubar.addSeparator()
        self.main_layout.setMenuBar(self.menubar)

    def create_widgets(self):
        try:

            self.first_window_widget=qtw.QWidget()
            self.setup_first_window(self.first_window_widget)
            self.stacked_widget.addWidget(self.first_window_widget)

            self.broker_window_widget=qtw.QWidget()
            self.setup_broker_window(self.broker_window_widget)
            self.stacked_widget.addWidget(self.broker_window_widget)


        except Exception as e:
            self.logger.error(f"Error in create widgets - {e}")

    def set_current_page(self,widget):
        try:
            if self.stacked_widget.currentWidget()!=widget:
                self.stacked_widget.setCurrentWidget(widget)
            else:
                print("Page already set.")
        except Exception as e:
            self.logMessageSignal.emit("Error in changing page")
            self.logger.error(f"Error in set_current_page - {e}")


    def setup_first_window(self, parent_widget):
        """Create first window to display connected drives etc. 
        argument: parent_widget(to set the parents and layout of this window)."""

        try:
            # Create the main layout for the parent widget
            parent_layout = qtw.QVBoxLayout(parent_widget)
            # Creating the QGroupBox and applying styles
            format_group = qtw.QGroupBox()
            format_group.setStyleSheet("""
                QGroupBox {
                    border: 2px solid black;
                    border-radius: 5px;
                    margin-top: 10px;
                    padding: 10px;
                    color: black;
                }
            """)
            width=int(self.screen_width*0.55)
            height=int(self.screen_height*0.55)
            format_group.setFixedSize(width,height)

            # Create a layout for the QGroupBox
            format_group_layout = qtw.QVBoxLayout(format_group)
            table_widget = qtw.QTableWidget(self)
            table_widget.setObjectName("Home_table")
            table_widget.setRowCount(3)  
            table_widget.setColumnCount(2)  
            table_widget.setFixedSize(int(width*0.7),int(height*0.5))
            table_widget.setColumnWidth(0,int(table_widget.width()*0.498))
            table_widget.setColumnWidth(1,int(table_widget.width()*0.498))
            table_widget.setHorizontalHeaderLabels(['Parameter', 'Value'])  # Set column labels
            table_widget.setContentsMargins(0, 0, 0, 0)
            # table_widget.resizeRowsToContents()
            table_widget.setEditTriggers(qtw.QTableWidget.NoEditTriggers)
            table_widget.horizontalHeader().setSectionResizeMode(qtw.QHeaderView.Fixed)
            table_widget.verticalHeader().setVisible(False)
            table_widget.setHorizontalScrollBarPolicy(qtc.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            table_widget.horizontalHeader().setStyleSheet("QHeaderView::section { background-color: #e28743; color: white; font-weight: bold; }")

            device_combobox=qtw.QComboBox()
            device_combobox.setObjectName("device_combobox")
            device_combobox.addItems(['LvIoT SS-1',"DT Pro","Grid IoT","LvIoT SS-2"])
            device_combobox.setCurrentIndex(0)
            serial_list=self.read_file(resource_path("./Internal_files/serial_number.tu"))
            serial_list=self.decrypt_data(serial_list)
            if serial_list is not None:
                self.serial_list=json.loads(serial_list)
                device_combobox.currentText()
            total_rows=self.serial_list.get(device_combobox.currentText(),"LvIoT SS-1")
            serial_number_combobox=qtw.QComboBox()
            serial_number_combobox.addItems([f"{i}" for i in range(1,total_rows+1)])
            serial_number_combobox.setObjectName("serial_number_combobox")

            broker_combobox=qtw.QComboBox()
            broker_combobox.setObjectName("broker_combobox")
            broker_combobox.addItems([f"Broker {i}" for i in range(1,3)])
            parameters=["Select Device","Select Serial Number","Select MQTT Broker"]
            for i in range(len(parameters)):
                item = qtw.QTableWidgetItem(parameters[i])
                item.setTextAlignment(qtc.Qt.AlignCenter)
                table_widget.setItem(i, 0, item)

            table_widget.setCellWidget(0,1,device_combobox)
            table_widget.setCellWidget(1,1,serial_number_combobox)
            table_widget.setCellWidget(2,1,broker_combobox)

            format_group_layout.addWidget(table_widget,alignment=qtc.Qt.AlignCenter)

            connect_button=qtw.QPushButton("Connect")
            connect_button.setStyleSheet(f"QPushButton {{background-color: skyblue; border: 2px solid black; font-weight: bold;}}")
            connect_button.setFixedSize(int(width*0.4),int(height*0.1))
            connect_button.clicked.connect(lambda: self.connect_client())
            format_group_layout.addWidget(connect_button,alignment=qtc.Qt.AlignCenter|qtc.Qt.AlignCenter)
            parent_layout.addWidget(format_group,alignment=qtc.Qt.AlignCenter)
            parent_widget.setLayout(parent_layout)

            device_combobox.currentIndexChanged.connect(self.change_serial_number)
            self.logger.info("First window setup successfully!")
        except Exception as e:
            print(e)
            self.logger.error(f"ERROR in setup first window - {e}")
        
    def setup_broker_window(self, parent_widget):
        """Setup Broker 1 window with a table and group box containing two QPlainTextEdit widgets."""
        try:
            # Create the main layout for the parent widget
            parent_layout = qtw.QVBoxLayout(parent_widget)

            # Create and configure the QGroupBox for the entire Broker 1 section
            width=int(self.screen_width*0.8)
            height=int(self.screen_height*0.65)
            broker_group = qtw.QGroupBox()
            broker_group.setStyleSheet("""
                QGroupBox {
                    border: 2px solid black;
                    border-radius: 5px;
                    margin-top: 10px;
                    padding: 10px;
                    color: black;
                }
            """)
            broker_group_layout = qtw.QVBoxLayout(broker_group)
            broker_group.setFixedSize(width,height)
            # Create and configure the table
            table = qtw.QTableWidget(3, 2)  # 5 rows, 3 columns
            table.setObjectName("broker_table1")
            table.setHorizontalHeaderLabels(["Parameter","Value"])
            table.setFixedSize(int(width*0.8),int(height*0.25))
            table.setColumnWidth(0, int(table.width()*0.498))  # Adjust column width
            table.setColumnWidth(1, int(table.width()*0.498))
            table.setEditTriggers(qtw.QTableWidget.NoEditTriggers)  # Make table non-editable
            table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            table.verticalHeader().setVisible(False)
            table.horizontalHeader().setStyleSheet("""
                QHeaderView::section { background-color: #e28743; color: white; font-weight: bold; }
            """)
            broker_group_layout.addWidget(table, alignment=Qt.AlignCenter)
            # Create the group box for QPlainTextEdit widgets
            text_edit_group_layout = qtw.QHBoxLayout()

            # Add two QPlainTextEdit widgets inside the group box
            plain_text_edit1 = QPlainTextEdit()
            plain_text_edit1.setObjectName("broker1_textedit")
            plain_text_edit1.setReadOnly(True)
            plain_text_edit1.setStyleSheet("border: 1px solid black;")
            text_edit_group_layout.addWidget(plain_text_edit1)

            plain_text_edit2 = QPlainTextEdit()
            plain_text_edit2.setObjectName("broker2_textedit")
            plain_text_edit2.setReadOnly(True)
            plain_text_edit2.setStyleSheet("border: 1px solid black;")
            text_edit_group_layout.addWidget(plain_text_edit2)

            # Add the text_edit_group to the broker_group_layout
            broker_group_layout.addLayout(text_edit_group_layout)

            
            # Add the broker_group to the parent_layout
            parent_layout.addWidget(broker_group, alignment=Qt.AlignCenter)
            parent_widget.setLayout(parent_layout)

            self.logger.info("Broker window setup successfully!")

        except Exception as e:
            print(e)
            self.logger.error(f"ERROR in setup_broker_window: {e}")


    def change_serial_number(self):
        try:
            sender=self.sender()
            selected_device=sender.currentText()
            total_rows=self.serial_list.get(selected_device,'LvIoT SS-1')
            serial_number_combobox=self.findChild(qtw.QComboBox,"serial_number_combobox")
            serial_number_combobox.clear()
            serial_number_combobox.addItems([f"{i}" for i in range(1,total_rows+1)])
        except Exception as e:
            self.logMessageSignal.emit("Error occurred during serial number list change.")
            self.logger.error(f"Error occured in change_serial_number - {e}")
    
    
    def read_certs(self, broker, mode):
        try:
            # Get the directory where the script is located
            script_dir = os.path.dirname(os.path.abspath(__file__))  # This will get the directory of main.py
            cert_dir = os.path.join(script_dir, "certs", f"broker{broker}")
            
            if mode == 1:
                cert_path = os.path.join(cert_dir, "root-CA.crt")
                print(f"Trying to read CA certificate from: {cert_path}")
                if not os.path.exists(cert_path):
                    print(f"Error: Certificate file {cert_path} does not exist.")
                    return None, None, None
                
                return cert_path, None, None

            elif mode == 2:
                cert_path1 = os.path.join(cert_dir, "root-CA.crt")
                cert_path2 = os.path.join(cert_dir, "testdevice1.cert.pem")
                cert_path3 = os.path.join(cert_dir, "testdevice1.private.key")
                print(f"Trying to read CA certificate from: {cert_path1}")
                print(f"Trying to read client certificate from: {cert_path2}")
                print(f"Trying to read private key from: {cert_path3}")
                
                # Check if files exist
                if not os.path.exists(cert_path1):
                    print(f"Error: Certificate file {cert_path1} does not exist.")
                    return None, None, None
                if not os.path.exists(cert_path2):
                    print(f"Error: Certificate file {cert_path2} does not exist.")
                    return None, None, None
                if not os.path.exists(cert_path3):
                    print(f"Error: Certificate file {cert_path3} does not exist.")
                    return None, None, None

                # If all files exist, read them
                return cert_path1,cert_path2,cert_path3

        except Exception as e:
            print(f"Error in reading certificate: {e}")
            return None, None, None

    
    def connect_client(self):
        selected_broker = self.findChild(qtw.QComboBox, "broker_combobox").currentIndex()
        selected_device = self.findChild(qtw.QComboBox, "device_combobox").currentText()
        selected_serial = self.findChild(qtw.QComboBox, "serial_number_combobox").currentText()
        self.selected_serial_number = selected_serial
        if selected_device=='LvIoT SS-1':
            l = [f"Broker {selected_broker+1} Status", f"{selected_device} Serial Number", "Latest Data Timestamp"]
            self.show_broker(l)
            self.start_queue_timers(selected_broker)
            self.logMessageSignal.emit(f"connecting to the broker {selected_broker+1}")
            self.create_client(selected_broker, selected_serial)
        else:
            QMessageBox.warning(None,"Notice",f"Currently we don't have support for {selected_device}\n we are working on it\n Please Select 'LvIoT SS-1'.")

    def create_client(self, selected_broker, selected_serial):
        mqtt_thread = threading.Thread(
            target=self.create_client_mqtt, args=(selected_broker, selected_serial), daemon=True
        )
        mqtt_thread.start()


    def create_client_mqtt(self, selected_broker, selected_serial):
        try:
            if selected_broker == 0:
                broker_address = self.config.get("mqtt0").get("ip")
                topic = self.config.get("mqtt0").get("topic")
                mode=self.config.get("mqtt0").get("secured")
                port=self.config.get("mqtt0").get("port")
                # client_id = f"DataSync/{random.randint(100000, 1000000)}/{os.getpid()}"
                client_id="basicPubSub"
                if mode!=0:
                    ca_cert,client_cert,client_key=self.read_certs(selected_broker,mode)
                self.cl0 = SimpleMQTTClient(
                    broker_address,
                    topic,
                    client_id,
                    port=port,
                    username="anurag",
                    password="dubey",
                    ca_cert=ca_cert,
                    client_cert=client_cert,
                    client_key=client_key
                )
                self.cl0.start()
            else:
                broker_address1 = self.config.get("mqtt1").get("ip")
                topic1 = self.config.get("mqtt1").get("topic")
                client_id1 = f"DataSync/{random.randint(100000, 1000000)}/{os.getpid()}"
                mode=self.config.get("mqtt1").get("secured")
                if mode!=0:
                    ca_cert,client_cert,client_key=self.read_certs(selected_broker,mode)
                else:
                    ca_cert,client_cert,client_key=None,None,None
                self.cl1 = SimpleMQTTClient(
                    broker_address1,
                    topic1,
                    client_id1,
                    username="anurag",
                    password="dubey",
                    ca_cert=ca_cert,
                    client_cert=client_cert,
                    client_key=client_key
                )
                self.cl1.start()

                broker_address2 = self.config.get("mqtt2").get("ip")
                topic2 = self.config.get("mqtt2").get("topic")
                client_id2 = f"DataSync/{random.randint(100000, 1000000)}/{os.getpid()}"
                mode=self.config.get("mqtt2").get("secured")
                if mode!=0:
                    ca_cert,client_cert,client_key=self.read_certs(selected_broker,mode)
                else:
                    ca_cert,client_cert,client_key=None,None,None
                self.cl2 = SimpleMQTTClient(
                    broker_address2,
                    topic2,
                    client_id2,
                    username="anurag",
                    password="dubey",
                    ca_cert=ca_cert,
                    client_cert=client_cert,
                    client_key=client_key
                )
                self.cl2.start()
        except Exception as e:
            print(f"Error creating MQTT client: {e}")


    def start_queue_timers(self, number):
        try:
            if number == 0:
                print("Starting broker1 timer...")
                self.broker1_timer = qtc.QTimer(self)
                self.broker1_timer.timeout.connect(self.check_broker1_queue)
                self.broker1_timer.start(2000)
            elif number == 1:
                print("Starting broker2 timer...")
                self.broker2_timer = qtc.QTimer(self)
                self.broker2_timer.timeout.connect(self.check_broker2_queue)
                self.broker2_timer.start(2000)
        except Exception as e:
            print(f"Exception {e}")
            self.logger.error(f"Exception in start_queue_timers -  {e}")


    def check_broker1_queue(self):
        print("INSIDE CHECK BROKER 1 QUEUE")
        if self.cl0 is not None:
            table1_data = []
            while not self.cl0.data_queue.empty():
                data = self.cl0.data_queue.get()
                self.store_data_queue1.put(data)
                print(f"Broker1 data: {data}")
                self.update_broker1_data(data)

            if self.cl0.is_connected():
                table1_data.append("Online")
            else:
                table1_data.append("Offline")

            time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            table1_data.append(time)
            self.update_broker_status(table1_data)

        
    
    def check_broker2_queue(self):
        print("INSIDE CHECK BROKER 1 QUEUE")
        if self.cl1 is not None:
            if not self.cl1.data_queue.empty():
                data=self.cl1.data_queue.get()
                self.store_data_queue1.put(data)
                self.update_broker1_data(data)
        if self.cl2 is not None:
            if not self.cl2.data_queue.empty():
                data=self.cl2.data_queue.get()
                self.store_data_queue2.put(data)
                self.update_broker2_data(data)

        table_data=[]
        table_data.append(f"{"Online" if self.cl1.is_connected() else "Offline"} | {"Online" if self.cl2.is_connected() else "Offline"}")
        time=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        table_data.append(time)
        self.update_broker_status(data=table_data)



    def update_broker_status(self, data):
        def update():
            if self.first_connect==False:
                index=self.findChild(qtw.QComboBox,"broker_combobox").currentIndex()
                self.logMessageSignal.emit(f"Device connected to the broker {index+1}")
                self.first_connect=True
            table1 = self.findChild(qtw.QTableWidget, "broker_table1")
            item = qtw.QTableWidgetItem(data[0])
            item.setTextAlignment(qtc.Qt.AlignCenter)
            table1.setItem(0, 1, item)

            item = qtw.QTableWidgetItem(data[1])
            item.setTextAlignment(qtc.Qt.AlignCenter)
            table1.setItem(2, 1, item)

        # Ensure the update runs in the main thread
        qtc.QTimer.singleShot(0, update)


    def update_broker1_data(self,data):
        text_edit=self.findChild(qtw.QPlainTextEdit,"broker1_textedit")
        self.check_and_clear_text(text_edit)
        text_edit.appendPlainText(data)


    def update_broker2_data(self,data):
        text_edit=self.findChild(qtw.QPlainTextEdit,"broker2_textedit")
        self.check_and_clear_text(text_edit)
        text_edit.appendPlainText(data)


    def show_broker(self,data):
        table=self.findChild(qtw.QTableWidget,"broker_table1")
        for i in range(len(data)):
            item = qtw.QTableWidgetItem(data[i])
            item.setTextAlignment(qtc.Qt.AlignCenter)
            table.setItem(i, 0, item)
        item=qtw.QTableWidgetItem(self.selected_serial_number)
        item.setTextAlignment(qtc.Qt.AlignCenter)
        table.setItem(1,1,item)
        text_edit=self.findChild(qtw.QPlainTextEdit,"broker1_textedit")
        text_edit.clear()
        text_edit=self.findChild(qtw.QPlainTextEdit,"broker2_textedit")
        text_edit.clear()
        self.set_current_page(self.broker_window_widget)

    def check_and_clear_text(self,text_edit):
        # Get the text from QPlainTextEdit and encode it to bytes
        text = text_edit.toPlainText()
        byte_size = len(text.encode('utf-8'))  # Get the byte size of the text

        print(f"Text byte size: {byte_size} bytes")

        # Check if the byte size exceeds 10,000 bytes
        if byte_size > 10000:
            queue_name=text.objectName().split("-")[0]
            print(f"Text exceeds 10,000 bytes in {queue_name}, clearing text.")
            text_edit.clear()  # Clear the text if it exceeds the limit
            self.logMessageSignal.emit(f"Data is cleared and log.")

    def disconnect_client(self):
        try:
            self.get_confirmation_to_download_log()
            if self.cl0 is not None:
                self.cl0.disconnect()
                self.cl0=None
            if self.cl1 is not None:
                self.cl1.disconnect()
                self.cl1=None
            if self.cl2 is not None:
                self.cl2.disconnect()
                self.cl2=None
            self.first_connect=False
            self.stop_timers()
            self.clear_data_queues()
            self.set_current_page(self.first_window_widget)
        except Exception as e:
            print(e)
            self.logger.error(f"Error in disconnect client")

    def clear_data_queues(self):
        try:
            self.store_data_queue1=queue.Queue()
            self.store_data_queue2=queue.Queue()
        except Exception as e:
            print(e)
            self.logger.error(f"Error in clear_data_queues - {e}")

    def get_confirmation_to_download_log(self):
        """Prompt a blocking dialog for confirmation to download log file."""
        try:
            if self.cl0 is not None or self.cl1 is not None or self.cl2 is not None:
                msg = QMessageBox(self)
                msg.setIcon(QMessageBox.Warning)
                msg.setText("Do you want to download log data?")
                msg.setWindowTitle('Warning')
                msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
                # Execute dialog in blocking mode during production
                confirmation = msg.exec_()

                if confirmation == QMessageBox.Yes:
                    self.download_log_thread_func()
                else:
                    self.logMessageSignal.emit("Log Download cancelled.")
            else:
                self.logMessageSignal.emit("No valid broker connections.")
        except Exception as e:
            self.logfile(f"Error in get_confirmation_to_download_log - {e}")

    def download_log_thread_func(self):
        try:
            if self.cl0 is not None or self.cl1 is not None or self.cl2 is not None:
                timestamp = time.strftime('%Y-%m-%d_%H-%M-%S', time.localtime())
                options = qtw.QFileDialog.Options()
                location, _ = qtw.QFileDialog.getSaveFileName(
                    self,
                    "Save Log File",
                    f"DataSync_log_{timestamp}.txt",
                    "Text Files (*.TXT);;All Files (*)",
                    options=options
                )
                if location:
                    # Correcting how arguments are passed to the thread
                    log_thread = threading.Thread(target=self.download_log_main_func, args=(location,), daemon=True)
                    log_thread.start()
                else:
                    self.logMessageSignal.emit("No Location selected.")
            else:
                self.logMessageSignal.emit("No logged data available.")
        except Exception as e:
            self.logfile(f"Error in download_log_thread_func - {e}")

    def download_log_main_func(self, location):
        try:
            data = ""
            
            if self.cl0 is not None:
                data += f"TekUncorked || DataSync\n\n Broker 1\nDevice Number {self.selected_serial_number}\n"
                while not self.store_data_queue1.empty():
                    data1 = self.store_data_queue1.get()
                    print("Data1: ",data1)
                    data += f"\n{data1}"
            
            elif self.cl1 is not None:
                data += f"TekUncorked || DataSync\n\n Broker 2\nDevice Number {self.selected_serial_number}\n Broker A\n"
                while not self.store_data_queue1.empty():
                    data2 = self.store_data_queue1.get()
                    print("Data2: ",data2)
                    data += f"\n{data2}"
                data += f"TekUncorked || DataSync\n\n Broker 2\nDevice Number {self.selected_serial_number}\n Broker B\n"
                while not self.store_data_queue2.empty():
                    data3 = self.store_data_queue2.get()
                    print("Data3: ",data3)
                    data += f"\n{data3}"
            
            # Writing the collected data to the specified location
            if data:  # Ensure there is data to write
                with open(location, "w") as file:
                    file.write(data)
                self.logMessageSignal.emit(f"Log downloaded successfully to {location}")
            else:
                self.logMessageSignal.emit("No data available to download.")
        
        except Exception as e:
            self.logfile(f"Error in download_log_main_func - {e}")
            self.logger.error(f"Error in download_log_main_func - {e}")


    def help(self):
        """Display a dialog with steps to operate DataSync."""
        try:
            Step1 = "Select Device, Select Serial Number, and Select Broker."
            Step2 = "Press Connect Button."
            Step3 = "Click on Save Button to download the report."
            Step4 = "Click Disconnect to disconnect the broker."

            # Info message with HTML for clear steps
            info_message = (
                    f"<ol>"
                    f"<li>{Step1}</li>"
                    f"<li>{Step2}</li>"
                    f"<li>{Step3}</li>"
                    f"<li>{Step4}</li>"
                    f"</ol>"
                )


            # Create the message box
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Help")

            # Set the text format to Qt.RichText for HTML support
            msg_box.setTextFormat(Qt.RichText)

            # Set the message text with HTML content (using <ul> for an unordered list)
            msg_box.setText(info_message)

            # Display the message box
            msg_box.exec_()
        except Exception as e:
            self.logger.error(f"Error in display help - {e}")

    def showAbout(self):
        """Display a dialog with software version and basic information."""
        try:
            software_version = "DataSync v1.0"
            # author = "John Doe"
            # license_info = "MIT License"
            release_date = '22-01-2025'
            
            # Info message with HTML for a clickable link
            info_message = (
                f"Software Version: {software_version}<br>"
                # f"Author: {author}\n"
                # f"License: {license_info}\n"
                f"Release Date: {release_date}<br>"
                f"For more information, please visit: <a href='https://www.tekuncorked.com/'>www.tekuncorked.com</a>"
            )

            # Create the message box
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("About DataSync v1.0")
            
            # Set the text format to Qt.RichText for HTML support
            msg_box.setTextFormat(Qt.RichText)
            
            # Set the message text with HTML content (including the clickable link)
            msg_box.setText(info_message)
            
            # Display the message box
            msg_box.exec_()
        except Exception as e:
            self.logger.error(f"Error in showAbout - {e}")

    def setup_text_logger(self):
        """Set up the text logger."""
        try:
            logger = logging.getLogger('TextLogger')
            logger.setLevel(logging.DEBUG)

            # Create custom handler for QTextEdit logging
            text_handler = QTextEditLogger(self,self.logTextBox)
            text_handler.setLevel(logging.DEBUG)
            text_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

            # Add the handler to the logger
            logger.addHandler(text_handler)

            return logger, text_handler
        except Exception as e:
            print(e)

    
    @pyqtSlot(str)  # This decorator makes the method a Qt slot
    def logMessageSlot(self, message):
        """This method updates the log widget in the main thread."""
        try:
            self.application_logger.info(message)
            # Update the log widget in the main thread
            # self.log_widget.appendPlainText(message)
        except Exception as e:
            print(e)

    def logMessage(self, message):
        """This method is called to log the message and ensures it's executed in the main thread."""
        # Use QMetaObject.invokeMethod to call logMessageSlot in the main thread
        try:
            QMetaObject.invokeMethod(self, "logMessageSlot", Qt.QueuedConnection,
                                    Q_ARG(str, message))
            self.logger.info(message)
        except Exception as e:
            print(e)

    def stop_timers(self):
        """Stop all timers that checking queues"""
        try:
            if hasattr(self, 'broker1_timer') and self.broker1_timer is not None:
                self.broker1_timer.stop()
                self.broker1_timer.deleteLater()
                self.broker1_timer = None
            if hasattr(self, 'broker2_timer') and self.broker2_timer is not None:
                self.broker2_timer.stop()
                self.broker2_timer.deleteLater()
                self.broker2_timer = None
            
            # print(f"Module Timer stopped, current timers: {QTimer.singleShot(0, lambda: None)}")
        except Exception as e:
            print(f"Exception {e}")
            self.logger.error(f"Exception in stop_timers -  {e}")


    def closeEvent(self, event):
        """Override close event to check for connection before closing."""
        try:
            if self.cl0 is not None or self.cl1 is not None or self.cl2 is not None:
                reply = QMessageBox.question(self, "Confirm",
                                            "Do you want to download the log file before exit?",
                                            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if reply == QMessageBox.Yes:
                    self.download_log_thread_func()
                    event.accept()  # Proceed with closing
                else:
                    event.accept()  # Ignore the close event and keep the window open
            else:
                event.accept()  # Close th
        except Exception as e:
            self.logfile(f"error in closeEvent - {e}")

    def read_file(self,path):
        """read file on the path"""
        try:
            filename=path.split()[-1]
            with open(path, 'r') as file:
                    content = file.read()
            return content
        except Exception as e:
            self.logMessageSignal.emit(f"Internal files missing- {filename}")
            self.logMessageSignal.emit("Please reinstall the software.") 
            self.logger.error(f"error in read_file - {e}")
            
        
    def decrypt_data(self,text):
        """Decrypt the data by using the export_key and return decrypted data."""
        try:
            cipher = Fernet(self.export_key)
            decrypted_data = cipher.decrypt(text)
            decrypted_data = decrypted_data.decode()
            return decrypted_data
        except Exception as e:
            print(f"Exception {e}") 
            self.logMessageSignal.emit("Internal file corrupt please reinstall the software")
            self.logger.error(f"error in decrypt_data - {e}") 
            



def main():
    # time.sleep(2)
    # Hide console if needed
    if not is_admin():
        run_as_admin()
    # if sys.platform == 'win32':
    #     pythoncom.CoInitialize()  # Initialize COM in the main thread
    try:
        app = QApplication(sys.argv)
        # Enable DPI awareness
        if hasattr(Qt, 'AA_EnableHighDpiScaling'):
            app.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
            app.setAttribute(Qt.AA_UseHighDpiPixmaps, True) 
        # Create and show main window

        screen = app.primaryScreen()
        screen_geometry = screen.geometry()
        print("Screen Geometery:",screen_geometry)
        screen_width = screen_geometry.width()
        screen_height = screen_geometry.height()
        mainWindow = MainWindow(screen_width,screen_height)
        mainWindow.show()
        
        # Get the screen size
    
        
        # Set minimum size based on screen size
        mainWindow.setMinimumSize(int(screen_width*0.98), int(screen_height*0.9))
        mainWindow.setMaximumSize(int(screen_width),int(screen_height))        # Start the application
        sys.exit(app.exec_())
    except Exception as e:
        print("ERROR:",e)

if __name__ == "__main__":
    main()




