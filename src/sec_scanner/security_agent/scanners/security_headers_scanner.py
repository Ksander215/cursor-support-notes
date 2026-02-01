"""
Сканер заголовков безопасности
"""

import requests

from .http_safe import safe_request


class SecurityHeadersScanner:
    """Проверка HTTP заголовков безопасности"""

    def __init__(self, timeout=10):
        self.timeout = timeout
        self.headers_to_check = {
            "Content-Security-Policy": {
                "description": "Content Security Policy",
                "importance": "HIGH",
                "recommendation": "Настройте CSP для защиты от XSS",
            },
            "X-Frame-Options": {
                "description": "Защита от clickjacking",
                "importance": "HIGH",
                "recommendation": "Установите DENY или SAMEORIGIN",
            },
            "X-Content-Type-Options": {
                "description": "Запрет MIME-sniffing",
                "importance": "MEDIUM",
                "recommendation": "Установите nosniff",
            },
            "Strict-Transport-Security": {
                "description": "HTTP Strict Transport Security",
                "importance": "HIGH",
                "recommendation": "Настройте HSTS с max-age не менее 31536000",
            },
            "Referrer-Policy": {
                "description": "Контроль передачи Referrer",
                "importance": "MEDIUM",
                "recommendation": "Установите strict-origin-when-cross-origin",
            },
            "Permissions-Policy": {
                "description": "Permissions Policy",
                "importance": "MEDIUM",
                "recommendation": "Ограничьте доступ к API устройства",
            },
            "X-XSS-Protection": {
                "description": "XSS Protection (устаревший, но встречается)",
                "importance": "LOW",
                "recommendation": "Установите 1; mode=block (если применимо)",
            },
        }

    def scan(self, domain):
        try:
            if not domain.startswith(("http://", "https://")):
                domain = "https://" + domain

            try:
                s = requests.Session()
                response = safe_request(
                    s,
                    "GET",
                    domain,
                    timeout=(5, self.timeout),
                    max_redirects=5,
                )
                protocol = "https"
            except Exception:
                domain_http = domain.replace("https://", "http://")
                s = requests.Session()
                response = safe_request(
                    s,
                    "GET",
                    domain_http,
                    timeout=(5, self.timeout),
                    max_redirects=5,
                )
                protocol = "http"

            headers = response.headers

            results = []
            missing_headers = []
            security_score = 100

            for header, info in self.headers_to_check.items():
                check_result = {
                    "header": header,
                    "description": info["description"],
                    "importance": info["importance"],
                    "required": header in ["Content-Security-Policy", "X-Frame-Options"],
                }

                if header in headers:
                    check_result["status"] = "PRESENT"
                    check_result["value"] = headers[header]
                    check_result["score"] = 10 if info["importance"] == "HIGH" else 5
                else:
                    check_result["status"] = "MISSING"
                    check_result["value"] = None
                    check_result["score"] = -15 if info["importance"] == "HIGH" else -5
                    missing_headers.append(header)
                    check_result["note"] = (
                        "КРИТИЧЕСКИЙ ЗАГОЛОВОК ОТСУТСТВУЕТ"
                        if check_result["required"]
                        else "Рекомендуется добавить"
                    )

                results.append(check_result)
                security_score += check_result["score"]

            security_score = max(0, min(100, security_score))

            if security_score >= 80:
                security_level = "HIGH"
            elif security_score >= 60:
                security_level = "MEDIUM"
            else:
                security_level = "LOW"

            server_header = headers.get("Server", "Неизвестно")
            powered_by = headers.get("X-Powered-By", None)

            recommendations = []
            if missing_headers:
                recommendations.append(
                    f"Добавьте отсутствующие заголовки: {', '.join(missing_headers)}"
                )
            if powered_by:
                recommendations.append(
                    f"Скрыть X-Powered-By: {powered_by} для уменьшения поверхности атаки"
                )

            return {
                "success": True,
                "domain": domain,
                "protocol": protocol,
                "status_code": response.status_code,
                "security_score": security_score,
                "security_level": security_level,
                "server": server_header,
                "powered_by": powered_by,
                "headers_count": len(headers),
                "checked_headers": len(self.headers_to_check),
                "results": results,
                "missing_critical": [
                    h
                    for h in missing_headers
                    if h in ["Content-Security-Policy", "X-Frame-Options"]
                ],
                "recommendations": recommendations,
                "raw_headers": dict(headers),
            }
        except requests.exceptions.RequestException as e:
            return {
                "success": False,
                "error": f"Ошибка подключения: {e!s}",
                "recommendations": ["Проверьте доступность сайта", "Проверьте настройки DNS"],
            }
        except Exception as e:
            return {"success": False, "error": f"Неожиданная ошибка: {e!s}"}
