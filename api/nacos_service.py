import json
import time

from nacos import NacosClient  # python链接nacos SDK —— nacos-python-sdk==0.2

from constents import (
    NACOS_ADDRESSES, NACOS_GROUP_NAME, NACOS_NAMESPACE, NACOS_USERNAME, NACOS_PASSWORD, NACOS_SERVICE_IP, SERVICE_PORT,
    NACOS_SERVICE_VOCALS
)

nacos_client = NacosClient(
    NACOS_ADDRESSES,
    namespace=NACOS_NAMESPACE,  # 命名空间ID 固定
    username=NACOS_USERNAME,  # nacos用户名 固定
    password=NACOS_PASSWORD  # cacos密码 固定
)

def service_register():
    """
    服务注册
    """
    nacos_client.add_naming_instance(
        NACOS_SERVICE_VOCALS,
        NACOS_SERVICE_IP,
        SERVICE_PORT,
        group_name=NACOS_GROUP_NAME,  # 固定
        metadata={
            # interval + timeout = 标记不健康时间
            # delete.timeout = 删除时间
            "preserved.heart.beat.interval": 5000,
            "preserved.heart.beat.timeout": 10000,
            "preserved.ip.delete.timeout": 20000
        })

def config_register():
    """
    发送配置
    """
    service_config_infer = {
        "service": NACOS_SERVICE_VOCALS,  # ai 服务名称
        "input": [  # AI接口入参
            {
                "param": "input_audio_mode",  # 入参
                "default": "url",  # 默认值
                "type": 1,  # 1 str  2 int   3 float 5 list 6 dict 7 bool...  测试没加那么多类型 可补充 同步给我们就好
                "required": True,  # 是否必填
                "description": "input_audio_mode"
            },
            {
                "param": "output_audio_mode",
                "default": "path",
                "type": 1,
                "required": True,
                "description": "output_audio_mode"
            },
            {
                "param": "input_audio_base64",
                "default": None,
                "type": 1,
                "required": False,
                "description": "input_audio_base64"
            },
            {
                "param": "input_audio_path",
                "default": None,
                "type": 1,
                "required": False,
                "description": "input_audio_path"
            },
            {
                "param": "input_audio_url",
                "default": None,
                "type": 1,
                "required": False,
                "description": "input_audio_url"
            }
        ],
        "output": [  # 出参配置待商议
            {
                "param": "vocals_base64",
                "type": 1,
                "description": "vocals_base64"
            },
            {
                "param": "others_base64",
                "type": 1,
                "description": "others_base64"
            },
            {
                "param": "vocals_audio",
                "type": 1,
                "description": "vocals_audio"
            },
            {
                "param": "backing_track",
                "type": 1,
                "description": "backing_track"
            },
        ],
        "config": {
            "path": "/vocals",  # 请求路径
            "request_method": 1,  # 请求方法: 0 - GET, 1 - POST
            "request_type": 0,  # 请求方式: 0 - 同步, 1 - 异步
            "data_type": 1,  # 请求数据类型: 0 - formData, 1 - json
            "timeout": 120  # timeout
        }
    }

    nacos_client.publish_config(
        data_id=service_config_infer["service"],
        group=NACOS_GROUP_NAME,
        content=json.dumps(service_config_infer, ensure_ascii=False),
        config_type="json"
    )

def service_beat():
    """
    心跳发送 每个服务都要发送
    未发送心跳 注册到nacos的服务会挂掉 默认该AI接口不可访问
    """
    while True:
        try:
            nacos_client.send_heartbeat(
                NACOS_SERVICE_VOCALS,
                NACOS_SERVICE_IP,
                SERVICE_PORT,
                group_name=NACOS_GROUP_NAME,  # 固定
                metadata={
                    # interval + timeout = 标记不健康时间
                    # delete.timeout = 删除时间
                    "preserved.heart.beat.interval": 5000,
                    "preserved.heart.beat.timeout": 10000,
                    "preserved.ip.delete.timeout": 20000
                }
            )
        except Exception as e:
            print(f"send heartbeat error:{e}")
        time.sleep(5)
