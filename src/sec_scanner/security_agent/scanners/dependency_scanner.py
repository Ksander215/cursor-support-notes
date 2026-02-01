"""
Сканер зависимостей для обнаружения уязвимостей в зависимостях проекта
Поддерживает: npm, pip, maven, composer
"""

import json
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

from httpx import Client


class DependencyScanner:
    """Сканер зависимостей для обнаружения уязвимостей"""

    def __init__(self, timeout=30):
        self.timeout = timeout
        self.client = Client(timeout=self.timeout)

    def _check_npm_advisory(self, package: str, version: str) -> list[dict[str, Any]]:
        """Проверяет уязвимости через npm advisories API"""
        try:
            # npm advisories API
            url = "https://registry.npmjs.org/-/npm/v1/security/advisories"
            # Простая проверка через GitHub advisories
            github_url = f"https://api.github.com/advisories?package={quote(f'npm:{package}')}"

            try:
                response = self.client.get(github_url)
                if response.status_code == 200:
                    advisories = response.json()
                    vulnerabilities = []
                    for advisory in advisories.get("advisories", []):
                        # Проверяем, влияет ли уязвимость на нашу версию
                        affected_versions = advisory.get("vulnerable_version_range", "")
                        if self._is_version_affected(version, affected_versions):
                            vulnerabilities.append(
                                {
                                    "package": package,
                                    "version": version,
                                    "advisory_id": advisory.get("ghsa_id", ""),
                                    "severity": advisory.get("severity", "unknown"),
                                    "title": advisory.get("summary", ""),
                                    "url": advisory.get("url", ""),
                                }
                            )
                    return vulnerabilities
            except Exception:
                pass

            # Fallback: проверка через OSV API
            return self._check_osv("npm", package, version)

        except Exception:
            return []

    def _check_osv(self, ecosystem: str, package: str, version: str) -> list[dict[str, Any]]:
        """Проверяет уязвимости через OSV (Open Source Vulnerabilities) API"""
        try:
            url = "https://api.osv.dev/v1/query"
            payload = {
                "version": version,
                "package": {
                    "ecosystem": ecosystem,
                    "name": package,
                },
            }

            response = self.client.post(url, json=payload)
            if response.status_code == 200:
                data = response.json()
                vulnerabilities = []
                for vuln in data.get("vulns", []):
                    vulnerabilities.append(
                        {
                            "package": package,
                            "version": version,
                            "vulnerability_id": vuln.get("id", ""),
                            "severity": self._extract_severity(vuln),
                            "summary": vuln.get("summary", ""),
                            "details": vuln.get("details", ""),
                            "references": vuln.get("references", []),
                        }
                    )
                return vulnerabilities
        except Exception:
            pass
        return []

    def _check_nvd(self, package: str, version: str) -> list[dict[str, Any]]:
        """Проверяет уязвимости через NVD (National Vulnerability Database)"""
        try:
            # NVD API требует API key для больших объемов, используем базовый поиск
            # В реальной реализации лучше использовать NVD API с ключом
            url = f"https://services.nvd.nist.gov/rest/json/cves/2.0?keywordSearch={quote(package)}"
            response = self.client.get(url)
            if response.status_code == 200:
                data = response.json()
                vulnerabilities = []
                for cve in data.get("vulnerabilities", []):
                    cve_data = cve.get("cve", {})
                    vulnerabilities.append(
                        {
                            "package": package,
                            "version": version,
                            "cve_id": cve_data.get("id", ""),
                            "severity": self._extract_cvss_severity(cve_data),
                            "description": cve_data.get("descriptions", [{}])[0].get("value", ""),
                            "references": [
                                ref.get("url", "") for ref in cve_data.get("references", [])
                            ],
                        }
                    )
                return vulnerabilities
        except Exception:
            pass
        return []

    def _is_version_affected(self, version: str, version_range: str) -> bool:
        """Проверяет, попадает ли версия в диапазон уязвимых версий"""
        # Упрощенная проверка, в реальности нужен semver парсер
        try:
            # Простая проверка для основных случаев
            if "<=" in version_range:
                parts = version_range.split("<=")
                if len(parts) == 2:
                    max_version = parts[1].strip()
                    return self._compare_versions(version, max_version) <= 0
            elif ">=" in version_range:
                parts = version_range.split(">=")
                if len(parts) == 2:
                    min_version = parts[1].strip()
                    return self._compare_versions(version, min_version) >= 0
            elif "<" in version_range:
                parts = version_range.split("<")
                if len(parts) == 2:
                    max_version = parts[1].strip()
                    return self._compare_versions(version, max_version) < 0
            elif ">" in version_range:
                parts = version_range.split(">")
                if len(parts) == 2:
                    min_version = parts[1].strip()
                    return self._compare_versions(version, min_version) > 0
        except Exception:
            pass
        return True  # По умолчанию считаем затронутым если не можем определить

    def _compare_versions(self, v1: str, v2: str) -> int:
        """Сравнивает две версии, возвращает -1, 0, или 1"""
        # Упрощенное сравнение версий
        v1_parts = [int(x) for x in re.findall(r"\d+", v1)]
        v2_parts = [int(x) for x in re.findall(r"\d+", v2)]

        for i in range(max(len(v1_parts), len(v2_parts))):
            v1_part = v1_parts[i] if i < len(v1_parts) else 0
            v2_part = v2_parts[i] if i < len(v2_parts) else 0

            if v1_part < v2_part:
                return -1
            elif v1_part > v2_part:
                return 1
        return 0

    def _extract_severity(self, vuln: dict[str, Any]) -> str:
        """Извлекает severity из уязвимости"""
        database_specific = vuln.get("database_specific", {})
        severity = database_specific.get("severity", "unknown")
        if isinstance(severity, list) and len(severity) > 0:
            severity = severity[0]
        return severity.upper() if isinstance(severity, str) else "UNKNOWN"

    def _extract_cvss_severity(self, cve_data: dict[str, Any]) -> str:
        """Извлекает CVSS severity из CVE"""
        metrics = cve_data.get("metrics", {})
        cvss_v3 = metrics.get("cvssMetricV31", [{}])[0] if metrics.get("cvssMetricV31") else {}
        if not cvss_v3:
            cvss_v3 = metrics.get("cvssMetricV30", [{}])[0] if metrics.get("cvssMetricV30") else {}

        base_score = cvss_v3.get("cvssData", {}).get("baseScore", 0)
        if base_score >= 9.0:
            return "CRITICAL"
        elif base_score >= 7.0:
            return "HIGH"
        elif base_score >= 4.0:
            return "MEDIUM"
        else:
            return "LOW"

    def _parse_package_json(self, content: str) -> list[dict[str, str]]:
        """Парсит package.json и извлекает зависимости"""
        try:
            data = json.loads(content)
            dependencies = []

            # dependencies
            for pkg, version in data.get("dependencies", {}).items():
                clean_version = (
                    version.replace("^", "").replace("~", "").replace(">=", "").replace("<=", "")
                )
                dependencies.append(
                    {"package": pkg, "version": clean_version, "type": "dependency"}
                )

            # devDependencies
            for pkg, version in data.get("devDependencies", {}).items():
                clean_version = (
                    version.replace("^", "").replace("~", "").replace(">=", "").replace("<=", "")
                )
                dependencies.append(
                    {"package": pkg, "version": clean_version, "type": "devDependency"}
                )

            return dependencies
        except Exception:
            return []

    def _parse_requirements_txt(self, content: str) -> list[dict[str, str]]:
        """Парсит requirements.txt и извлекает зависимости"""
        dependencies = []
        for line in content.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            # Формат: package==version или package>=version
            match = re.match(r"^([a-zA-Z0-9_-]+[a-zA-Z0-9._-]*)(?:==|>=|<=|>|<|~=)(.+)$", line)
            if match:
                package, version = match.groups()
                dependencies.append(
                    {"package": package, "version": version.strip(), "type": "dependency"}
                )
            else:
                # Только имя пакета без версии
                package = line.split(" ")[0].split("=")[0]
                dependencies.append({"package": package, "version": "latest", "type": "dependency"})

        return dependencies

    def _parse_pom_xml(self, content: str) -> list[dict[str, str]]:
        """Парсит pom.xml и извлекает зависимости"""
        dependencies = []
        # Упрощенный парсинг XML
        dependency_pattern = r"<dependency>.*?<groupId>([^<]+)</groupId>.*?<artifactId>([^<]+)</artifactId>.*?<version>([^<]+)</version>.*?</dependency>"

        for match in re.finditer(dependency_pattern, content, re.DOTALL):
            group_id, artifact_id, version = match.groups()
            package = f"{group_id}:{artifact_id}"
            dependencies.append(
                {"package": package, "version": version.strip(), "type": "dependency"}
            )

        return dependencies

    def scan_dependencies(
        self,
        file_path: str | None = None,
        file_content: str | None = None,
        file_type: str | None = None,
    ) -> dict[str, Any]:
        """
        Сканирует зависимости из файла манифеста

        Args:
            file_path: Путь к файлу манифеста
            file_content: Содержимое файла (если файл уже прочитан)
            file_type: Тип файла (package.json, requirements.txt, pom.xml)

        Returns:
            Словарь с результатами сканирования
        """
        try:
            # Определяем тип файла
            if file_path:
                path = Path(file_path)
                if path.suffix == ".json" or path.name == "package.json":
                    file_type = "package.json"
                elif path.name == "requirements.txt":
                    file_type = "requirements.txt"
                elif path.name == "pom.xml":
                    file_type = "pom.xml"

                if not file_content:
                    file_content = path.read_text(encoding="utf-8")

            if not file_content or not file_type:
                return {
                    "success": False,
                    "error": "Не указан файл или его содержимое",
                }

            # Парсим зависимости
            dependencies = []
            ecosystem = ""

            if file_type == "package.json":
                dependencies = self._parse_package_json(file_content)
                ecosystem = "npm"
            elif file_type == "requirements.txt":
                dependencies = self._parse_requirements_txt(file_content)
                ecosystem = "PyPI"
            elif file_type == "pom.xml":
                dependencies = self._parse_pom_xml(file_content)
                ecosystem = "Maven"
            else:
                return {
                    "success": False,
                    "error": f"Неподдерживаемый тип файла: {file_type}",
                }

            if not dependencies:
                return {
                    "success": True,
                    "dependencies_scanned": 0,
                    "vulnerabilities_found": 0,
                    "vulnerabilities": [],
                    "message": "Зависимости не найдены",
                }

            # Проверяем уязвимости для каждой зависимости
            all_vulnerabilities = []
            for dep in dependencies:
                package = dep["package"]
                version = dep["version"]

                # Проверяем через разные источники
                vulns = []

                if ecosystem == "npm":
                    vulns = self._check_npm_advisory(package, version)
                elif ecosystem == "PyPI":
                    vulns = self._check_osv("PyPI", package, version)
                elif ecosystem == "Maven":
                    vulns = self._check_osv("Maven", package, version)

                # Также проверяем через NVD для всех
                nvd_vulns = self._check_nvd(package, version)
                vulns.extend(nvd_vulns)

                for vuln in vulns:
                    vuln["ecosystem"] = ecosystem
                    vuln["dependency_type"] = dep.get("type", "dependency")
                    all_vulnerabilities.append(vuln)

            # Подсчитываем статистику
            critical_count = len(
                [v for v in all_vulnerabilities if v.get("severity", "").upper() == "CRITICAL"]
            )
            high_count = len(
                [v for v in all_vulnerabilities if v.get("severity", "").upper() == "HIGH"]
            )
            medium_count = len(
                [v for v in all_vulnerabilities if v.get("severity", "").upper() == "MEDIUM"]
            )
            low_count = len(
                [v for v in all_vulnerabilities if v.get("severity", "").upper() == "LOW"]
            )

            # Рассчитываем security score
            security_score = 100
            security_score -= critical_count * 20
            security_score -= high_count * 10
            security_score -= medium_count * 5
            security_score -= low_count * 2
            security_score = max(0, security_score)

            # Формируем рекомендации
            recommendations = []
            if critical_count > 0:
                recommendations.append(
                    f"Обнаружено {critical_count} критических уязвимостей. Немедленно обновите зависимости."
                )
            if high_count > 0:
                recommendations.append(
                    f"Обнаружено {high_count} уязвимостей высокого уровня. Рекомендуется обновление."
                )
            if all_vulnerabilities:
                recommendations.append(
                    "Регулярно обновляйте зависимости для получения исправлений безопасности."
                )

            return {
                "success": True,
                "scanner": "DependencyScanner",
                "ecosystem": ecosystem,
                "file_type": file_type,
                "dependencies_scanned": len(dependencies),
                "vulnerabilities_found": len(all_vulnerabilities),
                "vulnerabilities": all_vulnerabilities,
                "statistics": {
                    "critical": critical_count,
                    "high": high_count,
                    "medium": medium_count,
                    "low": low_count,
                },
                "security_score": security_score,
                "recommendations": recommendations,
                "timestamp": time.time(),
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Ошибка сканирования зависимостей: {e!s}",
                "scanner": "DependencyScanner",
            }
        finally:
            self.client.close()
