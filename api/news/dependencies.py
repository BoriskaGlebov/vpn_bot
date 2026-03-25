from api.news.services import NewsService


def get_news_service() -> NewsService:
    """Depends для VPNService."""
    return NewsService()
