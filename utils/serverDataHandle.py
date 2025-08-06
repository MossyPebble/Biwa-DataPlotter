import json
import SSHManager

# JSON 파일에서 SSH 설정 로드
config_path = "C:/Workspace/Python/Biwa-DataPlotter/config/ssh_config.json"
with open(config_path, "r") as config_file:
    ssh_config = json.load(config_file)

# SSH 설정을 사용하여 SSHManager 초기화
ssh = SSHManager.SSHManager(
    host=ssh_config["host"],
    port=ssh_config["port"],
    userId=ssh_config["userId"],
    key_path=ssh_config["key_path"]
)