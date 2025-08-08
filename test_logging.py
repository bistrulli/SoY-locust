#!/usr/bin/env python3
"""
Script di test per verificare il logging multi-controller colorato.
"""

import sys
import logging
from pathlib import Path

# Aggiungi il path per importare i nostri moduli
sys.path.append(str(Path(__file__).parent))

from config.locust_logging import setup_locust_logging, configure_module_loggers

def test_multicontroller_logging():
    """Testa il logging con i 3 controllori"""
    
    # Setup logging
    logger = setup_locust_logging(level='INFO', colored=True)
    configure_module_loggers()
    
    print("🎨 Testing Multi-Controller Colored Logging")
    print("="*60)
    
    # Simulate controller messages
    logger.info("[CTRL-MS-EXERCISE] ━━━ TICK 8 (t=8.76) ━━━")
    logger.info("[CTRL-MS-EXERCISE]  ├─ Response Time:  0.1810")
    logger.info("[CTRL-MS-EXERCISE]  ├─ Throughput:     9.7511")
    logger.info("[CTRL-MS-EXERCISE]  ├─ Replicas:       1")
    logger.info("[CTRL-MS-EXERCISE]  ├─ Ready Replicas: 1")
    logger.info("[CTRL-MS-EXERCISE]  ├─ Utilization:   1.6492")
    logger.info("[CTRL-MS-EXERCISE]  └─ Memory:         0")
    logger.info("[CTRL-MS-EXERCISE]  → Service Time: 0.0434 (stealth=True)")
    
    print()  # Blank line
    
    logger.info("[CTRL-MS-OTHER] ━━━ TICK 25 (t=27.21) ━━━")
    logger.info("[CTRL-MS-OTHER]  ├─ Response Time:  0.1244")
    logger.info("[CTRL-MS-OTHER]  ├─ Throughput:     38.0668")
    logger.info("[CTRL-MS-OTHER]  ├─ Replicas:       1")
    logger.info("[CTRL-MS-OTHER]  ├─ Ready Replicas: 1")
    logger.info("[CTRL-MS-OTHER]  ├─ Utilization:   0.3230")
    logger.info("[CTRL-MS-OTHER]  └─ Memory:         0")
    logger.info("[CTRL-MS-OTHER]  → Control Action: 2 replicas")
    
    print()  # Blank line
    
    logger.info("[CTRL-GATEWAY] ━━━ TICK 12 (t=15.33) ━━━")
    logger.info("[CTRL-GATEWAY]  ├─ Response Time:  0.0987")
    logger.info("[CTRL-GATEWAY]  ├─ Throughput:     25.4321")
    logger.info("[CTRL-GATEWAY]  ├─ Replicas:       2")
    logger.info("[CTRL-GATEWAY]  ├─ Ready Replicas: 2")
    logger.info("[CTRL-GATEWAY]  ├─ Utilization:   0.8765")
    logger.info("[CTRL-GATEWAY]  └─ Memory:         0")
    
    print()  # Blank line
    
    # Test warnings and errors
    logger.warning("[CTRL-MS-EXERCISE] ⚠️  Monitor data not ready (cycle 5)")
    logger.error("[CTRL-GATEWAY] ❌ Service 'ms-stack-v5_gateway' not found")
    logger.info("[CTRL-MS-OTHER] ⬆️  UPSCALE: ms-stack-v5_ms-other scaled to 3 replicas")
    logger.info("[CTRL-MS-EXERCISE] ⬇️  DOWNSCALE: Requested=1, Max=2, Target=1")
    
    print()
    print("="*60)
    print("Legend:")
    print("  🔵 BLUE   - MS-EXERCISE controller")
    print("  🟢 GREEN  - MS-OTHER controller") 
    print("  🟣 PURPLE - GATEWAY controller")
    print("  ⚠️  WARNING messages in YELLOW")
    print("  ❌ ERROR messages in RED")

if __name__ == "__main__":
    test_multicontroller_logging()