
import logging
import grpc


logger = logging.getLogger(__name__)

class LoggingInterceptor(grpc.ServerInterceptor):

    def intercept_service(self, continuation, handler_call_details):
        logger.info(f"Incoming RPC: {handler_call_details.method}")
        return continuation(handler_call_details)