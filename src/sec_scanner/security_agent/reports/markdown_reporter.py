"""Legacy Markdown reporter (kept for compatibility)."""

from datetime import datetime


class MarkdownReporter:
    """Генератор отчетов в Markdown (упрощенный)."""

    def generate(self, audit_results):
        template = """
# Отчет безопасности: {domain}
**Дата:** {date}
**Общая оценка риска:** {risk_score}/10

## 🔍 Результаты проверок

### SSL/TLS безопасность
{ssl_results}

### Заголовки безопасности
{headers_results}

### Рекомендации
{recommendations}

---
*Сгенерировано sec-scanner*
        """
        data = self.prepare_data(audit_results)
        return template.format(**data)

    def prepare_data(self, audit_results):
        return {
            "domain": audit_results.get("domain", "Неизвестный домен"),
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "risk_score": audit_results.get("risk_score", 5),
            "ssl_results": self.format_ssl_results(
                audit_results.get("results", {}).get("ssl", {})
            ),
            "headers_results": "См. детальный отчет в JSON",
            "recommendations": self.format_recommendations(
                audit_results.get("results", {}).get("ssl", {})
            ),
        }

    def format_ssl_results(self, ssl_data):
        if not ssl_data:
            return "Данные SSL не получены"

        result = f"**Оценка:** {ssl_data.get('grade', 'N/A')}\n\n"
        for check in ssl_data.get("checks", []):
            result += (
                f"- **{check.get('name', 'Проверка')}:** {check.get('status', 'UNKNOWN')}\n"
            )
            if check.get("details"):
                result += f"  *{check.get('details')}*\n"
        return result

    def format_recommendations(self, ssl_data):
        if not ssl_data:
            return "Рекомендации отсутствуют"

        recs = ssl_data.get("recommendations", [])
        if not recs:
            return "Нет рекомендаций"

        return "\n".join([f"{i}. {rec}" for i, rec in enumerate(recs, 1)]) + "\n"

