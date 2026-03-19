"""
Routers package — API endpoint modules.
"""

from .audits import router as audits_router
from .config import router as config_router
from .keys import router as keys_router
from .leads import router as leads_router
from .notifications import router as notifications_router
from .referrals import router as referrals_router
from .webhooks import router as webhooks_router

__all__ = [
    "audits_router",
    "keys_router",
    "notifications_router",
    "webhooks_router",
    "referrals_router",
    "leads_router",
    "config_router",
]
