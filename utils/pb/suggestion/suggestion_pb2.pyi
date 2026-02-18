from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class BookList(_message.Message):
    __slots__ = ("books",)
    BOOKS_FIELD_NUMBER: _ClassVar[int]
    books: _containers.RepeatedCompositeFieldContainer[Book]
    def __init__(self, books: _Optional[_Iterable[_Union[Book, _Mapping]]] = ...) -> None: ...

class Book(_message.Message):
    __slots__ = ("bookId", "title", "author")
    BOOKID_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    AUTHOR_FIELD_NUMBER: _ClassVar[int]
    bookId: int
    title: str
    author: str
    def __init__(self, bookId: _Optional[int] = ..., title: _Optional[str] = ..., author: _Optional[str] = ...) -> None: ...
