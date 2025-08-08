"""
Configurazione logging con colori per distinguere meglio i diversi controllori.
"""

import logging
import sys
from datetime import datetime

# Codici colore ANSI per terminale
class Colors:
    # Service-specific colors
    MS_EXERCISE = '\033[94m'    # Blue
    MS_OTHER = '\033[92m'       # Green  
    GATEWAY = '\033[95m'        # Magenta
    MONITOR = '\033[93m'        # Yellow
    CONTROLLER = '\033[96m'     # Cyan
    
    # Level colors
    DEBUG = '\033[37m'          # White
    INFO = '\033[97m'           # Bright White
    WARNING = '\033[93m'        # Yellow
    ERROR = '\033[91m'          # Red
    CRITICAL = '\033[41m'       # Red background
    
    # Formatting
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    RESET = '\033[0m'           # Reset all
    
    # Special symbols with colors
    TICK = '\033[92m●\033[0m'           # Green dot
    ERROR_MARK = '\033[91m✗\033[0m'     # Red X
    WARNING_MARK = '\033[93m⚠\033[0m'   # Yellow warning
    SUCCESS_MARK = '\033[92m✓\033[0m'   # Green check

class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors for different services"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
    def format(self, record):
        # Map service names to colors
        service_colors = {
            'MS-EXERCISE': Colors.MS_EXERCISE,
            'MS-OTHER': Colors.MS_OTHER, 
            'GATEWAY': Colors.GATEWAY,
            'MONITOR': Colors.MONITOR,
            'CONTROLLER': Colors.CONTROLLER,
            'CTRL-MS-EXERCISE': Colors.MS_EXERCISE + Colors.BOLD,
            'CTRL-MS-OTHER': Colors.MS_OTHER + Colors.BOLD,
            'CTRL-GATEWAY': Colors.GATEWAY + Colors.BOLD,
        }
        
        # Level colors
        level_colors = {
            'DEBUG': Colors.DEBUG,
            'INFO': Colors.INFO,
            'WARNING': Colors.WARNING,
            'ERROR': Colors.ERROR,
            'CRITICAL': Colors.CRITICAL,
        }
        
        # Get the original message
        message = record.getMessage()
        
        # Apply service-specific coloring
        colored_message = message
        for service, color in service_colors.items():
            if f'[{service}]' in message:
                colored_message = message.replace(
                    f'[{service}]', 
                    f'{color}[{service}]{Colors.RESET}'
                )
                break
        
        # Apply level coloring to level name
        level_color = level_colors.get(record.levelname, '')
        colored_level = f'{level_color}{record.levelname:8s}{Colors.RESET}'
        
        # Format timestamp
        if self.datefmt:
            timestamp = datetime.fromtimestamp(record.created).strftime(self.datefmt)
        else:
            timestamp = datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S')
        
        # Create final formatted message
        return f'{timestamp} [{colored_level}] {colored_message}'

def setup_colored_logging(level='INFO', log_to_file=False, log_file_path=None):
    """
    Setup logging with colored output for better multi-controller visibility.
    
    Args:
        level (str): Log level
        log_to_file (bool): Also log to file  
        log_file_path (str): Optional file path
    """
    from .logging_config import LOG_LEVELS
    
    log_level = LOG_LEVELS.get(level.upper(), logging.INFO)
    
    # Clear any existing handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Console handler with colors
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    
    # Use colored formatter for console if terminal supports it
    if hasattr(sys.stdout, 'isatty') and sys.stdout.isatty():
        console_formatter = ColoredFormatter(datefmt='%H:%M:%S')
    else:
        # Fallback to standard formatter for non-TTY
        console_formatter = logging.Formatter(
            '%(asctime)s [%(levelname)8s] %(message)s',
            datefmt='%H:%M:%S'
        )
    
    console_handler.setFormatter(console_formatter)
    
    # Setup root logger
    root_logger.setLevel(log_level)
    root_logger.addHandler(console_handler)
    
    # File handler (optional, without colors)
    if log_to_file:
        if log_file_path is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            log_file_path = f"logs/soy_locust_{timestamp}.log"
        
        import os
        os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
        
        file_handler = logging.FileHandler(log_file_path)
        file_handler.setLevel(log_level)
        file_formatter = logging.Formatter(
            '%(asctime)s [%(levelname)8s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)
    
    # Log setup info
    root_logger.info("="*70)
    root_logger.info(f"{Colors.BOLD}SoY-locust Framework - Enhanced Multi-Controller Logging{Colors.RESET}")
    root_logger.info("="*70)
    root_logger.info("🎨 Colored logging enabled")
    root_logger.info(f"📊 Log level: {level.upper()}")
    if log_to_file:
        root_logger.info(f"📄 Logging to file: {log_file_path}")
    root_logger.info("🎯 Services: MS-EXERCISE, MS-OTHER, GATEWAY")
    
    return root_logger

if __name__ == "__main__":
    # Test colored logging
    logger = setup_colored_logging(level='DEBUG')
    
    logger.info("[CTRL-MS-EXERCISE] ━━━ TICK 1 (t=1.23) ━━━")
    logger.info("[CTRL-MS-EXERCISE]  ├─ Response Time:  0.1234")
    logger.info("[CTRL-MS-EXERCISE]  ├─ Throughput:     9.8765")
    logger.info("[CTRL-MS-EXERCISE]  └─ Memory:         0")
    
    logger.info("[CTRL-MS-OTHER] ━━━ TICK 1 (t=1.25) ━━━")
    logger.info("[CTRL-MS-OTHER]  ├─ Response Time:  0.0987")  
    logger.info("[CTRL-MS-OTHER]  └─ Memory:         0")
    
    logger.info("[CTRL-GATEWAY] ━━━ TICK 1 (t=1.27) ━━━")
    logger.info("[CTRL-GATEWAY]  ├─ Response Time:  0.1567")
    logger.info("[CTRL-GATEWAY]  └─ Memory:         0")
    
    logger.warning("[CTRL-MS-EXERCISE] ⚠️  Monitor data not ready")
    logger.error("[CTRL-GATEWAY] ❌ Service 'ms-stack-v5_gateway' not found")
    
    print(f"\n{Colors.BOLD}Legend:{Colors.RESET}")
    print(f"  {Colors.MS_EXERCISE}[MS-EXERCISE]{Colors.RESET} - Exercise microservice")
    print(f"  {Colors.MS_OTHER}[MS-OTHER]{Colors.RESET} - Other microservice") 
    print(f"  {Colors.GATEWAY}[GATEWAY]{Colors.RESET} - Gateway service")