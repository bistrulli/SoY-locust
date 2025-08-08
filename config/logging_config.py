"""
Configurazione centralizzata del logging per il framework SoY-locust.
Questo modulo permette di configurare facilmente il livello di logging per tutti i componenti.
"""

import logging
import sys
from datetime import datetime

# Livelli di logging disponibili
LOG_LEVELS = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO, 
    'WARNING': logging.WARNING,
    'ERROR': logging.ERROR,
    'CRITICAL': logging.CRITICAL
}

def setup_logging(level='INFO', log_to_file=False, log_file_path=None):
    """
    Configura il sistema di logging centralizzato.
    
    Args:
        level (str): Livello di logging ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
        log_to_file (bool): Se True, salva i log anche su file
        log_file_path (str): Path del file di log (opzionale, viene generato automaticamente)
    
    Returns:
        logging.Logger: Logger configurato
    """
    
    # Converti il livello stringa in costante logging
    log_level = LOG_LEVELS.get(level.upper(), logging.INFO)
    
    # Configura il formato dei messaggi (ottimizzato per multi-controller)
    log_format = '%(asctime)s [%(levelname)8s] %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'
    
    # Lista degli handler
    handlers = []
    
    # Handler per console (sempre attivo)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_formatter = logging.Formatter(log_format, date_format)
    console_handler.setFormatter(console_formatter)
    handlers.append(console_handler)
    
    # Handler per file (opzionale)
    if log_to_file:
        if log_file_path is None:
            # Genera automaticamente il nome del file
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            log_file_path = f"logs/soy_locust_{timestamp}.log"
        
        # Crea la directory se non esiste
        import os
        os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
        
        file_handler = logging.FileHandler(log_file_path)
        file_handler.setLevel(log_level)
        file_formatter = logging.Formatter(log_format, date_format)
        file_handler.setFormatter(file_formatter)
        handlers.append(file_handler)
    
    # Configura il root logger
    logging.basicConfig(
        level=log_level,
        handlers=handlers,
        force=True  # Sovrascrive configurazioni esistenti
    )
    
    # Configura specificamente i logger dei nostri moduli
    module_loggers = [
        'estimator.monitoring',
        'controller.control_loop', 
        'controller.controlqueuing',
        '__main__'  # Per script principali
    ]
    
    for module_name in module_loggers:
        logger = logging.getLogger(module_name)
        logger.setLevel(log_level)
    
    root_logger = logging.getLogger()
    
    # Log del setup iniziale
    root_logger.info("=" * 60)
    root_logger.info("SoY-locust Framework - Logging Setup")
    root_logger.info("=" * 60)
    root_logger.info("Log level set to: %s", level.upper())
    if log_to_file:
        root_logger.info("Logging to file: %s", log_file_path)
    root_logger.info("Active handlers: %d", len(handlers))
    
    return root_logger

def set_log_level(level):
    """
    Cambia il livello di logging durante l'esecuzione.
    
    Args:
        level (str): Nuovo livello di logging
    """
    log_level = LOG_LEVELS.get(level.upper(), logging.INFO)
    
    # Aggiorna tutti i logger esistenti
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Aggiorna tutti gli handler
    for handler in root_logger.handlers:
        handler.setLevel(log_level)
    
    # Aggiorna i logger dei moduli specifici
    module_loggers = [
        'estimator.monitoring',
        'controller.control_loop',
        'controller.controlqueuing'
    ]
    
    for module_name in module_loggers:
        logger = logging.getLogger(module_name)
        logger.setLevel(log_level)
    
    root_logger.info("Log level changed to: %s", level.upper())

def get_current_log_level():
    """
    Restituisce il livello di logging corrente.
    
    Returns:
        str: Livello di logging corrente
    """
    root_logger = logging.getLogger()
    level_num = root_logger.getEffectiveLevel()
    
    # Mappa inversa per convertire il numero in stringa
    for name, num in LOG_LEVELS.items():
        if num == level_num:
            return name
    
    return 'UNKNOWN'

# Configurazione di default (può essere sovrascritta)
DEFAULT_LOG_LEVEL = 'INFO'