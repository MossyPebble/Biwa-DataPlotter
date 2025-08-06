import paramiko, time

class SSHManager:
    
    """
    어떤 ssh 서버에 접속하고 그 안에서 명령어 실행, 파일 송수신을 담당하는 클래스
    """

    def __init__(self, host, port, userId, key_path=None, password=None) -> None:
        """
        SSH 서버에 접속한다.

        Args:
            host (str): 접속할 SSH 서버의 주소
            port (int): 접속할 SSH 서버의 포트
            userId (str): SSH 서버에 접속할 계정
            key_path (str, optional): SSH 키 파일 경로. 기본값은 None.
            password (str, optional): SSH 키의 비밀번호 또는 계정 비밀번호. 기본값은 None.
        """
        try:
            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            # SSH 키를 사용하는 경우
            if key_path:
                private_key = paramiko.RSAKey.from_private_key_file(key_path, password)
                self.ssh.connect(host, port, userId, pkey=private_key)
            else:
                # 비밀번호를 사용하는 경우
                self.ssh.connect(host, port, userId, password=password)

            self.sftp = self.ssh.open_sftp()
        except Exception as e:
            print(e)
            raise Exception("SSH 서버에 접속할 수 없습니다. 인터넷 연결 상태를 확인해주세요.")
        
    def invoke_shell(self) -> paramiko.Channel:

        """
        ssh 서버에 shell을 실행한다.

        만약, 명령어 실행 경로를 계속 유지하고 싶다거나 하면 shell을 열어서 명령어를 실행하면 된다.

        Returns:
            paramiko.Channel: shell을 실행한 결과
        """

        return self.ssh.invoke_shell()
    
    def execute_commands_over_shell(channel: paramiko.Channel, commands: list) -> None:

        """
        SSH 채널을 통해 명령어를 실행하는 함수

        Args:
            channel (paramiko.Channel): SSH 채널
            commands (list): 실행할 명령어 리스트
        """

        
        for command in commands:
            output = ""
            print(f"\nSending command: {command.strip()}")
            channel.send(command + " && echo '__END__'\n")
            
            while True:
                if channel.recv_ready():
                    output += (recieved := channel.recv(2^20).decode('utf-8'))
                    print(recieved, end="")
                else:
                    if "__END__" in output: break
                time.sleep(0.1)

    def get_file(self, src, dst) -> None:

        """
        ssh 서버로부터 파일을 다운로드한다.

        Args:
            src (str): 다운로드할 파일의 경로 (서버)
            dst (str): 다운로드한 파일을 저장할 경로 (로컬)
        """

        self.sftp.get(src, dst)

    def put_file(self, src: str, dst: str) -> None:

        """
        ssh 서버로 파일을 업로드한다.

        Args:
            src (str): 업로드할 파일의 경로 (로컬)
            dst (str): 업로드할 파일을 저장할 경로 (서버)
        """

        self.sftp.put(src, dst)

    def send_command(self, cmd) -> str:

        """
        ssh 서버에 명령어를 전송한다.

        Args:
            cmd (str): 전송할 명령어

        Returns:
            str: 명령어의 실행 결과
        """

        print("명령어:", cmd)
        stdin, stdout, stderr = self.ssh.exec_command(cmd)
        return stdout.read().decode()
    
    def change_file_content(self, file_path, old, new) -> str:

        """
        ssh 서버에 있는 파일의 내용을 변경한다.

        Args:
            file_path (str): 내용을 변경할 파일의 경로
            old (str): 변경할 내용 중 변경 전 내용
            new (str): 변경할 내용 중 변경 후 내용

        Returns:
            str: 명령어의 실행 결과
        """

        return self.send_command(f"sed -i \"s/{old}/{new}/g\" {file_path}")

    def close(self) -> None:
        self.sftp.close()
        self.ssh.close()

    def __del__(self) -> None:
        self.sftp.close()
        self.ssh.close()