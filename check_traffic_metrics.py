#!/usr/bin/env python3
"""
Controlla se ci sono metriche di traffico HTTP in Envoy
"""

queries_to_test = [
    # Query originali che stai usando
    'rate(envoy_cluster_upstream_rq_total{envoy_cluster_name="ms_exercise_cluster"}[1m])',
    'rate(envoy_cluster_upstream_rq_completed{envoy_cluster_name="ms_exercise_cluster"}[1m])',
    
    # Metriche HTTP downstream (traffico in ingresso al gateway)
    'envoy_http_downstream_rq_total',
    'rate(envoy_http_downstream_rq_total[1m])',
    
    # Altre metriche di traffico possibili
    'envoy_http_downstream_rq_completed',
    'envoy_http_inbound_0_0_0_0_80_downstream_rq_total',
    'envoy_listener_downstream_cx_total',
    
    # Metriche a livello di listener
    'envoy_listener_http_downstream_rq_total',
]

print("🔍 Testing various Envoy traffic metrics...")
print("\nPaste these queries into Prometheus to check which ones return data:")
print("=" * 60)

for i, query in enumerate(queries_to_test, 1):
    print(f"{i}. {query}")

print("\n" + "=" * 60)
print("Look for queries that return NON-ZERO values!")
print("\nIf all return 0 or no data, it means:")
print("1. No traffic is flowing through Envoy proxies")
print("2. Load test is not running")  
print("3. Traffic is not being routed through Envoy")
print("\n🚀 Try running a load test and then check these metrics again")