"""
Безопасный сканер портов
Только основные порты, без агрессивного сканирования
"""

import concurrent.futures
import socket
import time

from ...targets import ensure_public_target_or_raise


class SafePortScanner:
    """Безопасное сканирование только основных портов"""

    def __init__(self, timeout=2, max_workers=10):
        self.timeout = timeout
        self.max_workers = max_workers

        # Только основные и безопасные для сканирования порты
        self.common_ports = {
            21: "FTP",
            22: "SSH",
            23: "Telnet",
            25: "SMTP",
            53: "DNS",
            80: "HTTP",
            110: "POP3",
            143: "IMAP",
            443: "HTTPS",
            465: "SMTPS",
            587: "SMTP Submission",
            993: "IMAPS",
            995: "POP3S",
            2082: "cPanel",
            2083: "cPanel SSL",
            2086: "WHM",
            2087: "WHM SSL",
            3306: "MySQL",
            5432: "PostgreSQL",
            8080: "HTTP Proxy",
            8443: "HTTPS Alt",
            8888: "HTTP Alt",
        }

    def scan_port(self, host, port):
        """Проверка одного порта"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            result = sock.connect_ex((host, port))
            sock.close()

            if result == 0:
                return {
                    "port": port,
                    "status": "OPEN",
                    "service": self.common_ports.get(port, "Unknown"),
                    "risk": self.get_port_risk_level(port),
                }
            return {
                "port": port,
                "status": "CLOSED",
                "service": self.common_ports.get(port, "Unknown"),
            }
        except socket.gaierror:
            return {"port": port, "status": "ERROR", "error": "Hostname resolution failed"}
        except Exception as e:  # noqa: B110
            return {"port": port, "status": "ERROR", "error": str(e)}

    def get_port_risk_level(self, port):
        high_risk_ports = [21, 23, 25, 110, 143, 3306, 5432]
        medium_risk_ports = [22, 80, 443, 8080, 8443]

        if port in high_risk_ports:
            return "HIGH"
        if port in medium_risk_ports:
            return "MEDIUM"
        return "LOW"

    def scan(self, domain, ports=None):
        try:
            ensure_public_target_or_raise(domain)
            try:
                ip_address = socket.gethostbyname(domain)
            except socket.gaierror:
                return {"success": False, "error": f"Не удалось разрешить домен: {domain}"}

            ports_to_scan = list(self.common_ports.keys()) if ports is None else ports

            results = []
            open_ports = []

            with concurrent.futures.ThreadPoolExecutor(
                max_workers=self.max_workers
            ) as executor:
                future_to_port = {
                    executor.submit(self.scan_port, ip_address, port): port
                    for port in ports_to_scan
                }

                for future in concurrent.futures.as_completed(future_to_port):
                    port = future_to_port[future]
                    try:
                        result = future.result()
                        results.append(result)
                        if result["status"] == "OPEN":
                            open_ports.append(result)
                    except Exception as e:  # noqa: B110
                        results.append({"port": port, "status": "ERROR", "error": str(e)})

            results.sort(key=lambda x: x["port"])

            security_issues = []
            recommendations = []

            for port_result in open_ports:
                port = port_result["port"]
                service = port_result["service"]
                risk = port_result.get("risk", "LOW")

                if risk == "HIGH":
                    security_issues.append(
                        {
                            "port": port,
                            "service": service,
                            "issue": "Высокорисковый открытый порт",
                            "recommendation": f"Рассмотрите возможность закрытия порта {port} ({service}) или усиления его защиты",
                        }
                    )

            if any(p["port"] == 22 for p in open_ports):
                recommendations.append(
                    "Настройте аутентификацию по ключам для SSH вместо паролей"
                )
            if any(p["port"] == 3306 for p in open_ports):
                recommendations.append(
                    "Не открывайте порт MySQL (3306) для внешнего доступа. Используйте SSH туннель"
                )
            if any(p["port"] == 21 for p in open_ports):
                recommendations.append("Замените FTP на SFTP или FTPS")

            total_ports = len(results)
            open_count = len(open_ports)
            high_risk_open = len([p for p in open_ports if p.get("risk") == "HIGH"])

            security_score = 100
            security_score -= high_risk_open * 20
            security_score -= (open_count - high_risk_open) * 5
            security_score = max(0, security_score)

            return {
                "success": True,
                "domain": domain,
                "ip_address": ip_address,
                "total_ports_scanned": total_ports,
                "open_ports_count": open_count,
                "security_score": security_score,
                "open_ports": open_ports,
                "all_results": results,
                "security_issues": security_issues,
                "recommendations": recommendations,
                "timestamp": time.time(),
            }

        except Exception as e:  # noqa: B110
            return {"success": False, "error": f"Ошибка сканирования портов: {str(e)}"}

