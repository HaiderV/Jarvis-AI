# backend/app/core/telemetry.py
import time

class PerformanceTracker:
    def __init__(self):
        self.metrics = {}
        self.start_time = time.perf_counter()

    def record(self, key: str, duration_ms: float):
        self.metrics[key] = round(duration_ms, 2)

    def total_duration_ms(self) -> float:
        return round((time.perf_counter() - self.start_time) * 1000, 2)

    def get_summary(self) -> dict:
        summary = dict(self.metrics)
        summary["total_backend_ms"] = self.total_duration_ms()
        return summary