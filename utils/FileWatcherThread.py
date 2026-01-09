from PyQt6.QtCore import QThread, pyqtSignal
import time, logging
from datetime import datetime

class FileWatcherThread(QThread):
    file_updated = pyqtSignal(str)  # 파일 변경 시 신호를 보냄

    def __init__(self, ssh_manager, remote_file_path):
        super().__init__()
        self.ssh_manager = ssh_manager
        self.remote_file_path = remote_file_path
        self.running = True

    def run(self):
        last_modified_time = None
        while self.running:
            try:
            
                # 서버에서 파일의 수정 시간 확인
                command = f"stat -c %Y \"{self.remote_file_path}\""
                stdin, stdout, stderr = self.ssh_manager.ssh.exec_command(command)
                current_modified_time = int(stdout.read().strip())

                if last_modified_time is None or current_modified_time != last_modified_time:
                    last_modified_time = current_modified_time
                    logging.info(f"마지막 수정 시간: {datetime.fromtimestamp(last_modified_time)}")
                    logging.info(f"파일이 변경되었습니다: {self.remote_file_path}")

                    # 파일 변경 신호 전송
                    self.file_updated.emit(self.remote_file_path)
            except Exception as e:
                logging.info(f"Error watching file: {e}")

            # 1초 간격으로 파일 감시
            time.sleep(1)