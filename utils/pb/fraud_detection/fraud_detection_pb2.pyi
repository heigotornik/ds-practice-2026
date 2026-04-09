from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class InitOrderResponse(_message.Message):
    __slots__ = ("ok",)
    OK_FIELD_NUMBER: _ClassVar[int]
    ok: bool
    def __init__(self, ok: bool = ...) -> None: ...

class StatusUpdateRequest(_message.Message):
    __slots__ = ("id", "TransactionServiceA", "TransactionServiceB", "FraudDetection", "Suggestions")
    ID_FIELD_NUMBER: _ClassVar[int]
    TRANSACTIONSERVICEA_FIELD_NUMBER: _ClassVar[int]
    TRANSACTIONSERVICEB_FIELD_NUMBER: _ClassVar[int]
    FRAUDDETECTION_FIELD_NUMBER: _ClassVar[int]
    SUGGESTIONS_FIELD_NUMBER: _ClassVar[int]
    id: str
    TransactionServiceA: int
    TransactionServiceB: int
    FraudDetection: int
    Suggestions: int
    def __init__(self, id: _Optional[str] = ..., TransactionServiceA: _Optional[int] = ..., TransactionServiceB: _Optional[int] = ..., FraudDetection: _Optional[int] = ..., Suggestions: _Optional[int] = ...) -> None: ...

class StatusUpdateResponse(_message.Message):
    __slots__ = ("id", "ok", "message")
    ID_FIELD_NUMBER: _ClassVar[int]
    OK_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    id: str
    ok: bool
    message: str
    def __init__(self, id: _Optional[str] = ..., ok: bool = ..., message: _Optional[str] = ...) -> None: ...

class OrderData(_message.Message):
    __slots__ = ("user", "creditCard", "userComment", "items", "billingAddress", "shippingMethod", "giftWrapping", "termsAccepted")
    USER_FIELD_NUMBER: _ClassVar[int]
    CREDITCARD_FIELD_NUMBER: _ClassVar[int]
    USERCOMMENT_FIELD_NUMBER: _ClassVar[int]
    ITEMS_FIELD_NUMBER: _ClassVar[int]
    BILLINGADDRESS_FIELD_NUMBER: _ClassVar[int]
    SHIPPINGMETHOD_FIELD_NUMBER: _ClassVar[int]
    GIFTWRAPPING_FIELD_NUMBER: _ClassVar[int]
    TERMSACCEPTED_FIELD_NUMBER: _ClassVar[int]
    user: User
    creditCard: CreditCard
    userComment: str
    items: _containers.RepeatedCompositeFieldContainer[Item]
    billingAddress: Address
    shippingMethod: str
    giftWrapping: bool
    termsAccepted: bool
    def __init__(self, user: _Optional[_Union[User, _Mapping]] = ..., creditCard: _Optional[_Union[CreditCard, _Mapping]] = ..., userComment: _Optional[str] = ..., items: _Optional[_Iterable[_Union[Item, _Mapping]]] = ..., billingAddress: _Optional[_Union[Address, _Mapping]] = ..., shippingMethod: _Optional[str] = ..., giftWrapping: bool = ..., termsAccepted: bool = ...) -> None: ...

class User(_message.Message):
    __slots__ = ("name", "contact")
    NAME_FIELD_NUMBER: _ClassVar[int]
    CONTACT_FIELD_NUMBER: _ClassVar[int]
    name: str
    contact: str
    def __init__(self, name: _Optional[str] = ..., contact: _Optional[str] = ...) -> None: ...

class CreditCard(_message.Message):
    __slots__ = ("number", "expirationDate", "cvv")
    NUMBER_FIELD_NUMBER: _ClassVar[int]
    EXPIRATIONDATE_FIELD_NUMBER: _ClassVar[int]
    CVV_FIELD_NUMBER: _ClassVar[int]
    number: str
    expirationDate: str
    cvv: str
    def __init__(self, number: _Optional[str] = ..., expirationDate: _Optional[str] = ..., cvv: _Optional[str] = ...) -> None: ...

class Item(_message.Message):
    __slots__ = ("name", "quantity")
    NAME_FIELD_NUMBER: _ClassVar[int]
    QUANTITY_FIELD_NUMBER: _ClassVar[int]
    name: str
    quantity: int
    def __init__(self, name: _Optional[str] = ..., quantity: _Optional[int] = ...) -> None: ...

class Address(_message.Message):
    __slots__ = ("street", "city", "state", "zip", "country")
    STREET_FIELD_NUMBER: _ClassVar[int]
    CITY_FIELD_NUMBER: _ClassVar[int]
    STATE_FIELD_NUMBER: _ClassVar[int]
    ZIP_FIELD_NUMBER: _ClassVar[int]
    COUNTRY_FIELD_NUMBER: _ClassVar[int]
    street: str
    city: str
    state: str
    zip: str
    country: str
    def __init__(self, street: _Optional[str] = ..., city: _Optional[str] = ..., state: _Optional[str] = ..., zip: _Optional[str] = ..., country: _Optional[str] = ...) -> None: ...

class VerifyResponse(_message.Message):
    __slots__ = ("isValid", "message")
    ISVALID_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    isValid: bool
    message: str
    def __init__(self, isValid: bool = ..., message: _Optional[str] = ...) -> None: ...

class InitOrderRequest(_message.Message):
    __slots__ = ("id", "order")
    ID_FIELD_NUMBER: _ClassVar[int]
    ORDER_FIELD_NUMBER: _ClassVar[int]
    id: str
    order: OrderData
    def __init__(self, id: _Optional[str] = ..., order: _Optional[_Union[OrderData, _Mapping]] = ...) -> None: ...
