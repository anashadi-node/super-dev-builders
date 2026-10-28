"""Runtime SDB (Fase 2b): billing prabayar ber-rantai hash + worker ber-lease.

Sengaja tanpa impor di level paket: menjalankan `python -m sdb_platform.runtime.worker` akan
memuat modul worker dua kali bila paket ini mengimpornya lebih dulu (RuntimeWarning). Impor
eksplisit di pemakai: `from sdb_platform.runtime.worker import Worker, echo_executor`.
"""
