from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class ElectionRequest(_message.Message):
    __slots__ = ("node_id",)
    NODE_ID_FIELD_NUMBER: _ClassVar[int]
    node_id: int
    def __init__(self, node_id: _Optional[int] = ...) -> None: ...

class ElectionResponse(_message.Message):
    __slots__ = ("ok",)
    OK_FIELD_NUMBER: _ClassVar[int]
    ok: bool
    def __init__(self, ok: bool = ...) -> None: ...

class CoordinatorRequest(_message.Message):
    __slots__ = ("leader_id",)
    LEADER_ID_FIELD_NUMBER: _ClassVar[int]
    leader_id: int
    def __init__(self, leader_id: _Optional[int] = ...) -> None: ...

class CoordinatorResponse(_message.Message):
    __slots__ = ("acknowledged",)
    ACKNOWLEDGED_FIELD_NUMBER: _ClassVar[int]
    acknowledged: bool
    def __init__(self, acknowledged: bool = ...) -> None: ...

class Empty(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...
