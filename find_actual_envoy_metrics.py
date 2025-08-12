#!/usr/bin/env python3
"""
Trova le metriche HTTP realmente disponibili in Envoy
"""

print("🔍 Check these queries in Prometheus to find ACTUAL HTTP metrics:")
print("=" * 70)

queries_to_test = [
    # HTTP listener metrics (potrebbe essere dove sono le metriche HTTP reali)
    'envoy_http_downstream_rq_total',
    'envoy_listener_downstream_cx_total', 
    'envoy_server_total_connections',
    
    # HTTP connection manager metrics  
    '{__name__=~"envoy_http.*"}',
    '{__name__=~"envoy_listener.*"}',
    '{__name__=~"envoy_server.*"}',
    
    # Upstream metrics (diverse da cluster)
    '{__name__=~"envoy_upstream.*"}',
    
    # Check all metrics starting with envoy_ to see what's available
    '{__name__=~"envoy_.*rq.*"}',  # All request-related metrics
    '{__name__=~"envoy_.*response.*"}',  # All response-related metrics
]

for i, query in enumerate(queries_to_test, 1):
    print(f"{i:2d}. {query}")

print("\n" + "=" * 70)
print("IMPORTANT: Look for metrics that contain:")
print("- 'rq_total' (request totals)")
print("- 'rq_time' (request times)")  
print("- 'downstream' (incoming traffic)")
print("- 'upstream' (outgoing traffic)")
print("\nOnce you find the actual metrics, we'll update the monitoring.py queries!")