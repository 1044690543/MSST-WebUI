import os
import socket
import platform

from dotenv import load_dotenv

def load_environment():
    load_dotenv('./api/.env.common')
    system = platform.system().lower()
    if system == 'windows':
        load_dotenv('./api/.env.windows')
    elif system == 'linux':
        load_dotenv('./api/.env.linux')
    else:
        raise ValueError(f"Unsupported operating system: {system}")
load_environment()

def get_local_ip():
    try:
        # 创建一个临时的套接字
        temp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        temp_socket.connect(("8.8.8.8", 80))  # 连接到一个公共的IP地址，如Google DNS
        local_ip = temp_socket.getsockname()[0]  # 获取本地IP地址
        temp_socket.close()  # 关闭套接字连接
        return local_ip
    except Exception as e:
        print("获取本地IP失败:", e)
        return None

LOCAL_IP = get_local_ip()
MSST_DIR_TMP = os.path.join(os.environ.get("BASE_DIR"), "msst_tmp")
MSST_DIR = os.path.join(os.environ.get("BASE_DIR"), "msst")
SERVICE_IP=os.environ.get("SERVICE_IP", None) if os.environ.get("SERVICE_IP", None) else LOCAL_IP
SERVICE_PORT=int(os.environ.get("SERVICE_PORT"))  # AI服务接口端口
API_WORKER = int(os.environ.get("API_WORKER"))
IS_MAAS = int(os.environ.get("IS_MAAS"))

# nacos config
NACOS_ADDRESSES=os.environ.get("NACOS_ADDRESSES")  # nacos地址 固定
NACOS_NAMESPACE=os.environ.get("NACOS_NAMESPACE")  # 命名空间ID 固定
NACOS_USERNAME=os.environ.get("NACOS_USERNAME")  # nacos用户名 固定
NACOS_PASSWORD=os.environ.get("NACOS_PASSWORD")  # cacos密码 固定
NACOS_SERVICE_NAME=os.environ.get("NACOS_SERVICE_NAME")  # infer 服务名称
NACOS_SERVICE_VOCALS=os.environ.get("NACOS_SERVICE_VOCALS")  # 接口名称
NACOS_SERVICE_IP=os.environ.get("NACOS_SERVICE_IP", None) if os.environ.get("NACOS_SERVICE_IP", None) else LOCAL_IP  # AI服务接口所在地址
NACOS_GROUP_NAME=os.environ.get("NACOS_GROUP_NAME")

# 初始化的三个模型
MSST_INFER_OBJECT = {}
