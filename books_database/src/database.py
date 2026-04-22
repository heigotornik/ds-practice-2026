import logging
import grpc
from logging.config import dictConfig
import os
import sys
import threading
from collections import defaultdict


FILE = __file__ if '__file__' in globals() else os.getenv("PYTHONFILE", "")
def add_proto_path(relative_path: str):
    abs_path = os.path.abspath(os.path.join(FILE, relative_path))
    if abs_path not in sys.path:
        sys.path.insert(0, abs_path)

add_proto_path('../../../utils/pb/books_database')

import books_database_pb2 as books_database
import books_database_pb2_grpc as books_database_grpc


dictConfig({
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'default': {
            'format': '[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
        }
    },
    'handlers': {
        'grpc': {
            'class': 'logging.StreamHandler',
            'stream': sys.stderr,
            'formatter': 'default',
        }
    },
    'root': {
        'level': 'DEBUG',
        'handlers': ['grpc']
    }
})

logger = logging.getLogger(__name__)


class TransactionState:
    PREPARED = "PREPARED"
    COMMITTED = "COMMITTED"
    ABORTED = "ABORTED"


class BooksDatabaseService(books_database_grpc.BooksDatabaseServicer):
    """
    Shared transaction logic for both primary and backup database instances.
    """

    def __init__(self, initial_store=None):
        self.store = dict(initial_store or {})
        self.locks = defaultdict(threading.Lock)   # per-book lock
        self.tx_lock = threading.Lock()            # protects self.transactions

        # tx_id -> {
        #   "state": PREPARED/COMMITTED/ABORTED,
        #   "title": str,
        #   "quantity": int,
        #   "new_stock": int
        # }
        self.transactions = {}

    def Read(self, request, context):
        title = request.title
        stock = self.store.get(title, 0)
        logger.info("[Read] %s -> %s", title, stock)
        return books_database.ReadResponse(stock=stock)

    # ---------- Local 2PC helpers ----------
    def _prepare_local(self, tx_id: str, title: str, quantity: int) -> bool:
        lock = self.locks[title]

        with lock:
            with self.tx_lock:
                tx = self.transactions.get(tx_id)

                if tx is not None:
                    state = tx["state"]

                    if state == TransactionState.PREPARED:
                        logger.info("[Prepare] tx %s already prepared", tx_id)
                        return True

                    if state == TransactionState.COMMITTED:
                        logger.warning("[Prepare] tx %s already committed", tx_id)
                        return False

                    if state == TransactionState.ABORTED:
                        logger.warning("[Prepare] tx %s already aborted", tx_id)
                        return False

                current_stock = self.store.get(title, 0)
                if current_stock < quantity:
                    logger.warning(
                        "[Prepare] insufficient stock for tx %s: title=%s stock=%d quantity=%d",
                        tx_id, title, current_stock, quantity
                    )
                    self.transactions[tx_id] = {
                        "state": TransactionState.ABORTED,
                        "title": title,
                        "quantity": quantity,
                        "new_stock": current_stock,
                    }
                    return False

                new_stock = current_stock - quantity
                self.transactions[tx_id] = {
                    "state": TransactionState.PREPARED,
                    "title": title,
                    "quantity": quantity,
                    "new_stock": new_stock,
                }

                logger.info(
                    "[Prepare] tx %s prepared locally: title=%s quantity=%d new_stock=%d",
                    tx_id, title, quantity, new_stock
                )
                return True

    def _commit_local(self, tx_id: str) -> bool:
        with self.tx_lock:
            tx = self.transactions.get(tx_id)

            if tx is None:
                logger.warning("[Commit] unknown tx %s", tx_id)
                return False

            state = tx["state"]

            if state == TransactionState.COMMITTED:
                logger.info("[Commit] tx %s already committed", tx_id)
                return True

            if state != TransactionState.PREPARED:
                logger.warning("[Commit] invalid state for tx %s: %s", tx_id, state)
                return False

            title = tx["title"]
            new_stock = tx["new_stock"]

            lock = self.locks[title]
            with lock:
                self.store[title] = new_stock
                tx["state"] = TransactionState.COMMITTED

            logger.info("[Commit] tx %s committed locally", tx_id)
            return True

    def _abort_local(self, tx_id: str) -> bool:
        with self.tx_lock:
            tx = self.transactions.get(tx_id)

            if tx is None:
                logger.info("[Abort] unknown tx %s treated as aborted", tx_id)
                return True

            state = tx["state"]

            if state == TransactionState.ABORTED:
                logger.info("[Abort] tx %s already aborted", tx_id)
                return True

            if state == TransactionState.COMMITTED:
                logger.warning("[Abort] cannot abort committed tx %s", tx_id)
                return False

            tx["state"] = TransactionState.ABORTED
            logger.info("[Abort] tx %s aborted locally", tx_id)
            return True

    # ---------- RPC methods for a standalone participant / backup ----------
    def Prepare(self, request, context):
        ready = self._prepare_local(
            tx_id=request.transaction_id,
            title=request.title,
            quantity=request.quantity,
        )
        return books_database.PrepareResponse(ready=ready)

    def Commit(self, request, context):
        success = self._commit_local(request.transaction_id)
        return books_database.CommitResponse(success=success)

    def Abort(self, request, context):
        aborted = self._abort_local(request.transaction_id)
        return books_database.AbortResponse(aborted=aborted)


