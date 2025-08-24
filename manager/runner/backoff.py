from __future__ import annotations

import random
import time
from dataclasses import dataclass, field


@dataclass(slots=True)
class BackoffPolicy:
    """Политика перезапуска процессов"""

    # базовая задержка при рестарте в секундах
    base_sec: float = 0.5
    # коэффициент роста задержки (экспонента)
    factor: float = 2.0
    # максимальная задержка в секундах, выше которой нельзя уходить
    max_sec: float = 30.0
    # добавка шума (джиттер) к задержке в секундах,
    # чтобы разные процессы не выстреливали синхронно
    jitter_sec: float = 0.4
    # если система проработала без падений больше этой величины (uptime),
    # то счетчик попыток сбрасывается
    reset_after_ok_sec: float = 60.0
    # скользящее окно в секундах для подсчета рестартов
    window_sec: float = 300.0
    # лимит рестартов в окне времени, иначе считаем "слишком много"
    max_restarts_in_window: int = 20


@dataclass(slots=True)
class BackoffState:
    """Состояние перезапуска процесса"""

    # политика перезапуска для процесса
    policy: BackoffPolicy
    # текущий номер попытки перезапуска
    attempt: int = 0
    # список времен последних запусков
    recent_starts: list[float] = field(default_factory=list)

    def next_delay_with_jitter(self) -> float:
        """Вычисляет задержку перед следующей попыткой"""

        # считает экспоненциальное время задержки и ограничивает максимальной
        base = min(
            self.policy.max_sec,
            self.policy.base_sec * (self.policy.factor ** max(self.attempt - 1, 0)),
        )
        # добавляет случайный джиттер в диапазоне
        jitter = random.uniform(-self.policy.jitter_sec, self.policy.jitter_sec)
        # не дает задержке быть меньше нуля
        return max(0.0, base + jitter)

    def register_start(self) -> None:
        """Регистрация запуска процесса"""

        # взять текущее время (monotonic = всегда растет, не зависит от сдвига системных часов)
        now = time.monotonic()
        # сохранить время запуска
        self.recent_starts.append(now)
        # удалить старые записи, которые выпали за окно
        cutoff = now - self.policy.window_sec
        self.recent_starts = [
            start_time for start_time in self.recent_starts if start_time >= cutoff
        ]
        # увеличить счетчик попыток
        self.attempt += 1

    def reset_if_uptime_good(self, uptime_sec: float) -> None:
        """
        Сбросить счетчик попыток

        :param uptime_sec: текущее время работы в секундах
        """
        if uptime_sec >= self.policy.reset_after_ok_sec:
            self.attempt = 0

    def too_many_restarts(self) -> bool:
        """
        Проверяет, не превышено ли число рестартов в окне.
        Если да, то пора включать circuit breaker
        """
        return len(self.recent_starts) > self.policy.max_restarts_in_window
