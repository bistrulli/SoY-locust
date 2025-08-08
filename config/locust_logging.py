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
    Solo i nostri script vanno sulla console, Locust va su file.
    """
    import os
    from pathlib import Path
    
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    # Get root logger
    root_logger = logging.getLogger()
    
    # Remove existing handlers to avoid conflicts with Locust
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create console handler SOLO per i nostri moduli
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
    
    # Create file handler for Locust logs
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    file_handler = logging.FileHandler(log_dir / "locust_output.log")
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        '%(asctime)s [%(name)s] [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    
    # Configure root logger with minimal level
    root_logger.setLevel(logging.DEBUG)
    
    # Redirect ALL Locust loggers to file only
    locust_loggers = [
        'locust',
        'locust.main', 
        'locust.runners',
        'locust.user',
        'locust.stats',
        'locust.web',
        'locust.dispatch',
        'locust.rpc'
    ]
    
    for logger_name in locust_loggers:
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()  # Remove all handlers
        logger.addHandler(file_handler)  # Add only file handler
        logger.setLevel(logging.INFO)
        logger.propagate = False  # Don't propagate to root
    
    return root_logger

def configure_module_loggers():
    """
    Configure specific module loggers for our framework - solo sulla console
    """
    import sys
    
    # Create console handler for our modules
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    
    # Use colored formatter
    if hasattr(sys.stdout, 'isatty') and sys.stdout.isatty():
        formatter = LocustColoredFormatter(datefmt='%H:%M:%S')
    else:
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)5s] %(message)s',
            datefmt='%H:%M:%S'
        )
    console_handler.setFormatter(formatter)
    
    # Our modules that should appear on console
    our_modules = [
        'estimator.monitoring',
        'controller.control_loop', 
        'controller.controlqueuing'
    ]
    
    for module_name in our_modules:
        logger = logging.getLogger(module_name)
        logger.handlers.clear()  # Remove any existing handlers
        logger.addHandler(console_handler)  # Add console handler
        logger.setLevel(logging.DEBUG)  # Temporary DEBUG for Traefik troubleshooting
        logger.propagate = False  # Don't propagate to root
    
    return our_modules