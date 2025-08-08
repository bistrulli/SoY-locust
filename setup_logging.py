#!/usr/bin/env python3
"""
Script di utilità per configurare il logging in modo centralizzato.
Importa e usa questo modulo nei tuoi script principali.
"""

from config.logging_config import setup_logging, set_log_level, get_current_log_level
from config.colored_logging import setup_colored_logging

def init_logging(level='INFO', log_to_file=False, log_file_path=None, colored=True):
    """
    Inizializza il sistema di logging centralizzato.
    
    Args:
        level (str): Livello di logging ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
        log_to_file (bool): Se True, salva i log anche su file
        log_file_path (str): Path del file di log (opzionale)
        colored (bool): Se True, usa logging colorato per multi-controller (default: True)
    
    Returns:
        logging.Logger: Logger configurato
        
    Example:
        # Logging colorato per multi-controller (RACCOMANDATO)
        init_logging()
        
        # Logging debug colorato
        init_logging(level='DEBUG')
        
        # Logging colorato con file
        init_logging(level='INFO', log_to_file=True)
        
        # Logging tradizionale (senza colori)
        init_logging(level='INFO', colored=False)
    """
    if colored:
        return setup_colored_logging(level=level, log_to_file=log_to_file, log_file_path=log_file_path)
    else:
        return setup_logging(level=level, log_to_file=log_to_file, log_file_path=log_file_path)

# Esempi di utilizzo rapido
def setup_debug_logging():
    """Setup rapido per debug completo"""
    return setup_logging(level='DEBUG')

def setup_production_logging():
    """Setup rapido per produzione (solo errori e warning)"""
    return setup_logging(level='WARNING', log_to_file=True)

def setup_test_logging():
    """Setup rapido per test con log su file"""
    return setup_logging(level='INFO', log_to_file=True)

if __name__ == "__main__":
    # Test della configurazione
    print("Testing logging configuration...")
    
    # Test con diversi livelli
    logger = init_logging(level='DEBUG')
    
    logger.debug("This is a DEBUG message")
    logger.info("This is an INFO message")
    logger.warning("This is a WARNING message")
    logger.error("This is an ERROR message")
    
    print(f"Current log level: {get_current_log_level()}")
    
    # Cambia livello durante l'esecuzione
    set_log_level('ERROR')
    logger.info("This INFO message should NOT appear")
    logger.error("This ERROR message should appear")
    
    print(f"New log level: {get_current_log_level()}")