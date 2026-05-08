"""Обновленное ядро Security Agent (портировано в fastapi-project)."""

from datetime import datetime

from .reports import MarkdownReporter
from .scanners import (
    AdvancedSSLScanner,
    DependencyScanner,
    NmapScanner,
    SafePortScanner,
    SecurityHeadersScanner,
    WebVulnerabilityScanner,
)


class SecurityAgentV2:
    """Агент безопасности с набором сканеров"""

    def __init__(self, mode="safe", timeout=30):
        self.mode = mode
        self.timeout = timeout

        self.scanners = self.initialize_scanners()
        self.reporter = MarkdownReporter()
        self.results_cache = {}

    def initialize_scanners(self):
        # Пытаемся использовать Nmap для расширенного сканирования, если доступен
        # В противном случае используем SafePortScanner
        try:
            import subprocess

            subprocess.run(["nmap", "--version"], capture_output=True, timeout=5, check=True)
            # Nmap доступен, используем его для режимов normal и full
            ports_scanner = (
                NmapScanner(timeout=30, use_nse=True)
                if self.mode in ["normal", "full"]
                else SafePortScanner(timeout=2, max_workers=10)
            )
        except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
            # Nmap не доступен, используем SafePortScanner
            ports_scanner = SafePortScanner(timeout=2, max_workers=10)

        return {
            "ssl": AdvancedSSLScanner(),
            "headers": SecurityHeadersScanner(timeout=10),
            "web": WebVulnerabilityScanner(timeout=15, delay=1),
            "ports": ports_scanner,
            "dependencies": DependencyScanner(timeout=30),
        }

    def audit_domain(self, domain, on_progress=None):
        """Scan domain for security issues.

        Args:
            domain: Domain to scan
            on_progress: Callback function(step_name, step_status, step_progress, step_message, total_steps, completed_steps)
                     If None - no callback is called (backward compatibility).
        """
        audit_id = f"{domain}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        results = {
            "audit_id": audit_id,
            "domain": domain,
            "timestamp": datetime.now().isoformat(),
            "mode": self.mode,
            "categories": {},
        }

        steps = ["ssl", "headers"]
        if self.mode in ["normal", "full"]:
            steps.append("ports")
        if self.mode == "full":
            steps.append("web_vulnerabilities")
        steps.append("report")
        total_steps = len(steps)
        completed_steps = 0

        def _progress(step_name, step_status, step_progress=0, step_message=""):
            if on_progress:
                on_progress(
                    step_name=step_name,
                    step_status=step_status,
                    step_progress=step_progress,
                    step_message=step_message,
                    total_steps=total_steps,
                    completed_steps=completed_steps,
                )

        _progress("ssl", "running", 0, "Scanning SSL certificate...")
        ssl_results = self.scanners["ssl"].scan(domain)
        results["categories"]["ssl"] = {
            "scanner": "AdvancedSSLScanner",
            "results": ssl_results,
            "score": self.calculate_ssl_score(ssl_results),
        }
        completed_steps += 1
        _progress("ssl", "completed", 100, "SSL scan completed")

        _progress("headers", "running", 0, "Scanning HTTP headers...")
        headers_results = self.scanners["headers"].scan(domain)
        results["categories"]["headers"] = {
            "scanner": "SecurityHeadersScanner",
            "results": headers_results,
            "score": (
                headers_results.get("security_score", 0) if headers_results.get("success") else 0
            ),
        }
        completed_steps += 1
        _progress("headers", "completed", 100, "HTTP headers scan completed")

        if self.mode in ["normal", "full"]:
            _progress("ports", "running", 0, "Scanning ports...")
            port_results = self.scanners["ports"].scan(domain)
            results["categories"]["ports"] = {
                "scanner": "SafePortScanner",
                "results": port_results,
                "score": (
                    port_results.get("security_score", 0) if port_results.get("success") else 0
                ),
            }
            completed_steps += 1
            _progress("ports", "completed", 100, "Port scan completed")
        else:
            results["categories"]["ports"] = {
                "scanner": "SafePortScanner",
                "skipped": "Port scanning disabled in safe mode",
                "score": 50,
            }

        if self.mode == "full":
            _progress("web_vulnerabilities", "running", 0, "Scanning web vulnerabilities...")
            web_results = self.scanners["web"].light_scan(domain)
            results["categories"]["web_vulnerabilities"] = {
                "scanner": "WebVulnerabilityScanner",
                "results": web_results,
                "score": (
                    web_results.get("security_score", 0) if web_results.get("success") else 0
                ),
            }
            completed_steps += 1
            _progress("web_vulnerabilities", "completed", 100, "Web vulnerability scan completed")
        else:
            results["categories"]["web_vulnerabilities"] = {
                "scanner": "WebVulnerabilityScanner",
                "skipped": f"Web vulnerability scanning requires full mode (current: {self.mode})",
                "score": 50,
            }

        _progress("report", "running", 0, "Generating report...")
        results["overall_score"] = self.calculate_overall_score(results["categories"])
        results["risk_level"] = self.determine_risk_level(results["overall_score"])
        results["critical_issues"] = self.find_critical_issues(results["categories"])
        results["recommendations"] = self.generate_recommendations(results["categories"])

        results["report_md"] = self.generate_comprehensive_report(results)
        completed_steps += 1
        _progress("report", "completed", 100, "Report generated")

        self.results_cache[audit_id] = results
        return results

    def calculate_ssl_score(self, ssl_results):
        if not ssl_results or "grade" not in ssl_results:
            return 0
        grade_scores = {"A+": 100, "A": 95, "B": 80, "C": 65, "D": 40, "E": 20, "F": 0}
        grade = ssl_results.get("grade", "F")
        return grade_scores.get(str(grade).upper(), 0)

    def calculate_overall_score(self, categories):
        weights = {"ssl": 0.35, "headers": 0.25, "ports": 0.20, "web_vulnerabilities": 0.20}
        total_score = 0.0
        total_weight = 0.0
        for category, data in categories.items():
            weight = weights.get(category, 0.10)
            score = data.get("score", 50)
            total_score += float(score) * weight
            total_weight += weight
        overall_score = (total_score / total_weight) if total_weight > 0 else 50
        return round(overall_score, 1)

    def determine_risk_level(self, score):
        if score >= 80:
            return "LOW"
        if score >= 60:
            return "MEDIUM"
        if score >= 40:
            return "HIGH"
        return "CRITICAL"

    def find_critical_issues(self, categories):
        critical_issues = []

        ssl_data = categories.get("ssl", {}).get("results", {})
        if ssl_data and ssl_data.get("grade") in ["D", "E", "F"]:
            critical_issues.append(
                {
                    "category": "ssl",
                    "issue": f"Критическая оценка SSL: {ssl_data.get('grade')}",
                    "details": "SSL сертификат небезопасен или скоро истекает",
                }
            )

        headers_data = categories.get("headers", {}).get("results", {})
        if headers_data and headers_data.get("success"):
            missing_critical = headers_data.get("missing_critical", [])
            if missing_critical:
                critical_issues.append(
                    {
                        "category": "headers",
                        "issue": "Отсутствуют критические заголовки безопасности",
                        "details": f"Отсутствуют: {', '.join(missing_critical)}",
                    }
                )

        ports_data = categories.get("ports", {}).get("results", {})
        if ports_data and ports_data.get("success"):
            security_issues = ports_data.get("security_issues", [])
            for issue in security_issues:
                if "высокорисковый" in issue.get("issue", "").lower():
                    critical_issues.append(
                        {
                            "category": "ports",
                            "issue": issue.get("issue"),
                            "details": f"Порт {issue.get('port')} ({issue.get('service')})",
                        }
                    )

        return critical_issues

    def generate_recommendations(self, categories):
        recommendations = []

        ssl_data = categories.get("ssl", {}).get("results", {})
        if ssl_data and ssl_data.get("recommendations"):
            recommendations.extend([f"SSL: {rec}" for rec in ssl_data.get("recommendations", [])])

        headers_data = categories.get("headers", {}).get("results", {})
        if headers_data and headers_data.get("success") and headers_data.get("recommendations"):
            recommendations.extend(headers_data["recommendations"])

        ports_data = categories.get("ports", {}).get("results", {})
        if ports_data and ports_data.get("success") and ports_data.get("recommendations"):
            recommendations.extend(ports_data["recommendations"])

        web_data = categories.get("web_vulnerabilities", {}).get("results", {})
        if web_data and web_data.get("success"):
            for warning in web_data.get("warnings", []):
                if warning.get("recommendation"):
                    recommendations.append(f"Web: {warning['recommendation']}")

        unique = []
        for rec in recommendations:
            if rec not in unique:
                unique.append(rec)
        return unique[:10]

    def generate_comprehensive_report(self, audit_results):
        report_parts = []
        report_parts.append(f"# 📊 Комплексный отчет безопасности: {audit_results['domain']}")
        report_parts.append(f"**Дата:** {audit_results['timestamp']}")
        report_parts.append(f"**Режим проверки:** {audit_results['mode']}")
        report_parts.append(f"**ID аудита:** {audit_results['audit_id']}")
        report_parts.append("")

        report_parts.append("## 📈 Сводка")
        report_parts.append(f"**Общая оценка безопасности:** {audit_results['overall_score']}/100")
        report_parts.append(f"**Уровень риска:** {audit_results['risk_level']}")
        report_parts.append("")

        report_parts.append("## 🔍 Категории")
        for category, data in audit_results["categories"].items():
            report_parts.append(f"- **{category}**: {data.get('score', 0)}/100")
        report_parts.append("")

        critical_issues = audit_results.get("critical_issues", [])
        if critical_issues:
            report_parts.append("## 🚨 Критические проблемы")
            for issue in critical_issues:
                report_parts.append(
                    f"- **{issue['category']}**: {issue['issue']} — {issue['details']}"
                )
            report_parts.append("")

        recommendations = audit_results.get("recommendations", [])
        if recommendations:
            report_parts.append("## 📋 Рекомендации")
            for i, rec in enumerate(recommendations, 1):
                report_parts.append(f"{i}. {rec}")
            report_parts.append("")

        report_parts.append("---")
        report_parts.append("*Сгенерировано sec-scanner*")
        return "\n".join(report_parts)
