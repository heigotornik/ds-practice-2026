from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class AccessRequest(_message.Message):
    __slots__ = ("nodeId",)
    NODEID_FIELD_NUMBER: _ClassVar[int]
    nodeId: int
    def __init__(self, nodeId: _Optional[int] = ...) -> None: ...

class AccessResponse(_message.Message):
    __slots__ = ("ok",)
    OK_FIELD_NUMBER: _ClassVar[int]
    ok: bool
    def __init__(self, ok: bool = ...) -> None: ...

class EnqueueRequest(_message.Message):
    __slots__ = ("id",)
    ID_FIELD_NUMBER: _ClassVar[int]
    id: str
    def __init__(self, id: _Optional[str] = ...) -> None: ...

class EnqueueResponse(_message.Message):
    __slots__ = ("ok",)
    OK_FIELD_NUMBER: _ClassVar[int]
    ok: bool
    def __init__(self, ok: bool = ...) -> None: ...

class DequeueRequest(_message.Message):
    __slots__ = ("dummy",)
    DUMMY_FIELD_NUMBER: _ClassVar[int]
    dummy: str
    def __init__(self, dummy: _Optional[str] = ...) -> None: ...

class DequeueResponse(_message.Message):
    __slots__ = ("id",)
    ID_FIELD_NUMBER: _ClassVar[int]
    id: str
    def __init__(self, id: _Optional[str] = ...) -> None: ...
