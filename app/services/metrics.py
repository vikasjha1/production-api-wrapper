from prometheus_client import CollectorRegistry, Counter, Histogram


class Metrics:
    def __init__(self, registry: CollectorRegistry) -> None:
        self.request_count = Counter(
            "gateway_requests_total",
            "Total number of requests handled",
            ["method", "path", "status_code"],
            registry=registry,
        )
        self.request_latency = Histogram(
            "gateway_request_duration_seconds",
            "Request latency in seconds",
            ["method", "path"],
            registry=registry,
        )


def build_metrics_registry() -> CollectorRegistry:
    return CollectorRegistry()


def build_metrics(registry: CollectorRegistry) -> Metrics:
    return Metrics(registry)
