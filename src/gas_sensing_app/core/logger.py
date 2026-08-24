# src/gas_sensing_app/core/logger.py

# # ==============================================================================
# O. GLOBAL PRINT INTERCEPTOR (Thread-Safe Queue Approach)
# ==============================================================================
class WriteStream:
    def __init__(self, original_stream, log_file=None, text_queue=None):
        self.original_stream = original_stream
        self.log_file = log_file
        self.text_queue = text_queue
        self._prevent_loop = False

    def write(self, text):
        if self._prevent_loop:
            self.original_stream.write(text)
            return
        self._prevent_loop = True
        try:
            self.original_stream.write(text)
            if self.log_file:
                self.log_file.write(text)
                self.log_file.flush()
            if self.text_queue and text:
                self.text_queue.put(text)
        finally:
            self._prevent_loop = False

    def flush(self):
        self.original_stream.flush()
        if self.log_file:
            self.log_file.flush()
