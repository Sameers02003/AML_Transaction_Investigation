from prometheus_client import Counter, Histogram

REQUESTS = Counter("aml_api_requests_total", "API requests", ["method", "path", "status"])
LATENCY = Histogram("aml_api_request_seconds", "API request latency in seconds", ["path"])