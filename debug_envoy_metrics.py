#!/usr/bin/env python3
"""
Script per debuggare i nomi dei cluster Envoy disponibili in Prometheus
"""

import sys
from pathlib import Path
from prometheus_api_client import PrometheusConnect

# Add the project root to sys.path
sys.path.append(str(Path(__file__).parent))

def debug_envoy_cluster_names(prom_host="localhost", prom_port=9090):
    """
    Cerca tutti i cluster names disponibili nelle metriche Envoy
    """
    print(f"🔍 Connecting to Prometheus at {prom_host}:{prom_port}")
    
    try:
        prom = PrometheusConnect(url=f"http://{prom_host}:{prom_port}", disable_ssl=True)
        
        print("\n=== 1. Searching for Envoy cluster metrics ===")
        
        # Query per trovare tutti i cluster names nelle metriche Envoy
        queries_to_check = [
            "envoy_cluster_upstream_rq_total",
            "envoy_cluster_upstream_rq_completed", 
            "envoy_cluster_upstream_rq_time_sum",
            "envoy_cluster_upstream_rq_time_count"
        ]
        
        all_cluster_names = set()
        
        for query in queries_to_check:
            print(f"\n📊 Checking metric: {query}")
            try:
                result = prom.custom_query(query)
                
                if result:
                    print(f"   Found {len(result)} series")
                    for series in result[:5]:  # Show first 5 series
                        if 'metric' in series and 'envoy_cluster_name' in series['metric']:
                            cluster_name = series['metric']['envoy_cluster_name']
                            all_cluster_names.add(cluster_name)
                            print(f"   - envoy_cluster_name: {cluster_name}")
                        else:
                            print(f"   - Series: {series.get('metric', {})}")
                    
                    if len(result) > 5:
                        print(f"   ... and {len(result) - 5} more")
                else:
                    print("   ❌ No data found")
                    
            except Exception as e:
                print(f"   ❌ Error: {e}")
        
        print(f"\n=== 2. All unique cluster names found ===")
        if all_cluster_names:
            for cluster_name in sorted(all_cluster_names):
                print(f"✅ {cluster_name}")
        else:
            print("❌ No cluster names found")
            
        print(f"\n=== 3. Checking cAdvisor service names ===")
        
        # Query per trovare tutti i service names in cAdvisor
        cadvisor_query = 'container_last_seen{container_label_com_docker_swarm_service_name!=""}'
        
        try:
            result = prom.custom_query(cadvisor_query)
            service_names = set()
            
            if result:
                print(f"Found {len(result)} containers")
                for series in result:
                    if 'metric' in series and 'container_label_com_docker_swarm_service_name' in series['metric']:
                        service_name = series['metric']['container_label_com_docker_swarm_service_name']
                        service_names.add(service_name)
                
                print(f"\n📦 Docker Swarm service names:")
                for service_name in sorted(service_names):
                    print(f"✅ {service_name}")
                    
            else:
                print("❌ No cAdvisor container data found")
                
        except Exception as e:
            print(f"❌ Error querying cAdvisor: {e}")
            
        print(f"\n=== 4. Suggested mappings ===")
        print("Based on the findings above, you should update your service names:")
        print("Example:")
        if 'gateway_cluster' in all_cluster_names:
            print("  ✅ 'gateway' → 'gateway_cluster' (correct)")
        if 'ms_exercise_cluster' in all_cluster_names:
            print("  ✅ 'ms-exercise' → 'ms_exercise_cluster' (correct)")  
        if 'ms_other_cluster' in all_cluster_names:
            print("  ✅ 'ms-other' → 'ms_other_cluster' (correct)")
            
        # Check for other patterns
        for cluster in all_cluster_names:
            if cluster not in ['gateway_cluster', 'ms_exercise_cluster', 'ms_other_cluster']:
                print(f"  ❓ Found unexpected cluster: '{cluster}'")
                
    except Exception as e:
        print(f"❌ Failed to connect to Prometheus: {e}")
        print("Make sure Prometheus is running and accessible")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Debug Envoy cluster names in Prometheus')
    parser.add_argument('--host', default='localhost', help='Prometheus host (default: localhost)')
    parser.add_argument('--port', type=int, default=9090, help='Prometheus port (default: 9090)')
    
    args = parser.parse_args()
    
    debug_envoy_cluster_names(args.host, args.port)