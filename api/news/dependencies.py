from api.news.services import NewsService


def get_news_service() -> NewsService:
    """Возвращает экземпляр NewsService."""
    return NewsService()
