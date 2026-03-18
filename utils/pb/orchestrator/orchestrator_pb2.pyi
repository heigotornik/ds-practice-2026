from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class ResultMessage(_message.Message):
    __slots__ = ("orderId", "success", "message")
    ORDERID_FIELD_NUMBER: _ClassVar[int]
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    orderId: str
    success: bool
    message: str
    def __init__(self, orderId: _Optional[str] = ..., success: bool = ..., message: _Optional[str] = ...) -> None: ...

class Ack(_message.Message):
    __slots__ = ("received",)
    RECEIVED_FIELD_NUMBER: _ClassVar[int]
    received: bool
    def __init__(self, received: bool = ...) -> None: ...
