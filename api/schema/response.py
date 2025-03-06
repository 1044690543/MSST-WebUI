"""
Custom General Response
"""

from typing import Generic, TypeVar

from fastapi.responses import JSONResponse
from pydantic import BaseModel

T = TypeVar("T")


class RespException(Exception):
    def __init__(self, value: int, msg: str, msg_cn: str):
        self.value = value
        self.msg = msg
        self.msg_cn = msg_cn

    def __int__(self):
        return self.value

    def __str__(self):
        return self.msg


class RespStatus:
    BASE = 200
    SUCCESS = RespException(BASE, "Success", "成功")
    FAILED = RespException(BASE + 1, "Faild", "失败")
    UNKNOWN = RespException(BASE + 2, "Unknown error", "未知错误")


class GeneralResponse(BaseModel, Generic[T]):
    code: int = int(RespStatus.SUCCESS)
    message: str = str(RespStatus.SUCCESS)
    success: bool = True
    data: T = None
    err_msg: str = ""

    def set_obj(
        self,
        obj: RespException = RespStatus.SUCCESS,
        success: bool = True,
        msg_type: str = "msg",
        err_msg: str = "",
        cuz_msg: str = "",
        cuz_msg_cn: str = "",
    ):
        self.message = (
            cuz_msg or str(obj) if msg_type == "msg" else cuz_msg_cn or obj.msg_cn
        )
        self.code = int(obj)
        self.success = success
        self.err_msg = err_msg


def http_response(data=None, message=None, obj=RespStatus.SUCCESS):
    content = {"code": int(obj), "data": data, "message": message or str(obj)}
    return JSONResponse(content)
