"""
Configurazione logging ottimizzata per Locust con formattazione migliorata.
"""

import logging
import sys

# Codici colore ANSI
class Colors:
    MS_EXERCISE = '\033[94m'    # Blue
    MS_OTHER = '\033[92m'       # Green  
    GATEWAY = '\033[95m'        # Magenta
    
    BOLD = '\033[1m'
    RESET = '\033[0m'
    
    # Level colors
    INFO = '\033[97m'           # Bright White
    WARNING = '\033[93m'        # Yellow
    ERROR = '\033[91m'          # Red

class LocustColoredFormatter(logging.Formatter):
    """Formatter ottimizzato per output Locust multi-controller"""
    
    def format(self, record):
        # Get the original message
        message = record.getMessage()
        
        # Service color mapping
        service_colors = {
            '[CTRL-MS-EXERCISE]': Colors.MS_EXERCISE + Colors.BOLD,
            '[MS-EXERCISE]': Colors.MS_EXERCISE,
            '[CTRL-MS-OTHER]': Colors.MS_OTHER + Colors.BOLD,
            '[MS-OTHER]': Colors.MS_OTHER,
            '[CTRL-GATEWAY]': Colors.GATEWAY + Colors.BOLD,
            '[GATEWAY]': Colors.GATEWAY,
        }
        
        # Apply coloring
        colored_message = message
        for service_tag, color in service_colors.items():
            if service_tag in message:
                colored_message = message.replace(
                    service_tag,
                    f'{color}{service_tag}{Colors.RESET}'
                )
                break
        
        # Level color
        level_color = {
            'INFO': Colors.INFO,
            'WARNING': Colors.WARNING,
            'ERROR': Colors.ERROR,
        }.get(record.levelname, '')
        
        # Simplified format for Locust
        timestamp = self.formatTime(record, self.datefmt)
        return f'{timestamp} [{level_color}{record.levelname:5s}{Colors.RESET}] {colored_message}'

def setup_locust_logging(level='INFO', colored=True):
    """
    Setup logging ottimizzato per Locust con multi-controller support.
    """
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    # Get root logger
    root_logger = logging.getLogger()
    
    # Remove existing handlers to avoid conflicts with Locust
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    
    # Choose formatter
    if colored and hasattr(sys.stdout, 'isatty') and sys.stdout.isatty():
        formatter = LocustColoredFormatter(
            datefmt='%H:%M:%S'
        )
    else:
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)5s] %(message)s',
            datefmt='%H:%M:%S'
        )
    
    console_handler.setFormatter(formatter)
    
    # Configure root logger
    root_logger.setLevel(log_level)
    root_logger.addHandler(console_handler)
    
    # Suppress some verbose Locust loggers
    logging.getLogger('locust.main').setLevel(logging.WARNING)
    logging.getLogger('locust.runners').setLevel(logging.WARNING)
    
    return root_logger

def configure_module_loggers():
    """
    Configure specific module loggers for our framework
    """
    # Set level for our modules
    our_modules = [
        'estimator.monitoring',
        'controller.control_loop',
        'controller.controlqueuing'
    ]
    
    for module in our_modules:
        logger = logging.getLogger(module)
        logger.setLevel(logging.INFO)  # Or whatever level you want
    
    return our_modules