class PrimaryReplica(BooksDatabaseService):
    """
    Primary database:
    - handles client/executor traffic
    - internally coordinates Prepare/Commit/Abort with backups
    """

    def __init__(self, backup_stubs, initial_store=None):
        super().__init__(initial_store=initial_store)
        self.backup_stubs = list(backup_stubs)

    def Prepare(self, request, context):
        tx_id = request.transaction_id
        title = request.title
        quantity = request.quantity

        logger.info("[Primary Prepare] tx %s starting", tx_id)

        local_ready = self._prepare_local(tx_id, title, quantity)
        if not local_ready:
            logger.warning("[Primary Prepare] local prepare failed for tx %s", tx_id)
            return books_database.PrepareResponse(ready=False)

        all_ready = True

        for idx, stub in enumerate(self.backup_stubs):
            try:
                resp = stub.Prepare(
                    books_database.PrepareRequest(
                        transaction_id=tx_id,
                        title=title,
                        quantity=quantity,
                    )
                )
                if not resp.ready:
                    logger.warning(
                        "[Primary Prepare] backup %s voted NO for tx %s",
                        self.backup_stubs[idx], tx_id
                    )
                    all_ready = False
                    break
            except grpc.RpcError as e:
                logger.error(
                    "[Primary Prepare] backup %s unreachable for tx %s: %s",
                    self.backup_stubs[idx], tx_id, e
                )
                all_ready = False
                break

        if not all_ready:
            # Best-effort rollback of local+remote prepared state
            logger.warning("[Primary Prepare] aborting tx %s due to backup prepare failure", tx_id)
            self._abort_local(tx_id)

            for idx, stub in enumerate(self.backup_stubs):
                try:
                    stub.Abort(
                        books_database.AbortRequest(transaction_id=tx_id)
                    )
                except grpc.RpcError:
                    logger.warning(
                        "[Primary Prepare] backup abort failed for %s after prepare failure",
                        self.backup_stubs[idx]
                    )

            return books_database.PrepareResponse(ready=False)

        logger.info("[Primary Prepare] tx %s all replicas prepared", tx_id)
        return books_database.PrepareResponse(ready=True)

    def Commit(self, request, context):
        tx_id = request.transaction_id
        logger.info("[Primary Commit] tx %s starting", tx_id)

        # Commit locally first or remotely first?
        # In this design we commit locally first, then require backups to commit.
        local_success = self._commit_local(tx_id)
        if not local_success:
            logger.warning("[Primary Commit] local commit failed for tx %s", tx_id)
            return books_database.CommitResponse(success=False)

        all_success = True

        for idx, stub in enumerate(self.backup_stubs):
            try:
                resp = stub.Commit(
                    books_database.CommitRequest(transaction_id=tx_id)
                )
                if not resp.success:
                    logger.error(
                        "[Primary Commit] backup %s failed commit for tx %s",
                        self.backup_stubs[idx], tx_id
                    )
                    all_success = False
            except grpc.RpcError as e:
                logger.error(
                    "[Primary Commit] backup %s unreachable during commit for tx %s: %s",
                    self.backup_stubs[idx], tx_id, e
                )
                all_success = False

        if not all_success:
            logger.error(
                "[Primary Commit] tx %s committed on primary but not all backups; replicas may be inconsistent",
                tx_id
            )

        return books_database.CommitResponse(success=all_success)

    def Abort(self, request, context):
        tx_id = request.transaction_id
        logger.info("[Primary Abort] tx %s starting", tx_id)

        local_aborted = self._abort_local(tx_id)

        all_aborted = local_aborted

        for idx, stub in enumerate(self.backup_stubs):
            try:
                resp = stub.Abort(
                    books_database.AbortRequest(transaction_id=tx_id)
                )
                if not resp.aborted:
                    logger.warning(
                        "[Primary Abort] backup %s did not abort tx %s",
                        self.backup_stubs[idx], tx_id
                    )
                    all_aborted = False
            except grpc.RpcError as e:
                logger.warning(
                    "[Primary Abort] backup %s unreachable during abort for tx %s: %s",
                    self.backup_stubs[idx], tx_id, e
                )
                all_aborted = False

        return books_database.AbortResponse(aborted=all_aborted)
