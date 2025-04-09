"""
Инициализация пакета handlers.
Экспортирует обработчики команд.
"""

from handlers.start import start_command_handler as start_command
from handlers.feedback import process_feedback, send_feedback_request, feedback_handler

__all__ = ['start_command', 'process_feedback', 'send_feedback_request', 'feedback_handler'] 