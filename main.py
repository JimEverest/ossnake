# main.py

import logging
import sys
from ui.main_window import MainWindow

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('ossnake.log'),
            logging.StreamHandler(sys.stdout)
        ]
    )

def main():
    setup_logging()
    logger = logging.getLogger(__name__)
    
    try:
        app = MainWindow()
        logger.info("Application started successfully")
        app.mainloop()
    except Exception as e:
        logger.error(f"Application failed to start: {str(e)}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()