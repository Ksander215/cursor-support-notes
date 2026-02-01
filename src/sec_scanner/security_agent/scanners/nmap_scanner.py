"""
Расширенный сканер портов на основе Nmap
Использует NSE скрипты для дополнительных проверок безопасности
"""

import subprocess
import time
from typing import Any

from ...targets import ensure_public_target_or_raise


class NmapScanner:
    """Расширенное сканирование портов с использованием Nmap и NSE скриптов"""

    def __init__(self, timeout=30, use_nse=True):
        self.timeout = timeout
        self.use_nse = use_nse

    def _run_nmap_command(
        self, target: str, ports: str | None = None, scripts: list[str] | None = None
    ) -> dict[str, Any]:
        """
        Запускает Nmap команду и возвращает результаты
        Использует безопасные флаги для автоматического сканирования
        """
        try:
            # Базовые флаги Nmap
            cmd = [
                "nmap",
                "-sV",
                "-sC",
                "--open",
                "-T4",
                "--max-retries",
                "2",
                "--host-timeout",
                str(self.timeout),
            ]

            # Добавляем порты если указаны
            if ports:
                cmd.extend(["-p", ports])
            else:
                # Сканируем топ 1000 портов (безопасно)
                cmd.append("--top-ports")
                cmd.append("1000")

            # Добавляем NSE скрипты если включены
            if self.use_nse and scripts:
                cmd.extend(["--script", ",".join(scripts)])
            elif self.use_nse:
                # Используем безопасные категории скриптов
                cmd.extend(["--script", "vuln,ssl-*,http-*,dns-*"])

            # Добавляем XML вывод для парсинга
            cmd.extend(["-oX", "-", target])

            # Запускаем команду
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout + 10,  # Дополнительное время на таймаут
            )

            if result.returncode != 0:
                return {
                    "success": False,
                    "error": f"Nmap command failed: {result.stderr}",
                    "stdout": result.stdout,
                }

            return {
                "success": True,
                "xml_output": result.stdout,
                "stderr": result.stderr,
            }

        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Nmap scan timed out"}
        except FileNotFoundError:
            return {
                "success": False,
                "error": "Nmap not found. Please install nmap: sudo apt-get install nmap",
            }
        except Exception as e:
            return {"success": False, "error": f"Nmap execution error: {e!s}"}

    def _parse_nmap_xml(self, xml_output: str) -> dict[str, Any]:
        """
        Парсит XML вывод Nmap и извлекает информацию о портах и сервисах
        Упрощенный парсинг без внешних библиотек
        """
        import re

        results = {
            "ports": [],
            "services": [],
            "vulnerabilities": [],
            "ssl_info": {},
            "host_info": {},
        }

        # Извлекаем открытые порты и сервисы
        port_pattern = r'<port protocol="(\w+)" portid="(\d+)">.*?<state state="(\w+)".*?</port>'
        service_pattern = (
            r'<service name="([^"]+)"(?:.*?product="([^"]*)")?(?:.*?version="([^"]*)")?'
        )

        for match in re.finditer(port_pattern, xml_output, re.DOTALL):
            protocol, port, state = match.groups()
            if state == "open":
                port_num = int(port)
                # Ищем информацию о сервисе
                service_match = re.search(
                    rf'<port protocol="{protocol}" portid="{port}">.*?<service name="([^"]+)"(?:.*?product="([^"]*)")?(?:.*?version="([^"]*)")?',
                    xml_output,
                    re.DOTALL,
                )

                service_name = "unknown"
                product = None
                version = None

                if service_match:
                    service_name = service_match.group(1)
                    if len(service_match.groups()) > 1:
                        product = service_match.group(2) if service_match.group(2) else None
                    if len(service_match.groups()) > 2:
                        version = service_match.group(3) if service_match.group(3) else None

                port_info = {
                    "port": port_num,
                    "protocol": protocol,
                    "state": state,
                    "service": service_name,
                    "product": product,
                    "version": version,
                    "risk": self._get_port_risk_level(port_num, service_name),
                }

                results["ports"].append(port_info)
                results["services"].append(service_name)

        # Извлекаем информацию об уязвимостях из NSE скриптов
        vuln_pattern = r'<script id="([^"]+)".*?output="([^"]+)"'
        for match in re.finditer(vuln_pattern, xml_output, re.DOTALL):
            script_id, output = match.groups()
            if "vuln" in script_id.lower() or "CVE" in output:
                results["vulnerabilities"].append({"script": script_id, "output": output})

        # Извлекаем SSL информацию
        ssl_pattern = r'<script id="ssl-([^"]+)".*?output="([^"]+)"'
        for match in re.finditer(ssl_pattern, xml_output, re.DOTALL):
            ssl_script, output = match.groups()
            results["ssl_info"][ssl_script] = output

        return results

    def _get_port_risk_level(self, port: int, service: str) -> str:
        """Определяет уровень риска порта"""
        high_risk_ports = [21, 23, 25, 110, 143, 3306, 5432, 3389, 5900]
        high_risk_services = ["ftp", "telnet", "mysql", "postgresql", "rdp", "vnc"]

        if port in high_risk_ports:
            return "HIGH"
        if service.lower() in high_risk_services:
            return "HIGH"

        medium_risk_ports = [22, 80, 443, 8080, 8443, 8000]
        if port in medium_risk_ports:
            return "MEDIUM"

        return "LOW"

    def scan(
        self, domain: str, ports: str | None = None, scripts: list[str] | None = None
    ) -> dict[str, Any]:
        """
        Выполняет расширенное сканирование портов с использованием Nmap

        Args:
            domain: Домен или IP для сканирования
            ports: Строка с портами для сканирования (например, "80,443,8080" или "1-1000")
            scripts: Список NSE скриптов для выполнения

        Returns:
            Словарь с результатами сканирования
        """
        try:
            ensure_public_target_or_raise(domain)

            # Запускаем Nmap
            nmap_result = self._run_nmap_command(domain, ports=ports, scripts=scripts)

            if not nmap_result.get("success"):
                return {
                    "success": False,
                    "error": nmap_result.get("error", "Unknown error"),
                    "scanner": "NmapScanner",
                }

            # Парсим XML вывод
            parsed_results = self._parse_nmap_xml(nmap_result["xml_output"])

            # Формируем результат
            open_ports = parsed_results["ports"]
            high_risk_ports = [p for p in open_ports if p.get("risk") == "HIGH"]
            medium_risk_ports = [p for p in open_ports if p.get("risk") == "MEDIUM"]

            # Рассчитываем security score
            security_score = 100
            security_score -= len(high_risk_ports) * 20
            security_score -= len(medium_risk_ports) * 5
            security_score = max(0, security_score)

            # Формируем рекомендации
            recommendations = []
            if high_risk_ports:
                recommendations.append(
                    f"Обнаружено {len(high_risk_ports)} высокорисковых открытых портов. Рекомендуется закрыть или усилить защиту."
                )

            if parsed_results.get("vulnerabilities"):
                recommendations.append(
                    f"Обнаружено {len(parsed_results['vulnerabilities'])} потенциальных уязвимостей. Проверьте детали в отчете."
                )

            # Формируем security issues
            security_issues = []
            for port_info in high_risk_ports:
                security_issues.append(
                    {
                        "port": port_info["port"],
                        "service": port_info["service"],
                        "issue": f"Высокорисковый открытый порт {port_info['port']} ({port_info['service']})",
                        "details": f"Протокол: {port_info['protocol']}, Продукт: {port_info.get('product', 'Unknown')}, Версия: {port_info.get('version', 'Unknown')}",
                        "recommendation": f"Закройте порт {port_info['port']} или усилите его защиту",
                    }
                )

            return {
                "success": True,
                "domain": domain,
                "scanner": "NmapScanner",
                "timestamp": time.time(),
                "total_ports_found": len(open_ports),
                "open_ports": open_ports,
                "high_risk_ports": high_risk_ports,
                "medium_risk_ports": medium_risk_ports,
                "services_detected": list(set(parsed_results["services"])),
                "vulnerabilities": parsed_results.get("vulnerabilities", []),
                "ssl_info": parsed_results.get("ssl_info", {}),
                "security_score": security_score,
                "security_issues": security_issues,
                "recommendations": recommendations,
                "nmap_enabled": True,
                "nse_scripts_used": self.use_nse,
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Ошибка Nmap сканирования: {e!s}",
                "scanner": "NmapScanner",
            }
