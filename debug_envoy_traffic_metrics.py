#!/usr/bin/env python3
"""
Debug per trovare le metriche HTTP reali di Envoy (non admin interface)
"""

queries_to_test = [
    # Metriche HTTP downstream (traffico in ingresso reale)
    'envoy_http_downstream_rq_total{envoy_http_conn_manager_prefix!="admin"}',
    'envoy_http_downstream_rq_completed{envoy_http_conn_manager_prefix!="admin"}',
    'envoy_http_downstream_rq_time_sum{envoy_http_conn_manager_prefix!="admin"}',
    'envoy_http_downstream_rq_time_count{envoy_http_conn_manager_prefix!="admin"}',
    
    # Metriche listener HTTP (potrebbe essere dove sono i dati reali)
    'envoy_http_inbound_*_downstream_rq_total',
    'envoy_listener_http_downstream_rq_total',
    
    # Tutte le metriche HTTP non-admin
    '{__name__=~"envoy_http.*rq.*", envoy_http_conn_manager_prefix!="admin"}',
    '{__name__=~"envoy_http.*time.*", envoy_http_conn_manager_prefix!="admin"}',
    
    # Metriche cluster per traffico upstream
    'envoy_cluster_upstream_rq_total',
    'envoy_cluster_upstream_rq_time_sum',
    'envoy_cluster_upstream_rq_time_count',
    
    # Pattern specifici per i tuoi servizi
    '{__name__=~"envoy_.*", job="envoy-ms-exercise"}',
    '{__name__=~"envoy_.*", job="envoy-gateway"}',
    '{__name__=~"envoy_.*rq.*", job=~"envoy-.*"}',
]

print("🔍 FIND REAL TRAFFIC METRICS (not admin interface):")
print("=" * 70)

for i, query in enumerate(queries_to_test, 1):
    print(f"{i:2d}. {query}")

print("\n" + "=" * 70)
print("EXPECTED BEHAVIOR:")
print("- Query should return metrics with job='envoy-ms-exercise', 'envoy-gateway', etc.")
print("- RPS should be ~22.5 (matching Locust)")
print("- Response time should be ~150ms average")
print("- Look for conn_manager_prefix != 'admin' (real traffic)")
print("\n🎯 Find queries that return REAL APPLICATION TRAFFIC metrics!")